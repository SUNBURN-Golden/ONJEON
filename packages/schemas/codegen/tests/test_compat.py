"""Compatibility check: diff rules, version rule, and the real check_compat.sh against a throwaway git repo.

  python3 -I -m unittest discover -s packages/schemas/codegen/tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
REPO_LOCK = HERE.parents[3] / "Cargo.lock"

import compat  # noqa: E402
import schema_model as sm  # noqa: E402
from test_schemas import copy_schemas, edit  # noqa: E402


def models(mutate_json=None, mutate_vocab=None):
    """(prev, new) models where `new` is the current schemas after the mutation."""
    prev = compat.model_of(sm.SCHEMAS_DIR)
    with tempfile.TemporaryDirectory() as t:
        d = copy_schemas(Path(t))
        if mutate_vocab:
            edit(d / "vocabulary.json", mutate_vocab)
            (d / "json" / sm.VOCAB_FILE).write_text(
                json.dumps(sm.vocabulary_schema(sm.load_vocab(d / "vocabulary.json")), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        if mutate_json:
            mutate_json(d / "json")
        return prev, compat.model_of(d)


def mutated_copy(root, mutate_vocab):
    """A copy of the current schemas under `root` with the vocabulary mutated and its schema regenerated."""
    d = copy_schemas(Path(root))
    edit(d / "vocabulary.json", mutate_vocab)
    (d / "json" / sm.VOCAB_FILE).write_text(
        json.dumps(sm.vocabulary_schema(sm.load_vocab(d / "vocabulary.json")), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    return d


def insert_first(axis_id, code):
    """Vocabulary mutator: a new value at the FRONT of an axis (the position minimal_value used to pick blindly)."""
    def go(v):
        axis = next(a for a in v["axes"] if a["id"] == axis_id)
        axis["values"].insert(0, {"code": code, "concept_ko": "x", "screen_ko": "x", "deprecated_aliases": []})
    return go


def remove_value(axis_id, code):
    def go(v):
        axis = next(a for a in v["axes"] if a["id"] == axis_id)
        axis["values"] = [x for x in axis["values"] if x["code"] != code]
    return go


def prop(file, type_name=None):
    """Return a mutator editing properties of `type_name` (a $defs entry, or the root when None)."""
    def wrap(fn):
        def run(jd):
            def go(doc):
                target = doc if type_name is None else doc["$defs"][type_name]
                fn(target)
            edit(jd / file, go)
        return run
    return wrap


class Diff(unittest.TestCase):
    def test_identical_schemas_have_no_changes(self):
        self.assertEqual(compat.diff(*models()), ([], []))

    def test_field_deletion_is_breaking(self):
        def drop(t):
            del t["properties"]["created_by_run"]
            t["required"].remove("created_by_run")
        breaking, compatible = compat.diff(*models(prop("assertion.schema.json")(drop)))
        self.assertEqual(breaking, ["field removed: Assertion.created_by_run"])
        self.assertEqual(compatible, [])

    def test_deleting_an_optional_field_is_breaking_too(self):
        breaking, _ = compat.diff(*models(prop("assertion.schema.json")(lambda t: t["properties"].pop("supersedes"))))
        self.assertEqual(breaking, ["field removed: Assertion.supersedes"])

    def test_nested_definition_field_deletion_is_breaking(self):
        breaking, _ = compat.diff(*models(prop("plan_view.schema.json", "Budget")(lambda t: (t["properties"].pop("step_man"), t["required"].remove("step_man")))))
        self.assertEqual(breaking, ["field removed: Budget.step_man"])

    def test_optional_field_addition_is_compatible(self):
        breaking, compatible = compat.diff(*models(prop("assertion.schema.json")(lambda t: t["properties"].update(note={"type": "string"}))))
        self.assertEqual(breaking, [])
        self.assertEqual(compatible, ["optional field added: Assertion.note"])

    def test_required_field_addition_is_breaking(self):
        def add(t):
            t["properties"]["note"] = {"type": "string"}
            t["required"].append("note")
        breaking, _ = compat.diff(*models(prop("assertion.schema.json")(add)))
        self.assertEqual(breaking, ["required field added: Assertion.note"])

    def test_making_a_field_required_or_optional_is_breaking(self):
        breaking, _ = compat.diff(*models(prop("assertion.schema.json")(lambda t: t["required"].append("supersedes"))))
        self.assertEqual(breaking, ["field became required: Assertion.supersedes"])
        breaking, _ = compat.diff(*models(prop("assertion.schema.json")(lambda t: t["required"].remove("scope"))))
        self.assertEqual(breaking, ["field no longer required: Assertion.scope"])

    def test_type_pattern_and_nullability_changes_are_breaking(self):
        breaking, _ = compat.diff(*models(prop("assertion.schema.json")(lambda t: t["properties"]["correction_reason"].update(type="integer"))))
        self.assertTrue(breaking[0].startswith("field type changed: Assertion.correction_reason"))
        breaking, _ = compat.diff(*models(prop("error_response.schema.json")(lambda t: t["properties"]["code"].update(pattern="^ONJ-.*$"))))
        self.assertTrue(breaking[0].startswith("field type changed: ErrorResponse.code"))
        breaking, _ = compat.diff(*models(prop("evaluation_result.schema.json")(lambda t: t["properties"]["release_id"].update(type="string"))))
        self.assertTrue(breaking[0].startswith("field type changed: EvaluationResult.release_id"))

    def test_type_removal_and_addition(self):
        def remove(jd):
            def go(doc):
                del doc["$defs"]["PriceCaption"]
                del doc["properties"]["price_caption"]
                doc["required"].remove("price_caption")
            edit(jd / "plan_view.schema.json", go)
        breaking, _ = compat.diff(*models(remove))
        self.assertIn("type removed: PriceCaption", breaking)
        self.assertIn("field removed: PlanView.price_caption", breaking)

        def add(jd):
            edit(jd / "plan_view.schema.json", lambda doc: doc["$defs"].__setitem__(
                "Banner", {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"], "additionalProperties": False}))
        breaking, compatible = compat.diff(*models(add))
        self.assertEqual((breaking, compatible), ([], ["type added: Banner"]))

    def test_enum_value_removal_is_breaking_and_addition_is_compatible(self):
        def drop(v):
            axis = next(a for a in v["axes"] if a["id"] == "plan_action")
            axis["values"] = [x for x in axis["values"] if x["code"] != "modify"]
        breaking, compatible = compat.diff(*models(mutate_vocab=drop))
        self.assertEqual(breaking, ["enum value removed: plan_action.modify"])

        def add(v):
            axis = next(a for a in v["axes"] if a["id"] == "plan_action")
            axis["values"].append({"code": "swap", "concept_ko": "x", "screen_ko": "x", "deprecated_aliases": []})
        breaking, compatible = compat.diff(*models(mutate_vocab=add))
        self.assertEqual(breaking, [])
        self.assertEqual(compatible, ["enum value added: plan_action.swap"])

    def test_enum_axis_removal_is_breaking(self):
        def drop(v):
            v["axes"] = [a for a in v["axes"] if a["id"] != "sale_status"]
        breaking, _ = compat.diff(*models(mutate_vocab=drop))
        self.assertEqual(breaking, ["vocabulary axis removed: sale_status"])


class Versions(unittest.TestCase):
    def test_version_rule(self):
        ok = compat.required_bump_ok
        self.assertIsNone(ok("0.1.0", "0.1.0", False, False))
        self.assertIn("still", ok("0.1.0", "0.1.0", False, True))
        self.assertIsNone(ok("0.1.0", "0.1.1", False, True))
        self.assertIsNone(ok("0.1.0", "0.2.0", True, True))
        self.assertIn("breaking", ok("0.1.0", "0.1.5", True, True))
        self.assertIn("breaking", ok("1.2.0", "1.3.0", True, True))
        self.assertIsNone(ok("1.2.0", "2.0.0", True, True))
        self.assertIn("backwards", ok("1.2.0", "1.1.0", False, False))


class Probe(unittest.TestCase):
    def test_each_probe_directory_gets_its_own_crate_name(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / "a", Path(t) / "b"
            compat.write_probe(a, sm.SCHEMAS_DIR, sm.SCHEMAS_DIR)
            compat.write_probe(b, sm.SCHEMAS_DIR, sm.SCHEMAS_DIR, lock=REPO_LOCK)
            names = {d: compat.probe_crate_name(d) for d in (a, b)}
            self.assertNotEqual(names[a], names[b])
            for d, name in names.items():
                self.assertRegex(name, r"^compat_probe_[0-9a-f]{12}$")
                self.assertIn(f'name = "{name}"', (d / "Cargo.toml").read_text(encoding="utf-8"))
            self.assertFalse((a / "Cargo.lock").exists())
            self.assertEqual((b / "Cargo.lock").read_text(encoding="utf-8"), REPO_LOCK.read_text(encoding="utf-8"))
            self.assertEqual(compat.probe_crate_name(a), names[a])  # stable for the same directory

    def test_probe_fills_every_root_document_and_only_known_previous_types(self):
        with tempfile.TemporaryDirectory() as t:
            names = compat.write_probe(Path(t), sm.SCHEMAS_DIR, sm.SCHEMAS_DIR)
            roots = {s.name for s in sm.build_model().structs.values() if s.root}
            self.assertEqual(set(names), roots)
            doc = json.loads((Path(t) / "docs" / "EvaluationResult.json").read_text(encoding="utf-8"))
            self.assertIn("contract_effect", doc)  # optional fields are filled so the old client reads them too

    def test_probe_documents_use_enum_values_the_previous_client_knows(self):
        """A new enum value inserted FIRST is a compatible change; the probe must not feed it to the old client."""
        with tempfile.TemporaryDirectory() as t:
            new_dir = mutated_copy(Path(t) / "new", insert_first("criticality", "zz_new_first"))
            prev, new = compat.model_of(sm.SCHEMAS_DIR), compat.model_of(new_dir)
            self.assertEqual(compat.diff(prev, new), ([], ["enum value added: criticality.zz_new_first"]))
            self.assertEqual([v["code"] for v in new.axes["criticality"].values][0], "zz_new_first")
            self.assertEqual(compat.enum_sample(new, prev, "criticality"), "c0")
            out = Path(t) / "probe"
            compat.write_probe(out, sm.SCHEMAS_DIR, new_dir)
            doc = json.loads((out / "docs" / "Assertion.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["criticality"], "c0")
            self.assertNotIn("zz_new_first", (out / "docs" / "Assertion.json").read_text(encoding="utf-8"))
            # the previous client's types do not know the new value at all
            self.assertNotIn("ZzNewFirst", (out / "src" / "vocabulary.rs").read_text(encoding="utf-8"))

    def test_enum_sample_fallbacks(self):
        model = compat.model_of(sm.SCHEMAS_DIR)
        first = model.axes["criticality"].values[0]["code"]
        self.assertEqual(compat.enum_sample(model, None, "criticality"), first)  # no previous model
        with tempfile.TemporaryDirectory() as t:
            # an axis the previous version did not have: first new code
            def add_axis(v):
                v["axes"].append({"id": "zz_axis", "name_ko": "x", "applies_to": "x", "layer": "x", "concept_ko": "x",
                                  "values": [{"code": "only", "concept_ko": "x", "screen_ko": "x", "deprecated_aliases": []}]})
            new = compat.model_of(mutated_copy(Path(t) / "a", add_axis))
            self.assertEqual(compat.enum_sample(new, model, "zz_axis"), "only")
            # every previous value removed (breaking, reported by diff): still a well-formed value
            def replace_all(v):
                axis = next(a for a in v["axes"] if a["id"] == "criticality")
                axis["values"] = [{"code": "zz_only", "concept_ko": "x", "screen_ko": "x", "deprecated_aliases": []}]
            new = compat.model_of(mutated_copy(Path(t) / "b", replace_all))
            self.assertEqual(compat.enum_sample(new, model, "criticality"), "zz_only")
            self.assertTrue(any(b.startswith("enum value removed: criticality.") for b in compat.diff(model, new)[0]))


class CheckCompatScript(unittest.TestCase):
    """Runs the shipped script in a throwaway repo with a real tag, so tag lookup and `git archive` are exercised."""

    @classmethod
    def setUpClass(cls):
        cls.target = tempfile.mkdtemp()
        cls.env = {**os.environ, "CARGO_TARGET_DIR": os.environ.get("CARGO_TARGET_DIR", str(sm.SCHEMAS_DIR.parent.parent / "target" / "compat-probe"))}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.target, ignore_errors=True)

    def repo(self, tagged=True, lockfile=True):
        root = Path(tempfile.mkdtemp(dir=self.target))
        dst = root / "packages" / "schemas"
        (dst).mkdir(parents=True)
        shutil.copytree(sm.JSON_DIR, dst / "json")
        shutil.copytree(sm.SCHEMAS_DIR / "codegen", dst / "codegen", ignore=shutil.ignore_patterns("tests", "generated", "evidence", "__pycache__"))
        shutil.copy(sm.VOCAB_PATH, dst / "vocabulary.json")
        shutil.copy(sm.SCHEMAS_DIR / "Cargo.toml", dst / "Cargo.toml")
        if lockfile:
            shutil.copy(REPO_LOCK, root / "Cargo.lock")  # the script pins the probe with the repository lockfile
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run([*git, "-C", str(root), "add", "-A"], check=True)
        subprocess.run([*git, "-C", str(root), "commit", "-q", "-m", "baseline"], check=True)
        if tagged:
            subprocess.run([*git, "-C", str(root), "tag", "contracts-0.1.0"], check=True)
        return root, dst

    def run_check(self, root, dst, *args):
        p = subprocess.run(["bash", str(dst / "codegen" / "check_compat.sh"), *args], capture_output=True, text=True, env=self.env, cwd=root)
        return p.returncode, p.stdout + p.stderr

    @staticmethod
    def bump(dst, version):
        p = dst / "Cargo.toml"
        p.write_text(p.read_text(encoding="utf-8").replace('version = "0.1.0"', f'version = "{version}"', 1), encoding="utf-8")

    def test_unchanged_schemas_pass_against_the_tag_including_the_compile_probe(self):
        root, dst = self.repo()
        rc, out = self.run_check(root, dst, "contracts-0.1.0")
        self.assertEqual(rc, 0, out)
        self.assertIn("compile probe", out)
        self.assertIn("compatible with contracts-0.1.0", out)

    def test_selftest_runs_without_a_repository_lockfile(self):
        """No Cargo.lock: the probe resolves serde itself. The script's empty `--lock` argument list must
        expand to nothing under `set -u` (bash before 4.4 fails on an empty array), so the self-test still runs."""
        root, dst = self.repo(tagged=False, lockfile=False)
        self.assertFalse((root / "Cargo.lock").exists())
        rc, out = self.run_check(root, dst, "--selftest")
        self.assertEqual(rc, 0, out)
        self.assertIn("compile probe: previous client cannot read", out)
        self.assertIn("self-test ok", out)

    def test_a_deleted_field_fails_without_a_major_bump(self):
        root, dst = self.repo()
        sch = dst / "json" / "assertion.schema.json"
        edit(sch, lambda d: (d["properties"].pop("created_by_run"), d["required"].remove("created_by_run")))
        rc, out = self.run_check(root, dst, "contracts-0.1.0")
        self.assertEqual(rc, 1, out)
        self.assertIn("BREAKING   field removed: Assertion.created_by_run", out)
        self.assertIn("breaking change needs a new minor (0.x", out)

    def test_a_deleted_field_with_a_major_bump_is_accepted_as_declared(self):
        root, dst = self.repo()
        edit(dst / "json" / "assertion.schema.json", lambda d: (d["properties"].pop("created_by_run"), d["required"].remove("created_by_run")))
        self.bump(dst, "0.2.0")
        rc, out = self.run_check(root, dst, "contracts-0.1.0")
        self.assertEqual(rc, 0, out)
        self.assertIn("breaking, major bumped", out)

    def test_an_added_optional_field_needs_a_version_bump(self):
        root, dst = self.repo()
        edit(dst / "json" / "error_response.schema.json", lambda d: d["properties"].update(hint={"type": "string"}))
        rc, out = self.run_check(root, dst, "contracts-0.1.0")
        self.assertEqual(rc, 1, out)
        self.assertIn("schemas changed but the version is still 0.1.0", out)
        self.bump(dst, "0.1.1")
        rc, out = self.run_check(root, dst, "contracts-0.1.0")
        self.assertEqual(rc, 0, out)
        self.assertIn("compile probe", out)

    def mutate_vocab(self, dst, fn):
        edit(dst / "vocabulary.json", fn)
        (dst / "json" / sm.VOCAB_FILE).write_text(
            json.dumps(sm.vocabulary_schema(sm.load_vocab(dst / "vocabulary.json")), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

    def test_a_new_enum_value_inserted_first_is_compatible_including_the_compile_probe(self):
        """Regression: the probe used to take values[0] of the NEW axis, so a value added at the front
        reached the previous client as an unknown enum value and the check reported a false INCOMPATIBLE."""
        root, dst = self.repo()
        self.mutate_vocab(dst, insert_first("criticality", "zz_new_first"))
        self.bump(dst, "0.1.1")
        rc, out = self.run_check(root, dst, "contracts-0.1.0")
        self.assertEqual(rc, 0, out)
        self.assertIn("compatible enum value added: criticality.zz_new_first", out)
        self.assertIn("compile probe", out)
        self.assertIn("compatible with contracts-0.1.0", out)
        self.assertNotIn("INCOMPATIBLE", out)

    def test_a_removed_enum_value_fails_without_a_major_bump(self):
        root, dst = self.repo()
        self.mutate_vocab(dst, remove_value("criticality", "c2"))
        self.bump(dst, "0.1.1")
        rc, out = self.run_check(root, dst, "contracts-0.1.0")
        self.assertEqual(rc, 1, out)
        self.assertIn("BREAKING   enum value removed: criticality.c2", out)
        self.assertIn("breaking change needs a new minor (0.x", out)

    def test_a_probe_that_cannot_be_prepared_is_a_setup_error_not_a_verdict(self):
        root, dst = self.repo()
        # an optional field whose pattern no probe sample satisfies: the probe cannot be generated
        edit(dst / "json" / "error_response.schema.json",
             lambda d: d["properties"].update(hint={"type": "string", "pattern": "^zzz[0-9]{5}$"}))
        self.bump(dst, "0.1.1")
        rc, out = self.run_check(root, dst, "contracts-0.1.0")
        self.assertEqual(rc, 2, out)
        self.assertIn("could not be prepared or built", out)
        self.assertNotIn("INCOMPATIBLE", out)

    def test_unknown_tag_is_an_error_once_a_contracts_tag_exists(self):
        root, dst = self.repo()
        rc, out = self.run_check(root, dst, "contracts-9.9.9")
        self.assertEqual(rc, 2, out)
        self.assertIn("does not exist", out)

    def test_without_any_tag_the_check_says_so_and_runs_the_self_test(self):
        root, dst = self.repo(tagged=False)
        rc, out = self.run_check(root, dst, "contracts-0.1.0")
        self.assertEqual(rc, 0, out)
        self.assertIn("BASELINE: no contracts-* tag exists", out)
        self.assertIn("self-test ok", out)

    def test_missing_argument_is_a_usage_error(self):
        root, dst = self.repo()
        rc, out = self.run_check(root, dst)
        self.assertEqual(rc, 2, out)


if __name__ == "__main__":
    unittest.main()
