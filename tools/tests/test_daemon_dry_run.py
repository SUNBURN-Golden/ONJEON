"""Dry run of the daemon core (tools/daemon): the T-OP-00 scenarios run on the shared core with mock adapters.

What must hold:
- every in-scope scenario (M26, M28-M30, M33-M44) ends with expected == actual on every check; checks marked GAP
  are specification gaps and are listed, not hidden;
- the core reads only the fields of core_contract.reads: its view of the file has no prose `when`, `note` or `_`
  keys, and replacing or deleting every such key changes no result;
- the behavior comes from the data: changing one structured field (resend checks, handoff order, thresholds,
  expiry condition, guards, side effects, the read list ...) makes the scenario that depends on it fail, so the
  scenarios are not matched by separate logic;
- usage is recorded and never capped (U-05);
- static checks: no merge API, no network or CLI, no wall clock, no start-up feature, one writer of
  lease_generation, one tree identity function, no model identifiers, no dry-run branch in the core.
"""
import contextlib
import copy
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from daemon import dry_run, scenarios as sc, static_checks  # noqa: E402
from daemon.core import Rules  # noqa: E402
from daemon.mock_env import MockEnv  # noqa: E402

RULES = ROOT / "docs/blueprint/proposals/설계검토_결과/daemon_rules.json"
TASKS = ROOT / "tools/daemon/mock_tasks.json"
SPEC_TASKS = ROOT / "docs/blueprint/proposals/설계검토_결과/tasks.json"
SCEN = {e[0]: e for e in sc.SCENARIOS}
_CACHE = {}


def results():
    if not _CACHE:
        for e in sc.SCENARIOS:
            _CACHE[e[0]] = dry_run.run_scenario(e, str(RULES), str(TASKS))
    return _CACHE


def raw_rules():
    return json.loads(RULES.read_text(encoding="utf-8"))


def run_fn(fn, rules, tasks=None):
    """Checks of one scenario function; an exception counts as a failed check."""
    rep = sc.Report()
    try:
        fn(rep, rules, str(tasks or TASKS))
    except Exception as exc:  # noqa: BLE001 - a stopped core is a different result
        rep.checks.append({"name": "exception", "expected": None, "actual": repr(exc), "status": sc.FAIL})
    return rep.checks


def failing(checks):
    return [c for c in checks if c["status"] == sc.FAIL]


class ScenarioResults(unittest.TestCase):
    pass


def _make(mid):
    def test(self):
        res = results()[mid]
        self.assertIsNone(res["error"], res["error"])
        self.assertTrue(res["checks"], "scenario produced no checks")
        bad = failing(res["checks"])
        self.assertEqual(bad, [], "\n".join(f"{c['name']}\n  expected {c['expected']}\n  actual   {c['actual']}" for c in bad))
    return test


for _mid, _tid, *_ in sc.SCENARIOS:
    setattr(ScenarioResults, f"test_{_mid}_{_tid.replace('-', '_')}", _make(_mid))


class Coverage(unittest.TestCase):
    def test_test_ids_are_the_ones_in_tasks_json(self):
        tasks = json.loads(SPEC_TASKS.read_text(encoding="utf-8"))["tasks"]
        required = [t for t in tasks if t["id"] == "T-OP-00"][0]["required_test_ids"]
        mock = json.loads(TASKS.read_text(encoding="utf-8"))["t_op_00_required_test_ids"]
        self.assertEqual(mock, required)
        implemented = [e[1] for e in sc.SCENARIOS if e[0] != "STATIC"]
        self.assertEqual([t for t in implemented if t not in required], [])
        wanted = {"restart-ttl-expired-no-resend", "restart-revoked-pending-void", "restart-valid-pending-resend",
                  "restart-corrupt-record-returned", "lease-issue-atomic-single-owner", "envelope-id-distinct-events",
                  "duplicate-delivery-noop", "retry-new-idempotency-key", "late-result-no-state-change",
                  "preserve-failure-recoverable-stop", "daemon-restart-during-handoff",
                  "handoff-quiescent-before-preserve", "preserve-manifest-same-function",
                  "usage-recorded-not-capped", "handoff-order", "lease-guards-all-paths"}
        self.assertEqual(wanted - set(implemented), set())

    def test_every_scenario_prints_expected_and_actual(self):
        for mid, res in results().items():
            for c in res["checks"]:
                self.assertIn("expected", c)
                self.assertIn("actual", c)
                self.assertIn(c["status"], (sc.PASS, sc.FAIL, sc.GAP))

    def test_gaps_are_listed_with_field_status_and_need(self):
        from daemon.spec_gaps import SPEC_GAPS, RESOLVED, PARTLY, OPEN, NEW
        self.assertGreater(len(SPEC_GAPS), 0)
        ids = [g["id"] for g in SPEC_GAPS]
        self.assertEqual(len(ids), len(set(ids)))
        for g in SPEC_GAPS:
            self.assertTrue(g["field"] and g["need"] and g["where"])
            self.assertIn(g["status"], (RESOLVED, PARTLY, OPEN, NEW))
            if g["status"] in (RESOLVED, PARTLY):
                self.assertTrue(g.get("resolved_by"), g["id"])
        # the 28 gaps reported first are all accounted for
        self.assertEqual([f"G{n:02d}" for n in range(1, 29)], [i for i in ids if int(i[1:]) <= 28])
        gap_checks = [c for r in results().values() for c in r["checks"] if c["status"] == sc.GAP]
        self.assertTrue(all(c.get("note") for c in gap_checks))


