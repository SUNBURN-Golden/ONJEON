"""Predicate and expression evaluation for the structured conditions in daemon_rules.json.

A predicate is {field, op, value}. op in {==, !=, <, <=, >, >=, in, not_in, all_pass, all_present, any, all}.
`field` is a store path, clock.now, a rules path, a function registered in `funcs`, or one of the special forms:
"any" / "all" (value is a list of predicates), "true", `<rules list>[*].<attr>` (one boolean per list item) and
`count(<collection> where <atom> and ...)`.

Expressions (clock.expressions): +, -, *, parentheses, coalesce(a, b), max(<collection>.<field>),
count(...), paths with call and index segments. A string that is not an expression is a literal. A dotted
path or a call whose root is unknown is an error, never a literal: reading a name that nothing defines
would make a condition pass or fail by accident.
"""
import re

from .ports import SpecGap

_NUM = re.compile(r"\d+(?:\.\d+)?")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BUILTINS = ("coalesce", "max", "count")


class Clockview:
    def __init__(self, now):
        self.now = now


class Lazy:
    """A root that is expensive to build; built on first use."""

    def __init__(self, fn):
        self._fn, self._done, self._val = fn, False, None

    def get(self):
        if not self._done:
            self._val, self._done = self._fn(), True
        return self._val


class GuardResult:
    def __init__(self, items):
        self.items = items  # [(name, bool)]

    @property
    def all_pass(self):
        return all(ok for _, ok in self.items)

    @property
    def failed(self):
        return [n for n, ok in self.items if not ok]


# ---------------------------------------------------------------- parser
class _Parser:
    def __init__(self, text):
        self.s, self.i = text, 0

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] == " ":
            self.i += 1

    def peek(self):
        self.ws()
        return self.s[self.i] if self.i < len(self.s) else ""

    def eat(self, ch):
        if self.peek() != ch:
            raise ValueError(f"expected {ch}")
        self.i += 1

    def parse(self):
        node = self.expr()
        if self.peek() != "":
            raise ValueError("trailing")
        return node

    def expr(self):
        node = self.term()
        while self.peek() in ("+", "-"):
            op = self.s[self.i]
            self.i += 1
            node = ("bin", op, node, self.term())
        return node

    def term(self):
        node = self.factor()
        while self.peek() == "*":
            self.i += 1
            node = ("bin", "*", node, self.factor())
        return node

    def factor(self):
        ch = self.peek()
        if ch == "(":
            self.i += 1
            node = self.expr()
            self.eat(")")
            return node
        m = _NUM.match(self.s, self.i)
        if m:
            self.i = m.end()
            return ("num", float(m.group()) if "." in m.group() else int(m.group()))
        return self.atom()

    def balanced(self):
        """Raw text up to the ')' that closes the call whose '(' was just consumed."""
        depth, start = 1, self.i
        while self.i < len(self.s):
            if self.s[self.i] == "(":
                depth += 1
            elif self.s[self.i] == ")":
                depth -= 1
                if depth == 0:
                    raw = self.s[start:self.i]
                    self.i += 1
                    return raw
            self.i += 1
        raise ValueError("unbalanced")

    def args(self):
        out = []
        if self.peek() == ")":
            self.i += 1
            return out
        for _ in range(len(self.s) + 1):
            out.append(self.expr())
            if self.peek() == ",":
                self.i += 1
                continue
            self.eat(")")
            return out
        raise ValueError("args")

    def atom(self):
        segs = []
        for _ in range(len(self.s) + 1):
            self.ws()
            m = _IDENT.match(self.s, self.i)
            if not m:
                raise ValueError("ident")
            name, self.i = m.group(), m.end()
            call = index = None
            if self.i < len(self.s) and self.s[self.i] == "(":
                self.i += 1
                if name == "count" and not segs:
                    return ("count", self.balanced())
                call = self.args()
            if self.i < len(self.s) and self.s[self.i] == "[":
                self.i += 1
                index = self.expr()
                self.eat("]")
            segs.append((name, call, index))
            if self.i < len(self.s) and self.s[self.i] == ".":
                self.i += 1
                continue
            return ("atom", segs)
        raise ValueError("atom")


def _parse(text):
    return _Parser(text).parse()


def _walk_atoms(node, acc):
    if node[0] == "atom":
        acc.append(node[1])
    elif node[0] == "bin":
        _walk_atoms(node[2], acc)
        _walk_atoms(node[3], acc)
    return acc


