"""audit2-spec-check-vacuous: G4c, G7b, G9 and G26 must not pass on an empty scan.

Each of these checks walks a list and passes when no item is bad. Before this change an empty list (no states, no
switch signals, no integration rows because the heading regex stopped matching, no `K1~Kn` mention because the
notation changed) gave zero bad items and therefore PASS. Now each check also asserts that it looked at more than
zero items, and reports how many.

Every mutation works on an in-memory copy or a temporary directory; the design bundle is not written.
"""
import copy
import importlib.util
import io
import json
import os
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
INTEGRATION = ROOT / "docs/blueprint/proposals/설계통합안_검토본.md"
_spec = importlib.util.spec_from_file_location("spec_check", BUNDLE / "검증/spec_check.py")
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

RULES = json.loads((BUNDLE / "daemon_rules.json").read_text(encoding="utf-8"))
TASKS = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))
TARGET = ("G4c", "G7b", "G9", "G26")


def results(D=None, T=None):
    sc.RESULTS.clear()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)  # spec_check's other checks read files without closing them
        sc.run(str(ROOT), copy.deepcopy(TASKS) if T is None else T, copy.deepcopy(RULES) if D is None else D)
    out = {r["check"].split(" ", 1)[0]: r for r in sc.RESULTS}
    sc.RESULTS.clear()
    return out


def rules():
    return copy.deepcopy(RULES)


def tasks():
    return copy.deepcopy(TASKS)


def json_dump_replace(T, old, new):
    return json.loads(json.dumps(T, ensure_ascii=False).replace(old, new))


class Baseline(unittest.TestCase):
    def test_bundle_passes_with_nonzero_counts(self):
        res = results()
        self.assertEqual({k: res[k]["ok"] for k in TARGET}, {k: True for k in TARGET}, {k: res[k]["detail"] for k in TARGET})
        self.assertGreater(res["G7b"]["detail"]["종료 아닌 상태 수"], 0)
        self.assertGreater(res["G7b"]["detail"]["전이 수"], 0)
        self.assertGreater(res["G9"]["detail"]["신호 수"], 0)
        self.assertGreater(res["G9"]["detail"]["판정 규칙 수"], 0)
        self.assertGreater(res["G26"]["detail"]["찾은 표기 수"], 0)
        self.assertGreater(res["G26"]["detail"]["T-box 제약 수"], 0)
        self.assertGreater(len(sc.integration_rows(str(ROOT))), 0)
        self.assertEqual([r for r in res.values() if not r["ok"]], [])


class G4cIntegrationRows(unittest.TestCase):
    def test_no_rows_fails(self):
        with mock.patch.object(sc, "integration_rows", lambda repo: []):
            res = results()
        self.assertFalse(res["G4c"]["ok"])
        self.assertIn("행 0개", res["G4c"]["detail"])

    def test_empty_registry_fails(self):
        T = tasks()
        T["feature_registry"] = []
        self.assertFalse(results(T=T)["G4c"]["ok"])

    def test_empty_document_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / INTEGRATION.relative_to(ROOT)
            dst.parent.mkdir(parents=True)
            dst.write_text("", encoding="utf-8")
            rows = sc.integration_rows(tmp)
        self.assertEqual(rows, [])
        with mock.patch.object(sc, "integration_rows", return_value=rows):
            self.assertFalse(results()["G4c"]["ok"])

    def test_heading_regex_stops_matching(self):
        """'### 2.1' rewritten as '### 2-1': the parser finds no row at all, and G4c must say so."""
        text = INTEGRATION.read_text(encoding="utf-8").replace("\n### 2.", "\n### 2-")
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / INTEGRATION.relative_to(ROOT)
            dst.parent.mkdir(parents=True)
            dst.write_text(text, encoding="utf-8")
            rows = sc.integration_rows(tmp)
        self.assertEqual(rows, [])
        with mock.patch.object(sc, "integration_rows", lambda repo: rows):
            self.assertFalse(results()["G4c"]["ok"])

    def test_unmapped_row_still_fails(self):
        real = sc.integration_rows(str(ROOT))
        with mock.patch.object(sc, "integration_rows", lambda repo: real + ["2.1 없는 기능"]):
            res = results()
        self.assertFalse(res["G4c"]["ok"])
        self.assertIn("2.1 없는 기능", res["G4c"]["detail"])


class G7bStates(unittest.TestCase):
    def test_no_states_fails(self):
        D = rules()
        D["states"] = {}
        res = results(D)
        self.assertFalse(res["G7b"]["ok"])
        self.assertEqual(res["G7b"]["detail"]["종료 아닌 상태 수"], 0)

    def test_states_missing_fails(self):
        D = rules()
        D.pop("states")
        self.assertFalse(results(D)["G7b"]["ok"])

    def test_only_terminal_states_fails(self):
        D = rules()
        D["states"] = {k: v for k, v in D["states"].items() if k in ("done", "cancelled")}
        self.assertFalse(results(D)["G7b"]["ok"])

    def test_no_states_and_no_transitions_fails(self):
        """The old check passed here: nothing to look at means nothing dead."""
        D = rules()
        D["states"], D["transitions"] = {}, []
        self.assertFalse(results(D)["G7b"]["ok"])

    def test_no_transitions_fails_with_live_states(self):
        D = rules()
        D["transitions"] = []
        res = results(D)
        self.assertFalse(res["G7b"]["ok"])
        self.assertGreater(res["G7b"]["detail"]["종료 아닌 상태 수"], 0)
        self.assertEqual(res["G7b"]["detail"]["전이 수"], 0)

    def test_dead_state_still_fails(self):
        D = rules()
        D["transitions"] = [t for t in D["transitions"] if t["from"] != "merge_wait" or t["to"] == "returned"]
        res = results(D)
        self.assertFalse(res["G7b"]["ok"])
        self.assertIn("merge_wait", res["G7b"]["detail"]["나가는 전이 없는 상태"])