class StructuredFieldsOnly(unittest.TestCase):
    def test_view_has_no_explanation_keys(self):
        def walk(node, path=""):
            if isinstance(node, dict):
                for k, v in node.items():
                    self.assertFalse(k in ("when", "note") or k.startswith("_"), f"{path}/{k}")
                    walk(v, f"{path}/{k}")
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    walk(v, f"{path}[{i}]")
        walk(Rules(raw_rules()).view)

    def test_structured_when_of_noop_rules_is_kept_as_cond(self):
        rules = Rules(raw_rules())
        raw = raw_rules()["noop_rules"]
        self.assertEqual(len(rules.noop_rules), len(raw))
        for r, orig in zip(rules.noop_rules, raw):
            self.assertEqual(r["cond"], orig["when"])
            self.assertNotIn("when", r)
            self.assertNotIn("note", r)

    def test_view_is_a_subset_of_the_read_list(self):
        raw = raw_rules()
        rules = Rules(raw)
        self.assertEqual(rules.unmatched_reads, [])
        view = rules.view
        tops = {e.replace("[]", "").split(".")[0] for e in raw["core_contract"]["reads"]} | {"switch_policy"}
        self.assertEqual(set(view) - tops, set())
        self.assertEqual(set(view["concurrency"]), {"lease", "fencing", "lease_end", "lease_issue", "quiescence",
                                                    "idempotency_key", "max_parallel_leases", "branch_naming"})
        self.assertEqual(set(view["concurrency"]["fencing"]), {"on_lease_end"})
        self.assertEqual(set(view["handoff_failure_policy"]),
                         {"max_attempts", "attempt_counting", "retry_detail", "restart_resume", "always_revoke"})
        self.assertEqual(set(view["hard_stop"]), {"grace_s", "trigger"})
        self.assertEqual(set(view["preserve_manifest"]), {"function", "excludes", "secret_patterns"})
        self.assertEqual(set(view["switch_policy"]), {"allowed_sources"})
        for name, body in view["envelopes"].items():
            self.assertEqual(set(body), {"required"}, name)
        for tr in view["transitions"]:
            self.assertEqual(set(tr) - {"from", "to", "event", "guard", "cond", "side_effects", "return_code", "on_cond_fail"}, set())
        for rc in view["return_codes"]:
            self.assertEqual(set(rc), {"code"})
        self.assertEqual(len(view["transitions"]), len(raw["transitions"]))

    def test_read_patterns_expand(self):
        from daemon.core.rules import expand_pattern
        seqs = expand_pattern("transitions[].{from,to}")
        self.assertEqual(seqs, [[("key", "transitions"), ("each",), ("key", "from")],
                                [("key", "transitions"), ("each",), ("key", "to")]])
        self.assertEqual(len(expand_pattern("concurrency.{lease,fencing.on_lease_end}")), 2)
        self.assertEqual(expand_pattern("envelopes.*.required"), [[("key", "envelopes"), ("all",), ("key", "required")]])

    def test_replacing_or_deleting_explanation_keys_changes_nothing(self):
        base = {mid: [(c["name"], c["status"], c["actual"]) for c in r["checks"]] for mid, r in results().items() if mid != "STATIC"}
        for mode in ("garble", "drop"):
            alt = sc.perturb(raw_rules(), mode)
            self.assertNotEqual(alt, raw_rules())
            for mid, e in SCEN.items():
                if mid == "STATIC":
                    continue
                got = [(c["name"], c["status"], c["actual"]) for c in run_fn(e[3], alt)]
                self.assertEqual(got, base[mid], f"{mode} {mid}")

    def test_names_without_a_root_are_errors_not_literals(self):
        from daemon.core.gate_evaluator import Ctx
        from daemon.core.ports import SpecGap
        ctx = Ctx(Rules(raw_rules()), {"event": {"at": 1}})
        self.assertEqual(ctx.value("active"), "active")
        self.assertEqual(ctx.value("R-08"), "R-08")
        self.assertEqual(ctx.value("daemon"), "daemon")
        self.assertEqual(ctx.value("event.at + 2"), 3)
        self.assertEqual(ctx.value("coalesce(event.nothing, event.at) * 2"), 2)
        with self.assertRaises(SpecGap):
            ctx.value("no_such_root.field")
        with self.assertRaises(SpecGap):
            ctx.value("hard_stop.no_such_field")


