"""Exercise HTML baseline migration with a local synthetic archive."""

import csv
import hashlib
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rebaseline_html_samples as migration


def digest(body):
    return hashlib.sha256(body).hexdigest()


class RebaselineHtmlSamples(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.samples = self.root / "samples.csv"
        self.raw_dir = self.root / "raw"
        self.raw = migration.sa.LocalStore(self.raw_dir)
        self.enterContext(mock.patch.object(migration.sa, "SAMPLES", self.samples))
        self.body = b'<title>Disclosure</title><a href="/terms.pdf?_t=1">Terms</a>'
        self.baseline = digest(self.body)
        self.rows = [
            dict(sample_id="pdf", format="text_pdf", url="https://example.org/terms.pdf",
                 sha256="1" * 64, content_sha256="", content_hash_rule="", notes="keep, 그대로"),
            dict(sample_id="kb", format="html", url="https://www.kbinsure.co.kr/page",
                 sha256=self.baseline, content_sha256="a" * 64, content_hash_rule="html-visible-text-v1",
                 notes="keep KB"),
            dict(sample_id="other", format="html", url="https://example.org/page",
                 sha256=self.baseline, content_sha256="b" * 64, content_hash_rule="html-visible-text-v2",
                 notes="keep other"),
            dict(sample_id="last", format="html", url="https://example.org/last",
                 sha256=digest(b"<p>last</p>"), content_sha256="", content_hash_rule="", notes="keep last"),
        ]
        with self.samples.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.rows[0]))
            writer.writeheader()
            writer.writerows(self.rows)
        self.raw.put_new(migration.sa.object_key(self.baseline), self.body, "text/html")

    def run_cli(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = migration.main(["--raw-dir", str(self.raw_dir)])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_verified_html_rows_use_the_source_host_and_preserve_other_fields(self):
        last_key = migration.sa.object_key(self.rows[-1]["sha256"])
        self.raw.put_new(last_key, b"<p>last</p>", "text/html")
        self.samples.chmod(0o640)
        result, stdout, stderr = self.run_cli()
        self.assertEqual((result, stderr), (0, ""))
        with self.samples.open(encoding="utf-8", newline="") as f:
            prepared = list(csv.DictReader(f))
        expected = [self.rows[0]]
        for row, normalized in zip(self.rows[1:], (
            b"Disclosure [link:/terms.pdf] Terms",
            b"Disclosure [link:/terms.pdf?_t=1] Terms",
            b"last",
        ), strict=True):
            expected.append(dict(row, content_sha256=digest(normalized), content_hash_rule=migration.hch.RULE))
        self.assertEqual(prepared, expected)
        self.assertEqual(stdout.splitlines(), [
            f"{r['sample_id']} {r['content_hash_rule']} {r['content_sha256']}" for r in expected[1:]])
        self.assertEqual(self.samples.stat().st_mode & 0o777, 0o640)
        original_inode = self.samples.stat().st_ino
        self.assertEqual(self.run_cli(), (0, stdout, ""))
        self.assertEqual(self.samples.stat().st_ino, original_inode)

    def test_missing_and_corrupt_final_original_leave_entire_csv_untouched(self):
        original = self.samples.read_bytes()
        code, stdout, stderr = self.run_cli()
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("last:", stderr)
        self.assertEqual(self.samples.read_bytes(), original)

        # Same length, wrong bytes, under the expected content-addressed key.
        self.raw.put_new(migration.sa.object_key(self.rows[-1]["sha256"]), b"<p>fake</p>", "text/html")
        code, stdout, stderr = self.run_cli()
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("last: archived bytes do not match the recorded SHA-256", stderr)
        self.assertEqual(self.samples.read_bytes(), original)
        self.assertEqual(set(self.root.iterdir()), {self.samples, self.raw_dir})

    def test_publish_failure_leaves_original_and_removes_staging_file(self):
        self.raw.put_new(migration.sa.object_key(self.rows[-1]["sha256"]), b"<p>last</p>", "text/html")
        original = self.samples.read_bytes()
        with mock.patch.object(Path, "replace", side_effect=OSError("replace failed")):
            self.assertEqual(self.run_cli(), (1, "", "replace failed\n"))
        self.assertEqual(self.samples.read_bytes(), original)
        self.assertEqual(set(self.root.iterdir()), {self.samples, self.raw_dir})

    def test_rejects_missing_columns_or_no_html_rows(self):
        for data, error in (
            (b"sample_id,format\r\n", "samples.csv is missing required columns"),
            (",".join(self.rows[0]).encode() + b"\r\n", "samples.csv has no HTML samples"),
        ):
            with self.subTest(error=error):
                self.samples.write_bytes(data)
                self.assertEqual(self.run_cli(), (1, "", error + "\n"))
                self.assertEqual(self.samples.read_bytes(), data)

    def test_blueprint_applies_current_rule_to_both_pipeline_sections(self):
        blueprint = Path(__file__).resolve().parents[2] / "docs" / "BLUEPRINT.md"
        paragraph = next(line for line in blueprint.read_text(encoding="utf-8").splitlines()
                         if line.startswith("동적 HTML의 현재 본문 해시 규칙"))
        self.assertIn(f"`{migration.hch.RULE}`", paragraph)
        self.assertIn("`DATA_PIPELINE_CONTRACT` §3·§3.1", paragraph)
        self.assertIn("`bytes_changed_content_same`", paragraph)