class G9SwitchSignals(unittest.TestCase):
    def test_no_signals_fails(self):
        D = rules()
        D["switch_policy"]["allowed_switch_signals"] = []
        res = results(D)
        self.assertFalse(res["G9"]["ok"])
        self.assertEqual(res["G9"]["detail"]["신호 수"], 0)

    def test_no_switch_policy_fails(self):
        D = rules()
        D.pop("switch_policy")
        self.assertFalse(results(D)["G9"]["ok"])

    def test_every_detect_empty_fails(self):
        D = rules()
        for sig in D["switch_policy"]["allowed_switch_signals"]:
            sig["detect"] = []
        res = results(D)
        self.assertFalse(res["G9"]["ok"])
        self.assertEqual(res["G9"]["detail"]["판정 규칙 수"], 0)

    def test_one_signal_without_detect_fails(self):
        D = rules()
        sig = D["switch_policy"]["allowed_switch_signals"][0]
        sig.pop("detect")
        res = results(D)
        self.assertFalse(res["G9"]["ok"])
        self.assertIn(f"{sig['id']}: 판정 규칙(detect) 없음", res["G9"]["detail"]["문제"])

    def test_one_empty_detect_fails_despite_other_valid_signals(self):
        D = rules()
        D["switch_policy"]["allowed_switch_signals"][0]["detect"] = []
        res = results(D)
        self.assertFalse(res["G9"]["ok"])
        self.assertGreater(res["G9"]["detail"]["판정 규칙 수"], 0)

    def test_unstructured_detect_still_fails(self):
        D = rules()
        D["switch_policy"]["allowed_switch_signals"][0]["detect"] = ["HTTP 429"]
        self.assertFalse(results(D)["G9"]["ok"])

    def test_third_party_http_still_fails(self):
        D = rules()
        D["switch_policy"]["allowed_switch_signals"][0]["detect"] = [
            {"source": "provider_http_response", "scope": "third_party", "match": "HTTP 429"}
        ]
        self.assertFalse(results(D)["G9"]["ok"])

    def test_wrong_source_still_fails(self):
        D = rules()
        D["switch_policy"]["allowed_switch_signals"][0]["detect"][0]["source"] = "stderr_text"
        self.assertFalse(results(D)["G9"]["ok"])


class G26ConstraintRange(unittest.TestCase):
    def _read_replacing(self, old, new, only=None):
        orig = sc.read

        def read(name):
            text = orig(name)
            return text.replace(old, new) if only in (None, name) else text
        return mock.patch.object(sc, "read", read)

    def test_no_range_mention_fails(self):
        """Every 'K1~K16' rewritten in words: the regex finds nothing and G26 must not pass."""
        with self._read_replacing("K1~K16", "T-box 제약 전부"):
            res = results(T=json_dump_replace(tasks(), "K1~K16", "T-box 제약 전부"))
        self.assertFalse(res["G26"]["ok"])
        self.assertEqual(res["G26"]["detail"]["찾은 표기 수"], 0)

    def test_stale_range_with_other_dash_fails(self):
        """A stale range written with an en dash used to escape the '~'-only regex."""
        for sep in ("~", "～", "〜", "-", "–", "—", " ~ "):
            with self.subTest(separator=sep):
                with self._read_replacing("K1~K16", f"K1{sep}K15", only="02_구현계약.md"):
                    res = results()
                self.assertFalse(res["G26"]["ok"])
                self.assertIn("02_구현계약.md: K1~K15", res["G26"]["detail"]["다른 표기"])

    def test_matching_ranges_with_supported_separators_pass(self):
        """Replace every scanned range, so another '~' match cannot hide a parser miss."""
        for sep in ("~", "～", "〜", "-", "–", "—", " ~ "):
            with self.subTest(separator=sep):
                with self._read_replacing("K1~K16", f"K1{sep}K16"):
                    res = results(T=json_dump_replace(tasks(), "K1~K16", f"K1{sep}K16"))
                self.assertTrue(res["G26"]["ok"], res["G26"]["detail"])
                self.assertGreater(res["G26"]["detail"]["찾은 표기 수"], 0)

    def test_stale_range_still_fails(self):
        res = results(T=json_dump_replace(tasks(), "K1~K16", "K1~K12"))
        self.assertFalse(res["G26"]["ok"])
        self.assertIn("tasks.json: K1~K12", res["G26"]["detail"]["다른 표기"])

    def test_empty_tbox_fails_instead_of_crashing(self):
        tbox = ROOT / "docs/blueprint/proposals/온톨로지/tbox.json"
        data = json.loads(tbox.read_text(encoding="utf-8"))
        data["constraints"] = []
        real_open = open

        def fake_open(path, *a, **kw):
            if os.path.abspath(path) == str(tbox):
                return io.StringIO(json.dumps(data, ensure_ascii=False))
            return real_open(path, *a, **kw)
        with mock.patch.object(sc, "open", fake_open, create=True):
            res = results()
        self.assertFalse(res["G26"]["ok"])
        self.assertEqual(res["G26"]["detail"]["T-box 제약 수"], 0)


if __name__ == "__main__":
    unittest.main()