# ---------------------------------------------------------------- evaluation context
class Ctx:
    """`roots` maps a root name to a dict / object / callable / Lazy; rules paths resolve through `rules`.
    `collections` maps a collection name to its rows (count, max). `task_of(row)` gives the task definition of a
    row (the `task.` prefix inside a where clause)."""

    def __init__(self, rules, roots, funcs=None, variables=None, collections=None, task_of=None):
        self.rules = rules
        self.roots = roots
        self.funcs = funcs or {}
        self.vars = variables or {}
        self.collections = collections or {}
        self.task_of = task_of
        self._rule_roots = set(rules.view.keys())

    # ---- path resolution
    def _known(self, name):
        return name in self.vars or name in self.roots or name in self._rule_roots

    def _call_args(self, args):
        out = []
        for a in args:
            out.append(self._eval(a, in_arg=True))
        return out

    def _step(self, cur, seg, strict):
        name, call, index = seg
        if call is not None:
            fn = cur.get(name) if isinstance(cur, dict) else getattr(cur, name, None)
            if not callable(fn):
                raise SpecGap(f"not callable: {name}")
            cur = fn(*self._call_args(call))
        elif isinstance(cur, dict):
            if name not in cur and strict:
                raise SpecGap(f"contract path not found: ...{name}")
            cur = cur.get(name)
        else:
            cur = getattr(cur, name, None)
        if index is not None:
            key = self._eval(index, in_arg=True)
            if isinstance(cur, dict):
                if key not in cur and strict:
                    raise SpecGap(f"contract key not found: {name}[{key}]")
                cur = cur.get(key)
            elif isinstance(cur, list):
                cur = cur[key]
            else:
                cur = None
        return cur

    def _atom(self, segs, in_arg):
        name0, call0, index0 = segs[0]
        if name0 in _BUILTINS and call0 is not None and len(segs) == 1:
            return self._builtin(name0, call0)
        if name0 in self.vars and call0 is None and index0 is None:
            cur, rest, strict = self.vars[name0], segs[1:], False
        elif name0 in self.roots:
            cur = self.roots[name0]
            if isinstance(cur, Lazy):
                cur = cur.get()
            cur = self._step_root(cur, segs[0])
            rest, strict = segs[1:], False
        elif name0 in self._rule_roots:
            cur = self._step(self.rules.view, (name0, call0, index0), True)
            rest, strict = segs[1:], True
        elif in_arg and len(segs) == 1 and call0 is None and index0 is None:
            return name0  # a bare word inside a call argument list is a literal (builder_available(next))
        else:
            raise SpecGap(f"unknown root {name0}")
        for seg in rest:
            if cur is None:
                return None
            cur = self._step(cur, seg, strict)
        return cur

    def _step_root(self, cur, seg):
        name, call, index = seg
        if call is not None:
            if not callable(cur):
                raise SpecGap(f"root is not callable: {name}")
            cur = cur(*self._call_args(call))
        if index is not None:
            key = self._eval(index, in_arg=True)
            cur = cur.get(key) if isinstance(cur, dict) else None
        return cur

    def _builtin(self, name, args):
        if name == "coalesce":
            vals = [self._eval(a, in_arg=True) for a in args]
            for v in vals:
                if v is not None:
                    return v
            return None
        if name == "max":
            node = args[0]
            if node[0] != "atom" or len(node[1]) != 2 or node[1][0][0] not in self.collections:
                raise SpecGap("max() takes <collection>.<field>")
            coll, field = node[1][0][0], node[1][1][0]
            vals = [r.get(field) for r in self.collections[coll] if r.get(field) is not None]
            return max(vals) if vals else None
        raise SpecGap(f"builtin {name} is not an expression here")

    def _eval(self, node, in_arg=False):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "count":
            return self._count(node[1])
        if kind == "atom":
            return self._atom(node[1], in_arg)
        _, op, a, b = node
        x, y = self._eval(a), self._eval(b)
        if x is None or y is None:
            return None
        return {"+": x + y, "-": x - y, "*": x * y}[op]

    # ---- count(<collection> where ...)
    def _count(self, raw):
        m = re.fullmatch(r"\s*([A-Za-z_]\w*)(?:\s+where\s+(.*))?\s*", raw, re.S)
        if not m or m.group(1) not in self.collections:
            raise SpecGap(f"count over an unknown collection: {raw[:40]}")
        atoms = re.split(r"\s+and\s+", m.group(2)) if m.group(2) else []
        return sum(1 for row in self.collections[m.group(1)] if all(self._where(a, row) for a in atoms))

    def _row_path(self, path, row):
        segs = path.strip().split(".")
        if segs[0] == "task" and self.task_of is not None:
            cur, segs = self.task_of(row), segs[1:]
        else:
            cur = row
        for s in segs:
            cur = cur.get(s) if isinstance(cur, dict) else None
        return cur

    def _rhs(self, text, row):
        text = text.strip()
        if text == "∅":
            return []
        head = text.split(".", 1)[0]
        if "." in text and self._known(head):
            return self.value(text)
        if re.fullmatch(r"-?\d+", text):
            return int(text)
        return text

    def _where(self, atom, row):
        m = re.fullmatch(r"(.+?)\s*∩\s*(.+?)\s*(==|!=)\s*∅", atom.strip())
        if m:
            a, b = self._row_path(m.group(1), row), self._rhs(m.group(2), row)
            hit = bool(set(a or []) & set(b or []))
            return hit if m.group(3) == "!=" else not hit
        m = re.fullmatch(r"(.+?)\s*(==|!=|<=|>=|<|>)\s*(.+)", atom.strip())
        if not m:
            raise SpecGap(f"where clause not understood: {atom}")
        return self._compare(self._row_path(m.group(1), row), m.group(2), self._rhs(m.group(3), row))

    # ---- values
    def value(self, v):
        """Constant, or expression over known roots. Anything else is a literal."""
        if isinstance(v, list):
            return [self.value(x) for x in v]
        if not isinstance(v, str):
            return v
        try:
            tree = _parse(v.strip())
        except ValueError:
            return v
        if tree[0] == "atom" and len(tree[1]) == 1 and tree[1][0][1] is None and tree[1][0][2] is None:
            return v  # a bare word is a literal ("active", "daemon"), never a root
        for segs in _walk_atoms(tree, []):
            name0, call0, index0 = segs[0]
            if name0 in _BUILTINS and call0 is not None:
                continue
            if self._known(name0):
                continue
            if len(segs) == 1 and call0 is None and index0 is None:
                return v  # a bare word inside an arithmetic-looking string: "R-08"
            raise SpecGap(f"unknown root in {v!r}: {name0}")
        return self._eval(tree)

    # ---- predicates
    def _call_func(self, field):
        if field in self.funcs:
            return True, self.funcs[field](None)
        m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_.]*)\(([^()]*)\)", field)
        if m and m.group(1) in self.funcs:
            return True, self.funcs[m.group(1)](m.group(2).strip())
        return False, None

    def predicate(self, p):
        field, op = p["field"], p["op"]
        raw_value = p.get("value")
        rec_extra = {}
        if field in ("any", "all") and isinstance(raw_value, list):
            subs = [self.predicate(x) for x in raw_value]
            left = any(r for r, _ in subs) if field == "any" else all(r for r, _ in subs)
            right = True
            rec_extra = {"sub_results": [rec for _, rec in subs]}
        elif field == "true":
            left, right = True, self.value(raw_value)
        else:
            m = re.fullmatch(r"(.+)\[\*\]\.(\w+)", field)
            if m:
                items = self.value(m.group(1))
                left = [self.all(it[m.group(2)] if isinstance(it[m.group(2)], list) else [it[m.group(2)]])[0] for it in items]
            else:
                found, left = self._call_func(field)
                if not found:
                    left = self.value(field)
            right = self.value(raw_value)
        result = self._compare(left, op, right)
        rec = {"field": field, "op": op, "value": _jsonable(right), "left": _jsonable(left), "result": result}
        rec.update(rec_extra)
        return result, rec

    def all(self, preds):
        recs, ok = [], True
        for p in preds or []:
            r, rec = self.predicate(p)
            recs.append(rec)
            ok = ok and r
        return ok, recs

    @staticmethod
    def _compare(left, op, right):
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op in ("<", "<=", ">", ">="):
            if left is None or right is None:
                return False
            return {"<": left < right, "<=": left <= right, ">": left > right, ">=": left >= right}[op]
        if op == "in":
            return left in (right or [])
        if op == "not_in":
            return left not in (right or [])
        if op == "all_pass":
            return bool(left.all_pass) == bool(right)
        if op == "all_present":
            return (len(left) == 0) == bool(right)
        if op == "any":
            return any(left) == bool(right)
        if op == "all":
            return all(left) == bool(right)
        raise SpecGap(f"unknown op {op}")


def _jsonable(v):
    if isinstance(v, GuardResult):
        return {"guards": v.items}
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return repr(v)