def _mutated(fn):
    raw = raw_rules()
    fn(raw)
    return raw


def _transition(raw, frm, event, to=None):
    return [t for t in raw["transitions"] if t["from"] == frm and t["event"] == event and (to is None or t["to"] == to)][0]


class BehaviorComesFromData(unittest.TestCase):
    """Changing one structured field must make the scenario that depends on it fail; separate hard-coded logic
    would not notice."""

    def assertBreaks(self, scenario, fn, msg=""):
        bad = failing(run_fn(scenario, _mutated(fn)))
        self.assertNotEqual(bad, [], msg or "the scenario did not notice the change")

    def test_baseline_is_clean(self):
        for fn in (sc.m26, sc.m41, sc.m42):
            self.assertEqual(failing(run_fn(fn, raw_rules())), [])

    def test_resend_checks_are_read_from_data(self):
        def f(raw):
            raw["core_contract"]["operations"]["resend_outbox"]["checks"] = raw["core_contract"]["operations"]["resend_outbox"]["checks"][:1]
        self.assertBreaks(sc.m42, f)

    def test_resend_on_fail_effects_are_read_from_data(self):
        def f(raw):
            raw["core_contract"]["operations"]["resend_outbox"]["on_fail"]["revoked_or_cancelled"]["effects"] = []
        self.assertBreaks(sc.m42, f)

    def test_handoff_order_is_read_from_data(self):
        def f(raw):
            seq = raw["handoff_sequence"]
            i, j = seq.index("confirm_quiescent"), seq.index("preserve")
            seq[i], seq[j] = seq[j], seq[i]
        self.assertBreaks(sc.m33, f)
        self.assertBreaks(sc.m29, f)

    def test_max_attempts_are_read_from_data(self):
        self.assertBreaks(sc.m37, lambda raw: raw["handoff_failure_policy"]["max_attempts"].update(quiescence_failed=2))

    def test_attempt_comparison_is_read_from_data(self):
        def f(raw):
            _transition(raw, "handoff", "quiescence_failed", "handoff")["cond"][0]["op"] = "<"
        self.assertBreaks(sc.m37, f)

    def test_expiry_condition_is_read_from_data(self):
        def f(raw):
            _transition(raw, "leased", "lease_expired")["cond"][1]["value"] = "lease_record.issued_at + concurrency.lease.heartbeat_s*100000"
        self.assertBreaks(sc.m41, f)

    def test_heartbeat_interval_is_read_from_data(self):
        self.assertBreaks(sc.m41, lambda raw: raw["concurrency"]["lease"].update(heartbeat_s=100))

    def test_transition_target_is_read_from_data(self):
        self.assertBreaks(sc.m41, lambda raw: _transition(raw, "leased", "lease_expired").update(to="returned"))

    def test_corruption_effects_are_read_from_data(self):
        def f(raw):
            effs = _transition(raw, "*", "state_corrupted")["side_effects"]
            effs[:] = [e for e in effs if e["id"] != "void_outbox"]
        self.assertBreaks(sc.m44, f)

    def test_corruption_detect_is_read_from_data(self):
        def f(raw):
            raw["state_integrity"]["corruption"]["detect"] = raw["state_integrity"]["corruption"]["detect"][2:]
        self.assertBreaks(sc.m44, f)

    def test_always_revoke_list_is_read_from_data(self):
        self.assertBreaks(sc.m37, lambda raw: raw["handoff_failure_policy"].update(always_revoke=["builder_write_credential", "builder_token"]))

    def test_noop_names_must_be_listed(self):
        self.assertBreaks(sc.m34, lambda raw: raw["noop_events"].remove("envelope_duplicate_delivery"))

    def test_noop_rules_are_read_from_data(self):
        def f(raw):
            raw["noop_rules"] = [r for r in raw["noop_rules"] if r["event"] != "lease_granted"]
        self.assertBreaks(sc.m40, f)

    def test_accept_envelope_check_order_is_read_from_data(self):
        def f(raw):
            checks = raw["core_contract"]["operations"]["accept_envelope"]["checks_in_order"]
            ids = [c["id"] for c in checks]
            checks.insert(ids.index("lease_matches"), checks.pop(ids.index("not_seen")))
        self.assertBreaks(sc.m35, f)

    def test_accept_envelope_on_fail_is_read_from_data(self):
        def f(raw):
            raw["core_contract"]["operations"]["accept_envelope"]["on_fail"]["late"]["return_code"] = None
        self.assertBreaks(sc.m28, f)

    def test_lease_guards_are_read_from_data(self):
        def f(raw):
            raw["lease_guards"] = [g for g in raw["lease_guards"] if g["id"] != "usage_slot_ready"]
        self.assertBreaks(sc.m26, f)
        self.assertBreaks(sc.m30, f)

    def test_parallel_limit_is_read_from_data(self):
        self.assertBreaks(sc.m30, lambda raw: raw["concurrency"].update(max_parallel_leases=5))

    def test_retry_limit_is_read_from_data(self):
        self.assertBreaks(sc.m26, lambda raw: raw["retry_limits"].update(consecutive_failed_tests=2))

    def test_return_code_of_a_row_is_read_from_data(self):
        def f(raw):
            row = _transition(raw, "building", "result_failed_tests", "returned")
            row["return_code"] = "R-07"
            for e in row["side_effects"]:
                if e["id"] == "record_r_code":
                    e["args"]["code"] = "R-07"
        self.assertBreaks(sc.m26, f)

    def test_max_wall_s_cond_is_read_from_data(self):
        def f(raw):
            row = _transition(raw, "building", "hard_stop_deadline")
            row["cond"][0]["value"][1]["value"] = "lease_record.issued_at + instruction.limits.max_wall_s + 5"
        self.assertBreaks(sc.m26, f)

    def test_on_lease_end_is_read_from_data(self):
        self.assertBreaks(sc.m41, lambda raw: raw["concurrency"]["fencing"].update(on_lease_end=["revoke_write_credential", "revoke_token", "record_handoff"]))

    def test_issue_lease_atomic_effects_are_read_from_data(self):
        def f(raw):
            effs = raw["core_contract"]["operations"]["issue_lease"]["effects_atomic"]
            effs[:] = [e for e in effs if e["id"] != "create_outbox"]
        self.assertBreaks(sc.m40, f)

    def test_issue_reason_of_a_row_is_read_from_data(self):
        def f(raw):
            _transition(raw, "ci_failed", "lease_granted")["side_effects"][0]["args"]["reason"] = "retry_review"
        self.assertBreaks(sc.m35, f)

    def test_restart_resume_is_read_from_data(self):
        def f(raw):
            raw["handoff_failure_policy"]["restart_resume"]["confirm_quiescent"] = "confirm_quiescent"
        self.assertBreaks(sc.m38, f)

    def test_secret_patterns_are_read_from_data(self):
        self.assertBreaks(sc.m36, lambda raw: raw["preserve_manifest"]["secret_patterns"].update(patterns=["never-matches-anything"]))

    def test_manifest_excludes_are_read_from_data(self):
        self.assertBreaks(sc.m36, lambda raw: raw["preserve_manifest"].update(excludes=[e for e in raw["preserve_manifest"]["excludes"] if e != "target/"]))

    def test_usage_fields_to_record_are_read_from_data(self):
        def f(raw):
            raw["usage_recording"]["record_after_result"] = ["calls", "wall_s"]
        self.assertBreaks(sc.m26, f)

    def test_the_read_list_is_what_the_core_reads(self):
        for entry in ("retry_limits", "usage_recording", "lease_guards[]"):
            def f(raw, entry=entry):
                raw["core_contract"]["reads"].remove(entry)
            self.assertBreaks(sc.m26, f, entry)

    def test_a_read_list_entry_without_a_field_stops_the_core(self):
        def f(raw):
            raw["core_contract"]["reads"].append("no_such_top_level_field")
        self.assertBreaks(sc.m41, f)

    def test_no_cost_cap_in_rules_or_core_and_a_cap_would_be_noticed(self):
        self.assertEqual(static_checks.no_cost_cap(raw_rules(), TASKS), [])
        raw = raw_rules()
        raw["events"].append("budget_exhausted")
        self.assertNotEqual(static_checks.no_cost_cap(raw, TASKS), [])

    def test_usage_is_recorded_whatever_the_amount(self):
        env = sc.MockEnv(str(RULES), str(TASKS))
        env.bring_to_building(sc.BASIC)
        env.builder_for(sc.BASIC).send_result(env.instr(sc.BASIC), "failed_tests", cost_units=10 ** 30, calls=10 ** 12, wall_s=10 ** 9)
        env.run_builders("first_heartbeat")
        self.assertEqual((env.state(sc.BASIC), env.task(sc.BASIC)["lease_generation"]), ("building", 2))
        rows = env.snap()["usage_record"]
        self.assertEqual((rows[0]["cost_units"], rows[0]["calls"]), (10 ** 30, 10 ** 12))
        self.assertEqual([r["return_code"] for r in env.journal() if r["kind"] == "return_record"], [])


