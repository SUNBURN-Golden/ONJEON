"""Regression tests for audit-1 I/O and audit-2 I2 fields/batch errors.

`docs/blueprint/proposals/온톨로지/검증/runner/src/main.rs` used to `expect()` on
`rule_path` and on reading the rule file, so one unreadable or malformed
`rule_path` panicked the process and lost the whole batch. The runner must now
emit a per-case `io_error` object and keep evaluating the remaining jobs, exiting
0 so `subprocess.run(..., check=True)` in `ontology_check.run_engine` still works.

Set ONJEON_ONTOLOGY_RUNNER to use an already-built runner (both rules-engine and
design-specs CI jobs build it before discovery). Otherwise build with
`cargo build --offline` and use its reported executable path (including target
directory/target overrides); a failed, timed-out build or missing executable
artifact fails the tests. Only a missing cargo without a prebuilt runner skips
them. The fallback build is bounded so a Cargo lock cannot consume the entire
900-second local verification budget without identifying the blocked setup.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO / "docs/blueprint/proposals/온톨로지/검증/runner"
RULE = REPO / "docs/blueprint/proposals/온톨로지/규칙/hana-2601-3d-cancer-dx.json"
CHECK_DIR = REPO / "docs/blueprint/proposals/온톨로지/검증"
BUILD_TIMEOUT_S = 120

sys.path.insert(0, str(CHECK_DIR))
import ontology_check  # noqa: E402

INPUTS = {
    "contract_date": "2026-08-20",
    "is_initial_contract": True,
    "renewal_date": None,
    "diagnosis_date": "2027-04-20",
    "policy_end_date": "2046-08-20",
    "dx_in_category": True,
    "already_paid": False,
    "insured_amount_krw": 10000000,
}


def jobs():
    return [
        {"case_id": "ok_before", "rule_path": str(RULE), "inputs": INPUTS},
        {"case_id": "missing_path", "inputs": INPUTS},
        {"case_id": "nonstring_path", "rule_path": 42, "inputs": INPUTS},
        {"case_id": "unreadable", "rule_path": str(RUNNER_DIR / "no-such-rule.json"), "inputs": INPUTS},
        {"case_id": "ok_after", "rule_path": str(RULE), "inputs": INPUTS},
    ]


@unittest.skipUnless(os.environ.get("ONJEON_ONTOLOGY_RUNNER") or shutil.which("cargo"), "cargo not installed")
class RunnerIoError(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = os.environ.get("ONJEON_ONTOLOGY_RUNNER")
        if cls.runner:
            return
        try:
            build = subprocess.run(
                ["cargo", "build", "--offline", "--bin", "ontology-case-runner", "--message-format=json"],
                cwd=RUNNER_DIR, capture_output=True, text=True, check=True, timeout=BUILD_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr or b""
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"ontology runner cargo build exceeded {BUILD_TIMEOUT_S}s; "
                "check for a competing Cargo build/target lock, or build the runner "
                "first and set ONJEON_ONTOLOGY_RUNNER.\n" + stderr
            ) from exc
        for line in build.stdout.splitlines():
            artifact = json.loads(line)
            if (artifact.get("reason") == "compiler-artifact"
                    and artifact.get("target", {}).get("name") == "ontology-case-runner"
                    and "bin" in artifact["target"].get("kind", [])
                    and artifact.get("executable")):
                cls.runner = artifact["executable"]
                return
        raise RuntimeError("cargo build did not report an ontology-case-runner executable")

    def run_jobs(self, batch):
        p = subprocess.run([self.runner], input=json.dumps(batch), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stderr, "")
        rows = json.loads(p.stdout)
        self.assertEqual(len(rows), len(batch))
        return rows

    def write_rule(self, directory, **changes):
        """Synthetic rules only; never change the frozen ontology rule files."""
        rule = {
            "rule_id": "runner-test", "rule_version": "v1", "schema_version": "rule-0.1",
            "publication_state": "fixture_only", "evidence_refs": ["clause:runner-test"],
            "unknown_policy": "use_three_valued_logic_never_default_to_zero",
            "inputs": {"gate": "bool"}, "eligibility": "gate", "amount": {"krw": 1234},
        }
        rule.update(changes)
        path = Path(directory) / "rule.json"
        path.write_text(json.dumps(rule), encoding="utf-8")
        return str(path)

    def assert_batch(self, results):
        self.assertEqual(set(results), {"ok_before", "missing_path", "nonstring_path", "unreadable", "ok_after"})
        for cid in ("missing_path", "nonstring_path", "unreadable"):
            self.assertIn("io_error", results[cid], cid)
            self.assertEqual(results[cid]["case_id"], cid)
        for cid in ("ok_before", "ok_after"):
            self.assertNotIn("io_error", results[cid], cid)
            self.assertEqual(results[cid]["payout"]["kind"], "payable")
            self.assertEqual(results[cid]["payout"]["amount"]["krw"], 5000000)
            self.assertIsNone(results[cid]["release_id"])
            self.assertEqual(results[cid]["schema_version"], "rule-0.1")

    def test_per_case_io_error_and_batch_continues(self):
        """Exit 0; bad rule_path cases get io_error; a case after them still evaluates."""
        self.assert_batch({r["case_id"]: r for r in self.run_jobs(jobs())})

    def test_run_engine_treats_io_error_like_load_error(self):
        """run_engine (check=True) stays up on io_error rows and keys them by case_id."""
        evs = ontology_check.run_engine(self.runner, jobs())
        self.assert_batch(evs)

    def test_release_and_schema_fields_for_every_payout_state(self):
        """Both DSLs, omitted/null fixture releases and distinct synthetic releases."""
        with tempfile.TemporaryDirectory() as directory:
            for schema in ("rule-0.1", "rule-0.2"):
                released_hashes = []
                for release in ("omitted", None, "rel:runner-1", "rel:runner-2"):
                    changes = {"schema_version": schema}
                    if release != "omitted":
                        changes["release_id"] = release
                    if release and release != "omitted":
                        changes["publication_state"] = "released"
                    path = self.write_rule(directory, **changes)
                    batch = [
                        {"case_id": "yes", "rule_path": path, "inputs": {"gate": True}},
                        {"case_id": "no", "rule_path": path, "inputs": {"gate": False}},
                        {"case_id": "unknown", "rule_path": path, "inputs": {}},
                    ]
                    with self.subTest(schema=schema, release=release):
                        rows = self.run_jobs(batch)
                        self.assertEqual(rows, self.run_jobs(batch))
                        self.assertEqual([r["case_id"] for r in rows], ["yes", "no", "unknown"])
                        self.assertEqual([r["eligibility"] for r in rows], ["true", "false", "unknown"])
                        self.assertEqual([r["payout"]["kind"] for r in rows], ["payable", "not_payable", "undetermined"])
                        self.assertEqual(rows[0]["payout"]["amount"], {"kind": "exact", "krw": 1234})
                        self.assertEqual(rows[2]["missing_inputs"], ["gate"])
                        for row in rows:
                            self.assertEqual(row["release_id"], None if release == "omitted" else release)
                            self.assertEqual(row["schema_version"], schema)
                            self.assertEqual(row["rule_id"], "runner-test")
                            self.assertEqual(row["rule_version"], "v1")
                            self.assertEqual(row["publication_state"], changes.get("publication_state", "fixture_only"))
                            self.assertEqual(row["evidence_refs"], ["clause:runner-test"])
                            for key in ("rule_content_hash", "input_snapshot_hash"):
                                self.assertRegex(row[key], r"^[0-9a-f]{64}$")
                            self.assertTrue(row["engine_version"])
                            self.assertGreater(row["trace_len"], 0)
                            self.assertTrue(row["trace_head"])
                        if changes.get("publication_state") == "released":
                            released_hashes.append(rows[0]["rule_content_hash"])
                self.assertEqual(released_hashes[0], released_hashes[1])

    def test_load_and_eval_errors_preserve_order_and_later_success(self):
        with tempfile.TemporaryDirectory() as directory:
            good = {"case_id": "before", "rule_path": str(RULE), "inputs": INPUTS}
            bad_json = Path(directory) / "broken.json"
            bad_json.write_text("{", encoding="utf-8")
            bad_utf8 = Path(directory) / "bad-utf8.json"
            bad_utf8.write_bytes(b"\xff")
            bad_rule = self.write_rule(directory, schema_version="unsupported")
            overflow_dir = Path(directory) / "overflow"
            overflow_dir.mkdir()
            overflow = self.write_rule(overflow_dir, amount={"add": [{"krw": 9223372036854775807}, {"krw": 1}]})
            errors = [
                ("json", str(bad_json), {}, "load_error", "invalid JSON:"),
                ("schema", bad_rule, {}, "load_error", "schema_version"),
                ("utf8", str(bad_utf8), {}, "io_error", str(bad_utf8)),
                ("missing_inputs", str(RULE), None, "eval_error", "InputsNotObject"),
                ("array_inputs", str(RULE), [], "eval_error", "InputsNotObject"),
                ("bad_type", str(RULE), {**INPUTS, "dx_in_category": "yes"}, "eval_error", "BadInput"),
                ("unknown_input", str(RULE), {"typo": True}, "eval_error", "UnknownInput"),
                ("overflow", overflow, {"gate": True}, "eval_error", "Overflow"),
            ]
            batch = [good]
            for cid, path, inputs, _, _ in errors:
                job = {"case_id": cid, "rule_path": path, "inputs": inputs}
                if cid == "missing_inputs":
                    del job["inputs"]
                batch.append(job)
            batch.append({**good, "case_id": "after"})
            rows = self.run_jobs(batch)
            self.assertEqual([r["case_id"] for r in rows], [j["case_id"] for j in batch])
            for row, (cid, _, _, key, detail) in zip(rows[1:-1], errors):
                with self.subTest(case=cid):
                    self.assertEqual(set(row), {"case_id", key})
                    self.assertIn(detail, row[key])
            self.assertEqual(rows[0]["payout"], rows[-1]["payout"])
            self.assertEqual(rows[-1]["payout"]["kind"], "payable")
            self.assertEqual(ontology_check.run_engine(self.runner, batch), {r["case_id"]: r for r in rows})

    def test_nonobject_jobs_are_per_job_errors(self):
        batch = [None, 42, "bad job", [], {"case_id": "after", "rule_path": str(RULE), "inputs": INPUTS}]
        rows = self.run_jobs(batch)
        for row in rows[:-1]:
            self.assertEqual(row, {"case_id": None, "io_error": "rule_path missing or not a string"})
        self.assertEqual(rows[-1]["case_id"], "after")
        self.assertEqual(rows[-1]["payout"]["kind"], "payable")

    def test_invalid_batch_is_reported_without_panic(self):
        for raw in ("", "[", '[{"case_id":"incomplete"}', '{}', 'null', '"string"', '1', '[] trailing'):
            with self.subTest(raw=raw):
                p = subprocess.run([self.runner], input=raw, capture_output=True, text=True)
                self.assertEqual(p.returncode, 1)
                self.assertEqual(p.stdout, "")
                self.assertIn("ontology-case-runner: jobs json:", p.stderr)
                self.assertNotIn("panicked", p.stderr)

    def test_empty_batch_is_valid(self):
        self.assertEqual(self.run_jobs([]), [])


class RunnerSetup(unittest.TestCase):
    def test_uses_cargo_executable_with_default_or_redirected_target(self):
        for override in (None, ""):
            for target_dir, executable in (
                ("", str(RUNNER_DIR / "target/debug/ontology-case-runner")),
                (str(REPO / "target/shared"), str(REPO / "target/shared/debug/ontology-case-runner")),
                ("", str(REPO / "target/configured/x86_64-unknown-linux-gnu/debug/ontology-case-runner")),
            ):
                with self.subTest(prebuilt=override, executable=executable), \
                        mock.patch.dict(os.environ, {"ONJEON_ONTOLOGY_RUNNER": "", "CARGO_TARGET_DIR": target_dir}), \
                        mock.patch.object(RunnerIoError, "runner", create=True):
                    if override is None:
                        os.environ.pop("ONJEON_ONTOLOGY_RUNNER", None)
                    messages = [
                        {"reason": "compiler-artifact", "target": {"name": "dependency", "kind": ["lib"]},
                         "executable": None},
                        {"reason": "compiler-artifact", "target": {"name": "other-bin", "kind": ["bin"]},
                         "executable": "/wrong/binary"},
                        {"reason": "compiler-artifact", "target": {"name": "ontology-case-runner", "kind": ["bin"]},
                         "executable": executable, "fresh": True},
                        {"reason": "build-finished", "success": True},
                    ]
                    with mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
                            [], 0, stdout="\n".join(map(json.dumps, messages)))) as build:
                        RunnerIoError.setUpClass()
                    self.assertEqual(RunnerIoError.runner, executable)
                    self.assertIn("--message-format=json", build.call_args.args[0])
                    self.assertEqual(build.call_args.kwargs["cwd"], RUNNER_DIR)
                    self.assertTrue(build.call_args.kwargs["check"])

    def test_successful_build_without_executable_fails_at_setup(self):
        for messages in ([], [{"reason": "compiler-artifact", "target": {
                "name": "ontology-case-runner", "kind": ["bin"]}, "executable": None}]):
            with self.subTest(messages=messages), \
                    mock.patch.dict(os.environ, {"ONJEON_ONTOLOGY_RUNNER": ""}), \
                    mock.patch.object(RunnerIoError, "runner", create=True), \
                    mock.patch.object(subprocess, "run", return_value=subprocess.CompletedProcess(
                        [], 0, stdout="\n".join(map(json.dumps, messages)))):
                with self.assertRaisesRegex(RuntimeError, "did not report.*executable"):
                    RunnerIoError.setUpClass()

    def test_prebuilt_runner_does_not_require_cargo_or_cached_dependencies(self):
        with mock.patch.dict(os.environ, {"ONJEON_ONTOLOGY_RUNNER": "/prebuilt/runner"}), \
                mock.patch.object(RunnerIoError, "runner", create=True), \
                mock.patch.object(subprocess, "run", side_effect=FileNotFoundError("cargo unavailable")) as build:
            RunnerIoError.setUpClass()
            self.assertEqual(RunnerIoError.runner, "/prebuilt/runner")
            build.assert_not_called()

    def test_failed_fallback_build_is_not_silently_skipped(self):
        with mock.patch.dict(os.environ, {"ONJEON_ONTOLOGY_RUNNER": ""}), \
                mock.patch.object(RunnerIoError, "runner", create=True), \
                mock.patch.object(subprocess, "run", side_effect=subprocess.CalledProcessError(101, ["cargo", "build"])):
            with self.assertRaises(subprocess.CalledProcessError):
                RunnerIoError.setUpClass()

    def test_stalled_fallback_build_fails_with_cargo_diagnostic(self):
        for stderr in (b"Blocking waiting for file lock on build directory", "cargo stalled", None):
            with self.subTest(stderr=stderr), \
                    mock.patch.dict(os.environ, {"ONJEON_ONTOLOGY_RUNNER": ""}), \
                    mock.patch.object(RunnerIoError, "runner", create=True), \
                    mock.patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired(
                        ["cargo", "build"], BUILD_TIMEOUT_S, stderr=stderr)) as build:
                with self.assertRaisesRegex(RuntimeError, "ontology runner cargo build exceeded") as caught:
                    RunnerIoError.setUpClass()
                self.assertFalse(RunnerIoError.runner)
                self.assertIsInstance(caught.exception.__cause__, subprocess.TimeoutExpired)
                self.assertIn("ONJEON_ONTOLOGY_RUNNER", str(caught.exception))
                if stderr:
                    self.assertIn(stderr.decode() if isinstance(stderr, bytes) else stderr, str(caught.exception))
                self.assertGreater(build.call_args.kwargs["timeout"], 0)
                self.assertLess(build.call_args.kwargs["timeout"], 900)

    @unittest.skipUnless(os.name == "posix" and shutil.which("cargo"), "POSIX Cargo lock test")
    def test_real_cargo_lock_cannot_hang_setup(self):
        import fcntl

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "debug").mkdir()
            with (target / "debug/.cargo-lock").open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                with mock.patch.dict(os.environ, {
                    "ONJEON_ONTOLOGY_RUNNER": "", "CARGO_TARGET_DIR": str(target),
                }), mock.patch.object(sys.modules[__name__], "BUILD_TIMEOUT_S", 5), \
                        mock.patch.object(RunnerIoError, "runner", create=True):
                    os.environ.pop("CARGO_BUILD_TARGET", None)  # lock the native debug directory
                    with self.assertRaisesRegex(RuntimeError, "Blocking waiting for file lock"):
                        RunnerIoError.setUpClass()
                    self.assertFalse(RunnerIoError.runner)


if __name__ == "__main__":
    unittest.main()
