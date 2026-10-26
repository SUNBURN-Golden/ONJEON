"""Archive command contracts using temporary samples and real LocalStore I/O."""
import argparse
import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import source_archive as sa


class ArchiveCommands(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.raw = sa.LocalStore(self.root / "raw")
        self.derived = sa.LocalStore(self.root / "derived")
        self.cache = self.root / "cache"
        self.cache.mkdir()
        self.body = b"<html>public filing</html>"
        self.row = dict(sample_id="sample", cache_path="nested/page.html", format="html",
                        sha256=sa.sha256_bytes(self.body), url="https://example.invalid/disclosure",
                        retrieved_at="2026-10-22T01:02:03Z", doc_role="terms")
        self.samples = self.root / "samples.csv"
        patcher = mock.patch.object(sa, "SAMPLES", self.samples)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.args = argparse.Namespace(raw=self.raw.root.as_uri(), derived=None, derived_src=None,
                                       cache=str(self.cache), endpoint_url=None,
                                       out=str(self.root / "restored"))
        self.write_samples(self.row)

    def write_samples(self, *rows):
        with self.samples.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.row))
            writer.writeheader()
            writer.writerows(rows)

    def cache_original(self):
        p = self.cache / self.row["cache_path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(self.body)
        return p

    def archive(self):
        with redirect_stdout(io.StringIO()) as out:
            code = sa.cmd_archive_samples(self.args)
        return code, json.loads(out.getvalue())

    def test_archive_records_bytes_provenance_and_idempotent_rerun(self):
        self.cache_original()
        code, result = self.archive()
        self.assertEqual(code, 0)
        self.assertEqual(result, [dict(sample_id="sample", sha256=self.row["sha256"],
                                       object="stored", observation="stored")])
        self.assertEqual(self.raw.get(sa.object_key(self.row["sha256"])), self.body)
        observation = json.loads(self.raw.get(self.raw.list("observations/")[0]))
        for field in ("sample_id", "url", "sha256", "doc_role", "format"):
            self.assertEqual(observation[field], self.row[field])
        self.assertEqual(observation["observed_at"], self.row["retrieved_at"])
        self.assertEqual(observation["bytes"], len(self.body))
        self.assertEqual(observation["content_type"], "text/html")
        before = sa.listing_of(self.raw)
        code, rerun = self.archive()
        self.assertEqual(code, 0)
        self.assertEqual((rerun[0]["object"], rerun[0]["observation"]),
                         ("already_present", "already_present"))
        self.assertEqual(sa.listing_of(self.raw), before)

    def test_archive_preserves_derived_manifest_and_raw_link(self):
        self.cache_original()
        src = self.root / "extracted" / "nested"
        src.mkdir(parents=True)
        (src / "page.tables.txt").write_bytes(b"table cells")
        self.args.derived = self.derived.root.as_uri()
        self.args.derived_src = str(src.parent)
        code, result = self.archive()
        self.assertEqual(code, 0)
        record = result[0]["derived"]
        self.assertEqual(record["outputs"], 1)
        key = f"derived/{self.row['sha256']}/manifests/{record['manifest_sha256']}.json"
        manifest_bytes = self.derived.get(key)
        self.assertEqual(sa.sha256_bytes(manifest_bytes), record["manifest_sha256"])
        manifest = json.loads(manifest_bytes)
        self.assertEqual(manifest["raw_sha256"], self.row["sha256"])
        self.assertEqual(manifest["sample_id"], "sample")
        self.assertEqual(self.derived.get(manifest["outputs"][0]["key"]), b"table cells")
        before = sa.listing_of(self.derived)
        self.assertEqual(self.archive()[0], 0)
        self.assertEqual(sa.listing_of(self.derived), before)

    def test_derived_store_without_source_does_not_create_outputs(self):
        self.cache_original()
        self.args.derived = self.derived.root.as_uri()
        code, result = self.archive()
        self.assertEqual(code, 0)
        self.assertNotIn("derived", result[0])
        self.assertEqual(self.derived.list(""), [])

    def test_missing_cache_is_failure_without_storage_writes(self):
        code, result = self.archive()
        self.assertEqual((code, result), (1, [dict(sample_id="sample", status="missing_in_cache")]))
        self.assertEqual(self.raw.list(""), [])

    def test_hash_mismatch_preserves_actual_bytes_but_creates_no_observation(self):
        p = self.cache_original()
        p.write_bytes(b"changed original")
        code, result = self.archive()
        digest = sa.sha256_bytes(b"changed original")
        self.assertEqual((code, result), (1, [dict(sample_id="sample",
                         status="hash_differs_from_samples_csv", sha256=digest)]))
        self.assertEqual(self.raw.list(""), [sa.object_key(digest)])
        self.assertEqual(self.raw.get(sa.object_key(digest)), b"changed original")

    def test_archive_conflicting_stored_object_aborts_without_observation(self):
        self.cache_original()
        key = sa.object_key(self.row["sha256"])
        self.raw.put_new(key, b"corrupted stored bytes", "text/html")
        with self.assertRaises(sa.Conflict):
            self.archive()
        self.assertEqual(self.raw.get(key), b"corrupted stored bytes")
        self.assertEqual(self.raw.list("observations/"), [])

    def test_archive_reports_bad_rows_and_continues_with_valid_rows(self):
        self.cache_original()
        self.write_samples(dict(self.row, sample_id="unsafe", cache_path="../outside"),
                           dict(self.row, sample_id="missing", cache_path="missing.pdf"), self.row)
        code, result = self.archive()
        self.assertEqual(code, 1)
        self.assertEqual([r.get("status", r.get("object")) for r in result],
                         ["unsafe_cache_path", "missing_in_cache", "stored"])
        self.assertEqual(len(self.raw.list("observations/")), 1)

    def test_fetch_restores_multiple_nested_originals_by_hash(self):
        digest, _ = sa.put_raw(self.raw, self.body, "text/html")
        other, _ = sa.put_raw(self.raw, b"PDF bytes", "application/pdf")
        self.write_samples(self.row, dict(self.row, sample_id="pdf", sha256=other,
                                         cache_path="pdf/terms.pdf"))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(sa.cmd_fetch(self.args), 0)
        out = Path(self.args.out)
        self.assertEqual((out / self.row["cache_path"]).read_bytes(), self.raw.get(sa.object_key(digest)))
        self.assertEqual((out / "pdf/terms.pdf").read_bytes(), b"PDF bytes")

    def test_fetch_missing_object_fails_without_writing_destination(self):
        with self.assertRaises(FileNotFoundError):
            sa.cmd_fetch(self.args)
        self.assertFalse((Path(self.args.out) / self.row["cache_path"]).exists())

    def observation_args(self, **overrides):
        args = dict(raw=self.args.raw, endpoint_url=None, file=str(self.cache_original()),
                    source_id="sample", url=self.row["url"], observed_at=self.row["retrieved_at"],
                    content_type=None, extra=None)
        args.update(overrides)
        return argparse.Namespace(**args)

    def add_observation(self, args):
        with redirect_stdout(io.StringIO()) as out:
            code = sa.cmd_add_observation(args)
        self.assertEqual(code, 0)
        return json.loads(out.getvalue())

    def test_add_observation_infers_type_and_rerun_does_not_overwrite(self):
        args = self.observation_args()
        first = self.add_observation(args)
        second = self.add_observation(args)
        self.assertEqual(first["sha256"], self.row["sha256"])
        self.assertEqual((first["object"], first["observation_state"]), ("stored", "stored"))
        self.assertEqual((second["object"], second["observation_state"]),
                         ("already_present", "already_present"))
        observation = json.loads(self.raw.get(first["observation"]))
        self.assertEqual(observation["content_type"], "text/html")
        self.assertEqual(observation["object_key"], sa.object_key(first["sha256"]))
        self.assertEqual(observation["source_id"], "sample")

    def test_add_observation_explicit_type_and_extra_metadata(self):
        args = self.observation_args(content_type="application/custom", extra='{"doc_role":"약관"}')
        result = self.add_observation(args)
        observation = json.loads(self.raw.get(result["observation"]))
        self.assertEqual(observation["doc_role"], "약관")
        self.assertEqual(observation["content_type"], "application/custom")

    def test_invalid_extra_is_rejected_before_opening_store_or_reading_input(self):
        for extra in ('{"sha256":"forged"}', '{"object_key":"forged"}',
                      '[]', '[["sha256","forged"]]', 'null', 'false', '0', '""'):
            args = self.observation_args(extra=extra, file=str(self.cache / "missing.pdf"))
            with self.subTest(extra=extra), mock.patch.object(sa, "store") as store:
                with self.assertRaises(ValueError):
                    sa.cmd_add_observation(args)
                store.assert_not_called()
                self.assertEqual(self.raw.list(""), [])

    def observation_cli(self, extra, args=None):
        args = args or self.observation_args(extra=extra)
        return subprocess.run([
            sys.executable, "-I", str(Path(sa.__file__)), "add-observation",
            "--file", args.file, "--source-id", args.source_id, "--url", args.url,
            "--observed-at", args.observed_at, "--raw", args.raw, "--extra", extra,
        ], capture_output=True, text=True, check=False)

    def test_cli_reserved_keys_fail_without_writing_archive(self):
        for field in ("source_id", "url", "observed_at", "sha256", "bytes", "content_type", "object_key"):
            with self.subTest(field=field):
                result = self.observation_cli(json.dumps({field: "forged"}))
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn("reserved", result.stderr)
                self.assertIn(field, result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.raw.list(""), [])

    def test_cli_non_object_extra_fails_without_writing_archive(self):
        for extra in ('[]', '[["sha256","forged"]]', 'null', 'false', '0', '""'):
            with self.subTest(extra=extra):
                result = self.observation_cli(extra)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("JSON object", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertEqual(self.raw.list(""), [])

    def test_cli_rejection_preserves_existing_archive(self):
        args = self.observation_args(extra='{"doc_role":"약관"}')
        self.add_observation(args)
        before = {key: self.raw.get(key) for key in self.raw.list("")}
        Path(args.file).write_bytes(b"different public filing")
        result = self.observation_cli('{"sha256":"forged","object_key":"forged"}', args)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("reserved", result.stderr)
        self.assertEqual({key: self.raw.get(key) for key in self.raw.list("")}, before)

    def test_add_observation_guesses_pdf_and_falls_back_for_unknown_extension(self):
        for extension, expected in (("pdf", "application/pdf"), ("unknown_extension", "application/octet-stream")):
            with self.subTest(extension=extension):
                path = self.cache / f"public.{extension}"
                path.write_bytes(f"public {extension} bytes".encode())
                args = self.observation_args(file=str(path))
                result = self.add_observation(args)
                self.assertEqual(json.loads(self.raw.get(result["observation"]))["content_type"], expected)

    def test_add_observation_missing_file_does_not_write_store(self):
        args = self.observation_args(file=str(self.cache / "missing.pdf"))
        with self.assertRaises(FileNotFoundError):
            sa.cmd_add_observation(args)
        self.assertEqual(self.raw.list(""), [])

    def test_changed_document_keeps_previous_object_and_observation(self):
        args = self.observation_args()
        old = self.add_observation(args)
        Path(args.file).write_bytes(b"new public filing")
        args.observed_at = "2026-10-23T01:02:03Z"
        new = self.add_observation(args)
        self.assertNotEqual(new["sha256"], old["sha256"])
        self.assertEqual(self.raw.get(sa.object_key(old["sha256"])), self.body)
        self.assertEqual(self.raw.get(sa.object_key(new["sha256"])), b"new public filing")
        self.assertEqual(len(self.raw.list("observations/")), 2)

    def test_conflicting_observation_does_not_replace_original_record(self):
        args = self.observation_args()
        result = self.add_observation(args)
        before = self.raw.get(result["observation"])
        args.url = "https://example.invalid/other"
        with self.assertRaises(sa.Conflict):
            sa.cmd_add_observation(args)
        self.assertEqual(self.raw.get(result["observation"]), before)

    def test_invalid_metadata_and_source_id_do_not_create_observations(self):
        for overrides, exception in ((dict(extra="invalid json"), json.JSONDecodeError),
                                     (dict(source_id="../unsafe"), SystemExit)):
            with self.subTest(overrides=overrides), self.assertRaises(exception):
                sa.cmd_add_observation(self.observation_args(**overrides))
        self.assertEqual(self.raw.list("observations/"), [])


if __name__ == "__main__":
    unittest.main()
