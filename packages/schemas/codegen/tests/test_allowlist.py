"""check_allowlist.py is the Python twin of src/allowlist.rs (02_구현계약 §3.2, C-17).

The committed analytics-events.json must be consistent, its examples must pass and fail as declared,
an event with a field outside the allow list must fail and name the field, and planted defects
(a listed coverage-name field, a promoted rejected example, version drift) must be caught. The value
matrix below is the one the Rust tests use, so the two implementations are held to the same answers.
"""
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import check_allowlist as ca  # noqa: E402

# 02 §3.2 이벤트 목록(초안); import_started/finished are two events
EVENTS_02 = {
    "screen_view", "state_shown", "evidence_opened", "scenario_requested", "scenario_result_state",
    "compare_opened", "plan_diff_opened", "import_started", "import_finished", "consent_changed",
    "error_shown", "api_latency",
}
FIELDS_02 = {"screen_id", "state_code", "latency_ms", "error_class", "release_id", "app_version"}


def mutated(base: ca.AllowList, edit) -> ca.AllowList:
    data = copy.deepcopy(base.data)
    edit(data)
    return ca.AllowList(data, base.vocabulary, base.package_version)


def run_main(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        rc = ca.main(list(argv))
    return rc, out.getvalue()


class CommittedFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allow = ca.AllowList.load()

    def test_file_is_consistent(self):
        self.assertEqual(self.allow.problems(), [])

    def test_contracts_version_is_the_crate_version(self):
        self.assertEqual(self.allow.data["contracts_version"], ca.crate_version())

    def test_examples_pass_and_fail_as_declared(self):
        self.assertEqual(self.allow.check_examples(), [])
        self.assertTrue(self.allow.examples["valid"] and self.allow.examples["rejected"])
        for ok in self.allow.examples["valid"]:
            self.assertEqual(self.allow.check_event(ok), [], ok)
        for bad in self.allow.examples["rejected"]:
            self.assertTrue(self.allow.check_event(bad["example"]), bad["reason_ko"])

    def test_every_02_event_and_field_is_listed(self):
        self.assertEqual(set(self.allow.events), EVENTS_02)
        self.assertTrue(FIELDS_02 <= set(self.allow.allowed_fields))

    def test_error_class_is_the_vocabulary_axis(self):
        # The same value the wire ErrorResponse.error_class carries (vocabulary 1.6.0), not the code letter.
        rule = self.allow.allowed_fields["error_class"]
        self.assertEqual((rule["kind"], rule["axes"]), ("vocabulary", ["error_class"]))
        self.assertEqual(
            set(ca.axis_codes("error_class", self.allow.vocabulary)),
            {"validation", "auth", "not_found", "state_conflict", "limit", "unsupported", "internal", "timeout"},
        )

    def test_forbidden_categories_cover_the_02_list(self):
        wanted = {"계약 금액", "담보 명", "상품 명(개인 화면)", "건강·가족력·DNA", "자유 입력", "문서 내용"}
        listed = {c["category_ko"] for c in self.allow.forbidden_categories}
        self.assertTrue(wanted <= listed, listed)
        self.assertTrue(any("사용자 식별자" in c for c in listed))


class CheckEvent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allow = ca.AllowList.load()

    def test_a_field_outside_the_list_fails_and_is_named(self):
        for field, value in [
            ("contract_amount", 53000),
            ("coverage_name", "암진단"),
            ("family_history", True),
            ("dna_marker", "x"),
            ("free_text", "hello"),
            ("document_excerpt", "..."),
            ("user_id", "u-1"),
            ("session_id", "s-1"),
            ("something_new", 1),
        ]:
            problems = self.allow.check_event({"event": "screen_view", "screen_id": "home", field: value})
            self.assertEqual(len(problems), 1, (field, problems))
            self.assertIn(f"`{field}`", problems[0])
        problems = self.allow.check_event({"event": "screen_view", "screen_id": "home", "coverage_name": "x"})
        self.assertIn("forbidden category: 담보 명", problems[0])
        problems = self.allow.check_event({"event": "screen_view", "screen_id": "home", "something_new": 1})
        self.assertIn("not on the allow list", problems[0])

    def test_required_fields_event_names_and_shape(self):
        self.assertTrue(self.allow.check_event({"event": "state_shown", "screen_id": "home"}))
        self.assertIn("required field `state_code` is missing",
                      self.allow.check_event({"event": "state_shown", "screen_id": "home"})[0])
        self.assertEqual(self.allow.check_event({"screen_id": "home"}), ["missing event name `event`"])
        self.assertEqual(self.allow.check_event({"event": 7, "screen_id": "home"}), ["missing event name `event`"])
        self.assertEqual(self.allow.check_event({"event": "page_hit"}), ["event `page_hit` is not on the allow list"])
        self.assertEqual(self.allow.check_event("screen_view"), ["an event must be a JSON object"])
        self.assertEqual(self.allow.check_event(["screen_view"]), ["an event must be a JSON object"])

    def test_purpose_only_on_consent_changed(self):
        problems = self.allow.check_event({"event": "screen_view", "screen_id": "home", "purpose": "p"})
        self.assertIn("allowed only on other events", problems[0])
        ok = {"event": "consent_changed", "screen_id": "s", "purpose": "health_analysis"}
        self.assertEqual(self.allow.check_event(ok), [])

    def test_value_shapes(self):
        def with_(k, v):
            e = {"event": "api_latency", "latency_ms": 5, k: v}
            return self.allow.check_event(e)

        self.assertEqual(with_("latency_ms", 0), [])
        self.assertTrue(with_("latency_ms", -1))
        self.assertTrue(with_("latency_ms", 1.5))
        self.assertTrue(with_("latency_ms", 5.0))
        self.assertTrue(with_("latency_ms", True))
        self.assertTrue(with_("latency_ms", "5"))
        self.assertTrue(with_("latency_ms", 2**63))
        self.assertTrue(with_("screen_id", "내 설계"))
        self.assertTrue(with_("screen_id", "Home"))
        self.assertTrue(with_("screen_id", "home\n"))
        self.assertTrue(with_("screen_id", "a" * 65))
        self.assertEqual(with_("screen_id", "a" * 64), [])
        self.assertTrue(with_("screen_id", {"a": 1}))
        self.assertTrue(with_("screen_id", None))
        self.assertEqual(with_("release_id", "rel:20261017-1"), [])
        self.assertTrue(with_("release_id", "rel:2026-1"))
        self.assertTrue(with_("release_id", "rel:20261017-1-2"))
        self.assertEqual(with_("app_version", "1.12.0"), [])
        self.assertTrue(with_("app_version", "1.0"))
        self.assertTrue(with_("app_version", "1.0.0\n"))

        def state(s):
            return self.allow.check_event({"event": "state_shown", "screen_id": "h", "state_code": s})

        self.assertEqual(state("hold"), [])
        self.assertEqual(state("blocked"), [])
        self.assertTrue(state("persona_x"))
        self.assertTrue(state(""))
        self.assertIn("vocabulary value of display_status", state("x")[0])

        def klass(s):
            return self.allow.check_event({"event": "error_shown", "screen_id": "h", "error_class": s})

        self.assertEqual(klass("timeout"), [])
        self.assertEqual(klass("internal"), [])
        self.assertTrue(klass("T"))
        self.assertTrue(klass("Z"))
        self.assertTrue(klass("VA"))
        self.assertTrue(klass("Timeout"))
        self.assertIn("vocabulary value of error_class", klass("T")[0])

    def test_field_names_for_the_leak_scanner(self):
        for f in FIELDS_02:
            self.assertTrue(self.allow.is_allowed_field(f), f)
        for f in ("user_id", "coverage_name", "monthly_premium_krw", "free_text"):
            self.assertFalse(self.allow.is_allowed_field(f), f)
        self.assertEqual(self.allow.forbidden_category("monthlyPremiumKrw"), "계약 금액")
        self.assertIsNone(self.allow.forbidden_category("screen_id"))


class PlantedDefects(unittest.TestCase):
    """넣으면 실패: each defect is caught by the check that owns it."""

    @classmethod
    def setUpClass(cls):
        cls.base = ca.AllowList.load()

    def test_listing_a_forbidden_looking_field_is_a_problem(self):
        def edit(d):
            d["allowed_fields"]["coverage_name"] = dict(d["allowed_fields"]["screen_id"])

        problems = mutated(self.base, edit).problems()
        self.assertTrue(any("coverage_name" in p and "forbidden category" in p for p in problems), problems)

    def test_an_event_rule_naming_an_unlisted_field_is_a_problem(self):
        def edit(d):
            d["events"]["screen_view"]["optional"].append("ghost")

        self.assertTrue(any("ghost" in p for p in mutated(self.base, edit).problems()))

    def test_only_events_is_enforced_both_ways(self):
        def edit(d):
            d["events"]["screen_view"]["optional"].append("purpose")

        self.assertTrue(any("restricted to" in p for p in mutated(self.base, edit).problems()))

        def edit2(d):
            d["allowed_fields"]["purpose"]["only_events"] = ["no_such_event"]

        self.assertTrue(any("unknown event" in p for p in mutated(self.base, edit2).problems()))

    def test_unknown_axis_and_kind_are_problems(self):
        def edit(d):
            d["allowed_fields"]["state_code"]["axes"].append("no_such_axis")
            d["allowed_fields"]["latency_ms"]["kind"] = "float"

        problems = mutated(self.base, edit).problems()
        self.assertTrue(any("no_such_axis" in p for p in problems), problems)
        self.assertTrue(any("unknown kind" in p for p in problems), problems)

    def test_moving_a_rejected_example_to_valid_fails(self):
        def edit(d):
            d["examples"]["valid"].append(d["examples"]["rejected"][0]["example"])

        self.assertTrue(any("was rejected" in p for p in mutated(self.base, edit).check_examples()))

    def test_listing_a_passing_example_as_rejected_fails(self):
        def edit(d):
            d["examples"]["rejected"].append({"example": d["examples"]["valid"][0], "reason_ko": "x"})

        self.assertTrue(any("was accepted" in p for p in mutated(self.base, edit).check_examples()))

    def test_version_drift_is_a_problem(self):
        def edit(d):
            d["contracts_version"] = "99.0.0"

        self.assertTrue(any("contracts_version" in p for p in mutated(self.base, edit).problems()))

    def test_selftest_passes_on_the_committed_file(self):
        self.assertEqual(ca.selftest(), [])


class CommandLine(unittest.TestCase):
    def test_passes_on_the_committed_file(self):
        rc, out = run_main()
        self.assertEqual(rc, 0, out)
        self.assertIn("PASSED", out)
        self.assertIn("12 events", out)

    def test_selftest_option(self):
        rc, out = run_main("--selftest")
        self.assertEqual(rc, 0, out)
        self.assertIn("self-test ok", out)

    def test_fails_on_a_leaking_copy(self):
        data = json.loads(ca.ALLOWLIST_PATH.read_text(encoding="utf-8"))
        data["examples"]["valid"].append({"event": "screen_view", "screen_id": "home", "user_id": "u-1"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "analytics-events.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            rc, out = run_main("--allowlist", str(path))
        self.assertEqual(rc, 1, out)
        self.assertIn("user_id", out)
        self.assertIn("RESULT: FAILED", out)

    def test_checks_event_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps([{"event": "api_latency", "latency_ms": 3},
                                        {"event": "screen_view", "screen_id": "home"}]), encoding="utf-8")
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"event": "screen_view", "screen_id": "home", "coverage_name": "x"}),
                           encoding="utf-8")
            rc, out = run_main(str(good))
            self.assertEqual(rc, 0, out)
            self.assertIn("1 event file(s)", out)
            rc, out = run_main(str(good), str(bad))
            self.assertEqual(rc, 1, out)
            self.assertIn("bad.json[0]", out)
            self.assertIn("담보 명", out)

    def test_setup_errors_exit_2(self):
        rc, out = run_main("/nonexistent/events.json")
        self.assertEqual(rc, 2, out)
        self.assertIn("Error", out)
        rc, out = run_main("--unknown-flag")
        self.assertEqual(rc, 2, out)
        rc, out = run_main("--allowlist")
        self.assertEqual(rc, 2, out)


