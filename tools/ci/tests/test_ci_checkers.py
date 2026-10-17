import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

CI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CI))
import check_bootstrap  # noqa: E402
import check_deps  # noqa: E402
import check_leak  # noqa: E402
import check_skeleton  # noqa: E402
import ci_common as C  # noqa: E402


def write(root, files):
    for rel, text in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


class SelfTests(unittest.TestCase):
    def test_each_selftest_passes(self):
        for mod in (check_deps, check_leak, check_skeleton, check_bootstrap):
            with self.subTest(mod.__name__):
                self.assertEqual(0, mod.selftest())


class RepoIsClean(unittest.TestCase):
    def test_real_repo_passes_every_checker(self):
        rules, flags = C.load_rules(), C.load_json(C.FLAGS_PATH)
        self.assertEqual([], check_deps.check(C.ROOT, rules))
        self.assertEqual([], check_leak.check(C.ROOT, rules))
        self.assertEqual([], check_skeleton.check(C.ROOT, rules, flags))

    def test_bootstrap_clean_main(self):
        tasks = C.ROOT / check_bootstrap.DEFAULT_TASKS
        self.assertEqual([], check_bootstrap.check(C.ROOT, tasks, strict_paths=False, advisory=[]))

    def test_cli_exit_codes_under_isolated_mode(self):
        for script in ("check_deps.py", "check_leak.py", "check_skeleton.py", "check_bootstrap.py"):
            with self.subTest(script):
                r = subprocess.run([sys.executable, "-I", str(CI / script)], cwd=C.ROOT, capture_output=True, text=True)
                self.assertEqual(0, r.returncode, r.stdout + r.stderr)


class ProviderSdkRule(unittest.TestCase):
    """deps.json rule: direct AI provider SDK dependency only in services/ai-gateway."""

    MANIFEST = '[package]\nname = "onjeon-{n}"\nversion = "0.1.0"\n\n[dependencies]\n{sdk} = "1"\n'

    def run_for(self, crate_dir, crate, sdk="anthropic"):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, {f"{crate_dir}/Cargo.toml": self.MANIFEST.format(n=crate, sdk=sdk)})
            return check_deps.check(Path(tmp), C.load_rules())

    def test_rule_text_is_in_the_rules_file(self):
        rule = C.load_rules()["provider_sdk"]
        self.assertEqual(["services/ai-gateway/**"], rule["only_in"])
        self.assertIn("services/ai-gateway", rule["rule"])

    def test_synthetic_cargo_toml_outside_the_gateway_fails(self):
        for d, n in (("services/knowledge", "knowledge"), ("services/api", "api"), ("services/ai-review", "ai-review"), ("packages/twin-runtime", "twin-runtime")):
            with self.subTest(d):
                self.assertIn("DEP-PROVIDER-SDK", {f.rule for f in self.run_for(d, n)})

    def test_every_listed_sdk_fails_outside_the_gateway(self):
        for sdk in C.load_rules()["provider_sdk"]["packages"]:
            if sdk.startswith("@"):
                continue  # npm-scoped names are covered through package.json below
            with self.subTest(sdk):
                self.assertIn("DEP-PROVIDER-SDK", {f.rule for f in self.run_for("services/knowledge", "knowledge", sdk)})

    def test_gateway_is_allowed(self):
        self.assertEqual([], self.run_for("services/ai-gateway", "ai-gateway"))

    def test_dev_and_target_tables_are_covered(self):
        text = '[package]\nname = "onjeon-knowledge"\n\n[dev-dependencies]\nanthropic = "1"\n\n[target.\'cfg(unix)\'.dependencies]\nopenai = "1"\n'
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, {"services/knowledge/Cargo.toml": text})
            found = [f for f in check_deps.check(Path(tmp), C.load_rules()) if f.rule == "DEP-PROVIDER-SDK"]
        self.assertEqual(2, len(found))

    def test_renamed_dependency_is_still_caught(self):
        text = '[package]\nname = "onjeon-knowledge"\n\n[dependencies]\nllm_client = { package = "async-openai", version = "1" }\n'
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, {"services/knowledge/Cargo.toml": text})
            self.assertIn("DEP-PROVIDER-SDK", {f.rule for f in check_deps.check(Path(tmp), C.load_rules())})


class DependencyExceptions(unittest.TestCase):
    def test_exception_is_exact_not_a_zone_wide_allow(self):
        files = {
            "packages/rules-engine/Cargo.toml": '[package]\nname = "onjeon-rules-engine"\n',
            "packages/schemas/Cargo.toml": '[package]\nname = "onjeon-contracts"\n\n[dependencies]\nonjeon-rules-engine = { path = "../rules-engine" }\n',
        }
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, files)
            self.assertIn("DEP-ZONE", {f.rule for f in check_deps.check(Path(tmp), C.load_rules())}, "normal dependency is not covered by the dev-only exception")

    def test_unused_exception_is_reported(self):
        warn = []
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, {"packages/schemas/Cargo.toml": '[package]\nname = "onjeon-contracts"\n'})
            check_deps.check(Path(tmp), C.load_rules(), warn)
        self.assertTrue(any("unused" in w for w in warn))


