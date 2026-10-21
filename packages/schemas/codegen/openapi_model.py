"""Language-neutral model of packages/schemas/openapi/*.v1.yaml (stdlib only).

The three documents are written as JSON, which is valid YAML 1.2, because the repository's tooling
has no YAML parser and the code generators are stdlib-only. Any YAML tool reads them.

The component schemas use the same JSON Schema subset as packages/schemas/json (see schema_model.py).
They are turned into pseudo schema files (`api_<surface>.schema.json`) and loaded together with the
contract schemas, so one loader and one lint cover both, and API structs can refer to contract structs
and vocabulary enums by name. Query parameters become `<OperationId>Query` structs. A multipart form
drops its binary parts (they are not JSON). Everything that cannot be expressed is a lint error here,
never silently skipped.

This module also holds the API-level lint: release_id on every 2xx body, no public cache headers on
personal and console responses, skeleton operations marked and off by default.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import schema_model as sm

OPENAPI_DIR = sm.SCHEMAS_DIR / "openapi"
SURFACES = ("public", "personal", "console")
SURFACE_PREFIX = {"public": "/v1/", "personal": "/v1/", "console": "/console/v1/"}
METHODS = ("get", "put", "post", "delete", "patch")
PRIVATE_CACHE = "private, no-store"
SHARED_CACHE_DIRECTIVES = ("public", "s-maxage", "max-age", "stale-while-revalidate", "stale-if-error", "immutable")
OPERATION_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class Operation:
    id: str
    surface: str
    method: str
    path: str
    cache: str  # public_keyed | no_store | private_no_store
    request: str | None  # struct name of the JSON body, or the form struct for multipart
    response: str  # struct name of the 200 body
    query: str | None  # `<OperationId>Query` struct name
    multipart: bool
    skeleton: bool
    flag: str | None
    cache_key: tuple
    roles: tuple
    summary: str
    path_params: tuple = ()


@dataclass
class ApiModel:
    docs: dict
    model: sm.Model
    ops: list = field(default_factory=list)
    api_structs: list = field(default_factory=list)  # sm.Struct, surface order then definition order
    skeleton_only: set = field(default_factory=set)  # struct names reachable only from skeleton operations
    errors: list = field(default_factory=list)

    def structs_of(self, surface: str) -> list:
        return [s for s in self.api_structs if s.file == f"api_{surface}.schema.json"]


def load_docs(openapi_dir: Path = OPENAPI_DIR) -> dict:
    docs = {}
    for surface in SURFACES:
        path = openapi_dir / f"{surface}.v1.yaml"
        docs[surface] = json.loads(path.read_text(encoding="utf-8"))
    return docs


def pascal_op(op_id: str) -> str:
    return sm.pascal(op_id)


def rewrite_refs(node, where: str, errors: list):
    """`#/components/schemas/X` -> `#/$defs/X`; `../json/f.schema.json#...` -> `f.schema.json#...`."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "$ref":
                if v.startswith("#/components/schemas/"):
                    out[k] = "#/$defs/" + v[len("#/components/schemas/"):]
                elif v.startswith("../json/"):
                    out[k] = v[len("../json/"):]
                else:
                    errors.append(f"{where}: unsupported $ref {v!r}")
                    out[k] = v
            else:
                out[k] = rewrite_refs(v, where, errors)
        return out
    if isinstance(node, list):
        return [rewrite_refs(v, where, errors) for v in node]
    return node


def strip_binary_parts(schema: dict) -> dict:
    s = copy.deepcopy(schema)
    props = s.get("properties", {})
    gone = [k for k, v in props.items() if v.get("format") == "binary"]
    for k in gone:
        del props[k]
    if "required" in s:
        s["required"] = [r for r in s["required"] if r not in gone]
    return s


def iter_operations(doc: dict):
    for path, item in doc["paths"].items():
        for method in METHODS:
            if method in item:
                yield path, method, item[method]


def body_schema(o: dict):
    rb = o.get("requestBody")
    if not rb:
        return None, False
    content = rb["content"]
    if "application/json" in content:
        return content["application/json"]["schema"], False
    return content["multipart/form-data"]["schema"], True


def ok_schema(o: dict):
    return o["responses"]["200"]["content"]["application/json"]["schema"]


def _type_name(ref: str, files: dict) -> str | None:
    """Struct name a $ref points at (after rewrite_refs)."""
    file, _, frag = ref.partition("#")
    if not frag:
        return files.get(file, {}).get("title")
    return frag.rsplit("/", 1)[-1]


