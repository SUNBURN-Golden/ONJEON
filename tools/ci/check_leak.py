#!/usr/bin/env python3
"""Leak static check: I10, I11 and Part 3 section 52.3. Rules: infra/ci/deps.json ("leak").

  LEAK-I10             an ad/commission field appears in sort, rank or recommendation code
  LEAK-I11-PUBLIC      a sensitivity label is referenced from a public API serializer
  LEAK-I11-ANALYTICS   a sensitivity label or private field name appears in analytics/telemetry/crash code
  LEAK-I11-AGENT       an agent/consultation module references a sensitivity label (genetic_private above all)
  LEAK-I11-GATEWAY     a sensitivity label reaches the external-AI gateway
  LEAK-I11-LOG         a log/print call names a sensitivity label or a private field
  LEAK-ANALYTICS-FIELD an analytics event call sends a field outside the allowed event fields
  LEAK-VOCAB-DRIFT     the sensitivity axis of packages/schemas/vocabulary.json has a label this check does not know
  LEAK-RULES           a rules-file entry is malformed (an allow entry without a reason)

Matching is textual (line- and path-based) and skips comment-only lines. It catches the direct
mention of a label, field or type; it does not follow data flow, so a value passed through an
untyped variable is invisible to it. Multi-line log or analytics calls are only seen when the
label sits on the call's first line (log) or the literal dict is on one line (analytics). The
runtime leak tests of T-PS-04 cover what a static check cannot.

Usage:
  python3 -I tools/ci/check_leak.py [--root DIR] [--rules FILE]
  python3 -I tools/ci/check_leak.py --selftest
Exit: 0 clean, 1 findings, 2 usage or unreadable rules.
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ci_common as C  # noqa: E402

COMMENT = re.compile(r"^\s*(//|#|/\*|--|<!--)")
CAMEL_A = re.compile(r"([A-Z]+)([A-Z][a-z])")
CAMEL_B = re.compile(r"([a-z0-9])([A-Z])")


def snake(line):
    """camelCase and PascalCase identifiers become snake_case, so adCost matches ad_cost (Dart and TS clients)."""
    return CAMEL_B.sub(r"\1_\2", CAMEL_A.sub(r"\1_\2", line))


def comment_lines(lines):
    """Flags per line: comment-only lines and the inside of /* ... */ blocks. A bare leading '*' is not a comment (rustfmt operator continuation)."""
    out, in_block = [], False
    for line in lines:
        if in_block:
            out.append(True)
            in_block = "*/" not in line
            continue
        if COMMENT.match(line):
            out.append(True)
            stripped = line.lstrip()
            in_block = stripped.startswith("/*") and "*/" not in stripped
            continue
        out.append(False)
        i = line.find("/*")
        in_block = i >= 0 and "*/" not in line[i:] and not re.search(r"""["'`].*/\*""", line[:i + 2])
    return out


def word_re(words):
    alt = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alt})(?![A-Za-z0-9])", re.I)


def allowed(allow, rule, rel):
    return any(a["rule"] == rule and C.match(rel, [a["path"]]) for a in allow)


