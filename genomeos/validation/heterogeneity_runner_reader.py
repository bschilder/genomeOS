"""Concrete read-only SQLite decoding (design §§5,7–8,12; runner §§4–5)."""

from __future__ import annotations

import sqlite3

from genomeos.validation.heterogeneity_codec import EncodedB0HEvidence, decode_b0h_evidence
from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt,
    CampaignManifest,
    EvidenceReceipt,
    OwnerLoss,
    PreparedNull,
    StageCompletion,
    StageExecutionFailure,
    StageStart,
    StoredStage,
)
from genomeos.validation.heterogeneity_runner_wire import (
    evidence_receipt,
    read_runner_record,
    record_digest,
    sha256,
)
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId

B0H_SQL_SCHEMA = (
    "CREATE TABLE objects(digest TEXT PRIMARY KEY NOT NULL,kind TEXT NOT NULL,"
    "body BLOB NOT NULL CHECK(typeof(body)='blob'))",
    "CREATE TABLE campaign(singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
    "manifest TEXT NOT NULL REFERENCES objects(digest),"
    "admission TEXT NOT NULL REFERENCES objects(digest),"
    "null_reference TEXT NOT NULL REFERENCES objects(digest))",
    "CREATE TABLE starts(case_id TEXT NOT NULL,stage TEXT NOT NULL,"
    "attempt INTEGER NOT NULL CHECK(attempt IN(-1,0,1)),"
    "digest TEXT UNIQUE NOT NULL REFERENCES objects(digest),"
    "PRIMARY KEY(case_id,stage,attempt))",
    "CREATE TABLE completions(start_digest TEXT PRIMARY KEY REFERENCES starts(digest),"
    "digest TEXT UNIQUE NOT NULL REFERENCES objects(digest),"
    "receipt TEXT UNIQUE REFERENCES objects(digest),failure TEXT UNIQUE REFERENCES objects(digest),"
    "CHECK((receipt IS NULL)!=(failure IS NULL)))",
    "CREATE TABLE metadata(receipt TEXT PRIMARY KEY REFERENCES objects(digest),"
    "body BLOB NOT NULL CHECK(typeof(body)='blob'))",
    "CREATE TABLE payloads(digest TEXT PRIMARY KEY NOT NULL,body BLOB NOT NULL CHECK(typeof(body)='blob'))",
    "CREATE TABLE payload_links(receipt TEXT NOT NULL REFERENCES metadata(receipt),"
    "ordinal INTEGER NOT NULL CHECK(ordinal>=0),payload TEXT NOT NULL REFERENCES payloads(digest),"
    "PRIMARY KEY(receipt,ordinal),UNIQUE(receipt,payload))",
    "CREATE TABLE losses(start_digest TEXT PRIMARY KEY REFERENCES starts(digest),"
    "digest TEXT UNIQUE NOT NULL REFERENCES objects(digest))",
)
B0H_SQL_TABLES = (
    "campaign",
    "completions",
    "losses",
    "metadata",
    "objects",
    "payload_links",
    "payloads",
    "starts",
)


class StoreIntegrityError(ValueError):
    """Unsupported, corrupt or conflicting evidence; never retry automatically."""


