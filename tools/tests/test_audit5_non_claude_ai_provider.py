"""Audit 5: DEC-D-02 left the procurement target open — which non-Claude model
family, keys and spend.

Finding: DEC-D-02 fixed the composition principles (author=claude, approver=X,
red team=Y, floor of 2 families) and the policy owner, but deliberately did not
pin a vendor or model ID, so access procurement had no target and never
started. The finding also claimed D-02 blocks the only independent merge-review
path, which audit1-independent-review-path already corrected.

The decision record (docs/decisions/audit5-non-claude-ai-provider.md) resolves
this as a delegated, reversible baseline: X=OpenAI gpt (gpt-6-astra first
candidate, the only non-claude family with operational identification evidence
in this repo), Y=grok conditional on the same 05 §2 API-path verification,
keys user-issued and execution-environment-only, no spend authorized, and D-02
registration in decisions_recorded only after the access-verification record
exists. This test pins both halves so a later edit cannot silently reopen the
finding:

1. The record keeps the delegated/no-spend/no-key boundaries, the
   registration-after-evidence choice and the merge-path premise correction.
2. The cited evidence actually backs the family choice (sha256-pinned Codex
   BLOCK/PASS records whose PASS heads equal the merge commits' second
   parents; grok's single run; the mislabelled devin/glm records excluded),
   the tasks.json/daemon gates match the registration choice, and the 05 §2/§4
   access-evidence and secrets rules still govern.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
RECORD = ROOT / "docs/decisions/audit5-non-claude-ai-provider.md"
DEC_D02 = ROOT / "docs/decisions/DEC-D-02.md"
AUDIT1 = ROOT / "docs/decisions/audit1-independent-review-path.md"
AUDIT2 = ROOT / "docs/decisions/audit2-v1-gate-closure.md"
LOG = ROOT / "tools/tests/evidence/audit1_independent_review_path/review_records.log"
VM_PREP = BUNDLE / "05_VM실행준비.md"
CONTRACT = BUNDLE / "02_구현계약.md"
ROLES = ROOT / "docs/blueprint/proposals/자동개발_설정안/roles.draft.json"
GATEWAY = ROOT / "services/ai-gateway"

START_COND = {"field": "task.decision_gates.start", "op": "subset_of",
              "value": "task_state.decisions_recorded"}
REAL_DATA_COND = {"field": "task.decision_gates.real_data", "op": "subset_of",
                  "value": "task_state.decisions_recorded"}


def read(path):
    return path.read_text(encoding="utf-8")


def log_section(text, number):
    for part in re.split(r"(?m)^## ", text)[1:]:
        if part.startswith(f"{number}. "):
            return part
    raise AssertionError(f"review_records.log has no section {number}")


def log_records(section):
    return re.split(r"(?m)^### ", section)[1:]


class RecordPinsTheDelegatedBaseline(unittest.TestCase):
    def setUp(self):
        self.record = read(RECORD)

    def test_record_names_the_evidence_backed_candidates(self):
        for phrase in ("Approver family X = OpenAI (gpt family)",
                       "first candidate gpt-6-astra",
                       "Red-team family Y = xAI grok (Grok 4.7)",
                       "degraded (3-family shortfall) recorded in ReviewDecision",
                       "GLM stays excluded",
                       "swe/Devin stays excluded until its model API is verified",
                       "records labeled devin/glm that actually ran claude-sonnet-5-5"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_authorizes_no_keys_and_no_spend(self):
        for phrase in ("the user issues dedicated provider keys",
                       "this decision issues, stores, or transmits none",
                       "Keys live only as execution-environment secrets",
                       "Spend: none authorized",
                       "provider-side monthly cap on the account",
                       "separate from U-05's no-cap auto-dev policy",
                       "this record authorizes no spend, account, contract, or key issuance"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_keeps_model_ids_out_of_canon_until_api_evidence(self):
        for phrase in ("pinned in review_policy.json (T-KN-06)",
                       "not in the dev role table and not in canon before that evidence",
                       "NOT through the Codex CLI dev-review path",
                       "CLI access does not prove API access",
                       "model_matches_role=true",
                       "vm_check/<date>/summary.json"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_registers_d02_only_after_access_evidence(self):
        for phrase in ("register D-02 in decisions_recorded only AFTER the access-verification record exists",
                       "no tasks.json gate split needed",
                       "the supervisor does not dispatch T-OP-03 before access record + registration + cap confirmation"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_corrects_the_merge_path_premise(self):
        for phrase in ("the independent merge-review path is NOT blocked by D-02",
                       "the merge gate is unchanged",
                       "dev review, separate from knowledge review",
                       "dev PR reviews are not a substitute"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_invents_no_threshold_numbers(self):
        for phrase in ("No threshold numbers are invented",
                       "T-OP-03 measures throughput/cost/latency",
                       "disagreement=hold"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_unblocks_mock_work_and_orders_the_rest(self):
        for phrase in ("T-KN-06 mock implementation/tests now (already unblocked)",
                       "S1 layer (a) and all mock/test paths proceed without D-02",
                       "user confirmation still pending",
                       "reversible"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.record)

    def test_record_links_resolve(self):
        for link in re.findall(r"\]\(([^)]+)\)", self.record):
            if "://" in link or link.startswith("#"):
                continue
            with self.subTest(link=link):
                target = (RECORD.parent / link.split("#", 1)[0]).resolve()
                self.assertTrue(target.is_relative_to(ROOT))
                self.assertTrue(target.is_file(), f"missing target: {link}")


class EvidenceBacksTheFamilyChoice(unittest.TestCase):
    def setUp(self):
        self.log = read(LOG)

    def codex_records(self):
        records = []
        for block in log_records(log_section(self.log, 1)):
            sha = re.search(r"sha256=([0-9a-f]{64})", block)
            verdict = re.search(r"pr=#(\d+) head=([0-9a-f]{40}) verdict=(BLOCK|PASS)", block)
            self.assertIsNotNone(sha, "every record keeps its source sha256")
            self.assertIsNotNone(verdict, "every record pins pr/head/verdict")
            self.assertIn("model: gpt-6-astra", block)
            self.assertIn("provider: openai", block)
            records.append((int(verdict.group(1)), verdict.group(2), verdict.group(3)))
        return records

    def test_openai_is_the_only_operational_non_claude_identification(self):
        self.assertEqual({(208, "BLOCK"), (208, "PASS"), (210, "BLOCK"), (210, "PASS")},
                         {(pr, verdict) for pr, _, verdict in self.codex_records()})

    def test_pass_heads_equal_the_merge_commits_second_parents(self):
        merges = {int(pr): (p1, p2) for _, p1, p2, pr in re.findall(
            r"(?m)^([0-9a-f]{40}) ([0-9a-f]{40}) ([0-9a-f]{40}) Merge pull request #(\d+)",
            log_section(self.log, 4))}
        passes = [(pr, head) for pr, head, verdict in self.codex_records()
                  if verdict == "PASS"]
        self.assertEqual({208, 210}, {pr for pr, _ in passes})
        for pr, head in passes:
            with self.subTest(pr=pr):
                self.assertIn(pr, merges)
                self.assertEqual(head, merges[pr][1])

    def test_grok_is_one_run_not_a_standing_path(self):
        records = log_records(log_section(self.log, 2))
        self.assertEqual(1, len(records))
        for phrase in ("Grok 4.7", "verdict=BLOCK", "DEC-D-02"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, records[0])

    def test_mislabelled_and_failed_runs_are_excluded(self):
        section = log_section(self.log, 3)
        self.assertEqual(2, section.count("modelUsage=['claude-sonnet-5-5']"))
        self.assertEqual(2, section.count("unrecognized_model"))
        self.assertIn("glm-5.3", section)

    def test_audit1_record_keeps_the_merge_gate_and_the_operating_path(self):
        audit1 = read(AUDIT1)
        for phrase in ("Keep the merge gate as it is",
                       "gpt-6-astra",
                       "one run, not a standing path",
                       "not out-of-family reviews"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, audit1)


class GatesMatchTheRegistrationChoice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = {t["id"]: t for t in json.loads(read(BUNDLE / "tasks.json"))["tasks"]}
        cls.rules = json.loads(read(BUNDLE / "daemon_rules.json"))

    def test_d02_gates_are_exactly_where_the_record_says(self):
        self.assertEqual(["D-02"], self.tasks["T-OP-03"]["decision_gates"]["start"])
        self.assertEqual([], self.tasks["T-OP-03"]["decision_gates"]["real_data"])
        self.assertEqual([], self.tasks["T-KN-06"]["decision_gates"]["start"])
        self.assertEqual(["D-02"], self.tasks["T-KN-06"]["decision_gates"]["real_data"])
        self.assertIn("D-02", self.tasks["T-OP-02"]["decision_gates"]["real_data"])
        self.assertEqual([], self.tasks["T-KN-05"]["decision_gates"]["start"])

    def test_unblock_order_prerequisites_are_intact(self):
        self.assertEqual(["T-KN-05"], self.tasks["T-KN-06"]["prereq_tasks"])
        self.assertEqual(["T-KN-06"], self.tasks["T-OP-03"]["prereq_tasks"])

    def test_start_gate_is_a_structured_cond_not_prose(self):
        transitions = [t for t in self.rules["transitions"]
                       if t.get("from") == "blocked" and t.get("to") == "queued"
                       and t.get("event") == "prereqs_satisfied"]
        self.assertEqual(1, len(transitions))
        self.assertIn(START_COND, transitions[0]["cond"])

    def test_real_data_allowed_is_derived_from_decisions_recorded(self):
        derive = self.rules["core_contract"]["operations"]["validate_instruction"]["derive"]
        self.assertIn(REAL_DATA_COND, [entry["pred"] for entry in derive])

    def test_s1_gate_splits_mock_layer_from_real_data_layer(self):
        criteria = self.tasks["T-OP-02"]["done_criteria"]
        split = next(item for item in criteria if "관문 기록을 두 층으로 나눈다" in item)
        for phrase in ("(a) 코드 경로 관통", "environment=test", "D-02 없이 가능",
                       "(b) 실제 데이터 관문 통과", "실제 제공자 ReviewDecision(D-02)",
                       "(b) 없이 S1 관문을 통과로 적지 않는다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, split)


class AccessEvidenceAndSecretsRulesGovern(unittest.TestCase):
    def test_05_section2_defines_the_access_verification_record(self):
        prep = read(VM_PREP)
        for phrase in ("vm_check/<날짜>/summary.json",
                       "model_matches_role",
                       "min_call{ok, latency_ms, cost_units}",
                       "checked_at",
                       "host_hash",
                       "`model_matches_role=false`면 가동에서 제외한다(운영 규칙 8)",
                       "자기 보고(\"나는 X 모델입니다\")는 증거가 아니다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prep)

    def test_05_section4_keeps_keys_out_of_daemon_and_builders(self):
        prep = read(VM_PREP)
        for phrase in ("데몬은 R2 토큰·DB 자격 증명·AI 검수 제공자 키를 갖지 않는다",
                       "시작 시 금지 변수 검사",
                       "키 필드 없음(스키마로 금지)",
                       "역할 이름과 설정 해시만"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, prep)

    def test_dec_d02_still_reserves_vendor_keys_and_spend_to_the_user(self):
        d02 = read(DEC_D02)
        for phrase in ("업체·모델 ID는 이 결정에서 고정하지 않는다",
                       "지출·계약·계정 개설·키 발급을 하지도 승인하지도 않는다",
                       "정책 소유자는 사용자 본인 1인",
                       "제공자 측 월 한도",
                       "실행 환경 비밀값으로만",
                       "3계열 미달(degraded)",
                       "어느 쪽을 쓸지와 등록은 그록봇 몫이다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, d02)

    def test_gateway_confines_sdks_and_keeps_degraded_caps(self):
        self.assertTrue((GATEWAY / "tests/provider_sdk_only_here.rs").is_file())
        readme = read(GATEWAY / "README.md")
        for phrase in ("ONJ-AP-L-020", "degraded = true",
                       "review_policy.json", "Operating rule 7",
                       "provider_sdk_only_here"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)

    def test_call_records_carry_family_label_and_hash_not_raw_model_ids(self):
        row = next(line for line in read(CONTRACT).splitlines()
                   if line.startswith("| C-19 |"))
        for phrase in ("provider_family_label", "model_ref_hash",
                       "사용자 문서 본문 저장 금지"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, row)

    def test_dev_roles_are_separate_from_review_composition(self):
        self.assertIn("운영 규칙 7", read(ROLES))
        self.assertIn("코드 리뷰와 보험 지식(약관) 검수는 별도다", read(ROLES))

    def test_v1_closure_forbids_substituting_dev_review_for_knowledge_review(self):
        closure = read(AUDIT2)
        for phrase in ("개발 PR 리뷰를 지식 검수로 대체하지 않는다",
                       "ReviewDecision을 대상 해시·실제 모델 계열·프롬프트 판·실행 로그·environment에 연결"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, closure)


if __name__ == "__main__":
    unittest.main()
