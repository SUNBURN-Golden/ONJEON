"""Minimal validator for the JSON Schema subset used by packages/schemas/json (stdlib only).

Used by the tests: fixtures must validate, deliberately broken documents must not.
Supports type (including ["x","null"]), properties, required, additionalProperties,
items, minItems/maxItems, pattern, minLength, minimum, format date/date-time,
enum, and $ref (same file, other file, file root).
"""
from __future__ import annotations

import re
from pathlib import Path

import schema_model as sm

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Validator:
    def __init__(self, json_dir: Path = sm.JSON_DIR):
        self.files = sm.read_schema_files(json_dir)

    def root_file(self, type_name: str) -> str:
        for name, doc in self.files.items():
            if doc.get("title") == type_name:
                return name
        raise KeyError(type_name)

    def validate(self, instance, type_name: str) -> list:
        file = self.root_file(type_name)
        errors: list = []
        self._check(instance, self.files[file], file, "$", errors)
        return errors

    def _resolve(self, ref: str, cur: str):
        file, _, frag = ref.partition("#")
        file = file or cur
        doc = self.files[file]
        if not frag:
            return doc, file
        name = frag.rsplit("/", 1)[-1]
        return doc["$defs"][name], file

    def _check(self, inst, schema: dict, file: str, path: str, errors: list):
        if "$ref" in schema:
            target, tfile = self._resolve(schema["$ref"], file)
            self._check(inst, target, tfile, path, errors)
            return
        if "enum" in schema and inst not in schema["enum"]:
            errors.append(f"{path}: {inst!r} is not one of the vocabulary values")
            return
        t = schema.get("type")
        if t is None:
            return  # any
        types = t if isinstance(t, list) else [t]
        if inst is None:
            if "null" not in types:
                errors.append(f"{path}: null not allowed")
            return
        kind = [x for x in types if x != "null"][0]
        if kind == "string":
            if not isinstance(inst, str):
                errors.append(f"{path}: expected string")
                return
            if "pattern" in schema and not re.search(schema["pattern"], inst):
                errors.append(f"{path}: {inst!r} does not match {schema['pattern']}")
            if len(inst) < schema.get("minLength", 0):
                errors.append(f"{path}: shorter than minLength")
            if schema.get("format") == "date" and not DATE_RE.match(inst):
                errors.append(f"{path}: not a date")
        elif kind == "integer":
            if isinstance(inst, bool) or not isinstance(inst, int):
                errors.append(f"{path}: expected integer")
            elif inst < schema.get("minimum", inst):
                errors.append(f"{path}: below minimum")
        elif kind == "number":
            if isinstance(inst, bool) or not isinstance(inst, (int, float)):
                errors.append(f"{path}: expected number")
        elif kind == "boolean":
            if not isinstance(inst, bool):
                errors.append(f"{path}: expected boolean")
        elif kind == "array":
            if not isinstance(inst, list):
                errors.append(f"{path}: expected array")
                return
            if len(inst) < schema.get("minItems", 0):
                errors.append(f"{path}: fewer than minItems")
            if len(inst) > schema.get("maxItems", len(inst)):
                errors.append(f"{path}: more than maxItems")
            for n, item in enumerate(inst):
                self._check(item, schema["items"], file, f"{path}[{n}]", errors)
        elif kind == "object":
            if not isinstance(inst, dict):
                errors.append(f"{path}: expected object")
                return
            props = schema.get("properties")
            if props is None:  # map
                for k, v in inst.items():
                    self._check(v, schema["additionalProperties"], file, f"{path}.{k}", errors)
                return
            for r in schema.get("required", []):
                if r not in inst:
                    errors.append(f"{path}: missing required {r!r}")
            for k, v in inst.items():
                if k not in props:
                    errors.append(f"{path}: unknown field {k!r}")
                else:
                    self._check(v, props[k], file, f"{path}.{k}", errors)
