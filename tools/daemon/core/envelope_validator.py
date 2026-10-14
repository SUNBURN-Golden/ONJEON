"""Envelope shape checks, the instruction composer, validate_instruction and the receiver-side validation."""
import re

from .gate_evaluator import Clockview, Ctx, GuardResult
from .ports import SpecGap

# message type (how an envelope arrives) -> envelope type (accept_envelope.view_bindings[envelope.kind].values)
TYPE_OF_MESSAGE = {"result": "result", "switch_signal": "signal", "heartbeat": "heartbeat",
                   "first_heartbeat": "heartbeat", "fence_violation": "fence_violation_report"}
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def key_fields(rules):
    """accept_envelope.idempotency_key_fields (G43)."""
    return list(rules.get("core_contract.operations.accept_envelope.idempotency_key_fields"))


def _spec(rules, msg_type):
    """Required entries of a message type. The payload table either holds the list or points at
    envelopes.<name>.required; result envelopes are envelopes.result."""
    payloads = rules.get("core_contract.events_in.payloads")
    spec = payloads.get(msg_type)
    if isinstance(spec, str):
        m = re.fullmatch(r"envelopes\.([A-Za-z_]\w*)\.required", spec)
        if not m:
            raise SpecGap(f"payload spec is not a pointer to a required list: {spec}")
        return list(rules.get(spec))
    if msg_type in rules.view["envelopes"]:
        return list(rules.view["envelopes"][msg_type]["required"])
    if isinstance(spec, list):
        return list(spec)
    raise SpecGap(f"no required list for message type {msg_type}")


def required_fields(rules, msg_type):
    out = []
    for e in _spec(rules, msg_type):
        if not _NAME.fullmatch(e):
            raise SpecGap(f"required entry of {msg_type} is not a field name: {e!r}")
        if e not in out:
            out.append(e)
    for f in key_fields(rules):
        if f != "envelope_kind" and f not in out:
            out.append(f)
    return out


def envelope_type(rules, msg_type):
    t = TYPE_OF_MESSAGE.get(msg_type)
    values = rules.get("core_contract.operations.accept_envelope.view_bindings")["envelope.kind"]["values"]
    if t not in values:
        raise SpecGap(f"message type {msg_type} has no envelope type in view_bindings")
    return t


def missing_fields(rules, msg_type, envelope):
    """Required fields that are absent, then fields whose value is outside field_value_sets (G44: such a value is
    treated like a missing field)."""
    out = [f for f in required_fields(rules, msg_type) if envelope.get(f) is None]
    sets = rules.get("core_contract.operations.accept_envelope.field_value_sets").get(envelope_type(rules, msg_type), {})
    for field, values in sets.items():
        if envelope.get(field) is not None and envelope.get(field) not in values:
            out.append(field)
    return out


def check_view(rules, msg_type, envelope):
    """accept_envelope.view_bindings: envelope.kind is the envelope type; the sender's own `kind` is violation_kind."""
    view = dict(envelope)
    if "kind" in envelope:
        view["violation_kind"] = envelope["kind"]
    view["kind"] = envelope_type(rules, msg_type)
    return view


def envelope_kind(msg_type):
    """The envelope_kind of the idempotency key (instruction | result | signal)."""
    return "result" if msg_type == "result" else "signal"


def dedup_key(rules, task_id, msg_type, envelope):
    parts = {"task_id": task_id, "lease_generation": envelope.get("lease_generation"),
             "envelope_kind": envelope_kind(msg_type), "envelope_id": envelope.get("envelope_id")}
    return "|".join(str(parts[f]) for f in key_fields(rules))


# ---------------------------------------------------------------- validate_instruction (G49)
def _vctx(core, task_id, instruction, decisions, funcs=None):
    task_def = core.ports.catalog.task(task_id)
    return Ctx(core.rules, {"envelope": instruction, "task": task_def,
                            "task_state": {"decisions_recorded": list(decisions)}}, funcs=funcs)


def derive(core, task_id, decisions):
    """validate_instruction.derive: the expected values, computed outside the envelope. A target whose input
    cannot be evaluated is left out (on_unevaluable)."""
    out = {}
    for item in core.rules.get("core_contract.operations.validate_instruction.derive"):
        ctx = _vctx(core, task_id, {}, decisions)
        pred = item["pred"]
        left = ctx.value(pred["field"])
        if not isinstance(left, list):
            continue  # null_list_is: unevaluable -> target unset
        ok, _ = ctx.predicate(pred)
        out[item["target"]] = ok
    return out


def validate_instruction(core, task_id, instruction, decisions):
    """Returns (result, missing_fields). Reads instruction.* exactly as received; never writes it."""
    spec = core.rules.get("core_contract.operations.validate_instruction")
    res = spec["result"]
    allowed_null = set(res["null_allowed_in_required"])
    missing_required = [k for k in core.rules.view["envelopes"]["instruction"]["required"]
                        if k not in instruction or (instruction[k] is None and k not in allowed_null)]
    ctx = _vctx(core, task_id, instruction, decisions)
    items, missing_rules = [], []
    for rule in spec["rules"]:
        applies, _ = ctx.all(rule["applies_when"])
        ok = ctx.all(rule["pred"])[0] if applies else True
        items.append((rule["id"], ok))
        if not ok and rule["missing"] not in missing_rules:
            missing_rules.append(rule["missing"])
    funcs = {"envelopes.instruction.required": lambda _a: missing_required,
             "core_contract.operations.validate_instruction.rules": lambda _a: GuardResult(items)}
    valid, _ = _vctx(core, task_id, instruction, decisions, funcs).all(res["valid_iff"])
    missing = list(missing_required) + [m for m in missing_rules if m not in missing_required]
    return ("valid" if valid else "invalid"), missing


# ---------------------------------------------------------------- the composer
def build_instruction(core, d, task_id, lease, envelope_id):
    t = d["tasks"][task_id]
    task_def = core.ports.catalog.task(task_id)
    decisions = t["task_state"]["decisions_recorded"]
    approval = (task_def.get("canon_change") or {}).get("approval")
    inst = {
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
        "limits": task_def.get("limits"),  # value_source_order[0]: the task definition (the defaults are G47)
        "reply_to": core.ports.catalog.reply_to(),
        # canon_change_approval: null | {decision_ref, scope_paths[]} (the task's approval may carry notes besides)
        "canon_change_approval": None if approval is None else {"decision_ref": approval.get("decision_ref"),
                                                                "scope_paths": approval.get("scope_paths")},
        "lease_generation": lease["lease_generation"],
        "lease_expires_at": lease["expires_at"],
    }
    # derive[].copied_into_envelope_by create_outbox: the composer writes the expected value; an underivable value
    # is not written, and the validator then rejects the envelope (real_data_derivable, real_data_allowed_is_bool)
    expected = derive(core, task_id, decisions)
    if "expected.real_data_allowed" in expected:
        inst["real_data_allowed"] = expected["expected.real_data_allowed"]
    return inst


def receiver_validation(rules, instruction, daemon, clock):
    """Run by the builder adapter before it starts work. Returns (ok, evaluated checks)."""
    checks = rules.get("core_contract.operations.receiver_validation.checks")
    ctx = Ctx(rules, {"instruction": instruction, "clock": Clockview(clock.now()), "daemon": daemon},
              variables={"task_id": instruction.get("task_id")})
    return ctx.all(checks)
