"""Language-neutral model of packages/schemas/json/*.schema.json (stdlib only).

Single place that reads the schemas. The code generators, the compatibility
check and the lint all work on this model, so they cannot disagree about what
a schema means.

Supported JSON Schema subset (anything else is a lint error, never ignored):
  type string|integer|number|boolean|array|object (or a list with "null"),
  properties/required/additionalProperties (false for structs, a schema for
  maps), items, pattern, format, minimum, minLength, minItems, $ref, {} (any).
  `enum` exists only in vocabulary.schema.json, which is generated from
  packages/schemas/vocabulary.json. `const`, oneOf/anyOf/allOf/if/not are not
  supported. Objects are named: inline objects must live in $defs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

SCHEMAS_DIR = Path(__file__).resolve().parent.parent
JSON_DIR = SCHEMAS_DIR / "json"
VOCAB_PATH = SCHEMAS_DIR / "vocabulary.json"
VOCAB_FILE = "vocabulary.schema.json"
PENDING_KEY = "x-onjeon-pending-axis"

STRUCT_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
ALLOWED_KEYS = {
    "$schema", "$id", "$ref", "$defs", "title", "description", "type", "properties",
    "required", "additionalProperties", "items", "pattern", "format", "minimum",
    "minLength", "minItems", "maxItems", PENDING_KEY, "x-onjeon-vocabulary-version",
    "x-onjeon-invariants", "enum",
}
CONSTRAINT_KEYS = ("pattern", "format", "minimum", "minLength", "minItems", "maxItems")


class SchemaError(Exception):
    pass


@dataclass(frozen=True)
class Type:
    kind: str  # string integer number boolean any array map ref enum
    name: str | None = None  # ref -> struct name, enum -> axis id
    item: "Type | None" = None  # element type of array / map
    nullable: bool = False
    constraints: tuple = ()  # sorted (key, value) pairs
    pending_axis: str | None = None

    def signature(self) -> str:
        """Stable description used by the compatibility check. Excludes docs."""
        parts = [self.kind]
        if self.name:
            parts.append(self.name)
        if self.item is not None:
            parts.append(f"<{self.item.signature()}>")
        if self.nullable:
            parts.append("nullable")
        for k, v in self.constraints:
            parts.append(f"{k}={v}")
        return " ".join(parts)


@dataclass
class Field:
    name: str
    type: Type
    required: bool
    description: str = ""


@dataclass
class Struct:
    name: str
    file: str
    fields: list = field(default_factory=list)
    description: str = ""
    root: bool = False  # the file's top-level schema (a wire document)


@dataclass
class Axis:
    id: str
    values: list  # [{"code","concept_ko","screen_ko"}]
    concept_ko: str = ""
    name_ko: str = ""


@dataclass
class Model:
    structs: dict = field(default_factory=dict)  # name -> Struct, definition order
    axes: dict = field(default_factory=dict)  # id -> Axis, vocabulary order
    vocabulary_version: str = ""
    errors: list = field(default_factory=list)

    def struct_names(self):
        return list(self.structs)


def pascal(snake: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in snake.split("_") if p)


def camel(snake: str) -> str:
    p = pascal(snake)
    return p[:1].lower() + p[1:]


def vocabulary_schema(vocab: dict) -> dict:
    """The only place where enum arrays are produced."""
    defs = {}
    for axis in vocab["axes"]:
        defs[axis["id"]] = {
            "type": "string",
            "description": f"{axis['name_ko']}: {axis['concept_ko']}",
            "enum": [v["code"] for v in axis["values"]],
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": VOCAB_FILE,
        "title": "Vocabulary",
        "description": "GENERATED from packages/schemas/vocabulary.json by codegen/gen.py. Do not edit.",
        "x-onjeon-vocabulary-version": vocab["version"],
        "$defs": defs,
    }


def load_vocab(path: Path = VOCAB_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_schema_files(json_dir: Path) -> dict:
    files = {}
    for p in sorted(json_dir.glob("*.schema.json")):
        files[p.name] = json.loads(p.read_text(encoding="utf-8"))
    return files


class _Loader:
    def __init__(self, files: dict, vocab: dict):
        self.files = files
        self.vocab = vocab
        self.model = Model(vocabulary_version=vocab["version"])
        self.axis_ids = {a["id"] for a in vocab["axes"]}

    def err(self, where: str, msg: str):
        self.model.errors.append(f"{where}: {msg}")

    # ---- references -------------------------------------------------------
    def resolve(self, ref: str, cur_file: str, where: str):
        file, _, frag = ref.partition("#")
        file = file or cur_file
        if file in self.files and not frag and self.files[file].get("title"):
            return file, self.files[file]["title"], self.files[file]  # the file's root type
        m = re.fullmatch(r"/\$defs/([A-Za-z0-9_]+)", frag)
        if file not in self.files or not m:
            self.err(where, f"unresolvable $ref {ref!r}")
            return None, None, None
        defs = self.files[file].get("$defs", {})
        if m.group(1) not in defs:
            self.err(where, f"$ref {ref!r}: no such definition")
            return None, None, None
        return file, m.group(1), defs[m.group(1)]

    # ---- types ------------------------------------------------------------
    def parse_type(self, s: dict, file: str, where: str) -> Type:
        for k in s:
            if k not in ALLOWED_KEYS:
                self.err(where, f"unsupported keyword {k!r}")
        if "enum" in s and file != VOCAB_FILE:
            self.err(where, "enum outside vocabulary.schema.json (enums come only from the vocabulary)")
        if "$ref" in s:
            extra = set(s) - {"$ref", "description"}
            if extra:
                self.err(where, f"$ref may only carry description, found {sorted(extra)}")
            rfile, rname, target = self.resolve(s["$ref"], file, where)
            if target is None:
                return Type("any")
            if rfile == VOCAB_FILE:
                return Type("enum", name=rname)
            if target.get("type") == "object" and "properties" in target:
                return Type("ref", name=rname)
            return self.parse_type(target, rfile, f"{rfile}#{rname}")
        pending = s.get(PENDING_KEY)
        if pending is not None:
            if pending in self.axis_ids:
                self.err(where, f"pending axis {pending!r} now exists in the vocabulary: use a $ref to it")
            if s.get("type") != "string" or "pattern" not in s:
                self.err(where, "a pending-axis value must be a string with a pattern")
        t = s.get("type")
        nullable = False
        if isinstance(t, list):
            if len(t) == 2 and "null" in t:
                nullable = True
                t = [x for x in t if x != "null"][0]
            else:
                self.err(where, f"unsupported type list {t!r}")
                t = None
        constraints = tuple(sorted((k, s[k]) for k in CONSTRAINT_KEYS if k in s))
        if "pattern" in s:
            try:
                re.compile(s["pattern"])
            except re.error as e:
                self.err(where, f"bad pattern: {e}")
        if t is None and "type" not in s:
            return Type("any", nullable=True)
        if t in ("string", "integer", "number", "boolean"):
            return Type(t, nullable=nullable, constraints=constraints, pending_axis=pending)
        if t == "array":
            if "items" not in s:
                self.err(where, "array without items")
                return Type("any")
            return Type("array", item=self.parse_type(s["items"], file, where + "[]"), nullable=nullable, constraints=constraints)
        if t == "object":
            ap = s.get("additionalProperties")
            if "properties" not in s and isinstance(ap, dict):
                return Type("map", item=self.parse_type(ap, file, where + "{}"), nullable=nullable)
            self.err(where, "inline object: move it to $defs (objects must be named)")
            return Type("any")
        self.err(where, f"unsupported type {t!r}")
        return Type("any")

    # ---- structs ----------------------------------------------------------
    def parse_struct(self, name: str, s: dict, file: str, root: bool):
        where = f"{file}#{name}"
        for k in s:
            if k not in ALLOWED_KEYS:
                self.err(where, f"unsupported keyword {k!r}")
        if not STRUCT_NAME_RE.match(name):
            self.err(where, "struct names must be PascalCase")
        if name in self.model.structs:
            self.err(where, f"duplicate type name {name!r}")
            return
        if s.get("additionalProperties") is not False:
            self.err(where, "structs must set additionalProperties: false")
        props = s["properties"]
        required = s.get("required", [])
        for r in required:
            if r not in props:
                self.err(where, f"required field {r!r} is not a property")
        if len(set(required)) != len(required):
            self.err(where, "duplicate required entries")
        st = Struct(name, file, description=s.get("description", ""), root=root)
        for fname, fs in props.items():
            if not SNAKE_RE.match(fname):
                self.err(where, f"field {fname!r} must be lower snake_case")
            st.fields.append(Field(fname, self.parse_type(fs, file, f"{where}.{fname}"), fname in required, fs.get("description", "")))
        self.model.structs[name] = st

    def run(self) -> Model:
        for a in self.vocab["axes"]:
            self.model.axes[a["id"]] = Axis(a["id"], a["values"], a.get("concept_ko", ""), a.get("name_ko", ""))
        # the vocabulary schema must be exactly the generated one
        if VOCAB_FILE not in self.files:
            self.err(VOCAB_FILE, "missing (run codegen/gen.py --write)")
        elif self.files[VOCAB_FILE] != vocabulary_schema(self.vocab):
            self.err(VOCAB_FILE, "differs from packages/schemas/vocabulary.json (run codegen/gen.py --write)")
        for file, doc in self.files.items():
            if file == VOCAB_FILE:
                continue
            for key in doc:
                if key not in ALLOWED_KEYS:
                    self.err(file, f"unsupported top-level keyword {key!r}")
            for name, d in doc.get("$defs", {}).items():
                if d.get("type") == "object" and "properties" in d:
                    self.parse_struct(name, d, file, False)
                else:
                    self.parse_type(d, file, f"{file}#{name}")
            if doc.get("type") == "object" and "properties" in doc:
                title = doc.get("title")
                if not title:
                    self.err(file, "root schema needs a title (the type name)")
                else:
                    self.parse_struct(title, doc, file, True)
        names = set(self.model.structs)
        for axis_id in self.model.axes:
            if pascal(axis_id) in names:
                self.err("model", f"type name {pascal(axis_id)!r} collides with vocabulary axis {axis_id!r}")
        return self.model


def build_model(json_dir: Path = JSON_DIR, vocab_path: Path = VOCAB_PATH, strict: bool = True) -> Model:
    model = _Loader(read_schema_files(json_dir), load_vocab(vocab_path)).run()
    if strict and model.errors:
        raise SchemaError("schema lint failed:\n  " + "\n  ".join(model.errors))
    return model


def contracts_version(cargo_toml: Path) -> str:
    in_package = False
    for line in cargo_toml.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.startswith("["):
            in_package = s == "[package]"
        elif in_package:
            m = re.match(r'version\s*=\s*"(\d+\.\d+\.\d+)"', s)
            if m:
                return m.group(1)
    raise SchemaError(f"no package version in {cargo_toml}")