def check(root, rules=None):
    rules = rules or C.load_rules()
    L = rules["leak"]
    findings = []
    allow = list(L["i10"].get("allow", [])) + list(L["i11"].get("allow", []))
    for a in allow:
        if not a.get("reason") or not a.get("rule") or not a.get("path"):
            findings.append(C.Finding("LEAK-RULES", "infra/ci/deps.json", 0, f"allow entry needs rule, path and reason: {a}"))
    if findings:
        return findings

    money = word_re(L["i10"]["money_fields"])
    ranking = word_re(L["i10"]["ranking_words"])
    labels = word_re(L["i11"]["sensitive_labels"])
    private_fields = word_re(L["i11"]["private_field_names"])
    log_call = re.compile(L["i11"]["log_call_pattern"])
    event_call = re.compile(L["analytics"]["call_pattern"], re.S)
    allowed_fields = set(L["analytics"]["allowed_fields"])
    ignore = list(rules["scan"]["ignore"]) + list(L["scan_ignore"])
    ext = set(L["scan_extensions"])
    i10_paths, pub, ana = L["i10"]["ranking_path_globs"], L["i11"]["public_serializer_globs"], L["i11"]["analytics_globs"]
    agent, gate = L["i11"]["agent_globs"], L["i11"]["gateway_globs"]

    findings += vocab_drift(root, L)

    for rel, full in C.iter_files(root, ignore, ext):
        text = C.read_text(full)
        if text is None:
            continue
        lines = text.splitlines()
        path_ranks = C.match(rel, i10_paths)
        skip = comment_lines(lines)
        for n, raw in enumerate(lines, 1):
            if skip[n - 1]:
                continue
            line = snake(raw)
            m = money.search(line)
            if m and not allowed(allow, "LEAK-I10", rel):
                window = snake(" ".join(lines[max(0, n - 2):n + 1]))
                if path_ranks or ranking.search(window):
                    findings.append(C.Finding("LEAK-I10", rel, n, f"'{m.group(0)}' in sort/rank/recommendation context; ad and commission fields are never an input (I10)"))
            lab = labels.search(line)
            priv = private_fields.search(line)
            hit = lab or priv
            if lab:
                if C.match(rel, pub) and not allowed(allow, "LEAK-I11-PUBLIC", rel):
                    findings.append(C.Finding("LEAK-I11-PUBLIC", rel, n, f"public serializer references sensitivity label '{lab.group(0)}' (52.3, 7.1)"))
                if C.match(rel, agent) and not allowed(allow, "LEAK-I11-AGENT", rel):
                    findings.append(C.Finding("LEAK-I11-AGENT", rel, n, f"agent/consultation module references sensitivity label '{lab.group(0)}' (52.3)"))
                if C.match(rel, gate) and not allowed(allow, "LEAK-I11-GATEWAY", rel):
                    findings.append(C.Finding("LEAK-I11-GATEWAY", rel, n, f"external-AI gateway references sensitivity label '{lab.group(0)}'; {L['i11']['gateway_note']}"))
            if hit and C.match(rel, ana) and not allowed(allow, "LEAK-I11-ANALYTICS", rel):
                findings.append(C.Finding("LEAK-I11-ANALYTICS", rel, n, f"analytics/telemetry/crash code references '{hit.group(0)}' (I11)"))
            if hit and log_call.search(raw) and not allowed(allow, "LEAK-I11-LOG", rel):
                findings.append(C.Finding("LEAK-I11-LOG", rel, n, f"log or print call names '{hit.group(0)}'; sensitive data is never logged (I11)"))
        for m in event_call.finditer(text):
            n = text.count("\n", 0, m.start()) + 1
            for key in re.findall(r"""["']?([A-Za-z_][A-Za-z0-9_]*)["']?\s*:""", m.group(1)):
                if key not in allowed_fields and not allowed(allow, "LEAK-ANALYTICS-FIELD", rel):
                    findings.append(C.Finding("LEAK-ANALYTICS-FIELD", rel, n, f"analytics event sends field '{key}' that is not in the event schema's allowed fields (52.3)"))
    return findings


def vocab_drift(root, L):
    vocab = Path(root) / "packages/schemas/vocabulary.json"
    if not vocab.exists():
        return []
    data = C.load_json(vocab)
    known = set(L["i11"]["sensitive_labels"])
    out = []
    for axis in data.get("axes", []):
        if axis.get("id") != L["i11"]["vocabulary_axis"]:
            continue
        for v in axis["values"]:
            code = v["code"]
            if code != L["i11"]["public_value"] and code not in known:
                out.append(C.Finding("LEAK-VOCAB-DRIFT", "packages/schemas/vocabulary.json", 0, f"sensitivity label '{code}' is not in infra/ci/deps.json leak.i11.sensitive_labels"))
    return out