def pseudo_files(docs: dict, errors: list) -> dict:
    files = {}
    for surface, doc in docs.items():
        defs = {}
        multipart_forms = set()
        for _, _, o in iter_operations(doc):
            schema, multi = body_schema(o)
            if multi and "$ref" in schema:
                multipart_forms.add(schema["$ref"].rsplit("/", 1)[-1])
        for name, schema in doc["components"]["schemas"].items():
            if name in multipart_forms:
                schema = strip_binary_parts(schema)
            defs[name] = rewrite_refs(schema, f"{surface}#{name}", errors)
        for path, method, o in iter_operations(doc):
            params = [p for p in o.get("parameters", []) if p["in"] == "query"]
            if params:
                props = {}
                for p in params:
                    ps = rewrite_refs(p["schema"], f"{surface} {o['operationId']}", errors)
                    if "description" in p:
                        ps = dict(ps, description=p["description"])
                    props[p["name"]] = ps
                defs[pascal_op(o["operationId"]) + "Query"] = {
                    "type": "object",
                    "description": f"{method.upper()} {path} 쿼리 파라미터",
                    "properties": props,
                    "required": [p["name"] for p in params if p.get("required")],
                    "additionalProperties": False,
                }
        files[f"api_{surface}.schema.json"] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"api_{surface}.schema.json",
            "$defs": defs,
        }
    return files


def load_header(doc: dict, node: dict):
    """(header object, component name); (None, name) when the $ref does not resolve."""
    if "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        return doc["components"]["headers"].get(name), name
    return node, None


def response_headers(doc: dict, resp: dict) -> dict:
    if "$ref" in resp:
        resp = doc["components"]["responses"][resp["$ref"].rsplit("/", 1)[-1]]
    return resp.get("headers", {})


def build(docs: dict | None = None, json_dir: Path = sm.JSON_DIR, vocab_path: Path = sm.VOCAB_PATH) -> ApiModel:
    docs = docs if docs is not None else load_docs()
    errors: list = []
    vocab = sm.load_vocab(vocab_path)
    files = sm.read_schema_files(json_dir)
    files[sm.VOCAB_FILE] = sm.vocabulary_schema(vocab)
    pseudo = pseudo_files(docs, errors)
    files.update(pseudo)
    model = sm._Loader(files, vocab).run()
    am = ApiModel(docs=docs, model=model)
    am.errors = errors + list(model.errors)
    am.api_structs = [s for s in model.structs.values() if s.file in pseudo]
    api_names = {s.name for s in am.api_structs}

    seen_ops = {}
    seen_routes = {}
    for surface, doc in docs.items():
        for path, method, o in iter_operations(doc):
            where = f"{surface} {method.upper()} {path}"
            op_id = o.get("operationId", "")
            if not OPERATION_ID_RE.match(op_id):
                am.errors.append(f"{where}: operationId must be snake_case")
            if op_id in seen_ops:
                am.errors.append(f"{where}: operationId {op_id!r} also used by {seen_ops[op_id]}")
            seen_ops[op_id] = where
            if not path.startswith(SURFACE_PREFIX[surface]):
                am.errors.append(f"{where}: {surface} paths must start with {SURFACE_PREFIX[surface]}")
            if (method, path) in seen_routes:
                am.errors.append(f"{where}: route also defined in {seen_routes[(method, path)]}")
            seen_routes[(method, path)] = surface
            body, multi = body_schema(o)
            req = None
            if body is not None:
                if "$ref" not in body:
                    am.errors.append(f"{where}: request body must be a $ref")
                else:
                    req = _type_name(rewrite_refs(body, where, am.errors)["$ref"], files)
            resp_schema = ok_schema(o)
            resp = _type_name(rewrite_refs(resp_schema, where, am.errors)["$ref"], files) if "$ref" in resp_schema else None
            if resp is None:
                am.errors.append(f"{where}: 200 body must be a $ref to a named type")
            cache_hdr = o["responses"]["200"].get("headers", {}).get("Cache-Control", {}).get("$ref", "")
            cache_name = cache_hdr.rsplit("/", 1)[-1]
            if surface == "public":
                cache = "public_keyed" if cache_name == "CacheControlPublic" else "no_store"
            else:
                cache = "private_no_store"
            qparams = [p for p in o.get("parameters", []) if p["in"] == "query"]
            pparams = tuple(p["name"] for p in o.get("parameters", []) if p["in"] == "path")
            am.ops.append(Operation(
                id=op_id, surface=surface, method=method.upper(), path=path, cache=cache, request=req,
                response=resp or "", query=(pascal_op(op_id) + "Query") if qparams else None, multipart=multi,
                skeleton=o.get("x-onjeon-skeleton") is True, flag=o.get("x-onjeon-flag"),
                cache_key=tuple(o.get("x-onjeon-cache-key", ())), roles=tuple(o.get("x-onjeon-roles", ())),
                summary=o.get("summary", ""), path_params=pparams))
    am.skeleton_only = _skeleton_only(am, api_names)
    am.errors += lint(am)
    return am


def _reachable(model: sm.Model, roots) -> set:
    seen = set()
    stack = [r for r in roots if r]
    while stack:
        n = stack.pop()
        if n in seen or n not in model.structs:
            continue
        seen.add(n)

        def walk(t):
            if t.kind == "ref":
                stack.append(t.name)
            if t.item is not None:
                walk(t.item)

        for f in model.structs[n].fields:
            walk(f.type)
    return seen


