import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import source_archive as sa


class PythonConformance(unittest.TestCase):
    def run_client(self, *args, success=True):
        result = subprocess.run([str(ROOT / "target/debug/onjeon-collect"), *map(str, args)], capture_output=True)
        self.assertEqual(result.returncode == 0, success, result.stderr.decode())
        return result.stdout

    def test_python_and_rust_observations_are_byte_identical_and_rerunnable(self):
        with tempfile.TemporaryDirectory(prefix="fixture_only-") as tmp:
            root = Path(tmp)
            py = sa.LocalStore(root / "python")
            body = b'{"origin":"fixture"}'
            digest, _ = sa.put_raw(py, body, "application/json")
            extra = {"doc_role": "terms", "format": "json", "origin": "fixture"}
            sa.put_observation(py, "fixture_only", "https://example.org/fixture_only", "2026-10-09T04:43:40Z", digest, len(body), "application/json", extra)
            meta = {"source_id": "fixture_only", "url": "https://example.org/fixture_only", "observed_at": "2026-10-09T04:43:40Z", "doc_role": "terms", "format": "json", "extra": {"origin": "fixture"}}
            (root / "metadata.json").write_text(json.dumps(meta))
            (root / "body.json").write_bytes(body)
            for target in [root / "rust", root / "python"]:
                self.run_client("observe", f"file://{target}", root / "metadata.json", root / "body.json", "application/json")
                listing = self.run_client("listing", f"file://{target}")
                expected = {"listing_rule": "key-sha256-v1", "keys": len(sa.listing_of(py)), "objects": sa.listing_of(py)}
                self.assertEqual(listing, (json.dumps(expected, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode())
                for key in py.list(""):
                    self.assertEqual((target / key).read_bytes(), py.get(key))
            self.run_client("copy", f"file://{root}/rust", f"file://{root}/copied")
            (root / "listing.json").write_bytes(listing)
            report = json.loads(self.run_client("verify-copy", root / "listing.json", f"file://{root}/copied"))
            self.assertEqual(report["summary"], {"byte_identical": 2})

    def test_cli_does_not_offer_delete_or_echo_input(self):
        output = subprocess.run([str(ROOT / "target/debug/onjeon-collect"), "delete", "fixture_only_sensitive_marker"], capture_output=True)
        self.assertNotEqual(output.returncode, 0)
        self.assertNotIn(b"fixture_only_sensitive_marker", output.stdout + output.stderr)


if __name__ == "__main__":
    unittest.main()
