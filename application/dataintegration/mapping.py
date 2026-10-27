"""Configurable column mappings (Pydantic) and the transformations they may apply.

A mapping file says which source column feeds which canonical field, which named transformations run on it, which value maps apply and how
timestamps are read. Every transformation that changes a value is returned as a step so the change is part of the record's history.
"""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .canonical import SourceSystem

MAPPING_DIR = Path(__file__).with_name("mappings")


class Step(BaseModel):
    model_config = ConfigDict(frozen=True)
    field: str
    step: str
    before: Any
    after: Any


class FieldSpec(BaseModel):
    """`source` is a column name (CSV) or a dotted path (JSON, flattened with '.'). A list of sources is joined with '/'."""
    model_config = ConfigDict(extra="forbid")
    source: str | list[str]
    required: bool = False
    transforms: list[str] = Field(default_factory=list)
    valueMap: Optional[str] = None            # name of an entry in MappingConfig.valueMaps; an unmapped value is an error, never passed through
    pattern: Optional[str] = None             # regular expression the TRANSFORMED value must fully match
    allowed: Optional[list[str]] = None       # closed vocabulary for the TRANSFORMED value

    @field_validator("transforms")
    @classmethod
    def known(cls, v):
        bad = [t for t in v if t not in TRANSFORMS]
        if bad:
            raise ValueError(f"unknown transform(s): {bad}")
        return v

    @field_validator("pattern")
    @classmethod
    def compiles(cls, v):
        if v is not None:
            re.compile(v)
        return v


class TimestampSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: str = "occurredAt"
    timezone: str                                       # IANA zone used for source timestamps that carry no offset; mandatory, never guessed
    formats: list[str] = Field(default_factory=lambda: ["iso"])

    @field_validator("timezone")
    @classmethod
    def zone(cls, v):
        if v != "UTC":
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValueError(f"unknown time zone {v}") from exc
        return v


class CaptureOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    createMissingUnits: bool = False                    # register an unknown motor serial (existing create_unit) when a capturable record names it
    historicalShipments: bool = False                   # logistics records may become MOTOR_SHIPPED history; never performs or authorises a shipment


class MappingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mappingId: str
    version: int = Field(ge=1)
    description: str = ""
    sourceSystem: SourceSystem
    adapter: str
    format: Literal["csv", "json"]
    encoding: str = "utf-8"
    delimiter: str = ","
    recordsPath: Optional[str] = None                   # JSON: dotted path to the list of records; None = top-level list
    fields: dict[str, FieldSpec]
    timestamps: TimestampSpec
    valueMaps: dict[str, dict[str, str]] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    capture: CaptureOptions = Field(default_factory=CaptureOptions)

    @model_validator(mode="after")
    def consistent(self):
        if self.timestamps.field not in self.fields:
            raise ValueError("timestamps.field must be one of fields")
        if "recordId" not in self.fields:
            raise ValueError("fields.recordId is required (the source's own record identity)")
        for name, spec in self.fields.items():
            if spec.valueMap and spec.valueMap not in self.valueMaps:
                raise ValueError(f"field {name}: valueMap {spec.valueMap} is not defined")
        if self.format == "csv" and len(self.delimiter) != 1:
            raise ValueError("CSV delimiter must be one character")
        return self

    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_mapping(path) -> MappingConfig:
    p = Path(path)
    if not p.is_file() and (MAPPING_DIR / str(path)).is_file():
        p = MAPPING_DIR / str(path)
    return MappingConfig.model_validate_json(p.read_text(encoding="utf-8"))


# ---- named transformations ------------------------------------------------------------------------------------------------------------------------

def _serial(v):
    return re.sub(r"[\s_]+", "-", v.strip().upper())


