"""Result models shared by the ingest, planning, capture and report stages."""
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .canonical import CanonicalEvent
from .mapping import Step

Severity = Literal["ERROR", "WARNING", "INFO"]
Outcome = Literal["ACCEPTED", "REJECTED", "UNRESOLVED"]

# Issue codes. ERROR codes decide the outcome: field/format errors reject a record, relationship errors leave it unresolved.
REJECT_CODES = {"MALFORMED_ROW", "MISSING_REQUIRED", "BAD_FORMAT", "BAD_VALUE", "BAD_TIMESTAMP", "BAD_IDENTITY", "BAD_SIGNAL_QUALITY", "SCHEMA_ERROR",
                "EXACT_DUPLICATE_IN_BATCH", "FILE_UNREADABLE", "MISSING_COLUMN"}


class Issue(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    severity: Severity = "ERROR"
    message: str
    field: Optional[str] = None
    related: Optional[str] = None               # canonicalId or source record id of the record this one conflicts with / depends on


class RecordResult(BaseModel):
    """Everything known about one source row: the verbatim original, each transformation applied, issues found and the final disposition."""
    rowIndex: int
    sourceSystem: str
    mappingId: str
    fileSha256: str
    sourceRecordId: Optional[str] = None
    motor: Optional[str] = None                 # motor the record is about (canonical, or resolved from its work order)
    raw: Any                                    # verbatim original record (CSV: header + cells as read; JSON: the object)
    mapped: dict = Field(default_factory=dict, exclude=True, repr=False)   # transformed field values handed to the adapter
    steps: list[Step] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    canonical: Optional[CanonicalEvent] = None
    outcome: Optional[Outcome] = None
    disposition: Optional[str] = None           # CAPTURE | STAGE_ONLY | ALREADY_IMPORTED | duplicate/rejection reason
    reason: Optional[str] = None
    ledgerEventIds: list[str] = Field(default_factory=list)

    def add(self, code, message, severity="ERROR", field=None, related=None):
        self.issues.append(Issue(code=code, severity=severity, message=message, field=field, related=related))

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == "ERROR"]


class FileResult(BaseModel):
    sourceSystem: str
    mappingId: str
    mappingSha256: str
    name: str
    sha256: str
    bytes: int
    format: str
    rows: int = 0
    blankRowsSkipped: int = 0
    fileIssues: list[Issue] = Field(default_factory=list)
    records: list[RecordResult] = Field(default_factory=list)
    content: Optional[bytes] = Field(default=None, exclude=True, repr=False)
