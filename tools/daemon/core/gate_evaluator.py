"""Predicate and expression evaluation for the structured conditions in daemon_rules.json.

A predicate is {field, op, value}. op in {==, !=, <, <=, >, >=, in, not_in, all_pass, any, all_present}.
`field` is a store path, clock.now, a rules path, a name registered in `funcs`, or the special fields
"any" (value is a list of predicates) and "true". `value` is a constant or an expression over paths
(+, -, *). A string that is not an expression over known roots is a literal.
"""
import re

from .ports import SpecGap

_TOKEN = re.compile(
    r"\s*(?:(?P<num>\d+(?:\.\d+)?)"
    r"|(?P<path>[A-Za-z_][A-Za-z0-9_]*(?:\([^()]*\))?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\([^()]*\))?)*)"
    r"|(?P<op>[+\-*()]))"
)
_SEG = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(?:\(([^()]*)\))?")


class Clockview:
    def __init__(self, now):
        self.now = now


def _tokenize(text):
    pos, out = 0, []
    text = text.rstrip()
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            return None
        if m.group("num") is not None:
            out.append(("num", float(m.group("num")) if "." in m.group("num") else int(m.group("num"))))
        elif m.group("path") is not None:
            out.append(("path", m.group("path")))
        else:
            out.append(("op", m.group("op")))
        pos = m.end()
    return out


def _parse(tokens):
    """expr := term (('+'|'-') term)* ; term := factor ('*' factor)* ; factor := num | path | '(' expr ')'"""
    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else (None, None)

    def take():
        t = tokens[pos[0]]
        pos[0] += 1
        return t

    def factor():
        kind, val = peek()
        if kind in ("num", "path"):
            take()
            return (kind, val)
        if (kind, val) == ("op", "("):
            take()
            node = expr()
            if peek() != ("op", ")"):
                raise ValueError("paren")
            take()
            return node
        raise ValueError("factor")

    def term():
        node = factor()
        while peek() == ("op", "*"):
            take()
            node = ("bin", "*", node, factor())
        return node

    def expr():
        node = term()
        while peek() in (("op", "+"), ("op", "-")):
            op = take()[1]
            node = ("bin", op, node, term())
        return node

    node = expr()
    if pos[0] != len(tokens):
        raise ValueError("trailing")
    return node


def _roots_in(node, acc):
    if node[0] == "path":
        acc.append(node[1])
    elif node[0] == "bin":
        _roots_in(node[2], acc)
        _roots_in(node[3], acc)
    return acc


class GuardResult:
    def __init__(self, items):
        self.items = items  # [(name, bool)]

    @property
    def all_pass(self):
        return all(ok for _, ok in self.items)

    @property
    def failed(self):
        return [n for n, ok in self.items if not ok]


class Ctx:
    """Evaluation context. `roots` maps a root name to a dict/object; rules paths resolve through `rules`."""

    def __init__(self, rules, roots, funcs=None, variables=None):
        self.rules = rules
        self.roots = roots
        self.funcs = funcs or {}
        self.vars = variables or {}
        self._rule_roots = set(rules.view.keys())

    # ---- values
    def known_root(self, path):
        root = path.split(".", 1)[0]
        root = _SEG.match(root).group(1)
        return root in self.roots or root in self._rule_roots

    def resolve(self, path):
        segs = path.split(".") if "(" not in path else self._split(path)
        first = _SEG.fullmatch(segs[0])
        if not first:
            raise SpecGap(f"bad path {path}")
        root = first.group(1)
        if root in self.roots:
            cur = self.roots[root]
            rest = segs[1:]
            for seg in rest:
                m = _SEG.fullmatch(seg)
                name, args = m.group(1), m.group(2)
                if args is not None:
                    argv = [self._arg(a.strip()) for a in args.split(",") if a.strip()]
                    cur = getattr(cur, name)(*argv)
                elif isinstance(cur, dict):
                    cur = cur.get(name)
                else:
                    cur = getattr(cur, name, None)
                if cur is None:
                    break
            return cur
        if root in self._rule_roots:
            return self.rules.get(path)
        raise SpecGap(f"unknown root in {path}")

    @staticmethod
    def _split(path):
        out, depth, cur = [], 0, ""
        for ch in path:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "." and depth == 0:
                out.append(cur)
                cur = ""
            else:
                cur += ch
        out.append(cur)
        return out

    def _arg(self, a):
        return self.vars.get(a, a)

    def _eval(self, node):
        kind = node[0]
        if kind == "num":
            return node[1]
        if kind == "path":
            return self.resolve(node[1])
        _, op, a, b = node
        x, y = self._eval(a), self._eval(b)
        if x is None or y is None:
            return None
        return {"+": x + y, "-": x - y, "*": x * y}[op]

    def value(self, v):
        """Constant, or expression over known roots. Anything else is a literal."""
        if isinstance(v, list):
            return [self.value(x) for x in v]
        if not isinstance(v, str):
            return v
        toks = _tokenize(v)
        if not toks:
            return v
        try:
            tree = _parse(toks)
        except ValueError:
            return v
        paths = _roots_in(tree, [])
        if not paths or not all(self.known_root(p) for p in paths):
            return v
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
        if field == "any" and isinstance(raw_value, list):
            subs = [self.predicate(x) for x in raw_value]
            left = any(r for r, _ in subs)
            right = True
            rec_extra = {"any_of": [rec for _, rec in subs]}
        else:
            rec_extra = {}
            if field == "true":
                left = True
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