class Ct04Evidence(unittest.TestCase):
    """The committed evidence of this task (codegen/evidence/ct04/) is complete and indexed.

    The rules test_evidence.py applies to ct03/ hold here: every log starts with its command, records only
    exit code 0, and is named in ct04/EVIDENCE.md, which pins the packages/schemas tree hash. The two
    commands of the task's own test list must be among the logged commands. The leak scan of
    test_evidence.py (test_no_leaks) already covers ct04/. This test lives here because that file
    is outside the task's allowed paths.
    """

    CT04 = HERE.parent / "evidence" / "ct04"
    TASK_TESTS = (
        "cargo test -p onjeon-contracts evidence_ref",
        "python3 -I packages/schemas/codegen/check_allowlist.py",
    )

    def test_logs_are_complete_and_indexed(self):
        index = (self.CT04 / "EVIDENCE.md").read_text(encoding="utf-8")
        self.assertRegex(index, r"\b[0-9a-f]{64}\b", "sha256 of the packages/schemas tree")
        self.assertRegex(index, r"\b[0-9a-f]{40}\b", "parent commit SHA")
        self.assertIn("tree_hash.sh", index)
        self.assertIn("T-CT-04", index)
        logs = sorted(self.CT04.glob("*.log"))
        self.assertTrue(logs, "no logs in ct04/")
        commands = []
        for path in logs:
            text = path.read_text(encoding="utf-8")
            self.assertIn(path.name, index, f"{path.name} not listed in ct04/EVIDENCE.md")
            self.assertTrue(text.startswith("$ "), f"{path.name}: first line must be the command")
            codes = [int(m) for m in re.findall(r"^exit code: (\d+)$", text, re.M)]
            self.assertTrue(codes, f"{path.name}: no 'exit code:' line")
            self.assertEqual(set(codes), {0}, f"{path.name}: exit codes {codes}")
            self.assertNotIn("FAILED", text, path.name)
            commands += re.findall(r"^\$ (.+)$", text, re.M)
        for cmd in self.TASK_TESTS:
            self.assertIn(cmd, commands, f"the task test command {cmd!r} was not logged")


if __name__ == "__main__":
    unittest.main()
