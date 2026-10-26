"""검토용 공통 완료 기준을 현행 PR 의무로 오인하지 않도록 문서 지위를 대조한다."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"


class PrPolicy(unittest.TestCase):
    def setUp(self):
        self.tasks = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))
        readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
        work_spec = (BUNDLE / "03_작업명세.md").read_text(encoding="utf-8")
        self.assertIn("## 0.1 PR 완료 기준의 적용 상태", readme)
        self.readme_policy = readme.split("## 0.1 PR 완료 기준의 적용 상태", 1)[1].split("## 1.", 1)[0]
        self.spec_policy = work_spec.split("## 2.", 1)[1].split("## 3.", 1)[0]
        self.policies = {
            "tasks.json": self.tasks.get("_common_done_criteria_note", ""),
            "README §0.1": self.readme_policy,
            "03 §2": self.spec_policy,
        }

    def test_json_and_both_documents_explicitly_defer_common_pr_criteria(self):
        self.assertEqual("non_binding_until_adopted",
                         self.tasks.get("_common_done_criteria_status"))
        self.assertIn("채택된 정본이 아니다", self.tasks["_status"])
        self.assertIn("과제 실행·완료 기준으로 채택", self.tasks["_status"])
        for name, policy in self.policies.items():
            with self.subTest(document=name):
                self.assertIn("common_done_criteria", policy)
                self.assertIn("채택 전 모든 PR에 구속력을 갖지 않는다", policy)

    def test_documented_current_policy_links_resolve_to_real_policy_files(self):
        for name, policy in list(self.policies.items())[1:]:
            targets = {(BUNDLE / path).resolve()
                       for path in re.findall(r"\[[^]]+\]\(([^)]+)\)", policy)}
            with self.subTest(document=name):
                for path in (".github/pull_request_template.md", "docs/BLUEPRINT.md"):
                    target = ROOT / path
                    self.assertIn(target, targets)
                    self.assertTrue(target.is_file())

    def test_adoption_instructions_cover_each_missing_field(self):
        for name, policy in self.policies.items():
            with self.subTest(document=name):
                for text in ("채택 시", "과제 ID", "모델 역할·실행 경로", "대상 SHA", "테스트 로그"):
                    self.assertIn(text, policy)

    def test_proposed_traceability_and_test_evidence_requirements_are_retained(self):
        criteria = self.tasks["common_done_criteria"]
        self.assertIn("과제 ID, 작성에 참여한 모델 역할·실행 경로, 대상 SHA를 적었다", criteria)
        self.assertIn("tests의 명령을 실행하고 로그를 첨부했다('시험 추가 예정'은 통과가 아님)", criteria)


class BundleStatus(unittest.TestCase):
    """DEC-BUNDLE-STATUS: 실행·완료 기준 채택과 정본 미채택을 모든 지위 문장이 함께 적는다."""

    EXECUTION = "과제 실행·완료 기준으로 채택"
    CANON = "채택된 정본이 아니다"
    RECORD = ROOT / "docs/decisions/DEC-BUNDLE-STATUS.md"

    def setUp(self):
        readme = (BUNDLE / "README.md").read_text(encoding="utf-8")
        self.status_line = next(line for line in readme.splitlines() if line.startswith("작성 2026-10-12 |"))
        self.readme = readme
        self.handoff = (BUNDLE / "그록봇_인계/README.md").read_text(encoding="utf-8").splitlines()[2]
        self.json_status = {name: json.loads((BUNDLE / name).read_text(encoding="utf-8"))["_status"]
                            for name in ("tasks.json", "daemon_rules.json")}

    def statements(self):
        return {"README 상태": self.status_line, "그록봇 README": self.handoff, **self.json_status}

    def test_record_exists_and_states_both_halves(self):
        record = self.RECORD.read_text(encoding="utf-8")
        for phrase in ("Execution and completion basis: adopted", "Canon: not adopted",
                       "D-21", "09_제품목적_대응표", "2026-10-13", "NOT personally decide"):
            self.assertIn(phrase, record)

    def test_every_status_statement_carries_both_halves_and_the_record(self):
        for name, text in self.statements().items():
            with self.subTest(document=name):
                self.assertIn(self.EXECUTION, text)
                self.assertIn(self.CANON, text)
                self.assertIn("D-21", text)
                self.assertIn("DEC-BUNDLE-STATUS", text)

    def test_markdown_links_to_the_record_resolve(self):
        for name, base, text in (("README 상태", BUNDLE, self.status_line),
                                 ("그록봇 README", BUNDLE / "그록봇_인계", self.handoff)):
            with self.subTest(document=name):
                targets = {(base / path).resolve() for path in re.findall(r"\]\(([^)]+)\)", text)}
                self.assertIn(self.RECORD, targets)

    def test_completion_criterion_is_09_in_bundle_handoff_and_blueprint(self):
        self.assertIn("09가 최상위 완료 기준", self.status_line)
        self.assertIn("09가 최상위 완료 기준", self.handoff)
        blueprint = (ROOT / "docs/BLUEPRINT.md").read_text(encoding="utf-8")
        self.assertIn("첫 출시 완료는 [09_제품목적_대응표]", blueprint)

    def test_superseded_wording_is_gone(self):
        for stale in ("수정 완료 판정은 독립 재검토 뒤", "채택 전 검토용 초안",
                      "자동 개발 가동은 그 검토 뒤"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, self.readme)
        for name, text in self.json_status.items():
            with self.subTest(document=name):
                self.assertNotIn("초안", text)


class SerialDaemonPrerequisite(unittest.TestCase):
    """audit1-serial-daemon-prerequisite: 남은 데몬 후속 과제가 제품 과제의 선행·관문이 되지 않는다."""

    DAEMON = {"T-OP-00", "T-OP-09"}
    S0 = ("T-CT-01", "T-OP-01", "T-TW-02")
    FINAL_AUDIT = "T-OP-08"
    RECORD = ROOT / "docs/decisions/audit1-serial-daemon-prerequisite.md"

    def setUp(self):
        tasks = json.loads((BUNDLE / "tasks.json").read_text(encoding="utf-8"))["tasks"]
        self.tasks = {task["id"]: task for task in tasks}
        self.handoff_dir = BUNDLE / "그록봇_인계"
        readme = (self.handoff_dir / "README.md").read_text(encoding="utf-8")
        self.stages = readme.split("## 3. ", 1)[1].split("## 4. ", 1)[0]
        self.note = self.stages.split("[상태 기록 2026-10-26]", 1)[1]
        self.first_tasks = readme.split("## 4. ", 1)[1].split("## 5. ", 1)[0]

    def test_s0_tasks_have_no_prerequisites_and_empty_start_gates(self):
        for task_id in self.S0:
            with self.subTest(task=task_id):
                task = self.tasks[task_id]
                self.assertEqual([], task["prereq_tasks"])
                self.assertEqual([], task["decision_gates"]["start"])

    def test_only_the_final_audit_depends_on_daemon_tasks(self):
        dependants = {task_id for task_id, task in self.tasks.items()
                      if task_id not in self.DAEMON and self.DAEMON & set(task["prereq_tasks"])}
        self.assertEqual({self.FINAL_AUDIT}, dependants)

    def test_final_audit_dependency_is_release_reporting_only(self):
        audit = self.tasks[self.FINAL_AUDIT]
        self.assertIs(True, audit["final_gate"])
        self.assertTrue(any("자동 개발 운영 기록" in item and "축 5" in item
                            for item in audit["done_criteria"]))
        self.assertFalse([task_id for task_id, task in self.tasks.items()
                          if self.FINAL_AUDIT in task["prereq_tasks"]])

    def test_handover_note_supersedes_the_serial_restriction(self):
        self.assertIn("제품 과제(T-CT-01 등)는 임대하지 않는다", self.stages)
        for phrase in ("직렬 제한 해제", "그 제한을 대체한다", "제품 과제를 막지 않는다",
                       "병행한다", "T-OP-08", "SerialDaemonPrerequisite"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.note)
        self.assertIn("[상태 기록 2026-10-26]", self.first_tasks)
        self.assertIn("남은 데몬 후속 과제는 이 표의 과제를 막지 않는다", self.first_tasks)

    def test_handover_note_records_as_run_order_and_open_daemon_evidence(self):
        order = [self.note.index(pr) for pr in ("#21", "#98", "#105", "#101", "#102")]
        self.assertEqual(sorted(order), order)
        for phrase in ("PASS 17", "PARTIAL 5", "FAIL 0", "R6", "R7", "R9", "R11", "R21",
                       "G51~G57", "G47", "남은 데몬 후속 과제", "05 §7", "미확인"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.note)
        results = (ROOT / "docs/vm_check/2026-10-16/RESULTS.md").read_text(encoding="utf-8")
        self.assertIn("PASS 17, FAIL 0, PARTIAL 5", results)
        for scenario in ("R6", "R7", "R9", "R11", "R21"):
            with self.subTest(scenario=scenario):
                self.assertRegex(results, rf"\| {scenario} \|[^\n]*\*\*PARTIAL\*\*")

    def test_note_links_resolve_to_the_decision_and_results(self):
        targets = {(self.handoff_dir / path).resolve()
                   for path in re.findall(r"\]\(([^)]+)\)", self.note)}
        self.assertIn(self.RECORD, targets)
        self.assertIn(ROOT / "docs/vm_check/2026-10-16/RESULTS.md", targets)
        record = self.RECORD.read_text(encoding="utf-8")
        self.assertIn("except the final pre-release audit T-OP-08", record)
        self.assertIn("other than T-OP-08", record)


if __name__ == "__main__":
    unittest.main()


class IndependentReviewPath(unittest.TestCase):
    """audit1-independent-review-path: 독립 리뷰 경로 근거가 실행 기록·결정 기록·인계 §6에서 같다."""

    EVIDENCE = ROOT / "tools/tests/evidence/audit1_independent_review_path/review_records.log"
    RECORD = ROOT / "docs/decisions/audit1-independent-review-path.md"
    # PR → (BLOCK한 head, PASS한 head, 병합 커밋). PASS head는 병합 커밋의 두 번째 부모다
    REVIEWED = {"208": ("92a339ec194d00f8b3101dab9593a81d80ad77b0",
                        "cab3d1977859509c70d84ebeafb1a84dcc6f0203", "3c76cc1"),
                "210": ("970331ac7fb36eee44cef412ee6f88890301f1ff",
                        "cfa8699d3dae894e1c46a331feda86d5f0081034", "52acae6")}
    NOT_OUT_OF_FAMILY = ("T-OP-01_review_r0_devin_devin_opus1", "T-OP-01_review_r0_glm_glm_glm_opus")

    def setUp(self):
        self.evidence = self.EVIDENCE.read_text(encoding="utf-8")
        self.record = self.RECORD.read_text(encoding="utf-8")
        readme = (BUNDLE / "그록봇_인계/README.md").read_text(encoding="utf-8")
        self.section = readme.split("## 6. ", 1)[1].split("## 7. ", 1)[0]
        self.assertIn("[상태 기록 2026-10-26]", self.section)
        self.note = self.section.split("[상태 기록 2026-10-26]", 1)[1]

    def reviews(self):
        """(pr, head, verdict) of every OpenAI-family review block in the evidence."""
        out = []
        for block in self.evidence.split("\n### ")[1:]:
            if "provider: openai" in block:
                self.assertIn("OpenAI Codex", block)
                self.assertIn("sandbox: read-only", block)
                m = re.search(r"pr=#(\d+) head=([0-9a-f]{40}) verdict=(PASS|BLOCK)", block)
                self.assertIsNotNone(m, block[:120])
                out.append(m.groups())
        return out

    def test_evidence_has_out_of_family_reviews_pinned_to_merged_heads(self):
        reviews = self.reviews()
        for pr, (blocked, passed, merge) in self.REVIEWED.items():
            with self.subTest(pr=pr):
                self.assertIn((pr, blocked, "BLOCK"), reviews)
                self.assertIn((pr, passed, "PASS"), reviews)
                merge_line = next(l for l in self.evidence.splitlines()
                                  if l.startswith(merge) and f"Merge pull request #{pr} " in l)
                self.assertEqual(passed, merge_line.split()[2], "PASS head must be the merged PR head")

    def test_authors_are_outside_the_reviewer_family(self):
        authors = self.evidence.split("## 5. ", 1)[1]
        self.assertTrue(authors.strip())
        for line in authors.strip().splitlines()[1:]:
            with self.subTest(run=line):
                self.assertIn("claude", line)
                self.assertNotIn("codex", line)

    def test_claude_runs_under_other_names_are_not_cited_as_independent(self):
        rejected = self.evidence.split("## 3. ", 1)[1].split("## 4. ", 1)[0]
        for name in self.NOT_OUT_OF_FAMILY:
            with self.subTest(run=name):
                block = rejected.split(name, 1)[1].split("###", 1)[0]
                self.assertIn("claude-sonnet-5-5", block)
                self.assertIn("claude-sonnet-5-5", self.record)
                self.assertNotIn(name, self.record.split("This corrects", 1)[0])
        self.assertIn("unrecognized_model", rejected)

    def test_record_and_handover_agree(self):
        for pr, (blocked, passed, merge) in self.REVIEWED.items():
            with self.subTest(pr=pr):
                for sha in (blocked, passed, merge):
                    self.assertIn(sha, self.record)
                    self.assertIn(sha[:7], self.note)
                self.assertIn(f"#{pr}", self.note)
        for phrase in ("첫 독립 리뷰 경로 운영 확인", "OpenAI Codex", "gpt-6-astra", "대체한다",
                       "IndependentReviewPath", "R6·R7", "해소된 것으로 적지 않는다"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.note)
        self.assertIn("지금까지는 작성 계열 밖의 리뷰가 없었다", self.section)  # 원문은 고치지 않는다
        self.assertIn("첫 독립 리뷰 경로 운영 확인", self.record)
        self.assertIn(str(self.EVIDENCE.relative_to(ROOT)), self.record)
        self.assertIn(str(self.EVIDENCE.relative_to(ROOT)), self.note)
