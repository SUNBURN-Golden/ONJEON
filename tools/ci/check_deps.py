#!/usr/bin/env python3
"""Zone dependency check (O15). Rules: infra/ci/deps.json (01_code_design section 2).

Checks, per manifest and per source file:
  DEP-UNZONED       a manifest (or an internal dependency target) sits in no zone
  DEP-ZONE          a manifest depends on an internal package from a zone it may not use
  DEP-PROVIDER-SDK  an AI provider SDK is declared outside services/ai-gateway
  IMP-ZONE          a source file imports an internal package or path from a zone it may not use
  IMP-CLIENT        mobile/web imports something other than the generated contracts client
  IMP-PROVIDER-SDK  an AI provider SDK is imported outside services/ai-gateway

Manifests: Cargo.toml, package.json, pubspec.yaml, pyproject.toml, requirements*.txt.
Sources: Rust, TypeScript/JavaScript, Dart, Python (Python only for the provider SDK rule).

Not checked here (other tasks): DB role grants, credential separation, the amount-arithmetic lint.

Usage:
  python3 -I tools/ci/check_deps.py [--root DIR] [--rules FILE]
  python3 -I tools/ci/check_deps.py --selftest
Exit: 0 clean, 1 findings, 2 usage or unreadable rules.
"""
import json
import os
import posixpath
import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ci_common as C  # noqa: E402

