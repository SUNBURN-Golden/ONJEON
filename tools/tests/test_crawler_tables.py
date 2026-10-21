"""crawler core 10: provisional table extractor skeleton (tables/{schema,extractor,writer}).

No network, no R2, no secrets; the only fixture is in-process text marked origin=fixture.
Deterministic: the observation timestamp is injected via source_meta, never read from a clock.
"""
import ast
import csv
import hashlib
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from crawler.tables import extractor as ex  # noqa: E402
from crawler.tables import schema as s  # noqa: E402
from crawler.tables import writer as w  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "crawler" / "sample_table.txt"
RAW = FIXTURE.read_bytes()
SHA = hashlib.sha256(RAW).hexdigest()
META = {
    "insurer_id": "ins-a", "product_id": "prod-1", "coverage_id": "cov-x",
    "source_url": "https://disclosure.example/doc1", "observed_at": "2026-10-21T00:00:00Z",
    "effective_reason": "sample text carries no effective dates",
}


def valid_row(**over):
    row = {c: "" for c in s.COLUMNS}
    row.update({
        "insurer_id": "ins-a", "product_id": "prod-1", "coverage_id": "cov-x",
        "coverage_name": "암진단비", "conditions": "최초 1회", "amount": "5,000만원",
        "period": "보험기간 중", "effective_from": "2026-01-01", "effective_to": "2026-12-31",
        "source_raw_sha256": SHA, "source_page": 3,
        "source_url": "https://disclosure.example/doc1", "observed_at": "2026-10-21T00:00:00Z",
        "extractor_version": "sample-text@1", "status": "verified",
    })
    row.update(over)
    return row


# ---- schema ----

class SchemaDocTest(unittest.TestCase):
    def test_docstring_marks_provisional_and_not_the_contract(self):
        doc = s.__doc__
        self.assertIn("PROVISIONAL", doc)
        self.assertRegex(doc.lower(), r"not the data contract")

    def test_column_order_and_statuses(self):
        self.assertEqual(s.COLUMNS[:4], ("insurer_id", "product_id", "coverage_id", "coverage_name"))
        self.assertIn("source_raw_sha256", s.COLUMN_SET)
        self.assertIn("source_page", s.COLUMN_SET)
        self.assertEqual(len(s.COLUMNS), len(s.COLUMN_SET))  # no duplicates
        self.assertEqual(s.STATUSES, {"verified", "needs_review"})


class ValidateRowTest(unittest.TestCase):
    def test_accepts_valid_rows(self):
        for row in (
            valid_row(),
            valid_row(status="needs_review"),
            valid_row(source_page="table 2 row 4 of serialized text"),
            valid_row(source_page="7"),
            valid_row(effective_from="", effective_to="", effective_reason="not dated in source"),
            valid_row(insurer_id="", product_id="", coverage_id="", source_url="", observed_at=""),
        ):
            with self.subTest(row=row):
                self.assertIsNone(s.validate_row(row))

    def test_rejects_bad_sha256(self):
        for sha in (None, "", SHA[:63], SHA.upper(), "g" * 64, SHA + "0", 123, b"x" * 64):
            row = valid_row(source_raw_sha256=sha)
            with self.subTest(sha=repr(sha)[:30]), self.assertRaises(s.RowError):
                s.validate_row(row)

    def test_rejects_bad_page(self):
        for page in (None, "", " ", 0, -1, "0", "-3", 1.5, True, b"3", []):
            row = valid_row(source_page=page)
            with self.subTest(page=repr(page)), self.assertRaises(s.RowError):
                s.validate_row(row)

    def test_rejects_unknown_columns(self):
        for extra in ({"note": "x"}, {"sha256": SHA}, {"page": 3}):
            row = valid_row()
            row.update(extra)
            with self.subTest(extra=extra), self.assertRaisesRegex(s.RowError, "unknown columns"):
                s.validate_row(row)

    def test_empty_effective_needs_reason(self):
        for over in ({"effective_from": ""}, {"effective_to": ""}, {"effective_from": "", "effective_to": ""},
                     {"effective_from": None}, {"effective_to": "  "}):
            row = valid_row(**over)
            row["effective_reason"] = ""
            with self.subTest(over=over), self.assertRaisesRegex(s.RowError, "effective_reason"):
                s.validate_row(row)

    def test_bad_status_and_version(self):
        for status in ("", None, "final", "VERIFIED", 1):
            with self.subTest(status=status), self.assertRaises(s.RowError):
                s.validate_row(valid_row(status=status))
        for ver in ("", None, "a/b", "a b", "a" * 64):
            with self.subTest(ver=repr(ver)[:20]), self.assertRaises(s.RowError):
                s.validate_row(valid_row(extractor_version=ver))

    def test_non_mapping_and_bad_types(self):
        for bad in (None, "row", 3, [("a", "b")]):
            with self.subTest(bad=repr(bad)[:20]), self.assertRaises(s.RowError):
                s.validate_row(bad)
        for key, value in (("amount", ["x"]), ("period", {"a": 1}), ("coverage_name", True),
                           ("conditions", "a\x00b")):
            with self.subTest(key=key), self.assertRaises(s.RowError):
                s.validate_row(valid_row(**{key: value}))


