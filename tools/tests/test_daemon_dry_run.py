"""Dry run of the daemon core (tools/daemon): the T-OP-00 scenarios run on the shared core with mock adapters.

What must hold:
- every in-scope scenario (M28, M33-M44) ends with expected == actual on every check; checks marked GAP are
  specification gaps and are listed, not hidden;
- the core reads only the structured fields of daemon_rules.json: its view of the file has no `when`,
  `note` or `_` keys, and replacing or deleting every such key changes no result;
- the behavior comes from the data: changing a structured rule (resend checks, handoff order, thresholds,
  expiry condition) changes the result, so the scenarios are not matched by separate logic;
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
                  "handoff-quiescent-before-preserve", "preserve-manifest-same-function"}
        self.assertEqual(wanted - set(implemented), set())

    def test_every_scenario_prints_expected_and_actual(self):
        for mid, res in results().items():
            for c in res["checks"]:
                self.assertIn("expected", c)
                self.assertIn("actual", c)
                self.assertIn(c["status"], (sc.PASS, sc.FAIL, sc.GAP))

    def test_gaps_are_listed_with_field_and_need(self):
        from daemon.spec_gaps import SPEC_GAPS
        self.assertGreater(len(SPEC_GAPS), 0)
        for g in SPEC_GAPS:
            self.assertTrue(g["field"] and g["need"] and g["where"])
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
        walk(Rules(raw_rules(), {}).view)

    def test_view_is_a_subset_of_the_read_list(self):
        view = Rules(raw_rules(), {}).view
        allowed = {"core_contract", "transitions", "lease_guards", "handoff_sequence", "handoff_failure_policy",
                   "concurrency", "envelopes", "state_integrity", "noop_events", "return_codes", "events", "hard_stop",
                   "preserve_manifest"}
        self.assertEqual(set(view) - allowed, set())
        self.assertEqual(set(view["concurrency"]) - {"lease", "lease_issue", "quiescence", "idempotency_key", "fencing"}, set())
        self.assertEqual(set(view["handoff_failure_policy"]), {"max_attempts", "always_revoke"})
        for name, body in view["envelopes"].items():
            self.assertEqual(set(body), {"required"}, name)
        for tr in view["transitions"]:
            self.assertEqual(set(tr) - {"from", "to", "event", "guard", "cond", "side_effects", "by"}, set())

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


class BehaviorComesFromData(unittest.TestCase):
    """Changing a structured rule must change the outcome; separate hard-coded logic would not notice."""

    def test_resend_checks_are_read_from_data(self):
        raw = raw_rules()
        raw["state_integrity"]["resend_same_envelope_id_only_if"] = raw["state_integrity"]["resend_same_envelope_id_only_if"][:1]
        self.assertNotEqual(failing(run_fn(sc.m42, raw)), [])

    def test_handoff_order_is_read_from_data(self):
        raw = raw_rules()
        seq = raw["handoff_sequence"]
        i, j = seq.index("confirm_quiescent"), seq.index("preserve")
        seq[i], seq[j] = seq[j], seq[i]
        self.assertNotEqual(failing(run_fn(sc.m33, raw)), [])

    def test_thresholds_are_read_from_data(self):
        cfg = json.loads(TASKS.read_text(encoding="utf-8"))
        cfg["parameters"]["handoff_failure_policy.max_attempts.quiescence_failed.value"] = 2
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "tasks.json"
            p.write_text(json.dumps(cfg), encoding="utf-8")
            self.assertNotEqual(failing(run_fn(sc.m37, str(RULES), p)), [])

    def test_expiry_condition_is_read_from_data(self):
        raw = raw_rules()
        tr = [t for t in raw["transitions"] if t["event"] == "lease_expired"][0]
        tr["cond"][0]["value"] = "lease_record.issued_at + concurrency.lease.heartbeat_s*100000"
        self.assertNotEqual(failing(run_fn(sc.m41, raw)), [])

    def test_transition_target_is_read_from_data(self):
        raw = raw_rules()
        tr = [t for t in raw["transitions"] if t["event"] == "lease_expired"][0]
        tr["to"] = "returned"
        self.assertNotEqual(failing(run_fn(sc.m41, raw)), [])

    def test_corruption_effects_list_is_read_from_data(self):
        raw = raw_rules()
        raw["state_integrity"]["corruption"]["effects"] = ["lease_record.status = revoked"]
        self.assertNotEqual(failing(run_fn(sc.m44, raw)), [])

    def test_always_revoke_list_is_read_from_data(self):
        raw = raw_rules()
        raw["handoff_failure_policy"]["always_revoke"] = ["builder_write_credential", "builder_token"]
        self.assertNotEqual(failing(run_fn(sc.m37, raw)), [])

    def test_noop_names_must_be_listed(self):
        raw = raw_rules()
        raw["noop_events"].remove("envelope_duplicate_delivery")
        self.assertNotEqual(failing(run_fn(sc.m34, raw)), [])


class Static(unittest.TestCase):
    def test_static_checks(self):
        for name, bad in static_checks.all_static(RULES):
            self.assertEqual(bad, [], name)

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
        raw["state_integrity"]["resend_same_envelope_id_only_if"] = raw["state_integrity"]["resend_same_envelope_id_only_if"][:1]
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


if __name__ == "__main__":
    unittest.main()
