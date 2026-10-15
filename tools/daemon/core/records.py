"""Journal records (core_contract.expected_outputs). The journal is append-only and lives in the store.

Every record passes the journal_text secret scan (preserve_manifest.secret_patterns.scan[journal_text], G38) before
it is appended: a matching string is replaced and only the match count is kept. The hit is queued in the store and
turned into a secret_detected event by the engine at the end of the operation (transition_engine.settle_secrets).
"""

from . import secret_scan
from .ports import SpecGap


class Recorder:
    def __init__(self, rules, clock):
        self.rules = rules
        self.clock = clock
        self._ids = set(rules.get("core_contract.expected_outputs.side_effect_ids"))
        self._noops = set(rules.noop_events)
        self._pats = secret_scan.patterns(rules)

    def _add(self, d, kind, **fields):
        clean, hits = secret_scan.redact(self._pats, fields)
        if hits:
            d.setdefault("secret_hits", []).append({"task_id": fields.get("task_id"), "scan_id": "journal_text",
                                                    "match_count": hits, "record_kind": kind})
        rec = {"seq": len(d["journal"]) + 1, "kind": kind}
        rec.update(clean)
        d["journal"].append(rec)
        return rec

    def transition(self, d, task_id, frm, to, event, cond_evaluated, source="transitions"):
        return self._add(d, "transition_record", task_id=task_id, **{"from": frm}, to=to, event=event,
                         at=self.clock.now(), cond_evaluated=cond_evaluated, source=source)

    def side_effect(self, d, task_id, sid, **args):
        if sid not in self._ids:
            raise SpecGap(f"side effect id not in expected_outputs.side_effect_ids: {sid}")
        return self._add(d, "side_effect_record", task_id=task_id, id=sid, at=self.clock.now(), args=args)

    def noop(self, d, task_id, noop_event, envelope_id=None, return_code=None, **extra):
        if noop_event is not None and noop_event not in self._noops:
            raise SpecGap(f"noop event not in noop_events: {noop_event}")
        rec = self._add(d, "noop_record", task_id=task_id, noop_event=noop_event, envelope_id=envelope_id,
                        at=self.clock.now(), return_code=return_code, **extra)
        if return_code:
            self.side_effect(d, task_id, "record_r_code", code=return_code, via="noop_record")
        return rec

    def returned(self, d, task_id, code):
        if not self.rules.return_code_known(code):
            raise SpecGap(f"return code not in return_codes: {code}")
        rec = self._add(d, "return_record", task_id=task_id, return_code=code,
                        to=self.rules.return_target(code), at=self.clock.now())
        self.side_effect(d, task_id, "record_r_code", code=code, via="return_record")
        return rec

    def intent(self, d, task_id, action, **args):
        return self._add(d, "intent_record", task_id=task_id, action=action, args=args, at=self.clock.now())

    def result(self, d, task_id, action, outcome, **args):
        return self._add(d, "result_record", task_id=task_id, action=action, outcome=outcome, args=args,
                         at=self.clock.now())

    def diagnostic(self, d, task_id, what, **fields):
        # Internal diagnostics. Not one of the contract's six record kinds.
        return self._add(d, "diagnostic_record", task_id=task_id, what=what, at=self.clock.now(), **fields)
