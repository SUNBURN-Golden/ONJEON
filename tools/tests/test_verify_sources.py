"""Regression tests for the reproduce decision in tools/verify_sources.py.

Found in the 839ecdb review: a derived output that differed from its regeneration was recorded
(derived_layout: differs) but the sample was still `reproduced` and the exit code was 0.
Now: any differing output -> derived_mismatch (failure); anything not comparable -> derived_unverified;
only all outputs byte-identical -> reproduced.

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


class Decide(unittest.TestCase):
    def test_matrix(self):
        ok = {"state": "byte_identical"}
        cases = [
            ((False, [ok, ok]), "reproduced"),
            ((False, [ok, {"state": "differs"}]), "derived_mismatch"),
            ((False, [{"state": "differs"}, {"state": "no_regenerator"}]), "derived_mismatch"),
            ((False, [ok, {"state": "tool_version_differs"}]), "derived_unverified"),
            ((False, [ok, {"state": "no_regenerator"}]), "derived_unverified"),
            ((False, [ok, {"state": "not_rerun"}]), "derived_unverified"),
            ((False, []), "derived_unverified"),
            ((False, None), "derived_unverified"),
            ((True, [ok]), "quote_mismatch"),
        ]
        for (missing, derived), want in cases:
            with self.subTest(derived=derived, missing=missing):
                self.assertEqual(vs.decide(missing, derived), want)


class CompareDerived(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = sa.LocalStore(self.tmp.name)
        d = "d" * 64
        self.digest = d
        sa.put_once(self.store, f"derived/{d}/text/poppler-pdftotext-layout@24.02.0/x.layout.txt", b"layout", "text/plain")
        sa.put_once(self.store, f"derived/{d}/text/html-table-serializer@v1-session/x.tables.txt", b"tables", "text/plain")
        sa.put_once(self.store, f"derived/{d}/manifests/{'e' * 64}.json", b"{}", "application/json")

    def tearDown(self):
        self.tmp.cleanup()

    def regen(self, layout_bytes):
        def f(kind, tool, name):
            if tool.startswith("poppler-pdftotext-layout@"):
                return layout_bytes
            return "no_regenerator"
        return f

    def test_differing_output_is_mismatch(self):
        out = vs.compare_derived(self.store, self.digest, self.regen(b"changed"))
        self.assertEqual(sorted(o["state"] for o in out), ["differs", "no_regenerator"])
        self.assertEqual(vs.decide(False, out), "derived_mismatch")

    def test_identical_but_unregenerable_is_unverified(self):
        out = vs.compare_derived(self.store, self.digest, self.regen(b"layout"))
        self.assertEqual(vs.decide(False, out), "derived_unverified")

    def test_manifests_are_not_outputs(self):
        out = vs.compare_derived(self.store, self.digest, self.regen(b"layout"))
        self.assertFalse(any("manifests" in o["key"] for o in out))


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

    def test_tampered_layout_fails_with_exit_1(self):
        with tempfile.TemporaryDirectory() as t:
            copy = Path(t) / "derived"
            shutil.copytree(os.environ["ONJEON_ARCHIVE_DERIVED"], copy)
            target = next((copy / "derived" / self.DIGEST / "text").glob("poppler-pdftotext-layout@*/*.txt"))
            target.write_bytes(target.read_bytes() + b"\ntampered\n")
            code, res = self.run_reproduce(copy)
        self.assertEqual(res[self.SAMPLE]["status"], "derived_mismatch")
        self.assertEqual(code, 1)

    def test_untampered_sample_is_reproduced(self):
        code, res = self.run_reproduce(os.environ["ONJEON_ARCHIVE_DERIVED"])
        self.assertEqual(res[self.SAMPLE]["status"], "reproduced")


if __name__ == "__main__":
    unittest.main()
