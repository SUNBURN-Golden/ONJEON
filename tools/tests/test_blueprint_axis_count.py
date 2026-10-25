"""Audit 1: prose references omit counts; the generated vocabulary states the live count."""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import vocab_check as vc

BLUEPRINT = ROOT / "docs/BLUEPRINT.md"
PROPOSAL = ROOT / "docs/blueprint/proposals/인계_설계책임/README.md"
GENERATED = ROOT / "docs/blueprint/VOCABULARY.md"

AXIS_COUNT = re.compile(r"(\d+)\s*개의?\s*축")
VOCAB_POINTER = re.compile(r"vocabulary|어휘", re.IGNORECASE)


def vocab():
    return json.loads((ROOT / "packages/schemas/vocabulary.json").read_text(encoding="utf-8"))


def prose_counts(path):
    """Find any hand-written axis counts next to vocabulary references, even current ones."""
    found = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "vocab:allow" in line or not VOCAB_POINTER.search(line):
            continue
        for m in AXIS_COUNT.finditer(line):
            found.append((i, int(m.group(1))))
    return found


class GeneratedDoc(unittest.TestCase):
    """Verify the committed artifact itself, as well as the generator."""

    def setUp(self):
        self.v = vocab()
        self.n = len(self.v["axes"])
        self.doc = GENERATED.read_text(encoding="utf-8")

    def test_committed_doc_states_the_live_axis_count_once(self):
        self.assertEqual(vc._count_lines(self.doc), [self.n])

    def test_committed_doc_is_fresh_for_the_check(self):
        self.assertEqual(self.doc, vc.render(self.v))
        self.assertEqual(vc.generated_doc_problems(self.doc, vc.render(self.v), self.n), [])

    def test_states_no_wrong_axis_count(self):
        wrong = [m.group(1) for m in AXIS_COUNT.finditer(self.doc) if int(m.group(1)) != self.n]
        self.assertEqual(wrong, [])


class DocumentReferences(unittest.TestCase):
    def test_no_document_reports_a_stale_count(self):
        findings = [p for p in vc.lint(vocab()) if " axes, vocabulary.json has " in p]
        self.assertEqual(findings, [])

    def test_blueprint_drops_the_count(self):
        self.assertEqual(prose_counts(BLUEPRINT), [])

    def test_proposal_readme_drops_the_count(self):
        self.assertEqual(prose_counts(PROPOSAL), [])


if __name__ == "__main__":
    unittest.main()