class B0HSqlReader:
    """Borrow one connection; expose only exact record reads and whole-store audit."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        manifest: CampaignManifest,
        admission: AdmissionReceipt,
        null: PreparedNull,
    ) -> None:
        self._db = connection
        self.manifest, self.admission, self.null = manifest, admission, null
        self.campaign_sha256 = record_digest(manifest)

    def record(self, digest, cls):
        row = self._db.execute("SELECT kind,body FROM objects WHERE digest=?", (digest,)).fetchone()
        if row is None or type(row[1]) is not bytes or sha256(row[1]) != digest:
            raise StoreIntegrityError("missing or corrupt operational record")
        value = read_runner_record(row[1])
        if type(value) is not cls or row[0] != value.format:
            raise StoreIntegrityError("wrong operational record type")
        return value

    def stage(self, digest: str) -> StoredStage:
        start = self.record(digest, StageStart)
        completed = self._db.execute(
            "SELECT digest,receipt,failure FROM completions WHERE start_digest=?", (digest,)
        ).fetchone()
        lost = self._db.execute("SELECT digest FROM losses WHERE start_digest=?", (digest,)).fetchone()
        loss = None if lost is None else self.record(lost[0], OwnerLoss)
        if loss is not None and (loss.start_sha256 != digest or loss.previous_owner_id != start.owner_id):
            raise StoreIntegrityError("owner loss START identity mismatch")
        if completed is None:
            return StoredStage(start, None, None, None, loss, None, None)
        if completed[0] is None or (completed[1] is None) == (completed[2] is None):
            raise StoreIntegrityError("completion has NULL or unmatched references")
        if loss is not None:
            raise StoreIntegrityError("completed stage also declares owner loss")
        completion = self.record(completed[0], StageCompletion)
        if (
            completion.start_sha256 != digest
            or completion.receipt_sha256 != completed[1]
            or completion.failure_sha256 != completed[2]
        ):
            raise StoreIntegrityError("completion foreign identity mismatch")
        if completed[2] is not None:
            failure = self.record(completed[2], StageExecutionFailure)
            if failure.start_sha256 != digest:
                raise StoreIntegrityError("execution failure START mismatch")
            return StoredStage(start, completion, None, failure, None, None, None)
        receipt = self.record(completed[1], EvidenceReceipt)
        metadata = self._db.execute("SELECT body FROM metadata WHERE receipt=?", (completed[1],)).fetchone()
        if metadata is None:
            raise StoreIntegrityError("missing scientific metadata")
        ordinals = tuple(
            row[0]
            for row in self._db.execute(
                "SELECT ordinal FROM payload_links WHERE receipt=? ORDER BY ordinal", (completed[1],)
            )
        )
        if ordinals != tuple(range(len(ordinals))):
            raise StoreIntegrityError("payload ordinal gap")
        payloads = tuple(
            self._db.execute(
                "SELECT p.digest,p.body FROM payload_links l JOIN payloads p ON p.digest=l.payload "
                "WHERE l.receipt=? ORDER BY l.ordinal",
                (completed[1],),
            )
        )
        encoded = EncodedB0HEvidence(metadata[0], payloads)
        if evidence_receipt(start, encoded, limits=self.manifest.limits) != receipt:
            raise StoreIntegrityError("scientific receipt differs from exact bytes")
        value = decode_b0h_evidence(encoded, limits=self.manifest.limits)
        return StoredStage(start, completion, receipt, None, None, encoded, value)

    def stages(self, case: SbcCaseId) -> tuple[StoredStage, ...]:
        rows = self._db.execute("SELECT digest FROM starts WHERE case_id=?", (case.canonical_id,))
        values = tuple(self.stage(row[0]) for row in rows)
        order = {"generation": 0, "structural": 1, "fit": 2, "quantities": 3, "summary": 4}
        return tuple(
            sorted(
                values,
                key=lambda s: (
                    order[s.start.key.stage],
                    -1 if s.start.key.attempt_id is None else s.start.key.attempt_id,
                ),
            )
        )

    def audit(self) -> None:
        actual_schema = dict(self._db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        expected_schema = {sql.split("TABLE ")[1].split("(")[0]: sql for sql in B0H_SQL_SCHEMA}
        if actual_schema != expected_schema:
            raise StoreIntegrityError("database table definition drift")
        if self._db.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]:
            raise StoreIntegrityError("unexpected database trigger")
        expected = (1, self.campaign_sha256, record_digest(self.admission), record_digest(self.null))
        if self._db.execute("SELECT * FROM campaign").fetchall() != [expected]:
            raise StoreIntegrityError("stored campaign differs")
        if self._db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise StoreIntegrityError("SQLite integrity check failed")
        if self._db.execute("PRAGMA foreign_key_check").fetchall():
            raise StoreIntegrityError("SQLite foreign key check failed")
        used = {self.campaign_sha256, record_digest(self.admission), record_digest(self.null)}
        for case_id, stage_name, attempt, digest in self._db.execute("SELECT * FROM starts"):
            used.add(digest)
            start = self.record(digest, StageStart)
            expected = (
                start.key.case.canonical_id,
                start.key.stage,
                -1 if start.key.attempt_id is None else start.key.attempt_id,
            )
            if (
                expected != (case_id, stage_name, attempt)
                or start.key.case not in self.manifest.cases
                or start.key.campaign_sha256 != self.campaign_sha256
            ):
                raise StoreIntegrityError("stored START index/campaign mismatch")
        for row in self._db.execute("SELECT start_digest,digest,receipt,failure FROM completions"):
            if row[0] is None:
                raise StoreIntegrityError("completion has NULL START reference")
            if self._db.execute("SELECT 1 FROM starts WHERE digest=?", (row[0],)).fetchone() is None:
                raise StoreIntegrityError("completion references unmatched START")
            used.update(value for value in row if value is not None)
        for start_digest, loss_digest in self._db.execute("SELECT start_digest,digest FROM losses"):
            if (
                start_digest is None
                or self._db.execute("SELECT 1 FROM starts WHERE digest=?", (start_digest,)).fetchone() is None
            ):
                raise StoreIntegrityError("loss references unmatched START")
            loss = self.record(loss_digest, OwnerLoss)
            indexed = self.record(start_digest, StageStart)
            if loss.start_sha256 != start_digest or loss.previous_owner_id != indexed.owner_id:
                raise StoreIntegrityError("owner loss START identity mismatch")
            used.add(loss_digest)
        if used != {row[0] for row in self._db.execute("SELECT digest FROM objects")}:
            raise StoreIntegrityError("orphan operational evidence; no receipt-only repair")
        receipts = {
            row[0] for row in self._db.execute("SELECT receipt FROM completions WHERE receipt IS NOT NULL")
        }
        if receipts != {row[0] for row in self._db.execute("SELECT receipt FROM metadata")}:
            raise StoreIntegrityError("orphan or missing metadata")
        linked = {row[0] for row in self._db.execute("SELECT payload FROM payload_links")}
        if linked != {row[0] for row in self._db.execute("SELECT digest FROM payloads")}:
            raise StoreIntegrityError("orphan payload")
        for value in (self.manifest, self.admission, self.null):
            if self.record(record_digest(value), type(value)) != value:
                raise StoreIntegrityError("campaign root differs")

    def inventory(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        self.audit()
        return tuple(
            (
                case.canonical_id,
                tuple(
                    digest
                    for stage in self.stages(case)
                    for digest in (
                        record_digest(stage.start),
                        None if stage.completion is None else record_digest(stage.completion),
                        None if stage.loss is None else record_digest(stage.loss),
                    )
                    if digest is not None
                ),
            )
            for case in self.manifest.cases
        )
