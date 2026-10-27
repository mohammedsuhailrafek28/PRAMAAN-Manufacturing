"""Read a CSV/JSON export, apply its mapping, validate it (Frictionless schema), build canonical events (adapter + Pydantic) and find duplicates (pandas).

Nothing here touches the ledger or the staging store. The original bytes are hashed and every row is kept verbatim in the result.
"""
import csv
import hashlib
import io
import json
import re
import warnings
from pathlib import Path

import pandas as pd

from .adapters import AdapterError, adapter_for
from .canonical import SERIAL_RE
from .mapping import MappingConfig, Step, apply_field, extract, parse_timestamp
from .models import FileResult, Issue, RecordResult

TS_PATTERN = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"


def _flatten(obj, prefix="", out=None):
    out = {} if out is None else out
    for k, v in obj.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            _flatten(v, key + ".", out)
        else:
            out[key] = v
    return out


def _no_dupes(pairs):
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate key in JSON object")
    return dict(pairs)


def _decode(data: bytes, cfg: MappingConfig) -> str:
    enc = "utf-8-sig" if cfg.encoding.lower().replace("_", "-") in ("utf-8", "utf8") else cfg.encoding
    return data.decode(enc)


def read_rows(data: bytes, cfg: MappingConfig, result: FileResult) -> list[tuple[int, object, dict | None]]:
    """-> [(rowIndex, verbatim raw, flat dict or None when the row is structurally malformed)]. File-level problems go to result.fileIssues."""
    try:
        text = _decode(data, cfg)
    except (UnicodeDecodeError, LookupError) as exc:
        result.fileIssues.append(Issue(code="FILE_UNREADABLE", message=f"cannot decode as {cfg.encoding}: {exc}"))
        return []
    rows: list = []
    if cfg.format == "csv":
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=cfg.delimiter, strict=False)
        try:
            table = list(reader)
        except csv.Error as exc:
            result.fileIssues.append(Issue(code="FILE_UNREADABLE", message=f"CSV error: {exc}"))
            return []
        if not table:
            result.fileIssues.append(Issue(code="FILE_UNREADABLE", message="file is empty"))
            return []
        header = [h.strip() for h in table[0]]
        if len(set(header)) != len(header):
            result.fileIssues.append(Issue(code="FILE_UNREADABLE", message="duplicate column names in header"))
            return []
        i = 0
        for cells in table[1:]:
            if not any(c.strip() for c in cells):
                result.blankRowsSkipped += 1
                continue
            i += 1
            raw = dict(header=header, cells=cells)
            rows.append((i, raw, dict(zip(header, cells)) if len(cells) == len(header) else None))
        present = set(header)
    else:
        try:
            doc = json.loads(text, object_pairs_hook=_no_dupes, parse_constant=lambda c: (_ for _ in ()).throw(ValueError(f"{c} is not valid JSON")))
        except ValueError as exc:
            result.fileIssues.append(Issue(code="FILE_UNREADABLE", message=f"invalid JSON: {exc}"))
            return []
        node = doc
        for part in filter(None, (cfg.recordsPath or "").split(".")):
            node = node.get(part) if isinstance(node, dict) else None
        if not isinstance(node, list):
            result.fileIssues.append(Issue(code="FILE_UNREADABLE", message=f"records not found at {cfg.recordsPath or '<top level>'} (expected a list)"))
            return []
        present = set()
        for i, item in enumerate(node, 1):
            if isinstance(item, dict):
                flat = _flatten(item)
                present |= set(flat)
                rows.append((i, item, flat))
            else:
                rows.append((i, item, None))
    sources = {s for spec in cfg.fields.values() for s in (spec.source if isinstance(spec.source, list) else [spec.source])}
    for name, spec in cfg.fields.items():
        for s in (spec.source if isinstance(spec.source, list) else [spec.source]):
            if spec.required and s not in present and (cfg.format == "csv" or rows):
                result.fileIssues.append(Issue(code="MISSING_COLUMN", message=f"required source column/path {s!r} (for {name}) is absent", field=name))
    return rows


def _frictionless_issues(names, cfg, table):
    """Validate the mapped table against a Frictionless schema (required, pattern, closed vocabulary). -> {(table position 0-based, field): (code, note)}"""
    from frictionless import Resource, Schema
    fields = []
    for name in names:
        spec = cfg.fields[name]
        c = {}
        if spec.required:
            c["required"] = True
        pat = spec.pattern or (TS_PATTERN if name == cfg.timestamps.field else None)
        if pat:
            c["pattern"] = pat                  # frictionless anchors the pattern: the whole value must match
        if spec.allowed:
            c["enum"] = list(spec.allowed)
        fields.append(dict(name=name, type="string", **({"constraints": c} if c else {})))
    schema = Schema.from_descriptor(dict(fields=fields))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = Resource(data=[names] + table, schema=schema).validate()
    out = {}
    for task in report.tasks:
        for err in task.errors:
            note = err.note or ""
            code = "MISSING_REQUIRED" if "required" in note else "BAD_FORMAT" if "pattern" in note else "BAD_VALUE" if "enum" in note else "SCHEMA_ERROR"
            out.setdefault(((err.row_number or 2) - 2, getattr(err, "field_name", None)), (code, f"{err.title}: {note}".strip(": ")))
    return out