RUST_USE = re.compile(r"^\s*(?:pub\s+)?(?:use|extern\s+crate)\s+([A-Za-z_][A-Za-z0-9_]*)", re.M)
RUST_PATH = re.compile(r"(?<![A-Za-z0-9_:])([A-Za-z_][A-Za-z0-9_]*)::")
JS_IMPORT = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\s*\(\s*)['"]([^'"]+)['"]""")
DART_IMPORT = re.compile(r"""^\s*(?:import|export|part)\s+['"]([^'"]+)['"]""", re.M)
PY_IMPORT = re.compile(r"^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_.]*)", re.M)
SRC_EXT = {".rs", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".dart", ".py"}
MANIFESTS = {"Cargo.toml", "package.json", "pubspec.yaml", "pyproject.toml"}


def is_manifest(name):
    return name in MANIFESTS or (name.startswith("requirements") and name.endswith(".txt"))


# ---------- manifest parsing: returns (own name or None, [(dep name, kind, line)]) ----------
def _line_of(text, needle):
    i = text.find(needle)
    return text.count("\n", 0, i) + 1 if i >= 0 else 0


def parse_cargo(text):
    data = tomllib.loads(text)
    own = (data.get("package") or {}).get("name")
    deps = []

    def table(tbl, kind):
        for key, spec in (tbl or {}).items():
            name = spec.get("package", key) if isinstance(spec, dict) else key
            deps.append((name, kind, _line_of(text, key)))

    for sect, kind in (("dependencies", "normal"), ("dev-dependencies", "dev"), ("build-dependencies", "build")):
        table(data.get(sect), kind)
    for tgt in (data.get("target") or {}).values():
        for sect, kind in (("dependencies", "normal"), ("dev-dependencies", "dev"), ("build-dependencies", "build")):
            table(tgt.get(sect), kind)
    table((data.get("workspace") or {}).get("dependencies"), "normal")
    return own, deps


def parse_package_json(text):
    data = json.loads(text)
    deps = []
    for sect in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name in (data.get(sect) or {}):
            deps.append((name, "dev" if sect == "devDependencies" else "normal", _line_of(text, f'"{name}"')))
    return data.get("name"), deps


def parse_pubspec(text):
    own, deps, section = None, [], None
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" "):
            key = raw.split(":", 1)[0].strip()
            section = key if key in ("dependencies", "dev_dependencies", "dependency_overrides") else None
            if key == "name":
                own = raw.split(":", 1)[1].strip()
        elif section and re.match(r"^  [A-Za-z_][A-Za-z0-9_]*\s*:", raw):
            deps.append((raw.split(":", 1)[0].strip(), "dev" if section == "dev_dependencies" else "normal", n))
    return own, deps


def parse_pyproject(text):
    data = tomllib.loads(text)
    proj = data.get("project") or {}
    deps = []
    for spec in proj.get("dependencies", []) + [d for g in (proj.get("optional-dependencies") or {}).values() for d in g]:
        deps.append((re.split(r"[\s<>=!~\[;]", spec, maxsplit=1)[0], "normal", _line_of(text, spec)))
    for name in ((data.get("tool") or {}).get("poetry") or {}).get("dependencies", {}):
        deps.append((name, "normal", _line_of(text, name)))
    return proj.get("name"), deps


def parse_requirements(text):
    deps = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            deps.append((re.split(r"[\s<>=!~\[;]", line, maxsplit=1)[0], "normal", n))
    return None, deps


def parse_manifest(name, text):
    if name == "Cargo.toml":
        return parse_cargo(text)
    if name == "package.json":
        return parse_package_json(text)
    if name == "pubspec.yaml":
        return parse_pubspec(text)
    if name == "pyproject.toml":
        return parse_pyproject(text)
    return parse_requirements(text)


# ---------- the check ----------
class Zones:
    def __init__(self, rules):
        self.rules = rules
        self.zones = rules["zones"]
        self.sdk = {C.norm_pkg(p) for p in rules["provider_sdk"]["packages"]}
        self.sdk_home = rules["provider_sdk"]["only_in"]
        self.exceptions = rules.get("dependency_exceptions", [])
        self.used_exceptions = set()

    def allowed(self, src_zone, dst_zone, dst_pkg):
        z = self.zones[src_zone]
        return dst_zone == src_zone or dst_zone in z["allow_zones"] or C.norm_pkg(dst_pkg) in {C.norm_pkg(p) for p in z["allow_packages"]}

    def excepted(self, src_pkg, dst_pkg, kind):
        for i, e in enumerate(self.exceptions):
            if C.norm_pkg(e["from"]) == C.norm_pkg(src_pkg or "") and C.norm_pkg(e["to"]) == C.norm_pkg(dst_pkg) and e.get("kind", kind) == kind:
                self.used_exceptions.add(i)
                return True
        return False


def collect_manifests(root, rules):
    out = []  # (rel, own, deps)
    for rel, full in C.iter_files(root, rules["scan"]["manifest_ignore"], None):
        name = posixpath.basename(rel)
        if not is_manifest(name):
            continue
        text = C.read_text(full)
        if text is None:
            continue
        try:
            own, deps = parse_manifest(name, text)
        except (ValueError, tomllib.TOMLDecodeError) as e:
            out.append((rel, None, [("__unparsable__", str(e), 0)]))
            continue
        out.append((rel, own, deps))
    return out


def check(root, rules=None, warn=None):
    rules = rules or C.load_rules()
    Z = Zones(rules)
    findings = []
    manifests = collect_manifests(root, rules)

    # internal package name -> zone (manifests that name themselves and live in a zone)
    pkg_zone = {}
    for rel, own, _ in manifests:
        if own:
            z = C.zone_of(rel, Z.zones)
            if z:
                pkg_zone[C.norm_pkg(own)] = z

    for rel, own, deps in manifests:
        base = posixpath.basename(rel)
        if deps and deps[0][0] == "__unparsable__":
            findings.append(C.Finding("DEP-UNPARSABLE", rel, 0, f"manifest cannot be parsed: {deps[0][1]}"))
            continue
        zone = C.zone_of(rel, Z.zones)
        if base == "Cargo.toml" and own is None and not deps:
            continue  # virtual workspace root
        if base in ("Cargo.toml", "package.json", "pubspec.yaml") and own and not zone:
            findings.append(C.Finding("DEP-UNZONED", rel, 0, f"package '{own}' is in no zone of infra/ci/deps.json; assign it a zone before it grows dependencies"))
        for name, kind, line in deps:
            key = C.norm_pkg(name)
            if key in Z.sdk and not C.match(rel, Z.sdk_home):
                findings.append(C.Finding("DEP-PROVIDER-SDK", rel, line, f"'{name}' is an AI provider SDK; only {', '.join(Z.sdk_home)} may depend on it directly"))
                continue
            if not zone:
                continue
            dst_zone = pkg_zone.get(key)
            if dst_zone is None:
                continue  # external package (or an internal one not yet in a zone: flagged by its own manifest)
            if Z.allowed(zone, dst_zone, name) or Z.excepted(own, name, kind):
                continue
            findings.append(C.Finding("DEP-ZONE", rel, line, f"zone '{zone}' may not depend on '{name}' (zone '{dst_zone}'); allowed zones: {Z.zones[zone]['allow_zones'] or 'none'}"))

    owners = {posixpath.dirname(rel): own for rel, own, _ in manifests if own and posixpath.basename(rel) in ("Cargo.toml", "package.json", "pubspec.yaml")}
    findings += check_imports(root, rules, Z, pkg_zone, owners)
    if warn is not None:
        for i, e in enumerate(Z.exceptions):
            if i not in Z.used_exceptions:
                warn.append(f"dependency exception {e['from']} -> {e['to']} ({e.get('kind', 'any')}) is unused; remove it from infra/ci/deps.json")
    return findings


def _line(text, pos):
    return text.count("\n", 0, pos) + 1


def check_imports(root, rules, Z, pkg_zone, owners):
    findings = []
    client = rules["client_rules"]
    generated = {C.norm_pkg(p) for p in client["generated_client_packages"]}
    namespaces = client["internal_namespaces"]
    for rel, full in C.iter_files(root, rules["scan"]["ignore"], SRC_EXT):
        text = C.read_text(full)
        if text is None:
            continue
        ext = full.suffix
        zone = C.zone_of(rel, Z.zones)
        in_sdk_home = C.match(rel, Z.sdk_home)
        refs = []  # (kind, target, line)
        if ext == ".rs":
            seen = set()
            for rx in (RUST_USE, RUST_PATH):
                for m in rx.finditer(text):
                    if m.group(1) not in seen:
                        seen.add(m.group(1))
                        refs.append(("pkg", m.group(1), _line(text, m.start())))
        elif ext in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
            for m in JS_IMPORT.finditer(text):
                refs.append(("spec", m.group(1), _line(text, m.start())))
        elif ext == ".dart":
            for m in DART_IMPORT.finditer(text):
                refs.append(("spec", m.group(1), _line(text, m.start())))
        elif ext == ".py":
            for m in PY_IMPORT.finditer(text):
                refs.append(("pkg", m.group(1), _line(text, m.start())))

        for kind, target, line in refs:
            if kind == "spec":
                kind, target = classify_spec(target, rel)
            if kind == "pkg":
                key = C.norm_pkg(target)
                if (key in Z.sdk or C.norm_pkg(target.split(".")[0]) in Z.sdk) and not in_sdk_home:
                    findings.append(C.Finding("IMP-PROVIDER-SDK", rel, line, f"imports AI provider SDK '{target}'; only {', '.join(Z.sdk_home)} may"))
                    continue
                if ext == ".py" or not zone:
                    continue
                dst = pkg_zone.get(key)
                if zone == "client" and any(target.startswith(ns) or f"package:{target}".startswith(ns) for ns in namespaces) and key not in generated:
                    findings.append(C.Finding("IMP-CLIENT", rel, line, f"mobile/web may import only the generated contracts client, not '{target}'"))
                elif dst and not Z.allowed(zone, dst, target) and not Z.excepted(owner_of(rel, owners), target, "dev"):
                    findings.append(C.Finding("IMP-ZONE", rel, line, f"zone '{zone}' may not import '{target}' (zone '{dst}')"))
            elif kind == "path":
                dst_rel = target
                if zone == "client" and any(dst_rel.startswith(p) for p in client["forbidden_import_paths"]):
                    findings.append(C.Finding("IMP-CLIENT", rel, line, f"mobile/web imports '{dst_rel}', which is not the generated client"))
                    continue
                dst = C.zone_of(dst_rel, Z.zones)
                if zone and dst and not (dst == zone or dst in Z.zones[zone]["allow_zones"]):
                    findings.append(C.Finding("IMP-ZONE", rel, line, f"zone '{zone}' may not import '{dst_rel}' (zone '{dst}')"))
    return findings


def owner_of(rel, owners):
    """Name of the package whose manifest is the nearest ancestor of rel."""
    d = posixpath.dirname(rel)
    while True:
        if d in owners:
            return owners[d]
        if not d:
            return None
        d = posixpath.dirname(d)


def classify_spec(spec, importer_rel):
    """('path', repo-relative path) for a relative import, ('pkg', name) for a package import."""
    if spec.startswith("."):
        return "path", posixpath.normpath(posixpath.join(posixpath.dirname(importer_rel), spec))
    if spec.startswith("package:"):
        return "pkg", spec[len("package:"):].split("/", 1)[0]
    if spec.startswith("dart:"):
        return "skip", spec
    if spec.startswith("@"):
        return "pkg", "/".join(spec.split("/")[:2])
    return "pkg", spec.split("/", 1)[0]


# ---------- selftest ----------
CARGO = '[package]\nname = "{n}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n{d}\n'


def cargo(name, deps=""):
    return CARGO.format(n=name, d=deps)


BASE = {
    "Cargo.toml": '[workspace]\nmembers = ["packages/schemas", "packages/twin-runtime", "services/api", "services/knowledge", "services/ai-gateway"]\n',
    "packages/schemas/Cargo.toml": cargo("onjeon-contracts", 'serde = "1"'),
    "packages/twin-runtime/Cargo.toml": cargo("onjeon-twin-runtime", 'onjeon-contracts = { path = "../schemas" }'),
    "services/api/Cargo.toml": cargo("onjeon-api", 'onjeon-contracts = { path = "../../packages/schemas" }\nonjeon-twin-runtime = { path = "../../packages/twin-runtime" }'),
    "services/knowledge/Cargo.toml": cargo("onjeon-knowledge", 'onjeon-contracts = { path = "../../packages/schemas" }'),
    "services/ai-gateway/Cargo.toml": cargo("onjeon-ai-gateway", 'onjeon-contracts = { path = "../../packages/schemas" }'),
    "services/personal/Cargo.toml": cargo("onjeon-personal", 'onjeon-contracts = { path = "../../packages/schemas" }'),
    "services/collect/Cargo.toml": cargo("onjeon-collect", 'onjeon-contracts = { path = "../../packages/schemas" }'),
}


def selftest_cases():
    def with_(**overrides):
        files = dict(BASE)
        files.update(overrides)
        return files

    return [
        ("clean zone graph passes", with_(), None),
        ("AI gateway may hold the provider SDK", with_(**{"services/ai-gateway/Cargo.toml": cargo("onjeon-ai-gateway", 'async-openai = "0.1"\nonjeon-contracts = { path = "../../packages/schemas" }')}), None),
        ("provider SDK in a knowledge crate (synthetic Cargo.toml)", with_(**{"services/knowledge/Cargo.toml": cargo("onjeon-knowledge", 'anthropic = "0.1"')}), "DEP-PROVIDER-SDK"),
        ("provider SDK in an api crate", with_(**{"services/api/Cargo.toml": cargo("onjeon-api", 'genai = "0.1"')}), "DEP-PROVIDER-SDK"),
        ("provider SDK in package.json outside the gateway", with_(**{"apps/web/package.json": '{"name": "onjeon-web", "dependencies": {"@anthropic-ai/sdk": "1"}}'}), "DEP-PROVIDER-SDK"),
        ("provider SDK in pubspec outside the gateway", with_(**{"apps/mobile/pubspec.yaml": "name: onjeon_mobile\ndependencies:\n  google_generative_ai: ^1\n"}), "DEP-PROVIDER-SDK"),
        ("provider SDK in requirements.txt outside the gateway", with_(**{"services/docproc/requirements.txt": "openai==1.0\n"}), "DEP-PROVIDER-SDK"),
        ("contracts depends on twin", with_(**{"packages/schemas/Cargo.toml": cargo("onjeon-contracts", 'onjeon-twin-runtime = { path = "../twin-runtime" }')}), "DEP-ZONE"),
        ("knowledge depends on api", with_(**{"services/knowledge/Cargo.toml": cargo("onjeon-knowledge", 'onjeon-api = { path = "../api" }')}), "DEP-ZONE"),
        ("data depends on knowledge", with_(**{"services/collect/Cargo.toml": cargo("onjeon-collect", 'onjeon-knowledge = { path = "../knowledge" }')}), "DEP-ZONE"),
        ("api depends on data crate", with_(**{"services/api/Cargo.toml": cargo("onjeon-api", 'onjeon-collect = { path = "../collect" }')}), "DEP-ZONE"),
        ("dev-dependency crossing a zone is still a violation", with_(**{"services/knowledge/Cargo.toml": cargo("onjeon-knowledge", "") + '\n[dev-dependencies]\nonjeon-personal = { path = "../personal" }\n'}), "DEP-ZONE"),
        ("crate in no zone", with_(**{"tools/newthing/Cargo.toml": cargo("onjeon-newthing")}), "DEP-UNZONED"),
        ("rust import of a forbidden zone", with_(**{"services/knowledge/src/lib.rs": "use onjeon_api::routes;\nfn main() {}\n"}), "IMP-ZONE"),
        ("rust path use of a forbidden zone", with_(**{"services/api/src/lib.rs": "fn f() { onjeon_collect::fetch(); }\n"}), "IMP-ZONE"),
        ("rust import of an allowed zone passes", with_(**{"services/api/src/lib.rs": "use onjeon_twin_runtime::evaluate;\nuse onjeon_contracts::Krw;\n"}), None),
        ("rust import of provider SDK outside the gateway", with_(**{"services/knowledge/src/lib.rs": "use async_openai::Client;\n"}), "IMP-PROVIDER-SDK"),
        ("rust import of provider SDK inside the gateway", with_(**{"services/ai-gateway/src/lib.rs": "use async_openai::Client;\n"}), None),
        ("python import of provider SDK outside the gateway", with_(**{"services/docproc/main.py": "import openai\n"}), "IMP-PROVIDER-SDK"),
        ("ts relative import reaching a service from the web app", with_(**{"apps/web/package.json": '{"name": "onjeon-web"}', "apps/web/src/a.ts": "import { x } from '../../../services/api/src/x';\n"}), "IMP-CLIENT"),
        ("ts import of a non-generated internal package", with_(**{"apps/web/package.json": '{"name": "onjeon-web"}', "apps/web/src/a.ts": "import { e } from '@onjeon/rules-engine';\n"}), "IMP-CLIENT"),
        ("dart import of a non-generated internal package", with_(**{"apps/mobile/pubspec.yaml": "name: onjeon_mobile\n", "apps/mobile/lib/a.dart": "import 'package:onjeon_twin/x.dart';\n"}), "IMP-CLIENT"),
        ("ts import of the generated client passes", with_(**{"apps/web/package.json": '{"name": "onjeon-web"}', "apps/web/src/a.ts": "import { Krw } from '@onjeon/contracts';\nimport { y } from './y';\n"}), None),
        ("ts relative import from knowledge into api", with_(**{"services/knowledge/ts/a.ts": "import x from '../../api/src/x';\n"}), "IMP-ZONE"),
    ]


def selftest():
    rules = C.load_rules()
    return C.run_selftest("check_deps", selftest_cases(), lambda root: check(root, rules))


def main(argv):
    args = argv[1:]
    if args == ["--selftest"]:
        return selftest()
    root, rules_path = C.ROOT, C.RULES_PATH
    while args:
        flag = args.pop(0)
        if flag == "--root" and args:
            root = Path(args.pop(0))
        elif flag == "--rules" and args:
            rules_path = Path(args.pop(0))
        else:
            return C.usage_error(__doc__.split("Usage:")[1].strip())
    try:
        rules = C.load_rules(rules_path)
    except (OSError, ValueError) as e:
        return C.usage_error(f"cannot read rules {rules_path}: {e}")
    warnings = []
    findings = check(root, rules, warnings)
    for w in warnings:
        print("warning: " + w)
    return C.report(findings, "no zone dependency violations", "check_deps")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
