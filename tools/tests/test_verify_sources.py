"""Regression tests for the reproduce decision in tools/verify_sources.py.

839ecdb review: a differing derived output was recorded but the sample stayed `reproduced` (exit 0).
Follow-up review: outputs were enumerated from the store, so a file listed in the manifest but
deleted from the store vanished from the comparison and the sample passed. Now the manifest to
verify is pinned by SHA-256 in samples.csv; its hash, raw link, every listed output's presence and
hash, and the absence of unlisted outputs are checked before any regeneration is compared.

The unit tests need no originals or extractors. The archive tests run only when
ONJEON_ARCHIVE_RAW and ONJEON_ARCHIVE_DERIVED point at local stores (the originals are not in
the public repository) and pdftotext is installed.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
import source_archive as sa  # noqa: E402
import verify_sources as vs  # noqa: E402


OK = {"state": "byte_identical"}


def rec(outputs, errors=(), manifest="m" * 64):
    return {"manifest": manifest, "record_errors": list(errors), "outputs": outputs}


class Decide(unittest.TestCase):
    def test_matrix(self):
        cases = [
            ((False, rec([OK, OK])), "reproduced"),
            ((False, rec([OK, {"state": "differs"}])), "derived_mismatch"),
            ((False, rec([OK, {"state": "tool_version_differs"}])), "derived_unverified"),
            ((False, rec([OK, {"state": "no_regenerator"}])), "derived_unverified"),
            ((False, rec([OK, {"state": "not_rerun"}])), "derived_unverified"),
            ((False, rec([])), "derived_unverified"),
            ((False, rec([OK], errors=["listed output missing"])), "derived_record_invalid"),
            ((False, rec([], manifest=None)), "derived_unverified"),
            ((False, None), "derived_unverified"),
            ((True, rec([OK])), "quote_mismatch"),
        ]
        for (missing, derived), want in cases:
            with self.subTest(derived=derived, missing=missing):
                self.assertEqual(vs.decide(missing, derived), want)


class VerifyDerived(unittest.TestCase):
    """839ecdb follow-up: outputs were enumerated from the store, so a file listed in the manifest
    but deleted from the store simply disappeared from the comparison and the sample passed."""

    RAW = "d" * 64
    LAYOUT = f"derived/{'d' * 64}/text/poppler-pdftotext-layout@24.02.0/x.layout.txt"
    READING = f"derived/{'d' * 64}/text/poppler-pdftotext-reading-order@24.02.0/x.raw.txt"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = sa.LocalStore(self.root)
        sa.put_once(self.store, self.LAYOUT, b"layout", "text/plain")
        sa.put_once(self.store, self.READING, b"reading", "text/plain")
        self.pin = self.write_manifest({"raw_sha256": self.RAW, "sample_id": "s", "outputs": [
            {"key": self.LAYOUT, "sha256": sa.sha256_bytes(b"layout")},
            {"key": self.READING, "sha256": sa.sha256_bytes(b"reading")}]})

    def tearDown(self):
        self.tmp.cleanup()

    def write_manifest(self, m, raw=None):
        body = (json.dumps(m, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
        pin = sa.sha256_bytes(body)
        sa.put_once(self.store, vs.manifest_key(raw or self.RAW, pin), body, "application/json")
        return pin

    @staticmethod
    def regen(layout=b"layout", reading=b"reading"):
        def f(kind, tool, name):
            return layout if "layout" in tool else reading
        return f

    def status(self, pin, regen=None):
        d = vs.verify_derived(self.store, self.RAW, pin, "s", regen or self.regen())
        return vs.decide(False, d), d

    def path(self, key):
        return self.root / key

    def test_intact_record_and_identical_regeneration_is_reproduced(self):
        self.assertEqual(self.status(self.pin)[0], "reproduced")

    def test_listed_output_deleted_is_invalid(self):
        self.path(self.READING).unlink()  # the reviewer's reproduction: 2 listed, 1 deleted
        st, d = self.status(self.pin)
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("listed output missing" in e for e in d["record_errors"]))

    def test_listed_output_bytes_changed_is_invalid(self):
        self.path(self.LAYOUT).write_bytes(b"other")
        st, d = self.status(self.pin, self.regen(layout=b"other"))  # even if regeneration agrees
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("hash differs from manifest" in e for e in d["record_errors"]))

    def test_manifest_tampered_is_invalid(self):
        mk = self.path(vs.manifest_key(self.RAW, self.pin))
        m = json.loads(mk.read_bytes())
        m["outputs"] = m["outputs"][:1]  # drop an entry to hide a deleted file
        mk.write_bytes((json.dumps(m) + "\n").encode())
        self.path(self.READING).unlink()
        st, d = self.status(self.pin)
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("do not hash to the pin" in e for e in d["record_errors"]))

    def test_pinned_manifest_missing_is_invalid(self):
        self.path(vs.manifest_key(self.RAW, self.pin)).unlink()
        st, d = self.status(self.pin)
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("pinned manifest missing" in e for e in d["record_errors"]))

    def test_no_pinned_manifest_is_not_success(self):
        self.assertEqual(self.status(None)[0], "derived_unverified")

    def test_manifest_for_another_raw_is_invalid(self):
        pin = self.write_manifest({"raw_sha256": "e" * 64, "sample_id": "s", "outputs": [
            {"key": self.LAYOUT, "sha256": sa.sha256_bytes(b"layout")}]})
        st, d = self.status(pin)
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("manifest links raw" in e for e in d["record_errors"]))

    def test_unlisted_output_in_store_is_invalid(self):
        extra = f"derived/{self.RAW}/text/poppler-pdftotext-layout@24.02.0/extra.layout.txt"
        sa.put_once(self.store, extra, b"x", "text/plain")
        st, d = self.status(self.pin)
        self.assertEqual(st, "derived_record_invalid")
        self.assertTrue(any("not in the pinned manifest" in e for e in d["record_errors"]))

    def test_regeneration_differs_is_mismatch(self):
        self.assertEqual(self.status(self.pin, self.regen(layout=b"changed"))[0], "derived_mismatch")

    def test_unregenerable_output_is_unverified(self):
        def f(kind, tool, name):
            return b"layout" if "layout" in tool else "no_regenerator"
        self.assertEqual(self.status(self.pin, f)[0], "derived_unverified")


@unittest.skipUnless(os.environ.get("ONJEON_ARCHIVE_RAW") and os.environ.get("ONJEON_ARCHIVE_DERIVED")
                     and shutil.which("pdftotext"), "local archive and pdftotext required")
class ArchiveReproduce(unittest.TestCase):
    SAMPLE = "kyobo_cancer_summary"
    DIGEST = "11b72fb0f018d55f6f1c3c53d28660d5ecf6cecec47331634f4fc4a9e4a9d6f1"

    def run_reproduce(self, derived_root):
        with tempfile.TemporaryDirectory() as t:
            rep = Path(t) / "r.json"
            p = subprocess.run([sys.executable, "-I", str(TOOLS / "verify_sources.py"), "reproduce",
                                "--raw", f"file://{os.environ['ONJEON_ARCHIVE_RAW']}",
                                "--derived", f"file://{derived_root}", "--report", str(rep)],
                               capture_output=True, text=True)
            doc = json.loads(rep.read_text())
        return p.returncode, {x["sample_id"]: x for x in doc["results"]}

    def test_tampered_stored_output_fails_with_exit_1(self):
        with tempfile.TemporaryDirectory() as t:
            copy = Path(t) / "derived"
            shutil.copytree(os.environ["ONJEON_ARCHIVE_DERIVED"], copy)
            target = next((copy / "derived" / self.DIGEST / "text").glob("poppler-pdftotext-layout@*/*.txt"))
            target.write_bytes(target.read_bytes() + b"\ntampered\n")
            code, res = self.run_reproduce(copy)
        # caught by the record check (hash differs from the pinned manifest) before regeneration;
        # the regeneration-differs path (derived_mismatch) is covered by VerifyDerived
        self.assertEqual(res[self.SAMPLE]["status"], "derived_record_invalid")
        self.assertEqual(code, 1)

    def test_deleted_listed_output_fails_with_exit_1(self):
        with tempfile.TemporaryDirectory() as t:
            copy = Path(t) / "derived"
            shutil.copytree(os.environ["ONJEON_ARCHIVE_DERIVED"], copy)
            next((copy / "derived" / self.DIGEST / "text").glob("poppler-pdftotext-layout@*/*.txt")).unlink()
            code, res = self.run_reproduce(copy)
        self.assertEqual(res[self.SAMPLE]["status"], "derived_record_invalid")
        self.assertEqual(code, 1)

    def test_untampered_sample_is_reproduced(self):
        code, res = self.run_reproduce(os.environ["ONJEON_ARCHIVE_DERIVED"])
        self.assertEqual(res[self.SAMPLE]["status"], "reproduced")


if __name__ == "__main__":
    unittest.main()