def _skeleton_only(am: ApiModel, api_names: set) -> set:
    live = _reachable(am.model, [x for o in am.ops if not o.skeleton for x in (o.request, o.response, o.query)]
                      + ["ErrorResponse"])
    skel = _reachable(am.model, [x for o in am.ops if o.skeleton for x in (o.request, o.response, o.query)])
    return (skel - live) & api_names


# ---------------------------------------------------------------- API-level lint
def _resolve_schema_struct(am: ApiModel, schema: dict):
    if "$ref" not in schema:
        return None
    ref = schema["$ref"]
    if ref.startswith("#/components/schemas/"):
        return am.model.structs.get(ref.rsplit("/", 1)[-1])
    name = ref[len("../json/"):] if ref.startswith("../json/") else ref
    file, _, frag = name.partition("#")
    if frag:
        return am.model.structs.get(frag.rsplit("/", 1)[-1])
    for st in am.model.structs.values():
        if st.file == file and st.root:
            return st
    return None


def lint(am: ApiModel) -> list:
    errs = []
    for surface, doc in am.docs.items():
        policy = doc.get("x-onjeon-cache-policy", {})
        if doc.get("x-onjeon-surface") != surface:
            errs.append(f"{surface}: x-onjeon-surface must be {surface!r}")
        if not doc.get("openapi", "").startswith("3.1"):
            errs.append(f"{surface}: openapi must be 3.1.x")
        if surface != "public":
            if policy.get("public_cache") != "forbidden":
                errs.append(f"{surface}: x-onjeon-cache-policy.public_cache must be 'forbidden'")
            for d in SHARED_CACHE_DIRECTIVES:
                if d not in policy.get("forbidden_directives", []):
                    errs.append(f"{surface}: forbidden_directives must list {d!r}")
        for path, method, o in iter_operations(doc):
            where = f"{surface} {method.upper()} {path}"
            responses = o["responses"]
            if "200" not in responses:
                errs.append(f"{where}: no 200 response")
                continue
            # every JSON body of a 2xx response carries release_id (required, ReleaseId-typed)
            for code, resp in responses.items():
                hdrs = response_headers(doc, resp)
                cc, cc_name = load_header(doc, hdrs["Cache-Control"]) if "Cache-Control" in hdrs else (None, None)
                if cc is None:
                    errs.append(f"{where} {code}: response must declare a resolvable Cache-Control header")
                elif surface != "public":
                    if cc.get("schema", {}).get("enum") != [PRIVATE_CACHE]:
                        errs.append(f"{where} {code}: {surface} responses must pin Cache-Control to {PRIVATE_CACHE!r}")
                if code.startswith("2"):
                    if "X-Onjeon-Release-Id" not in hdrs:
                        errs.append(f"{where} {code}: missing X-Onjeon-Release-Id header")
                    st = _resolve_schema_struct(am, responses[code]["content"]["application/json"]["schema"])
                    if st is None:
                        errs.append(f"{where} {code}: body type not found")
                    else:
                        f = next((x for x in st.fields if x.name == "release_id"), None)
                        if f is None or not f.required:
                            errs.append(f"{where} {code}: {st.name} has no required release_id")
                        elif f.type.kind != "string" or ("pattern", "^rel:[0-9]{8}-[0-9]+$") not in f.type.constraints:
                            errs.append(f"{where} {code}: {st.name}.release_id must be a ReleaseId")
            if surface == "public":
                cc = o["responses"]["200"]["headers"]["Cache-Control"]["$ref"].rsplit("/", 1)[-1]
                if method == "get" and cc != "CacheControlPublic":
                    errs.append(f"{where}: public GET must be publicly cacheable")
                if method != "get" and cc == "CacheControlPublic":
                    errs.append(f"{where}: only GET may be publicly cached")
                if cc == "CacheControlPublic" and "release_id" not in o.get("x-onjeon-cache-key", []):
                    errs.append(f"{where}: cache key must include release_id")
                if "x-onjeon-skeleton" in o:
                    errs.append(f"{where}: skeleton operations belong to the personal document")
            elif "x-onjeon-cache-key" in o:
                errs.append(f"{where}: {surface} operations have no cache key (no public cache)")
            if "x-onjeon-skeleton" in o:
                if o["x-onjeon-skeleton"] is not True:
                    errs.append(f"{where}: x-onjeon-skeleton must be true when present")
                if not o.get("x-onjeon-flag") or o.get("x-onjeon-flag-default") is not False:
                    errs.append(f"{where}: a skeleton operation needs x-onjeon-flag and x-onjeon-flag-default: false")
                if o.get("tags") != ["skeleton"]:
                    errs.append(f"{where}: a skeleton operation is tagged exactly ['skeleton']")
            elif o.get("x-onjeon-flag") or "skeleton" in o.get("tags", []):
                errs.append(f"{where}: flag/skeleton tag without x-onjeon-skeleton: true")
        for name in doc["components"]["schemas"]:
            if "skeleton" in name.lower():
                errs.append(f"{surface}#{name}: do not put 'skeleton' in a type name; the reachability rule gates it")
    return errs
