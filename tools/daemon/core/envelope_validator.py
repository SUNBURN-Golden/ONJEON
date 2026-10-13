"""Envelope shape checks, the instruction builder and the receiver-side validation."""
import re

from .gate_evaluator import Clockview, Ctx
from .ports import SpecGap

# message type -> envelope kind used by accept_envelope.current_lease_rules (envelope.kind)
FENCE_REPORT = "fence_violation"


def key_fields(rules):
    """concurrency.idempotency_key is written as 'a + b + c + d'."""
    text = rules.get("concurrency.idempotency_key")
    fields = [re.match(r"[A-Za-z_][A-Za-z0-9_]*", f.strip()).group(0) for f in text.split("+")]
    rules.token_log.add(("concurrency.idempotency_key", "split on '+', leading identifiers"))
    return fields


def _spec(rules, msg_type):
    """(required entries, envelope name) for a message type. The payload table either holds the list or points
    at envelopes.<name>.required; result envelopes are envelopes.result."""
    payloads = rules.get("core_contract.events_in.payloads")
    spec = payloads.get(msg_type)
    if isinstance(spec, str):
        m = re.fullmatch(r"envelopes\.([A-Za-z_]\w*)\.required", spec)
        if not m:
            raise SpecGap(f"payload spec is not a pointer to a required list: {spec}")
        return list(rules.get(spec)), m.group(1)
    if msg_type in rules.view["envelopes"]:
        return list(rules.view["envelopes"][msg_type]["required"]), msg_type
    if isinstance(spec, list):
        return list(spec), msg_type
    raise SpecGap(f"no required list for message type {msg_type}")


def required_fields(rules, msg_type):
    entries, _name = _spec(rules, msg_type)
    out = []
    for e in entries:
        name = re.match(r"[A-Za-z_][A-Za-z0-9_]*", e).group(0)  # 'kind ∈ {...}' names the field 'kind'
        if name not in out:
            out.append(name)
    for f in key_fields(rules):
        if f not in ("envelope_kind",) and f not in out:
            out.append(f)
    return out


def envelope_name(rules, msg_type):
    return _spec(rules, msg_type)[1]


def missing_fields(rules, msg_type, envelope):
    return [f for f in required_fields(rules, msg_type) if envelope.get(f) is None]


def envelope_kind(msg_type):
    return "result" if msg_type == "result" else "signal"


def dedup_key(rules, task_id, msg_type, envelope):
    parts = {"task_id": task_id, "lease_generation": envelope.get("lease_generation"),
             "envelope_kind": envelope_kind(msg_type), "envelope_id": envelope.get("envelope_id")}
    return "|".join(str(parts[f]) for f in key_fields(rules))


def build_instruction(core, d, task_id, lease, envelope_id):
    t = d["tasks"][task_id]
    task_def = core.ports.catalog.task(task_id)
    gates = (task_def.get("decision_gates") or {})
    recorded = set(t["task_state"]["decisions_recorded"])
    return {
        "envelope_id": envelope_id,
        "task_id": task_id,
        "attempt": t["task_state"]["attempt"],
        "lease_id": lease["lease_id"],
        "fencing_token": lease["fencing_token"],
        "builder": lease["builder"],
        "runner": lease["runner"],
        "branch": lease["branch"],
        "base_sha": lease["base_sha"],
        "worktree": core.ports.worktree.path_for(task_id, lease["lease_id"]),
        "allowed_paths": task_def.get("allowed_paths"),
        "forbidden_paths": task_def.get("forbidden_paths"),
        "inputs": task_def.get("inputs"),
        "tests": task_def.get("tests"),
        "done_criteria": task_def.get("done_criteria"),
        "deadline_heartbeat_s": core.rules.get("concurrency.lease.heartbeat_s"),
        "limits": task_def.get("limits"),
        "reply_to": core.ports.catalog.reply_to(),
        "real_data_allowed": set(gates.get("real_data", [])) <= recorded,
        "canon_change_approval": task_def.get("canon_change_approval"),
        "lease_generation": lease["lease_generation"],
        "lease_expires_at": lease["expires_at"],
    }


def missing_instruction_fields(core, task_id, instruction):
    task_def = core.ports.catalog.task(task_id)
    canon = task_def.get("canon_change")
    out = []
    for k in core.rules.view["envelopes"]["instruction"]["required"]:
        if k not in instruction:
            out.append(k)
        elif instruction[k] is None:
            if k == "canon_change_approval" and not (canon and canon.get("required")):
                continue
            out.append(k)
    return out


def receiver_validation(rules, instruction, daemon, clock):
    """Run by the builder adapter before it starts work. Returns (ok, evaluated checks)."""
    checks = rules.get("core_contract.operations.receiver_validation.checks")
    ctx = Ctx(rules, {"instruction": instruction, "clock": Clockview(clock.now()), "daemon": daemon},
              variables={"task_id": instruction.get("task_id")})
    return ctx.all(checks)
