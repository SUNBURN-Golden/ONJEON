"""Source bucket variables must remain data, including in the actual Bash commands.

Like the secret-scope guard, this reads the repository's block-style YAML only.
The Python archive commands are replaced by a local argument recorder; no R2 or
GitHub requests, installers, or credential reads are needed.
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[2] / ".github/workflows/sources.yml"
BUCKETS = ("ONJEON_RAW_BUCKET", "ONJEON_DERIVED_BUCKET")
OCR_EXPRESSION = "${{ inputs.ocr && '--ocr' || '--allow-unverified' }}"


def run_blocks(text):
    return [body for body in re.findall(
        r"(?m)^        run: \|\n((?:          [^\n]*\n|\n)+)", text
    )]


class WorkflowSourceVariables(unittest.TestCase):
    def assert_variables_are_data(self, text):
        job = text.split("  reproduce:\n", 1)[1]
        env = re.search(r"(?m)^    env:\n((?:      [^\n]*\n)+)", job)
        self.assertIsNotNone(env, "reproduce job env required")
        for key in BUCKETS:
            self.assertIn(f"      {key}: ${{{{ vars.{key} }}}}\n", env.group(1))
        scripts = run_blocks(text)
        self.assertGreaterEqual(len(scripts), 6, "source workflow run blocks must be checked")
        for script in scripts:
            self.assertNotRegex(script, r"\bvars\s*[.\[]", "vars must pass through env")

    def test_live_bucket_variables_are_env_bindings(self):
        self.assert_variables_are_data(SOURCE.read_text(encoding="utf-8"))

    def test_live_inline_variable_regressions_are_rejected(self):
        text = SOURCE.read_text(encoding="utf-8")
        self.assert_variables_are_data(text)
        for key in BUCKETS:
            for expression in (f"vars.{key}", f"vars['{key}']"):
                with self.subTest(key=key, expression=expression):
                    mutated = text.replace(f"${key}", "${{ " + expression + " }}")
                    self.assertNotEqual(mutated, text)
                    with self.assertRaisesRegex(AssertionError, "vars must pass through env"):
                        self.assert_variables_are_data(mutated)

    def test_live_consumer_scripts_preserve_bucket_arguments(self):
        text = SOURCE.read_text(encoding="utf-8")
        scripts = [body for body in run_blocks(text)
                   if "tools/source_archive.py" in body or "tools/verify_sources.py --job" in body]
        self.assertEqual(len(scripts), 2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "injected"
            capture = root / "argv.jsonl"
            recorder = root / "python3"
            recorder.write_text(
                f"#!{sys.executable}\n"
                "import json, os, sys\n"
                "with open(os.environ['CAPTURE'], 'a') as out:\n"
                "    out.write(json.dumps(sys.argv[1:]) + '\\n')\n",
                encoding="utf-8",
            )
            recorder.chmod(0o755)
            hostile = f'bucket\"; touch {marker}; # $(touch {marker}) `touch {marker}`\n* space'
            for raw, derived in (("raw-bucket", "derived-bucket"), (hostile, hostile + "-derived")):
                for ocr in ("--ocr", "--allow-unverified"):
                    with self.subTest(raw=raw, ocr=ocr):
                        capture.unlink(missing_ok=True)
                        env = {
                            "PATH": str(root), "RUNNER_TEMP": str(root), "CAPTURE": str(capture),
                            "JOB": "infra/r2/jobs/initial-119.json",
                            "ONJEON_RAW_BUCKET": raw, "ONJEON_DERIVED_BUCKET": derived,
                        }
                        for body in scripts:
                            script = "\n".join(line[10:] for line in body.splitlines())
                            # Simulate GitHub's fixed boolean-to-flag expression, in both modes.
                            script = script.replace(OCR_EXPRESSION, ocr)
                            result = subprocess.run(
                                ["/bin/bash", "-e", "-u", "-o", "pipefail", "-c", script],
                                cwd=root, env=env, text=True, capture_output=True, timeout=10,
                            )
                            self.assertEqual(result.returncode, 0, result.stderr)
                        calls = [json.loads(line) for line in capture.read_text().splitlines()]
                        self.assertEqual(len(calls), 3)
                        for args, bucket in zip(calls[:2], (raw, derived)):
                            self.assertEqual(args[:5], ["-I", "tools/source_archive.py", "--job",
                                                      env["JOB"], "verify-copy"])
                            self.assertEqual(args[args.index("--dst") + 1], f"s3://{bucket}")
                            self.assertIn("--expected", args)
                            self.assertIn("--report", args)
                        args = calls[2]
                        self.assertEqual(args[:5], ["-I", "tools/verify_sources.py", "--job",
                                                  env["JOB"], "reproduce"])
                        self.assertEqual(args[args.index("--raw") + 1], f"s3://{raw}")
                        self.assertEqual(args[args.index("--derived") + 1], f"s3://{derived}")
                        self.assertIn(ocr, args)
                        self.assertEqual(args[-2:], ["--report", str(root / "reproduce.json")])
                        self.assertFalse(marker.exists(), "bucket data executed as shell code")


if __name__ == "__main__":
    unittest.main()