TRANSFORMS = {
    "strip": lambda v: v.strip(),
    "upper": lambda v: v.upper(),
    "lower": lambda v: v.lower(),
    "collapse_space": lambda v: re.sub(r"\s+", " ", v).strip(),
    "motor_serial": _serial,                                              # 'mtr 27001' / 'mtr_27001' -> 'MTR-27001'
    "decimal_comma": lambda v: v.replace(",", ".") if re.fullmatch(r"[+-]?\d+,\d+", v.strip()) else v,
    "null_if_blank": lambda v: None if v.strip() == "" else v,
}


def to_text(value) -> Optional[str]:
    """Source cell -> text. JSON numbers become their canonical text; booleans and containers are not text and stay as they are for validation to refuse."""
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, (list, dict)):
        return value
    if isinstance(value, float) and value == int(value) and abs(value) < 1e15:
        return str(int(value)) if "e" not in repr(value) else repr(value)
    return str(value)


def extract(flat: dict, spec: FieldSpec):
    srcs = spec.source if isinstance(spec.source, list) else [spec.source]
    cells = [to_text(flat.get(s)) for s in srcs]
    if any(isinstance(c, (list, dict, bool)) for c in cells):
        raise ValueError("source value is not a scalar")
    if len(cells) == 1:
        return cells[0]
    return None if any(c is None or c == "" for c in cells) else "/".join(c.strip() for c in cells)


def apply_field(name: str, raw, spec: FieldSpec, cfg: MappingConfig) -> tuple[Any, list[Step], Optional[str]]:
    """Run a field's transforms and value map. Returns (value, steps, error). Blank text becomes None before anything else (recorded as a step)."""
    steps: list[Step] = []
    v = raw
    if isinstance(v, str) and v.strip() == "":
        steps.append(Step(field=name, step="blank_to_null", before=v, after=None))
        v = None
    if v is None:
        return None, steps, None
    for t in spec.transforms:
        out = TRANSFORMS[t](v)
        if out != v:
            steps.append(Step(field=name, step=t, before=v, after=out))
        v = out
        if v is None:
            return None, steps, None
    if spec.valueMap:
        table = cfg.valueMaps[spec.valueMap]
        key = v if v in table else v.upper() if v.upper() in table else None
        if key is None:
            return v, steps, f"value {v!r} is not in value map {spec.valueMap}"
        steps.append(Step(field=name, step=f"valueMap:{spec.valueMap}", before=v, after=table[key]))
        v = table[key]
    return v, steps, None


_ISO_SUBSECOND = re.compile(r"(\d{2}:\d{2}:\d{2})[.,]\d+")


def parse_timestamp(raw: str, spec: TimestampSpec) -> tuple[str, list[Step]]:
    """Source timestamp -> whole-second UTC 'YYYY-MM-DDTHH:MM:SSZ'. Raises ValueError. A timestamp without an offset is read in spec.timezone (stated in the
    mapping, never assumed); fractional seconds are truncated and that truncation is a recorded step."""
    steps: list[Step] = []
    text = raw.strip()
    zone = timezone.utc if spec.timezone == "UTC" else ZoneInfo(spec.timezone)
    parsed = None
    for fmt in spec.formats:
        try:
            if fmt == "iso":
                t = text
                if _ISO_SUBSECOND.search(t):
                    t2 = _ISO_SUBSECOND.sub(r"\1", t)
                    steps.append(Step(field=spec.field, step="truncate_subsecond", before=t, after=t2))
                    t = t2
                if t.endswith(("Z", "z")):
                    t = t[:-1] + "+00:00"
                parsed = datetime.fromisoformat(t)
            else:
                parsed = datetime.strptime(text, fmt)
            break
        except ValueError:
            steps = [s for s in steps if s.step != "truncate_subsecond"]
            parsed = None
    if parsed is None:
        raise ValueError(f"timestamp {raw!r} matches none of {spec.formats}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
        steps.append(Step(field=spec.field, step=f"assume_zone:{spec.timezone}", before=text, after=parsed.isoformat()))
    utc = parsed.astimezone(timezone.utc).replace(microsecond=0)
    out = utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    steps.append(Step(field=spec.field, step="to_utc", before=text, after=out))
    return out, steps