class Static(unittest.TestCase):
    def test_static_checks(self):
        for name, bad in static_checks.all_static(RULES):
            self.assertEqual(bad, [], name)

    def _network_or_cli_in(self, source):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "probe.py").write_text(source, encoding="utf-8")
            return static_checks.no_network_or_cli(Path(d))

    def test_dynamic_code_execution_and_import_are_noticed(self):
        for source in ("eval('1')", "exec('x = 1')", "compile('1', 'f', 'eval')", "__import__('os')",
                       "import importlib", "from importlib import import_module", "import importlib.util",
                       "import runpy", "import builtins", "from builtins import eval", "f = eval",
                       "import os\nos.__import__('x')", "x.import_module('y')", "from . import importlib"):
            self.assertNotEqual(self._network_or_cli_in(source), [], source)

    def test_ordinary_code_and_re_compile_are_not_flagged(self):
        self.assertEqual(self._network_or_cli_in("import re\nimport json\nP = re.compile('a')\nv = json.loads('1')\n"), [])

    def test_existing_network_and_cli_bans_still_hold(self):
        for source in ("import subprocess", "import socket", "import os\nos.system('x')"):
            self.assertNotEqual(self._network_or_cli_in(source), [], source)

    def test_this_test_file_has_no_model_identifiers(self):
        self.assertEqual(static_checks.no_model_identifiers([__file__]), [])

    def test_core_does_not_name_prose_keys(self):
        self.assertEqual(static_checks.no_natural_language_reads(), [])


