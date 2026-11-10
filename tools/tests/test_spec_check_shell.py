"""audit5-tasks-json-shell-invalid-tests: spec_check G48 rejects test commands the shell cannot run.

The design bundle's `tasks.json` is also the daemon's task source. Test entries there are read as
shell commands. Audit 5 found `<시험용 원격>`/`<날짜>`/`<prev_tag>` (the shell reads them as
redirections), prose appended to a command, and `cargo test` commands with two positional filters
(cargo accepts one TESTNAME). The descriptive `시험 …` lines are not commands and stay skipped.

Every mutation works on an in-memory copy; the design bundle is not written.
"""
import copy
import importlib.util
import json
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
_spec = importlib.util.spec_from_file_location("spec_check", BUNDLE / "검증/spec_check.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

RULES = json.loads((BUNDLE / "daemon_rules.json").read_text(encoding="utf-8"))
TASKS = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))


def results(T=None, D=None):
    sc.RESULTS.clear()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)  # spec_check's other checks read files without closing them
        sc.run(str(ROOT), copy.deepcopy(TASKS if T is None else T),
               D if D is not None else copy.deepcopy(RULES))
    out = {r["check"].split(" ", 1)[0]: r for r in sc.RESULTS}
    sc.RESULTS.clear()
    return out


def task(T, tid):
    return next(t for t in T["tasks"] if t["id"] == tid)


def feature(T, fid):
    return next(f for f in T["feature_registry"] if f["id"] == fid)


class CommandShape(unittest.TestCase):
    def test_unquoted_angle_placeholders_are_rejected(self):
        for command in (
            "bash tools/daemon/runner_verify/run.sh --remote <시험용 원격> --report docs/vm_check/<날짜>/runner_verify.json",
            "bash packages/schemas/codegen/check_compat.sh <prev_tag>",
        ):
            with self.subTest(command=command):
                self.assertIn("자리표시자", " ".join(sc.shell_command_problems(command)))

    def test_quoted_placeholders_and_real_redirection_are_allowed(self):
        for command in (
            "bash run.sh --remote '<시험용 원격>'",
            "bash run.sh --report docs/vm_check/2026-11-10/runner_verify.json",
            "cargo run -p onjeon-twin-runtime --bin case-runner < packages/ontology/tests/golden/jobs.json",
        ):
            with self.subTest(command=command):
                self.assertEqual([], sc.shell_command_problems(command))

    def test_trailing_prose_and_parenthesized_descriptions_are_rejected(self):
        for command in (
            "bash infra/db/public/test.sh (Compose Postgres에서 제약 시험)",
            "cargo test -p onjeon-ai-review review (모의 제공자 2계열)",
            "(점검 작업)",
            "실제 제공자 2계열 실행 기록(D-02 후)",
        ):
            with self.subTest(command=command):
                self.assertTrue(sc.shell_command_problems(command))

    def test_normal_commands_pass(self):
        for command in (
            "cargo test -p onjeon-api coverage",
            "python3 -I tools/ci/check_leak.py --selftest",
            "cd apps/mobile && flutter test",
            'python3 -I tools/release_readiness/check.py --purpose docs/blueprint/proposals/설계검토_결과/09_제품목적_대응표.md',
        ):
            with self.subTest(command=command):
                self.assertEqual([], sc.shell_command_problems(command))


class CargoFilters(unittest.TestCase):
    def test_one_positional_filter_is_allowed(self):
        self.assertEqual(["coverage"], sc.cargo_test_filters("cargo test -p onjeon-api coverage"))

    def test_two_positional_filters_are_counted(self):
        self.assertEqual(["coverage", "evidence"],
                         sc.cargo_test_filters("cargo test -p onjeon-api coverage evidence"))

    def test_flags_and_values_are_not_filters(self):
        self.assertEqual(["coverage"], sc.cargo_test_filters(
            "cargo test -p onjeon-api --features a,b --all --locked coverage"))
        self.assertEqual([], sc.cargo_test_filters("cargo test -p onjeon-api -- --exact name"))
        self.assertEqual(["eval"], sc.cargo_test_filters("cargo test -p onjeon-criteria --test eval eval"))

    def test_non_cargo_test_is_ignored(self):
        self.assertIsNone(sc.cargo_test_filters("cargo build -p onjeon-api"))
        self.assertIsNone(sc.cargo_test_filters("python3 -m unittest discover"))


class CheckG48(unittest.TestCase):
    def test_baseline_passes(self):
        res = results()
        self.assertTrue(res["G48"]["ok"], res["G48"]["detail"])
        self.assertEqual([r for r in res.values() if not r["ok"]], [])

    def test_placeholder_in_a_task_fails(self):
        T = copy.deepcopy(TASKS)
        task(T, "T-OP-09")["tests"].append("bash run.sh --remote <시험용 원격>")
        res = results(T)
        self.assertFalse(res["G48"]["ok"])
        self.assertTrue(any("T-OP-09" in x for x in res["G48"]["detail"]["셸 구문 문제"]))

    def test_trailing_prose_in_a_task_fails(self):
        T = copy.deepcopy(TASKS)
        task(T, "T-CT-05")["tests"].append("bash infra/db/public/test.sh (설명)")
        res = results(T)
        self.assertFalse(res["G48"]["ok"])

    def test_two_filters_in_a_task_fails(self):
        T = copy.deepcopy(TASKS)
        task(T, "T-TW-05")["tests"].append("cargo test -p onjeon-twin-runtime multi plan_diff")
        res = results(T)
        self.assertFalse(res["G48"]["ok"])
        self.assertTrue(any("T-TW-05" in x for x in res["G48"]["detail"]["cargo test 필터 2개 이상"]))

    def test_two_filters_in_the_feature_registry_fails(self):
        T = copy.deepcopy(TASKS)
        feature(T, "multi-contract")["acceptance_tests"].append(
            "cargo test -p onjeon-twin-runtime multi dependency")
        res = results(T)
        self.assertFalse(res["G48"]["ok"])
        self.assertTrue(any("multi-contract" in x for x in res["G48"]["detail"]["cargo test 필터 2개 이상"]))

    def test_descriptive_sihm_lines_are_skipped(self):
        """A '시험 …' line is a description (required test IDs, manual evidence), not a command."""
        T = copy.deepcopy(TASKS)
        task(T, "T-OP-03")["tests"].append("시험 측정: <날짜> (자동 시험 없음)")
        before = results()["G48"]["detail"]
        after = results(T)["G48"]["detail"]
        self.assertTrue(results(T)["G48"]["ok"])
        self.assertEqual(before["검사한 과제 시험 명령"], after["검사한 과제 시험 명령"])
        self.assertEqual(before["건너뛴 '시험 …' 설명"] + 1, after["건너뛴 '시험 …' 설명"])

    def test_empty_inputs_fail_instead_of_passing_vacuously(self):
        T = copy.deepcopy(TASKS)
        for t in T["tasks"]:
            t["tests"] = []
        for f in T["feature_registry"]:
            f["acceptance_tests"] = []
        res = results(T)
        self.assertFalse(res["G48"]["ok"])
        self.assertEqual(0, res["G48"]["detail"]["검사한 과제 시험 명령"])


if __name__ == "__main__":
    unittest.main()