def ingest(path, cfg: MappingConfig, *, data: bytes | None = None, name: str | None = None) -> FileResult:
    """One export file -> FileResult with one RecordResult per row (outcome still undecided except for rejections found here)."""
    adapter = adapter_for(cfg)
    if data is None:
        data = Path(path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    res = FileResult(sourceSystem=cfg.sourceSystem.value, mappingId=f"{cfg.mappingId}@{cfg.version}", mappingSha256=cfg.sha256(), name=name or (Path(path).name if path else "<memory>"),
                     sha256=sha, bytes=len(data), format=cfg.format, content=data)
    raw_rows = read_rows(data, cfg, res)
    res.rows = len(raw_rows)
    if any(i.code in ("FILE_UNREADABLE", "MISSING_COLUMN") for i in res.fileIssues):
        return res
    names = list(cfg.fields)
    table, positions = [], []
    for idx, raw, flat in raw_rows:
        rec = RecordResult(rowIndex=idx, sourceSystem=cfg.sourceSystem.value, mappingId=res.mappingId, fileSha256=sha, raw=raw)
        res.records.append(rec)
        if flat is None:
            n = len(raw["cells"]) if isinstance(raw, dict) and "cells" in raw else None
            rec.add("MALFORMED_ROW", f"row has {n} cells, header has {len(raw['header'])}" if n is not None else "record is not an object")
            continue
        mapped = {}
        for fname in names:
            spec = cfg.fields[fname]
            try:
                value, steps, err = apply_field(fname, extract(flat, spec), spec, cfg)
            except ValueError as exc:
                rec.add("BAD_FORMAT", str(exc), field=fname); value, steps = None, []
            else:
                if err:
                    rec.add("BAD_VALUE", err, field=fname)
            rec.steps += steps
            if fname == cfg.timestamps.field and value is not None:
                try:
                    value, tsteps = parse_timestamp(value, cfg.timestamps)
                    rec.steps += tsteps
                except ValueError as exc:
                    rec.add("BAD_TIMESTAMP", str(exc), field=fname); value = None
            mapped[fname] = value
        rec.sourceRecordId = mapped.get("recordId")
        rec.mapped = mapped
        table.append([mapped[n] for n in names]); positions.append(rec)
    if table:
        errors = _frictionless_issues(names, cfg, table)
        for (pos, fname), (code, msg) in sorted(errors.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
            rec = positions[pos]
            if any(i.field == fname for i in rec.issues):
                continue                                    # already reported (bad timestamp / value map)
            if fname == "motorSerial" and code == "BAD_FORMAT":
                code = "BAD_IDENTITY"
            what = {"MISSING_REQUIRED": "is empty or missing", "BAD_FORMAT": "does not match its expected format", "BAD_VALUE": "is not an allowed value",
                    "BAD_IDENTITY": "is not a valid motor serial"}.get(code, "failed schema validation")
            rec.add(code, f"field '{fname}' {what} ({msg})", field=fname)
    for rec in positions:
        if rec.errors:
            continue
        m = rec.mapped
        if rec.sourceRecordId is None:
            rec.add("MISSING_REQUIRED", "record has no source record id", field="recordId")
            continue
        try:
            rec.canonical = adapter(m, cfg)
        except AdapterError as exc:
            rec.add(exc.code, exc.message, field=exc.field)
    for rec in res.records:
        if rec.errors:
            rec.outcome, rec.disposition = "REJECTED", "REJECTED_" + rec.errors[0].code
            rec.reason = "; ".join(f"{i.code}: {i.message}" for i in rec.errors)
    return res


def find_duplicates(files: list[FileResult]) -> None:
    """Same (system, source record id) more than once across the supplied files. Identical content: the later copies are rejected as duplicates.
    Different content: nothing about that record id can be trusted, so every copy is left UNRESOLVED as contradictory."""
    rows = [dict(f=fi, r=r, system=r.sourceSystem, rid=r.canonical.sourceRecordId, sha=r.canonical.contentSha256)
            for fi, f in enumerate(files) for r in f.records if r.canonical is not None and r.outcome is None]
    if not rows:
        return
    df = pd.DataFrame(rows)
    for (_, rid), group in df.groupby(["system", "rid"], sort=False):
        if len(group) < 2:
            continue
        first = group.iloc[0]["r"]
        if group["sha"].nunique() == 1:
            for _, row in group.iloc[1:].iterrows():
                r = row["r"]
                r.add("EXACT_DUPLICATE_IN_BATCH", f"identical to row {first.rowIndex} of {files[group.iloc[0]['f']].name} (same record id, same content)", related=first.canonical.canonicalId)
                r.outcome, r.disposition, r.reason = "REJECTED", "REJECTED_EXACT_DUPLICATE_IN_BATCH", "exact duplicate of an earlier row in this import"
        else:
            for _, row in group.iterrows():
                r = row["r"]
                others = [f"row {o['r'].rowIndex} of {files[o['f']].name}" for _, o in group.iterrows() if o["r"] is not r]
                r.add("CONTRADICTORY_DUPLICATE", f"record id {rid!r} appears with different content ({', '.join(others)}); none of the copies is used", related=first.canonical.canonicalId)
                r.outcome, r.disposition, r.reason = "UNRESOLVED", "UNRESOLVED_CONTRADICTORY_DUPLICATE", "same record id with contradictory content"