class Journal(unittest.TestCase):
    def test_journal_is_append_only_and_ordered(self):
        env = sc.MockEnv(str(RULES), str(TASKS))
        env.bring_to_building(sc.BASIC)
        first = env.journal()
        env.submit(sc.BASIC, "heartbeat", env.builder_for(sc.BASIC).heartbeat_envelope(env.instr(sc.BASIC)))
        env.restart()
        later = env.journal()
        self.assertEqual(later[: len(first)], first)
        self.assertEqual([r["seq"] for r in later], list(range(1, len(later) + 1)))
        kinds = {r["kind"] for r in later}
        self.assertLessEqual(kinds, {"transition_record", "side_effect_record", "noop_record", "return_record",
                                      "intent_record", "result_record", "diagnostic_record"})

    def test_transition_record_has_the_contract_fields(self):
        env = sc.MockEnv(str(RULES), str(TASKS))
        env.start_task(sc.BASIC)
        rec = [r for r in env.journal() if r["kind"] == "transition_record"][0]
        for k in ("task_id", "from", "to", "event", "at", "cond_evaluated"):
            self.assertIn(k, rec)
        grant = env.grant(sc.BASIC)
        rec = [r for r in env.journal() if r["kind"] == "transition_record"][-1]
        self.assertTrue(rec["cond_evaluated"] and all("result" in c for c in rec["cond_evaluated"]))

    def test_clock_is_virtual(self):
        env = sc.MockEnv(str(RULES), str(TASKS))
        t0 = env.clock.now()
        env.clock.advance(10)
        self.assertEqual(env.clock.now(), t0 + 10)
        env.clock.set(5)
        self.assertEqual(env.clock.now(), 5)


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = dry_run.main(list(args))
        return code, buf.getvalue()

    def test_all_scenarios_exit_zero_and_print_expected_and_actual(self):
        code, out = self.run_cli("--rules", str(RULES), "--tasks", str(TASKS), "--scenario", "all")
        self.assertEqual(code, 0, out[-2000:])
        self.assertIn("기대:", out)
        self.assertIn("실제:", out)
        self.assertIn("실행하지 않은 시험 ID", out)

    def test_single_scenario_by_number_and_by_test_id(self):
        for sel in ("M41", "restart-ttl-expired-no-resend"):
            code, out = self.run_cli("--rules", str(RULES), "--tasks", str(TASKS), "--scenario", sel, "--quiet")
            self.assertEqual(code, 0)
            self.assertIn("== M41", out)

    def test_exit_code_is_one_when_one_check_differs(self):
        raw = raw_rules()
        raw["core_contract"]["operations"]["resend_outbox"]["checks"] = raw["core_contract"]["operations"]["resend_outbox"]["checks"][:1]
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "rules.json"
            p.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            code, out = self.run_cli("--rules", str(p), "--tasks", str(TASKS), "--scenario", "M42", "--quiet")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL]", out)

    def test_report_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "out" / "report.json"
            code, _ = self.run_cli("--rules", str(RULES), "--tasks", str(TASKS), "--scenario", "M44", "--report", str(p), "--quiet")
            data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(code, 0)
        self.assertEqual(data["results"][0]["id"], "M44")
        self.assertIn("spec_gaps", data)

    def test_unknown_scenario_is_an_error(self):
        with self.assertRaises(SystemExit):
            self.run_cli("--rules", str(RULES), "--tasks", str(TASKS), "--scenario", "M99")