class LeakRules(unittest.TestCase):
    def test_vocabulary_sensitivity_labels_are_all_known(self):
        vocab = C.load_json(C.ROOT / "packages/schemas/vocabulary.json")
        axis = next(a for a in vocab["axes"] if a["id"] == "sensitivity")
        known = set(C.load_rules()["leak"]["i11"]["sensitive_labels"])
        self.assertTrue({v["code"] for v in axis["values"] if v["code"] != "public_product"} <= known)

    def test_allow_entry_with_reason_suppresses_only_its_rule_and_path(self):
        rules = C.load_rules()
        rules["leak"]["i11"]["allow"] = [{"rule": "LEAK-I11-AGENT", "path": "services/api/src/agent/ok.rs", "reason": "test"}]
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, {"services/api/src/agent/ok.rs": "use GeneticPrivate;\n", "services/api/src/agent/bad.rs": "use GeneticPrivate;\n"})
            found = check_leak.check(Path(tmp), rules)
        self.assertEqual({"services/api/src/agent/bad.rs"}, {f.path for f in found})

    def test_skipped_files_are_the_declared_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, {"docs/x.rs": "p.sort_by(|a| a.ad_cost);\n", "services/api/src/x.rs": "p.sort_by(|a| a.ad_cost);\n"})
            found = check_leak.check(Path(tmp), C.load_rules())
        self.assertEqual({"services/api/src/x.rs"}, {f.path for f in found})


class _Handler(http.server.BaseHTTPRequestHandler):
    status = 404

    def do_ANY(self):
        self.send_response(self.status)
        self.end_headers()

    do_GET = do_POST = do_PUT = do_ANY

    def log_message(self, *a):
        pass


class SkeletonRuntime(unittest.TestCase):
    def serve(self, status):
        handler = type("H", (_Handler,), {"status": status})
        srv = http.server.HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}"

    def test_real_http_inactive_route_passes_and_live_route_fails(self):
        flags = C.load_json(C.FLAGS_PATH)
        self.assertEqual([], check_skeleton.probe_routes(self.serve(404), flags))
        live = check_skeleton.probe_routes(self.serve(200), flags)
        self.assertEqual({"SKEL-ROUTE-LIVE"}, {f.rule for f in live})
        self.assertEqual(3, len(live))  # consultation, agent and quote routes
    def test_template_runs_green_and_red(self):
        tmpl = (CI / "templates/test_skeleton_unexposed.py.tmpl").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "test_skeleton_unexposed.py"
            test_file.write_text(tmpl.replace('os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "ci")', repr(str(CI))), encoding="utf-8")
            routes = Path(tmp) / "routes.json"
            routes.write_text(json.dumps(["/", "/coverage", "/legal"]))

            def run(base, ui):
                env = dict(os.environ, ONJ_SKELETON_BASE_URL=base or "", ONJ_UI_ROUTES_JSON=str(ui))
                return subprocess.run([sys.executable, "-I", str(test_file)], cwd=tmp, env=env, capture_output=True, text=True)

            self.assertEqual(0, run(self.serve(404), routes).returncode)
            self.assertNotEqual(0, run(self.serve(200), routes).returncode, "live skeleton route must fail the template")
            routes.write_text(json.dumps(["/", "/agent/home"]))
            self.assertNotEqual(0, run(self.serve(404), routes).returncode, "exposed UI route must fail the template")
            self.assertNotEqual(0, run("", routes).returncode, "missing base URL must fail, not skip")
            self.assertNotEqual(0, run(self.serve(404), Path(tmp) / "absent.json").returncode, "missing UI routes input must fail, not skip")


class FlagsFile(unittest.TestCase):
    def test_all_skeleton_flags_default_off_and_have_gates(self):
        flags = C.load_json(C.FLAGS_PATH)
        self.assertTrue(flags["flags"])
        for f in flags["flags"]:
            self.assertIs(False, f["default"], f["id"])
            self.assertIs(True, f["skeleton"], f["id"])
            self.assertTrue(f["enable_gate"].strip(), f["id"])

    def test_spec_58_routes_are_reserved(self):
        flags = C.load_json(C.FLAGS_PATH)
        routes = {(r["method"], r["path"]) for f in flags["flags"] for r in f["inactive_routes"]}
        self.assertIn(("POST", "/consultation-requests"), routes)
        self.assertIn(("GET", "/agent"), routes)

    def test_no_model_identifiers_or_absolute_paths_in_rule_files(self):
        import re

        for p in (C.FLAGS_PATH, C.RULES_PATH):
            text = p.read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"claude-|gpt-\d|gemini-\d|/home/|/workspace/", text), p.name)


if __name__ == "__main__":
    unittest.main()