# ---- extractor ----

class ExtractorTest(unittest.TestCase):
    def test_bad_version_rejected(self):
        for v in ("", "x/y", "x y", "x" * 64, None, 5):
            with self.subTest(v=repr(v)[:20]), self.assertRaises(ValueError):
                ex.SampleTextExtractor(v)
        class Good(ex.Extractor):
            def extract(self, raw_bytes, raw_sha256, source_meta):
                return []
        self.assertEqual(Good("v1").version, "v1")  # abstract base is subclassable

    def test_sample_parses_fixture_into_valid_rows(self):
        rows = ex.SampleTextExtractor().extract(RAW, SHA, META)
        self.assertEqual(len(rows), 3)
        for row, page, name in zip(rows, (3, 4, 5), ("암진단비", "수술비", "입원일당")):
            self.assertIsNone(s.validate_row(row))  # every row is storable/servable
            self.assertEqual(row["source_page"], page)
            self.assertIsInstance(row["source_page"], int)
            self.assertEqual(row["coverage_name"], name)
            self.assertEqual(row["source_raw_sha256"], SHA)
            self.assertEqual(row["extractor_version"], "sample-text@1")
            self.assertEqual(row["status"], "needs_review")
            self.assertEqual(row["observed_at"], META["observed_at"])
        self.assertEqual(rows[0]["amount"], "5,000만원")

    def test_extract_is_deterministic(self):
        e = ex.SampleTextExtractor()
        self.assertEqual(e.extract(RAW, SHA, META), e.extract(RAW, SHA, META))

    def test_text_locator_page_allowed(self):
        raw = "담보|조건|금액|기간|list.tables.txt row 7".encode("utf-8")
        rows = ex.SampleTextExtractor().extract(raw, hashlib.sha256(raw).hexdigest(), META)
        self.assertEqual(rows[0]["source_page"], "list.tables.txt row 7")

    def test_malformed_input_rejected(self):
        sha = "a" * 64
        for raw, meta in (
            (b"only|three|fields", META),
            (b"|conditions|amount|period|3", META),      # empty coverage
            (b"cov|cond|amt|per|", META),               # empty page: no evidence
            (b"\xff\xfe not utf-8", META),
            (RAW, "not-a-mapping"),
            ("not-bytes", META),
            (RAW, "G" * 64),                             # wrong evidence hash shape
        ):
            with self.subTest(raw=repr(raw)[:30]), self.assertRaises(ex.ExtractError):
                ex.SampleTextExtractor().extract(raw, sha if meta is META else sha, meta)

    def test_source_meta_cannot_inject_owned_columns(self):
        for key in ("source_page", "source_raw_sha256", "status", "extractor_version",
                    "coverage_name", "note"):
            meta = dict(META, **{key: "injected"})
            with self.subTest(key=key), self.assertRaisesRegex(ex.ExtractError, "not allowed"):
                ex.SampleTextExtractor().extract(RAW, SHA, meta)


# ---- writer ----

