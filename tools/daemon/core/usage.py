"""usage_recording (U-05): usage is recorded, never capped.

record_before_send: a usage slot (task, lease generation, envelope, created_at) exists before the instruction
envelope goes out. record_after_result: calls, wall_s and cost_units of an accepted result envelope are written
into the slot. A recording failure after a result is a warning and a retry entry; it never stops processing.
Nothing in this module reads an amount to decide anything.
"""


def result_fields(core):
    """usage_recording.record_after_result, as far as the store row has a column for it (store.usage_record)."""
    wanted = core.rules.get("usage_recording.record_after_result")
    columns = core.rules.get("core_contract.store.usage_record")
    return [f for f in wanted if f in columns]


def _rows(d):
    return d.setdefault("usage_record", [])


def _find(d, task_id, generation):
    for r in _rows(d):
        if r["task_id"] == task_id and r["lease_generation"] == generation:
            return r
    return None


class UsageView:
    """Root `usage_record` of the store predicates (lease_guards.usage_slot_ready)."""

    def __init__(self, core, d):
        self.core, self.d = core, d

    def slot(self, task_id, next_generation):
        """The slot of the next generation, prepared on first use. None only if the state store cannot be
        written (a storage failure, not a cost decision)."""
        row = _find(self.d, task_id, next_generation)
        if row is not None:
            return row
        if self.core.ports.faults.fails("usage:slot_create"):
            return None
        row = {"task_id": task_id, "lease_generation": next_generation, "envelope_id": None,
               "slot_created_at": self.core.clock.now(), "calls": None, "wall_s": None, "cost_units": None,
               "recorded_at": None}
        _rows(self.d).append(row)
        self.core.rec.side_effect(self.d, task_id, "record_usage", phase="before_send", lease_generation=next_generation)
        return row


def attach_envelope(core, d, task_id, generation, envelope_id):
    """The slot learns the instruction envelope it belongs to. A missing slot is a warning, not a stop."""
    row = UsageView(core, d).slot(task_id, generation)
    if row is None:
        core.rec.diagnostic(d, task_id, "usage_slot_missing", lease_generation=generation, envelope_id=envelope_id)
        return None
    row["envelope_id"] = envelope_id
    return row


def _fill(core, d, row, values):
    for k in result_fields(core):
        if row[k] is None:
            row[k] = values.get(k)
    row["recorded_at"] = core.clock.now()


def record_result(core, d, task_id, envelope):
    """record_after_result for an accepted result envelope."""
    gen = envelope.get("lease_generation")
    values = {k: envelope.get(k) for k in result_fields(core)}
    if core.ports.faults.fails("usage:record_result"):
        d.setdefault("usage_retry", []).append({"task_id": task_id, "lease_generation": gen, **values})
        core.rec.diagnostic(d, task_id, "usage_record_failed_warning", lease_generation=gen, retry="queued")
        return False
    row = _find(d, task_id, gen)
    if row is None:
        row = {"task_id": task_id, "lease_generation": gen, "envelope_id": envelope.get("envelope_id"),
               "slot_created_at": None, "calls": None, "wall_s": None, "cost_units": None, "recorded_at": None}
        _rows(d).append(row)
    _fill(core, d, row, values)
    core.rec.side_effect(d, task_id, "record_usage", phase="after_result", lease_generation=gen, **values)
    return True


def retry_pending(core):
    """The asynchronous retry of recordings that failed. Returns how many were written now."""
    done = 0
    with core.ports.store.transaction() as d:
        keep = []
        for item in d.get("usage_retry", []):
            if core.ports.faults.fails("usage:record_result"):
                keep.append(item)
                continue
            row = _find(d, item["task_id"], item["lease_generation"])
            if row is None:
                row = {"task_id": item["task_id"], "lease_generation": item["lease_generation"], "envelope_id": None,
                       "slot_created_at": None, "calls": None, "wall_s": None, "cost_units": None, "recorded_at": None}
                _rows(d).append(row)
            _fill(core, d, row, item)
            core.rec.side_effect(d, item["task_id"], "record_usage", phase="after_result_retry",
                                 lease_generation=item["lease_generation"], **{k: item.get(k) for k in result_fields(core)})
            done += 1
        d["usage_retry"] = keep
    return done
