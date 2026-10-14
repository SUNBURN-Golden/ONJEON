"""Dry run of the daemon core (tools/daemon): the T-OP-00 scenarios run on the shared core with mock adapters.

What must hold:
- every scenario M1-M44 (05 §5, with M10a·M10b·M18a·M18b) ends with expected == actual on every check, and every
  required test id of T-OP-00 is run; checks marked GAP would be specification gaps and are listed, not hidden;
- the G29-G50 fields are read by the core (t_op_00_followups): the structure checks of tests_to_add hold on the file
  and the behavior checks hold on the core;
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
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from daemon import dry_run, scenarios as sc, scenarios_flow as fl, static_checks  # noqa: E402
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
        self.assertEqual([t for t in implemented if t not in required and t != "-"], [])
        self.assertEqual(set(required) - set(implemented), set(), "every required test id runs")
        self.assertEqual(len([t for t in implemented if t != "-"]), len(set(t for t in implemented if t != "-")))

    def test_every_prose_test_line_has_a_passing_scenario(self):
        """Each '시험 <id>(Mxx): ...' line of tasks.json is a description, not a command: it maps to the scenario
        selected by `dry_run.py --scenario <id>`, to the unittest method of that scenario, and the scenario passes."""
        tasks = json.loads(SPEC_TASKS.read_text(encoding="utf-8"))["tasks"]
        node = [t for t in tasks if t["id"] == "T-OP-00"][0]
        prose = [re.match(r"시험 ([a-z0-9-]+)(?:\((M\d+[ab]?)\b)?", line) for line in node["tests"]
                 if line.startswith("시험 ")]
        self.assertTrue(prose and all(prose))
        self.assertEqual(sorted(m.group(1) for m in prose), sorted(node["required_test_ids"]))
        for m in prose:
            tid, mid = m.group(1), m.group(2)
            with self.subTest(test_id=tid):
                [entry] = dry_run.select(tid)
                if mid:
                    self.assertEqual(entry[0], mid, "the M number in the prose line is the scenario run")
                self.assertTrue(hasattr(ScenarioResults, f"test_{entry[0]}_{tid.replace('-', '_')}"))
                res = results()[entry[0]]
                self.assertEqual(dry_run.scenario_status(res), "PASS", tid)

    def test_every_m_number_of_05_runs(self):
        ids = {e[0] for e in sc.SCENARIOS}
        self.assertEqual({f"M{n}" for n in range(1, 45)} - ids, set())
        self.assertLessEqual({"M10a", "M10b", "M18a", "M18b"}, ids)

    def test_dry_run_reports_all_required_ids_run(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = dry_run.main(["--rules", str(RULES), "--tasks", str(TASKS), "--scenario", "all", "--quiet",
                                 "--require-all"])
        self.assertEqual(code, 0, buf.getvalue()[-3000:])
        self.assertIn("실행하지 않은 것 0개", buf.getvalue())
        self.assertIn("검사", buf.getvalue())
        self.assertIn("실패 0건, 명세 공백 표시 0건", buf.getvalue())

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
        self.assertEqual(gap_checks, [], "no scenario carries a gap mark after G29-G50 (t_op_00_followups)")

    def test_g29_to_g50_are_read_by_the_core(self):
        """spec_gaps: G29-G50 resolved and read by the core, except G47 (its read-list entry is in daemon_rules.json,
        outside this task's paths). gap_resolutions[].mock_core_reads describes the core before this change."""
        from daemon.spec_gaps import SPEC_GAPS, RESOLVED, PARTLY
        gaps = {g["id"]: g for g in SPEC_GAPS}
        for n in range(29, 51):
            g = gaps[f"G{n}"]
            if g["id"] == "G47":
                self.assertEqual((g["status"], g["core_reads"]), (PARTLY, "partly"))
                self.assertIn("envelopes.instruction.limits", g["remaining"])
                self.assertNotIn("envelopes.instruction.limits", raw_rules()["core_contract"]["reads"])
            else:
                self.assertEqual((g["status"], g["core_reads"]), (RESOLVED, "yes"), g["id"])
        self.assertEqual(sorted(Rules.token_log), [], "no token was pulled out of a sentence")

    def test_outside_reads_are_reported_gaps(self):
        from daemon.core.rules import OUTSIDE_READS
        from daemon.spec_gaps import SPEC_GAPS, NEW
        open_ids = {g["id"] for g in SPEC_GAPS if g["status"] == NEW}
        for path, gap in OUTSIDE_READS.items():
            self.assertIn(gap, open_ids, path)
            self.assertNotIn(path, raw_rules()["core_contract"]["reads"])
        rules = Rules(raw_rules())
        from daemon.core.ports import SpecGap
        with self.assertRaises(SpecGap):
            rules.outside("roles")


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
        tops = {e.replace("[]", "").split(".")[0] for e in raw["core_contract"]["reads"]}
        self.assertEqual(set(view) - tops, set())
        self.assertIn("switch_policy.allowed_sources", raw["core_contract"]["reads"])  # G32: no extension list
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


# ---------------------------------------------------------------- t_op_00_followups.tests_to_add
def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield path + "." + k, k, v
            yield from _walk(v, path + "." + k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def _resolve(raw, path):
    """'a.b[k=v,k2=v2].c' -> the value, or raise KeyError."""
    import re
    cur = raw
    for seg in re.findall(r"[^.\[]+(?:\[[^\]]*\])?", path):
        m = re.fullmatch(r"([^\[]+)(?:\[([^\]]*)\])?", seg)
        key, sel = m.group(1), m.group(2)
        cur = cur[key]
        if sel:
            want = dict(x.split("=", 1) for x in sel.split(","))
            hits = [x for x in cur if all(str(x.get(k)) == v for k, v in want.items())]
            if not hits:
                raise KeyError(path)
            cur = hits[0]
    return cur


def _rows(raw, frm=None, event=None, to=None):
    return [t for t in raw["transitions"] if (frm is None or t["from"] == frm) and (event is None or t["event"] == event)
            and (to is None or t["to"] == to)]


def _effect_ids(row):
    return [e["id"] for e in row.get("side_effects", [])]


_COMPLEMENT = {("==", "!="), ("!=", "=="), ("<=", ">"), (">", "<="), ("<", ">="), (">=", "<")}


def _exclusive(a, b):
    """Two conds cannot both hold: a shared field with complementary ops on the same value, or == on different values."""
    for p in a.get("cond") or []:
        for q in b.get("cond") or []:
            if p["field"] != q["field"]:
                continue
            if (p["op"], q["op"]) in _COMPLEMENT and p["value"] == q["value"]:
                return True
            if p["op"] == q["op"] == "==" and p["value"] != q["value"]:
                return True
    return False


class FollowupStructure(unittest.TestCase):
    """tests_to_add.structure: consistency of the file itself (no core)."""

    def setUp(self):
        self.raw = raw_rules()

    def test_g29_scope_in_the_expressions_and_overlap_of_nested_globs(self):
        from daemon.core.gate_evaluator import intersects, patterns_overlap
        guards = {g["id"]: g for g in self.raw["lease_guards"]}
        for gid in ("no_conflict_lease", "single_writer", "max_parallel_leases"):
            self.assertIn("task_id != this.task_id", guards[gid]["check"]["field"], gid)
        swl = [d for d in self.raw["state_integrity"]["corruption"]["detect"] if d["id"] == "state_without_lease"][0]
        self.assertTrue(any("task_id == this.task_id" in p["field"] for p in swl["pred"]))
        self.assertEqual(guards["no_conflict_lease"]["conflict_match"]["relation"], "patterns_overlap")
        self.assertTrue(patterns_overlap("services/knowledge/**", "services/knowledge/release/**"))
        self.assertFalse(patterns_overlap("services/knowledge/**", "services/knowledge2/**"))
        tasks = json.loads(SPEC_TASKS.read_text(encoding="utf-8"))["tasks"]
        nested = [(a["id"], b["id"]) for a in tasks for b in tasks if a["id"] < b["id"]
                  and intersects(a.get("conflict_paths") or [], b.get("conflict_paths") or [], "patterns_overlap")
                  and not set(a.get("conflict_paths") or []) & set(b.get("conflict_paths") or [])]
        self.assertTrue(nested, "tasks.json has nested conflict_paths that only the pattern relation sees")

    def test_g30_recovery_rows_are_exclusive_and_write_phases(self):
        rows = _rows(self.raw, "handoff_blocked", "recovery_decision", "handoff")
        self.assertEqual(len(rows), 2)
        self.assertTrue(_exclusive(rows[0], rows[1]))
        enum = self.raw["core_contract"]["store"]["enums"]["handoff_record_phase"]
        stages = [k for k in self.raw["handoff_failure_policy"]["restart_resume"] if not k.startswith("_")]
        for row in self.raw["transitions"]:
            for e in row.get("side_effects", []):
                if e["id"] == "set_handoff_field" and e["args"]["field"] == "phase":
                    self.assertIn(e["args"]["value"], enum)
                    self.assertIn(e["args"]["value"], stages)
        self.assertEqual(set(enum) - {None}, set(stages))

    def test_g31_restart_resume_forms(self):
        rr = self.raw["handoff_failure_policy"]["restart_resume"]
        stages = [k for k in rr if not k.startswith("_")]
        self.assertEqual(stages, ["stop", "isolate", "confirm_quiescent", "preserve", "preserve_remote", "revoke_token",
                                  "issue_next_lease"])
        for k in stages:
            v = rr[k]
            if isinstance(v, str):
                self.assertIn(v, stages)
                continue
            self.assertEqual(set(v), {"check", "then", "else"}, k)
            for branch in (v["then"], v["else"]):
                (kind, target), = [(x, branch[x]) for x in ("stage", "event", "noop") if x in branch]
                if kind == "stage":
                    self.assertIn(target, stages)
                elif kind == "event":
                    self.assertIn(target, self.raw["events"])

    def test_g32_g33_read_list_and_condition_keys(self):
        self.assertIn("switch_policy.allowed_sources", self.raw["core_contract"]["reads"])
        for r in self.raw["noop_rules"]:
            self.assertTrue(isinstance(r["when"], list) and all({"field", "op", "value"} <= set(x) for x in r["when"]))
        for path, key, v in _walk(self.raw):
            if key == "when" and not path.startswith(".noop_rules") and isinstance(v, list):
                self.fail(f"a predicate-list `when` outside noop_rules: {path}")

    def test_g34_to_g36_lease_end_and_credentials(self):
        enum = set(self.raw["core_contract"]["store"]["enums"]["lease_record_status"])
        le = self.raw["concurrency"]["lease_end"]
        written = {e["args"]["status"] for t in self.raw["transitions"] for e in t.get("side_effects", []) if e["id"] == "end_lease"}
        self.assertLessEqual(written, enum)
        with_end = {(t["from"], t["to"], t["event"]) for t in self.raw["transitions"] if "end_lease" in _effect_ids(t)}
        listed = [tuple(x) for x in le["transitions"]]
        for frm, to, ev in with_end:
            self.assertTrue(any(f == frm and t2 == to and e in (ev, "*") for f, t2, e in listed), (frm, to, ev))
        for f, t2, e in listed:
            self.assertTrue(any(fr == f and to == t2 and (e == "*" or ev == e) for fr, to, ev in with_end), (f, t2, e))
        table = self.raw["core_contract"]["expected_outputs"]["credential_of_effect"]
        self.assertEqual(sorted(table.values()), sorted(self.raw["handoff_failure_policy"]["always_revoke"]))
        self.assertEqual(len(set(table.values())), len(table))

    def test_g37_leaving_an_active_lease_ends_it(self):
        le = self.raw["concurrency"]["lease_end"]
        active = set(le["active_lease_states"])
        exceptions = {tuple(x) for x in le["handed_off_exceptions"]}
        conditional = {tuple(r["transition"]) for r in le["conditional_rows"]}
        for t in self.raw["transitions"]:
            key = (t["from"], t["to"], t["event"])
            if t["from"] in active and t["to"] not in active and key not in exceptions:
                self.assertIn("end_lease", _effect_ids(t), key)
            if t["to"] == "cancelled":
                self.assertIn("set_cancelled", _effect_ids(t), key)
            if t["from"] == "*" and t["to"] == "returned" and key not in conditional:
                self.assertIn("end_lease", _effect_ids(t), key)
        seen = {}
        for t in self.raw["transitions"]:
            seen.setdefault((t["from"], t["to"], t["event"]), []).append(t)
        for key, rows in seen.items():
            for i in range(len(rows)):
                for j in range(i + 1, len(rows)):
                    self.assertTrue(_exclusive(rows[i], rows[j]), key)

    def test_g38_g39_secret_and_index_lock_rows(self):
        row = _rows(self.raw, "handoff", "secret_detected", "returned")
        self.assertEqual((len(row), row[0]["return_code"]), (1, "R-10"))
        for scan in self.raw["preserve_manifest"]["secret_patterns"]["scan"]:
            for st in scan["states"]:
                self.assertTrue(_rows(self.raw, st, "secret_detected"), (scan["id"], st))
        rows = _rows(self.raw, "handoff", "index_lock", "handoff")
        self.assertEqual(len(rows), 2)
        self.assertTrue(_exclusive(rows[0], rows[1]))
        stages = {e["args"]["stage"] for r in rows for e in r["side_effects"] if e["id"] == "resume_from_phase"}
        self.assertEqual(stages, {"handoff_failure_policy.retry_detail.index_lock.retry_from",
                                  "handoff_failure_policy.retry_detail.index_lock.owner_alive_then"})

    def test_g40_to_g44_order_enums_detect_events_values(self):
        cc = self.raw["core_contract"]
        ae = cc["operations"]["accept_envelope"]
        self.assertEqual([c["id"] for c in ae["checks_in_order"]],
                         ["required_present", "lease_matches", "not_seen", "lease_active_unexpired", "current_lease_rules"])
        reasons = set()
        for t in self.raw["transitions"]:
            reasons |= {e["args"]["reason"] for e in t.get("side_effects", []) if e["id"] == "void_outbox"}
        for v in cc["operations"]["resend_outbox"]["on_fail"].values():
            reasons |= {e["args"]["reason"] for e in v.get("effects", []) if e["id"] == "void_outbox"}
        reasons |= {e["args"]["reason"] for e in self.raw["state_integrity"]["corruption"]["effects"] if e["id"] == "void_outbox"}
        self.assertEqual(reasons, set(cc["store"]["enums"]["outbox_void_reason"]))
        ids = [d["id"] for d in self.raw["state_integrity"]["corruption"]["detect"]]
        self.assertEqual((len(ids), len(set(ids))), (5, 5))
        self.assertIn("outbox_lease_id_mismatch", ids)
        self.assertEqual(set(self.raw["state_integrity"]["corruption"]["bindings"]), {"lease_record", "outbox", "journal"})
        events = set(self.raw["events"])
        ne = self.raw["state_integrity"]["normal_expiry"]
        self.assertEqual(set(ne["events"]), set(ne["events_by_state"].values()))
        self.assertLessEqual(set(ne["events"]), events)
        for v in cc["operations"]["resend_outbox"]["on_fail"].values():
            self.assertLessEqual(set(v["then_events"]), events)
        self.assertEqual(ae["idempotency_key_fields"], ["task_id", "lease_generation", "envelope_kind", "envelope_id"])
        self.assertIn("kind", self.raw["envelopes"]["fence_violation_report"]["required"])
        self.assertEqual(set(ae["field_value_sets"]), {"fence_violation_report"})

    def test_g45_to_g50(self):
        cc = self.raw["core_contract"]
        lock = self.raw["concurrency"]["lease_issue"]["lock"]
        self.assertEqual(lock["acquire"]["writes"]["holder"], "core_contract.daemon_instance.id")
        self.assertIn("when a guard fails", lock["release"]["at"])
        self.assertIn("clears_rows_where", lock["restart"])
        ur = self.raw["usage_recording"]
        self.assertEqual(ur["record_semantics"]["columns"], "write_once (null → value)")
        self.assertEqual(ur["accepted_vs_rejected"]["late_envelope_rejected"], "not_recorded")
        self.assertEqual(self.raw["envelopes"]["instruction"]["limits"]["value_source_order"][0], "task definition limits.<key>")
        payloads = cc["events_in"]["payloads"]
        guard_states = {t["from"] for t in self.raw["transitions"] if t.get("guard")}
        for g in self.raw["lease_guards"]:
            if g["on_fail"].get("action") == "emit_event":
                self.assertIn(g["on_fail"]["event"], payloads)
                self.assertEqual(set(g["on_fail"]["only_in_states"]), guard_states)
        for st in guard_states:
            rows = _rows(self.raw, st, "envelope_invalid", "returned")
            self.assertEqual((len(rows), rows[0]["return_code"]), (1, "R-13"), st)
        vi = cc["operations"]["validate_instruction"]
        self.assertEqual((len(vi["rules"]), len(vi["derive"])), (8, 1))
        for step in self.raw["hard_stop"]["procedure"]:
            if "transition" in step:
                self.assertTrue(_rows(self.raw, *step["transition"][:2], to=step["transition"][1]) or True)
                self.assertTrue([t for t in self.raw["transitions"] if [t["from"], t["to"], t["event"]] == step["transition"]], step)
        self.assertTrue(_rows(self.raw, "building", "owner_stop", "building"))
        self.assertEqual({r["noop_event"] for r in self.raw["noop_rules"] if r["event"] == "owner_stop"},
                         {"owner_stop_already_requested", "owner_stop_ignored_during_handoff"})
        self.assertEqual(cc["operations"]["hard_stop"]["trigger_events"]["owner_stop"]["then"], "hard_stop_deadline")

    def test_g29_to_g50_resolved_by_paths_exist_and_07_lists_them(self):
        gr = self.raw["t_op_00_followups"]["gap_resolutions"]
        self.assertEqual(sorted(gr), [f"G{n}" for n in range(29, 51)])
        for gid, item in gr.items():
            for path in item["resolved_by"]:
                if path == "events":
                    continue
                try:
                    _resolve(self.raw, path)
                except (KeyError, TypeError, IndexError):
                    self.fail(f"{gid}: {path} not found")
        doc = (ROOT / "docs/blueprint/proposals/설계검토_결과/07_수정대응표.md").read_text(encoding="utf-8")
        for n in range(29, 51):
            self.assertIn(f"G{n}", doc)


class FollowupBehavior(unittest.TestCase):
    """tests_to_add.behavior: the same checks on the core (MockEnv)."""

    def env(self):
        return sc.MockEnv(str(RULES), str(TASKS))

    def tr(self, env, m):
        return sc.tr(env.journal()[m:])

    def test_g37_unmapped_condition_ends_an_active_lease(self):
        env = self.env()
        env.start_task(sc.BASIC)
        env.grant(sc.BASIC)
        env.event("owner_stop", sc.BASIC, stop_ref="S")  # owner_stop from leased: unmapped
        self.assertEqual((env.state(sc.BASIC), env.lease(sc.BASIC)["status"]), ("returned", "revoked"))
        env.event("owner_resolved", sc.BASIC, resolution_ref="R")
        env.grant(sc.BASIC)
        self.assertEqual((env.state(sc.BASIC), env.task(sc.BASIC)["lease_generation"]), ("leased", 2))
        env = self.env()
        env.start_task(sc.BASIC)
        m = sc.mark(env)
        env.event("owner_stop", sc.BASIC, stop_ref="S")  # queued: no lease
        js = env.journal()[m:]
        self.assertEqual((sc.tr(js), sc.se(js)), ([("queued", "returned", "unmapped_condition")], ["record_r_code"]))

    def test_g38_secret_during_handoff(self):
        env, path = sc.handoff_bench(str(RULES), str(TASKS))
        env.ports.worktree.write(path, "s.txt", sc.fake_secret("token"))
        env.clock.advance(1)
        sc.switch(env)
        self.assertEqual((env.state(sc.HANDOFF), env.ports.git.commit_count, env.ports.git.push_count,
                          env.lease(sc.HANDOFF)["status"]), ("returned", 0, 0, "revoked"))

    def test_g39_index_lock_owner_alive(self):
        from daemon.core.ports import IndexLockError
        for alive, stage in ((True, "isolate"), (False, "preserve")):
            env, _ = sc.handoff_bench(str(RULES), str(TASKS))
            env.ports.git.inject("commit", [IndexLockError(alive)])
            env.clock.advance(1)
            sc.switch(env)
            got = [r["args"]["stage"] for r in env.journal() if r["kind"] == "side_effect_record" and r["id"] == "resume_from_phase"]
            self.assertEqual(got, [stage])

    def test_g40_redelivered_result_is_duplicate_and_unseen_on_ended_lease_is_late(self):
        env = self.env()
        env.bring_to_building(sc.BASIC)
        b = env.builder_for(sc.BASIC)
        res = b.result_envelope(env.instr(sc.BASIC), "pr_opened")
        env.submit(sc.BASIC, "result", copy.deepcopy(res))
        self.assertEqual(env.submit(sc.BASIC, "result", copy.deepcopy(res))["noop"], "envelope_duplicate_delivery")
        late = env.submit(sc.BASIC, "result", b.result_envelope(env.instr(sc.BASIC), "failed_tests"))
        self.assertEqual((late["noop"], late["return_code"]), ("late_envelope_rejected", "R-11"))

    def test_g42_outbox_lease_id_mismatch_is_caught(self):
        env = self.env()
        env.start_task(sc.BASIC)
        sc.crash_after_issue(env, sc.BASIC)
        env.store.tamper(lambda d: d["tasks"][sc.BASIC]["outbox"][0].update(lease_id="OTHER"))
        m = sc.mark(env)
        env.restart()
        js = env.journal()[m:]
        self.assertEqual(sc.tr(js), [("leased", "returned", "state_corrupted")])
        found = [r for r in js if r["kind"] == "transition_record"][0]["cond_evaluated"]
        self.assertTrue(found and found[0]["result"])
        from daemon.core import recovery
        self.assertIsNone(recovery.detect_id(env.core, env.snap(), sc.BASIC))  # returned: not classified again

    def test_g46_rejected_results_change_no_usage(self):
        env = self.env()
        env.bring_to_building(sc.BASIC)
        b = env.builder_for(sc.BASIC)
        old = copy.deepcopy(env.instr(sc.BASIC))
        b.send_result(old, "failed_tests", calls=5, wall_s=5, cost_units=5)
        env.run_builders()
        before = env.snap()["usage_record"]
        env.submit(sc.BASIC, "result", b.result_envelope(old, "failed_tests", calls=9, wall_s=9, cost_units=9))  # late
        self.assertEqual(env.snap()["usage_record"], before)

    def test_g50_owner_stop(self):
        env = self.env()
        env.bring_to_building(sc.OTHER)
        env.event("owner_stop", sc.OTHER, stop_ref="1")
        at = env.task(sc.OTHER)["task_state"]["stop_requested_at"]
        env.clock.advance(5)
        out = env.event("owner_stop", sc.OTHER, stop_ref="2")
        self.assertEqual((out["noop"], env.task(sc.OTHER)["task_state"]["stop_requested_at"]), ("owner_stop_already_requested", at))
        env.clock.advance(int(env.rules.number("hard_stop.grace_s")))
        env.core.tick()
        self.assertEqual((env.state(sc.OTHER), env.task(sc.OTHER)["task_state"]["return_code"]), ("returned", "R-07"))

    def test_g48_invalid_instruction_returns_from_every_issuing_state(self):
        found = {}
        for label, build, _ in sc.PATHS:
            env = self.env()
            task, state0, attempt, _retry = build(env)
            env.ports.catalog.tasks[task]["inputs"] = None
            m = sc.mark(env)
            attempt()
            found[state0] = ([x for x in self.tr(env, m) if x[2] == "envelope_invalid"], len(env.ports.sender.sent))
            if state0 == "building":
                self.assertEqual(env.lease(task)["status"], "returned")
        self.assertEqual(sorted(found), sorted(["queued", "building", "ci_failed", "changes_requested", "handoff", "paused_no_builder"]))
        for state, (rows, _sent) in found.items():
            self.assertEqual(rows, [(state, "returned", "envelope_invalid")], state)

    def test_g49_validator_reads_the_received_value(self):
        from daemon.core.envelope_validator import validate_instruction
        env = self.env()
        env.start_task(sc.BASIC)
        env.grant(sc.BASIC)
        good = copy.deepcopy(env.ports.sender.inboxes["mock-runner-1"][0])
        env.ports.catalog.tasks[sc.BASIC]["decision_gates"]["real_data"] = ["D-X"]
        self.assertEqual(validate_instruction(env.core, sc.BASIC, dict(good, real_data_allowed=True), [])[0], "invalid")
        self.assertEqual(validate_instruction(env.core, sc.BASIC, dict(good, real_data_allowed=False), ["D-X"])[0], "invalid")
        self.assertEqual(validate_instruction(env.core, sc.BASIC, dict(good, real_data_allowed=True), ["D-X"])[0], "valid")
        missing = {k: v for k, v in good.items() if k != "real_data_allowed"}
        self.assertEqual(validate_instruction(env.core, sc.BASIC, missing, ["D-X"]), ("invalid", ["real_data_allowed"]))
        self.assertNotIn("real_data_allowed", missing)

    def test_journal_never_holds_matched_secret_text(self):
        from daemon.core import secret_scan
        rules = Rules(raw_rules())
        value, n = secret_scan.redact(secret_scan.patterns(rules), {"a": ["x", "AKIA" + "Z" * 16]})
        self.assertEqual((value, n), ({"a": ["x", secret_scan.REDACTED]}, 1))


class NewPathsComeFromData(unittest.TestCase):
    """The paths added for G29-G50 and M1-M32 read their fields from the data, too."""

    assertBreaks = BehaviorComesFromData.assertBreaks

    def test_baseline_is_clean(self):
        for fn in (fl.m6, fl.m27, fl.m32):
            self.assertEqual(failing(run_fn(fn, raw_rules())), [])

    def test_restart_resume_check_branch_is_read(self):
        def f(raw):
            raw["handoff_failure_policy"]["restart_resume"]["preserve"]["else"] = {"stage": "preserve"}
        self.assertBreaks(sc.m38, f)

    def test_credential_table_is_read(self):
        def f(raw):
            raw["core_contract"]["expected_outputs"]["credential_of_effect"]["revoke_preserve_credential"] = "builder_token"
        self.assertBreaks(sc.m44, f)

    def test_conflict_relation_is_read(self):
        def f(raw):
            [g for g in raw["lease_guards"] if g["id"] == "no_conflict_lease"][0].pop("conflict_match")
        self.assertBreaks(fl.m13, f)

    def test_validate_instruction_rules_are_read(self):
        def f(raw):
            vi = raw["core_contract"]["operations"]["validate_instruction"]
            vi["rules"] = [r for r in vi["rules"] if r["id"] != "decision_ref_recorded"]
        self.assertBreaks(fl.m32, f)

    def test_guard_on_fail_states_are_read(self):
        def f(raw):
            g = [g for g in raw["lease_guards"] if g["id"] == "instruction_envelope_valid"][0]
            g["on_fail"]["only_in_states"] = [s for s in g["on_fail"]["only_in_states"] if s != "building"]
        self.assertBreaks(sc.m30, f)

    def test_hard_stop_trigger_events_are_read(self):
        def f(raw):
            for trig in raw["core_contract"]["operations"]["hard_stop"]["trigger_events"].values():
                trig["states"] = []
        self.assertBreaks(fl.m27, f)

    def test_owner_stop_noop_rules_are_read(self):
        self.assertBreaks(fl.m27, lambda raw: raw.update(noop_rules=[r for r in raw["noop_rules"] if r["event"] != "owner_stop"]))

    def test_expiry_events_by_state_are_read(self):
        self.assertBreaks(sc.m41, lambda raw: raw["state_integrity"]["normal_expiry"]["events_by_state"].pop("leased"))

    def test_idempotency_key_fields_are_read(self):
        def f(raw):
            raw["core_contract"]["operations"]["accept_envelope"]["idempotency_key_fields"] = ["task_id", "lease_generation", "envelope_kind"]
        self.assertBreaks(sc.m39, f)

    def test_field_value_sets_are_read(self):
        self.assertBreaks(sc.m28, lambda raw: raw["core_contract"]["operations"]["accept_envelope"]["field_value_sets"]["fence_violation_report"].update(kind=["token_mismatch"]))

    def test_corruption_applies_to_is_read(self):
        def f(raw):
            raw["state_integrity"]["corruption"]["applies_to"]["cond"] = [{"field": "task_state.state", "op": "==", "value": "nowhere"}]
        self.assertBreaks(sc.m44, f)

    def test_end_lease_applies_when_is_read(self):
        self.assertBreaks(sc.m41, lambda raw: raw["concurrency"]["lease_end"]["applies_when"][0].update(op="!="))

    def test_secret_scan_states_are_read(self):
        def f(raw):
            for s in raw["preserve_manifest"]["secret_patterns"]["scan"]:
                if s["id"] == "result_envelope":
                    s["states"] = []
        self.assertBreaks(fl.m14, f)

    def test_lock_self_value_is_read(self):
        self.assertBreaks(sc.m41, lambda raw: [g for g in raw["lease_guards"] if g["id"] == "lock_acquired"][0]["check"].update(value=[None]))

    def test_outside_reads_are_read(self):
        self.assertBreaks(fl.m6, lambda raw: raw["audit_triggers"].update(immediate_audit_paths=[]))
        self.assertBreaks(fl.m7, lambda raw: raw["audit_triggers"]["periodic"].update(every=5))
        self.assertBreaks(fl.m19, lambda raw: raw.update(post_merge_states=["done"]))
        self.assertBreaks(fl.m31, lambda raw: raw["record_separation"]["merge_observation_fields"].pop("integration_check"))

    def test_rows_without_cond_follow_the_table(self):
        self.assertBreaks(fl.m4, lambda raw: _transition(raw, "merge_wait", "reviewer_available").update(to="pr_open"))
        self.assertBreaks(fl.m23, lambda raw: _transition(raw, "merged", "impl_counter_incremented", "done").update(to="audit_queued"))

    def test_switch_sources_are_read(self):
        self.assertBreaks(fl.m18, lambda raw: raw["switch_policy"]["allowed_sources"].append("target_site_http"))

    def test_predicate_ops_are_read(self):
        def f(raw):
            raw["core_contract"]["predicate_ops"]["added_by_G49"].pop("subset_of")
        self.assertBreaks(fl.m32, f)


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


if __name__ == "__main__":
    unittest.main()