# ---------- selftest ----------
def selftest_cases():
    return [
        ("clean tree passes", {"services/api/src/lib.rs": "pub fn price(p: u64) -> u64 { p }\n"}, None),
        ("sorting uses a neutral key", {"services/api/src/sort_plans.rs": "plans.sort_by_key(|p| p.premium_krw);\n"}, None),
        ("a commission field outside any ranking context passes", {"services/api/src/agent_fee.rs": "struct Statement { commission: u64 }\n"}, None),
        ("ad cost in a sort closure", {"services/api/src/plans.rs": "plans.sort_by(|a, b| a.ad_cost.cmp(&b.ad_cost));\n"}, "LEAK-I10"),
        ("commission rate in a recommend function", {"services/api/src/x.rs": "fn recommend(p: &Plan) -> f64 {\n    p.commission_rate * 2.0\n}\n"}, "LEAK-I10"),
        ("Korean ad-cost field in a ranking file", {"services/api/src/rank.ts": "const k = plan.광고비;\n"}, "LEAK-I10"),
        ("commission field in a recommendation file by path", {"apps/web/src/recommend.ts": "const w = offer.referral_fee;\n"}, "LEAK-I10"),
        ("camelCase commission field in a Dart sort", {"apps/mobile/lib/plans.dart": "plans.sort((a, b) => b.commissionRate - a.commissionRate);\n"}, "LEAK-I10"),
        ("camelCase ad cost in a TypeScript sortBy", {"apps/web/src/list.ts": "const k = rows.sortBy(r => r.adCost);\n"}, "LEAK-I10"),
        ("rustfmt operator continuation line is not a comment", {"services/api/src/x.rs": "fn recommend(p: &Plan) -> f64 {\n    let score = base\n        * (1.0 + p.commission_rate);\n    score\n}\n"}, "LEAK-I10"),
        ("block comment body does not fail", {"services/api/src/x.rs": "/*\n * sort by commission_rate is forbidden\n */\nfn f() {}\n"}, None),
        ("camelCase private field in a Dart log call", {"apps/mobile/lib/crash/x.dart": "debugPrint(profile.familyHistory);\n"}, "LEAK-I11-LOG"),
        ("camelCase private field in Dart crash code", {"apps/mobile/lib/crash/x.dart": "report.add(profile.familyHistory);\n"}, "LEAK-I11-ANALYTICS"),
        ("camelCase sensitivity label in a TypeScript log", {"apps/web/src/a.ts": "console.log(row.privateHealth);\n"}, "LEAK-I11-LOG"),
        ("consultation file module importing the genetic schema", {"services/api/src/consultation.rs": "use onjeon_contracts::GeneticPrivate;\n"}, "LEAK-I11-AGENT"),
        ("agent file module importing a label", {"services/api/src/agent.rs": "use onjeon_contracts::PrivateHealth;\n"}, "LEAK-I11-AGENT"),
        ("agent_portal file module referencing a label", {"services/api/src/agent_portal.rs": 'let s = "private_policy";\n'}, "LEAK-I11-AGENT"),
        ("sensitivity label in a public serializer", {"services/api/src/public/plan.rs": "use onjeon_contracts::Sensitivity; fn f() { let _ = Sensitivity::PrivateHealth; }\n"}, "LEAK-I11-PUBLIC"),
        ("sensitivity string in a public response file", {"services/api/src/routes/public_response.rs": 'const L: &str = "genetic_private";\n'}, "LEAK-I11-PUBLIC"),
        ("sensitivity label in analytics code", {"apps/mobile/lib/analytics/events.dart": "final s = 'private_health';\n"}, "LEAK-I11-ANALYTICS"),
        ("private field in crash reporting", {"apps/mobile/lib/crash/report.dart": "report.add(family_history);\n"}, "LEAK-I11-ANALYTICS"),
        ("agent module importing the genetic schema", {"services/api/src/agent/portal.rs": "use onjeon_contracts::GeneticPrivate;\n"}, "LEAK-I11-AGENT"),
        ("consultation module referencing a label", {"services/personal/src/consultation/share.rs": 'let s = "genetic_private";\n'}, "LEAK-I11-AGENT"),
        ("sensitivity label in the external-AI gateway", {"services/ai-gateway/src/req.rs": 'if label == "private_policy" { send(); }\n'}, "LEAK-I11-GATEWAY"),
        ("log call naming a private field (Rust)", {"services/personal/src/x.rs": 'info!("saved {}", family_history);\n'}, "LEAK-I11-LOG"),
        ("log call naming a label (TypeScript)", {"apps/web/src/a.ts": "console.log(row.private_health);\n"}, "LEAK-I11-LOG"),
        ("print call naming a private field (Python)", {"services/docproc/a.py": "print(pdf_password)\n"}, "LEAK-I11-LOG"),
        ("analytics event with a field outside the schema", {"apps/web/src/a.ts": "track('home_view', { screen: 'home', diagnosis: d });\n"}, "LEAK-ANALYTICS-FIELD"),
        ("comment-only mention does not fail", {"services/api/src/public/a.rs": "// never expose private_health here\n"}, None),
        ("vocabulary has a sensitivity label the check does not know", {"packages/schemas/vocabulary.json": '{"axes":[{"id":"sensitivity","values":[{"code":"public_product"},{"code":"private_policy"},{"code":"private_health"},{"code":"genetic_private"},{"code":"private_new"}]}]}'}, "LEAK-VOCAB-DRIFT"),
    ]


def selftest():
    rules = C.load_rules()
    code = C.run_selftest("check_leak", selftest_cases(), lambda root: check(root, rules))
    # An allow entry needs a reason: a malformed rules file must fail, not silently allow.
    bad = dict(rules, leak=dict(rules["leak"], i10=dict(rules["leak"]["i10"], allow=[{"rule": "LEAK-I10", "path": "**"}])))
    if "LEAK-RULES" not in {f.rule for f in check(Path("."), bad)}:
        print("check_leak selftest failed: allow entry without reason was accepted")
        return 1
    return code


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
    return C.report(check(root, rules), "no leak patterns (I10, I11, 52.3)", "check_leak")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