class InboxSeenPruning(unittest.TestCase):
    """audit1: inbox_seen keeps the idempotency keys of the ended lease and of the live one, not of every generation."""

    def generations(self, env, t):
        return sorted({v["lease_generation"] for v in env.task(t)["inbox_seen"].values()})

    def test_end_lease_drops_keys_of_older_generations_and_keeps_its_own(self):
        env = MockEnv(str(RULES), str(TASKS))
        t = sc.BASIC
        env.bring_to_building(t)
        old, ob = copy.deepcopy(env.instr(t)), env.builder_for(t)
        ob.send_result(old, "failed_tests")  # ends generation 1
        self.assertEqual(self.generations(env, t), [1])  # the ended generation's own keys stay (nothing older to drop)
        env.run_builders("first_heartbeat")  # re-lease: generation 2 starts
        self.assertEqual(self.generations(env, t), [1, 2])  # superseded, but not yet pruned
        instr2 = copy.deepcopy(env.instr(t))
        env.submit(t, "heartbeat", ob.heartbeat_envelope(instr2))
        env.builder_for(t).send_result(instr2, "failed_tests")  # ends generation 2
        self.assertEqual(self.generations(env, t), [2])  # generation 1 keys are gone, generation 2's stay

    def test_pruning_does_not_change_how_old_envelopes_are_classified(self):
        env = MockEnv(str(RULES), str(TASKS))
        t = sc.BASIC
        env.bring_to_building(t)
        old, ob = copy.deepcopy(env.instr(t)), env.builder_for(t)
        hb1 = ob.heartbeat_envelope(old)
        env.submit(t, "heartbeat", copy.deepcopy(hb1))
        ob.send_result(old, "failed_tests")
        env.run_builders("first_heartbeat")
        instr2 = copy.deepcopy(env.instr(t))
        env.builder_for(t).send_result(instr2, "failed_tests")
        self.assertEqual(self.generations(env, t), [2])
        late = env.submit(t, "heartbeat", copy.deepcopy(hb1))  # generation 1 key is gone: still late, not accepted
        self.assertEqual((late["accepted"], late["noop"], late["return_code"]), (False, "late_envelope_rejected", "R-11"))


if __name__ == "__main__":
    unittest.main()