class WriterTest(unittest.TestCase):
    def setUp(self):
        self.rows = ex.SampleTextExtractor().extract(RAW, SHA, META)
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)

    def test_header_matches_schema_and_roundtrip(self):
        path = w.write_table(self.rows, self.td.name, "sample-text@1")
        with path.open("r", encoding="utf-8", newline="") as f:
            header = f.readline().rstrip("\n")
        self.assertEqual(header, ",".join(s.COLUMNS))
        back = w.read_table(path)
        self.assertEqual(len(back), len(self.rows))
        for got, want in zip(back, self.rows):
            self.assertEqual(got, {c: ("" if want[c] is None else str(want[c])) for c in s.COLUMNS})
            self.assertIsNone(s.validate_row(got))  # CSV-read pages like "3" stay valid

    def test_filename_has_version_and_content_hash(self):
        path = w.write_table(self.rows, self.td.name, "sample-text@1")
        self.assertRegex(path.name, r"^table-sample-text@1-[0-9a-f]{64}\.csv$")
        self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), path.name)

    def test_same_content_is_same_file_noop(self):
        p1 = w.write_table(self.rows, self.td.name, "sample-text@1")
        p2 = w.write_table(list(self.rows), self.td.name, "sample-text@1")
        self.assertEqual(p1, p2)
        self.assertEqual(len(list(Path(self.td.name).iterdir())), 1)

    def test_existing_file_with_different_content_is_never_overwritten(self):
        p = w.write_table(self.rows, self.td.name, "sample-text@1")
        original = p.read_bytes()
        p.write_bytes(b"tampered")
        with self.assertRaises(w.TableWriteError):
            w.write_table(self.rows, self.td.name, "sample-text@1")
        self.assertEqual(p.read_bytes(), b"tampered")  # left untouched

    def test_new_version_or_content_writes_new_file(self):
        p1 = w.write_table(self.rows, self.td.name, "sample-text@1")
        p2 = w.write_table(self.rows, self.td.name, "sample-text@2")
        changed = [dict(r) for r in self.rows]
        changed[0]["amount"] = "6,000만원"
        p3 = w.write_table(changed, self.td.name, "sample-text@1")
        self.assertEqual(len({p1, p2, p3}), 3)
        self.assertEqual(len(list(Path(self.td.name).iterdir())), 3)
        self.assertIn("sample-text@2", p2.name)

    def test_invalid_row_rejected_and_nothing_written(self):
        bad = [valid_row(), valid_row(source_raw_sha256="")]
        with self.assertRaises(s.RowError):
            w.write_table(bad, self.td.name, "sample-text@1")
        self.assertEqual(list(Path(self.td.name).iterdir()), [])

    def test_read_table_rejects_wrong_header(self):
        p = Path(self.td.name) / "x.csv"
        p.write_text("a,b\n1,2\n", encoding="utf-8")
        with self.assertRaises(w.TableWriteError):
            w.read_table(p)


class ServiceViewTest(unittest.TestCase):
    def test_only_valid_rows_pass(self):
        good = ex.SampleTextExtractor().extract(RAW, SHA, META)
        mixed = good + [valid_row(source_page=0), {"not": "a row"}, "garbage", valid_row(source_raw_sha256="no")]
        out = w.service_view(iter(mixed))
        self.assertEqual(len(out), len(good))
        self.assertEqual(out, good)


# ---- static guard for the new modules (no fetch code added, but the rules still apply) ----

TABLES = Path(s.__file__).resolve().parent
FORBIDDEN = re.compile(
    r"rotat|spoof|bypass|circumvent|captcha|stealth|impersonat|socks|\btor\b|vpn|set_proxy|"
    r"proxy_(url|list|pool)|fake_?(ua|agent)|ignore_robots|skip_robots", re.IGNORECASE)


class StaticTest(unittest.TestCase):
    def test_files_present_and_stdlib_only(self):
        files = sorted(TABLES.glob("*.py"))
        self.assertEqual({p.name for p in files},
                         {"__init__.py", "schema.py", "extractor.py", "writer.py"})
        std = set(sys.stdlib_module_names)
        banned = {"socket", "urllib.request", "http.client", "ssl", "requests", "httpx", "aiohttp",
                  "subprocess", "selenium", "playwright", "boto3", "botocore", "random", "secrets", "os"}
        for p in files:
            tree = ast.parse(p.read_text())
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    mods = [(node.module or "")]
                for m in mods:
                    top = m.split(".")[0]
                    self.assertNotIn(top, banned, f"{p.name}: imports {m}")
                    self.assertIn(top, std, f"{p.name}: {m}")

    def test_no_circumvention_identifiers(self):
        for p in TABLES.glob("*.py"):
            for node in ast.walk(ast.parse(p.read_text())):
                name = getattr(node, "id", None) or getattr(node, "attr", None) or getattr(node, "name", None)
                if name:
                    self.assertIsNone(FORBIDDEN.search(name), f"{p.name}:{node.lineno} {name}")

    def test_no_env_or_secret_reads(self):
        for p in TABLES.glob("*.py"):
            self.assertNotIn("environ", p.read_text(), p.name)


if __name__ == "__main__":
    unittest.main()
