"""Single-owner SQLite B0H evidence (design §§5,7–8,12; runner §§4–5)."""

from __future__ import annotations

import fcntl
import os
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

from genomeos.validation.heterogeneity_codec import EncodedB0HEvidence
from genomeos.validation.heterogeneity_runner_reader import (
    B0H_SQL_SCHEMA,
    B0H_SQL_TABLES,
    B0HSqlReader,
    StoreIntegrityError,
)
from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt,
    CampaignManifest,
    EvidenceReceipt,
    OwnerLoss,
    PreparedNull,
    PublicationPacket,
    StageCompletion,
    StageExecutionFailure,
    StageStart,
    StoredStage,
)
from genomeos.validation.heterogeneity_runner_wire import (
    evidence_receipt,
    read_runner_record,
    record_digest,
    runner_record_bytes,
    sha256,
)
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId

_RETRYABLE = {
    sqlite3.SQLITE_BUSY,
    sqlite3.SQLITE_LOCKED,
    sqlite3.SQLITE_IOERR,
    sqlite3.SQLITE_FULL,
    sqlite3.SQLITE_CANTOPEN,
}


class StoreUnavailable(RuntimeError):
    """A storage I/O or lock failure prevented establishing the exact state."""


class PendingPublication(StoreUnavailable):
    """Exact known live bytes remain available; this is no second science delivery."""

    def __init__(self, packet: PublicationPacket, cause: BaseException) -> None:
        if type(packet) is not PublicationPacket:
            raise StoreIntegrityError("pending publication requires exact immutable packet")
        super().__init__("publication pending; science paused")
        self.packet = packet
        self.__cause__ = cause


class LocalB0HStore:
    def __init__(
        self,
        database: Path,
        *,
        manifest: CampaignManifest,
        admission: AdmissionReceipt,
        null: PreparedNull,
        owner_id: str,
    ) -> None:
        self.database = database
        self.manifest = read_runner_record(runner_record_bytes(manifest))
        self.admission = read_runner_record(runner_record_bytes(admission))
        self.null = read_runner_record(runner_record_bytes(null))
        if type(self.manifest) is not CampaignManifest or type(self.admission) is not AdmissionReceipt:
            raise StoreIntegrityError("wrong campaign or admission root")
        if type(self.null) is not PreparedNull or type(owner_id) is not str or not owner_id:
            raise StoreIntegrityError("wrong null or owner identity")
        if (
            record_digest(admission) != manifest.admission_sha256
            or record_digest(null) != manifest.null_sha256
            or admission.source != manifest.source
            or admission.runtime != manifest.runtime
        ):
            raise StoreIntegrityError("campaign admission/null identity mismatch")
        if (
            database.name != "study.sqlite3"
            or database.parent.resolve() != Path(admission.storage.database_parent)
            or database.parent.stat().st_dev != admission.storage.device_id
        ):
            raise StoreIntegrityError("database filesystem differs from admission")
        self.owner_id = owner_id
        self.campaign_sha256 = record_digest(self.manifest)
        self._create = False
        self._lock = None
        self._db = None

    @classmethod
    def create(
        cls,
        database: Path,
        *,
        manifest: CampaignManifest,
        admission: AdmissionReceipt,
        null: PreparedNull,
        owner_id: str,
    ) -> LocalB0HStore:
        result = cls(database, manifest=manifest, admission=admission, null=null, owner_id=owner_id)
        result._create = True
        return result

    def __enter__(self) -> LocalB0HStore:
        lockpath = self.database.with_name(self.database.name + ".lock")
        if self.database.is_symlink() or lockpath.is_symlink():
            raise StoreIntegrityError("database/lock symlink refused")
        if not self._create and not self.database.is_file():
            raise StoreIntegrityError("existing campaign database is missing")
        self._lock = os.open(lockpath, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if os.fstat(self._lock).st_ino != lockpath.stat().st_ino:
                raise StoreIntegrityError("lock inode changed")
            if self._create:
                descriptor = os.open(self.database, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                os.close(descriptor)
            self._db = sqlite3.connect(
                "file:" + quote(str(self.database.resolve())) + "?mode=rw", uri=True, isolation_level=None
            )
            self._reader = B0HSqlReader(
                self._db, manifest=self.manifest, admission=self.admission, null=self.null
            )
            if (
                not self._create
                and not self._db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            ):
                raise StoreIntegrityError("existing empty database is not a prepared campaign")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=EXTRA")
            self._db.execute("PRAGMA foreign_keys=ON")
            for pragma, expected in (("journal_mode", "delete"), ("synchronous", 3), ("foreign_keys", 1)):
                if self._db.execute("PRAGMA " + pragma).fetchone()[0] != expected:
                    raise StoreIntegrityError("SQLite setting not established: " + pragma)
            tables = tuple(
                row[0]
                for row in self._db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            )
            if not tables:
                if not self._create:
                    raise StoreIntegrityError("existing empty database is not a prepared campaign")
                self._db.execute("BEGIN IMMEDIATE")
                try:
                    for statement in B0H_SQL_SCHEMA:
                        self._db.execute(statement)
                    for value in (self.manifest, self.admission, self.null):
                        self._put_object(value)
                    self._db.execute(
                        "INSERT INTO campaign VALUES(1,?,?,?)",
                        (self.campaign_sha256, record_digest(self.admission), record_digest(self.null)),
                    )
                    self._commit()
                except BaseException:
                    if self._db.in_transaction:
                        self._db.execute("ROLLBACK")
                    raise
            elif tables != B0H_SQL_TABLES:
                raise StoreIntegrityError("unsupported database schema")
            self._integrity()
            for case in self.manifest.cases:
                self.stages(case)
            return self
        except BlockingIOError as error:
            self.__exit__(None, None, None)
            raise StoreUnavailable("campaign already owned") from error
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            if self._db is not None:
                self._db.close()
                self._db = None
        finally:
            if self._lock is not None:
                os.close(self._lock)
                self._lock = None

    def _require_open(self) -> None:
        if self._db is None or self._lock is None:
            raise StoreIntegrityError("store requires live campaign exclusion")

    def _commit(self) -> None:
        self._db.execute("COMMIT")

    def _object(self, digest, cls):
        return self._reader.record(digest, cls)

    def _put_object(self, value):
        raw = runner_record_bytes(value)
        digest = sha256(raw)
        prior = self._db.execute("SELECT kind,body FROM objects WHERE digest=?", (digest,)).fetchone()
        if prior is None:
            self._db.execute("INSERT INTO objects VALUES(?,?,?)", (digest, value.format, raw))
        elif prior != (value.format, raw):
            raise StoreIntegrityError("operational object conflict")
        return digest

    def _transaction(self, write, matches) -> None:
        self._require_open()
        try:
            self._db.execute("BEGIN IMMEDIATE")
            write()
            self._commit()
        except sqlite3.Error as error:
            retryable = getattr(error, "sqlite_errorcode", -1) & 255 in _RETRYABLE
            try:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                if matches():
                    return
            except sqlite3.Error as inspection_error:
                inspection_retryable = getattr(inspection_error, "sqlite_errorcode", -1) & 255 in _RETRYABLE
                if inspection_retryable:
                    raise StoreUnavailable("transaction cannot be inspected") from inspection_error
                raise inspection_error
            if retryable:
                raise StoreUnavailable("publication absent after storage failure") from error
            raise
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise
        if not matches():
            raise StoreIntegrityError("committed transaction readback differs")

    def start(self, record: StageStart) -> None:
        self._require_open()
        if (
            record.key.case not in self.manifest.cases
            or record.key.campaign_sha256 != self.campaign_sha256
            or record.worker_id != self.manifest.worker_id
            or record.owner_id != self.owner_id
            or record.source != self.manifest.source
            or record.runtime != self.manifest.runtime
        ):
            raise StoreIntegrityError("START admission mismatch")
        key = record.key
        slot = (key.case.canonical_id, key.stage, -1 if key.attempt_id is None else key.attempt_id)
        prior = self._db.execute(
            "SELECT digest FROM starts WHERE case_id=? AND stage=? AND attempt=?", slot
        ).fetchone()
        if prior is not None:
            raise StoreIntegrityError("stage already has one START")
        from genomeos.validation.heterogeneity_runner_binding import validate_case_evidence
        from genomeos.validation.heterogeneity_runner_records import CaseEvidence

        try:
            existing = self.stages(key.case)
            validate_case_evidence(self.manifest, CaseEvidence(self.campaign_sha256, key.case, existing))
            prospective = StoredStage(record, None, None, None, None, None, None)
            validate_case_evidence(
                self.manifest, CaseEvidence(self.campaign_sha256, key.case, existing + (prospective,))
            )
        except (ValueError, sqlite3.Error) as error:
            raise StoreIntegrityError("START case-bound admission mismatch") from error
        digest = record_digest(record)

        def write():
            self._put_object(record)
            self._db.execute("INSERT INTO starts VALUES(?,?,?,?)", (*slot, digest))

        def matches():
            row = self._db.execute(
                "SELECT digest FROM starts WHERE case_id=? AND stage=? AND attempt=?", slot
            ).fetchone()
            return row == (digest,) and self._object(digest, StageStart) == record

        self._transaction(write, matches)

    def complete(
        self,
        start: StageStart,
        completion: StageCompletion,
        *,
        receipt: EvidenceReceipt | None,
        encoded: EncodedB0HEvidence | None,
        failure: StageExecutionFailure | None,
    ) -> None:
        packet = PublicationPacket(start, completion, receipt, encoded, failure)
        try:
            self._complete(start, completion, receipt=receipt, encoded=encoded, failure=failure)
        except sqlite3.Error as error:
            if getattr(error, "sqlite_errorcode", -1) & 255 in _RETRYABLE:
                raise PendingPublication(packet, error) from error
            raise

    def _complete(
        self,
        start: StageStart,
        completion: StageCompletion,
        *,
        receipt: EvidenceReceipt | None,
        encoded: EncodedB0HEvidence | None,
        failure: StageExecutionFailure | None,
    ) -> None:
        self._require_open()
        if self._db.in_transaction:
            self._db.execute("ROLLBACK")
        packet = PublicationPacket(start, completion, receipt, encoded, failure)
        digest = record_digest(start)
        if self._object(digest, StageStart) != start or completion.start_sha256 != digest:
            raise StoreIntegrityError("completion START mismatch")
        if self._db.execute("SELECT 1 FROM losses WHERE start_digest=?", (digest,)).fetchone():
            raise StoreIntegrityError("lost stage cannot complete")
        if receipt is not None:
            if (
                encoded is None
                or failure is not None
                or evidence_receipt(start, encoded, limits=self.manifest.limits) != receipt
                or completion.receipt_sha256 != record_digest(receipt)
                or completion.failure_sha256 is not None
            ):
                raise StoreIntegrityError("scientific publication packet mismatch")
        elif (
            failure is None
            or encoded is not None
            or failure.start_sha256 != digest
            or completion.failure_sha256 != record_digest(failure)
            or completion.receipt_sha256 is not None
        ):
            raise StoreIntegrityError("failure publication packet mismatch")
        wanted = (record_digest(completion), completion.receipt_sha256, completion.failure_sha256)

        def matches():
            row = self._db.execute(
                "SELECT digest,receipt,failure FROM completions WHERE start_digest=?", (digest,)
            ).fetchone()
            if row is None:
                return False
            if row != wanted:
                raise StoreIntegrityError("immutable completion conflict")
            self._check_publication_relationships(digest, receipt, encoded, failure)
            stage = self._stage(digest)
            if (
                stage.completion != completion
                or stage.receipt != receipt
                or stage.failure != failure
                or stage.encoded != encoded
            ):
                raise StoreIntegrityError("immutable result bytes conflict")
            return True

        if matches():
            return
        if start.owner_id != self.owner_id:
            raise StoreIntegrityError("only live START owner publishes new evidence")
        self._check_publication_relationships(digest, receipt, encoded, failure)

        def write():
            result_digest = self._put_object(receipt if receipt is not None else failure)
            if encoded is not None:
                self._db.execute("INSERT INTO metadata VALUES(?,?)", (result_digest, encoded.metadata))
                for ordinal, (payload_digest, raw) in enumerate(encoded.payloads):
                    prior = self._db.execute(
                        "SELECT body FROM payloads WHERE digest=?", (payload_digest,)
                    ).fetchone()
                    if prior is None:
                        self._db.execute("INSERT INTO payloads VALUES(?,?)", (payload_digest, raw))
                    elif prior != (raw,):
                        raise StoreIntegrityError("payload digest collision")
                    self._db.execute(
                        "INSERT INTO payload_links VALUES(?,?,?)", (result_digest, ordinal, payload_digest)
                    )
            self._put_object(completion)
            self._db.execute("INSERT INTO completions VALUES(?,?,?,?)", (digest, *wanted))

        try:
            self._transaction(write, matches)
        except StoreUnavailable as error:
            raise PendingPublication(packet, error) from error

    def _check_publication_relationships(self, start_digest, receipt, encoded, failure) -> None:
        """Reject retained partial evidence before adding publication rows."""
        if receipt is not None:
            receipt_digest = record_digest(receipt)
            if (
                self._db.execute("SELECT 1 FROM objects WHERE digest=?", (receipt_digest,)).fetchone()
                is not None
                and self._db.execute(
                    "SELECT 1 FROM completions WHERE start_digest=?", (start_digest,)
                ).fetchone()
                is None
            ):
                raise StoreIntegrityError("orphan receipt; no receipt-only repair")
        if failure is not None:
            failure_digest = record_digest(failure)
            if (
                self._db.execute("SELECT 1 FROM objects WHERE digest=?", (failure_digest,)).fetchone()
                is not None
                and self._db.execute(
                    "SELECT 1 FROM completions WHERE start_digest=?", (start_digest,)
                ).fetchone()
                is None
            ):
                raise StoreIntegrityError("orphan failure; no receipt-only repair")
        if self._db.execute(
            "SELECT count(*) FROM metadata WHERE receipt NOT IN "
            "(SELECT receipt FROM completions WHERE receipt IS NOT NULL)"
        ).fetchone()[0]:
            raise StoreIntegrityError("orphan metadata; no receipt-only repair")
        if self._db.execute(
            "SELECT count(*) FROM payload_links WHERE receipt NOT IN (SELECT receipt FROM metadata)"
        ).fetchone()[0]:
            raise StoreIntegrityError("orphan payload link; no receipt-only repair")
        if self._db.execute(
            "SELECT count(*) FROM payloads WHERE digest NOT IN (SELECT payload FROM payload_links)"
        ).fetchone()[0]:
            raise StoreIntegrityError("orphan payload; no receipt-only repair")
        if self._db.execute(
            "SELECT count(*) FROM objects o WHERE NOT EXISTS ("
            "SELECT 1 FROM campaign c WHERE o.digest IN (c.manifest,c.admission,c.null_reference)) "
            "AND NOT EXISTS (SELECT 1 FROM starts s WHERE o.digest=s.digest) "
            "AND NOT EXISTS (SELECT 1 FROM completions c WHERE o.digest IN "
            "(c.start_digest,c.digest,c.receipt,c.failure)) "
            "AND NOT EXISTS (SELECT 1 FROM losses l WHERE o.digest IN (l.start_digest,l.digest))"
        ).fetchone()[0]:
            raise StoreIntegrityError("orphan operational object; no receipt-only repair")

    def publish_pending(self, packet: PublicationPacket) -> None:
        self.complete(
            packet.start,
            packet.completion,
            receipt=packet.receipt,
            encoded=packet.encoded,
            failure=packet.failure,
        )

    def record_owner_loss(self, start: StageStart) -> OwnerLoss:
        self._require_open()
        digest = record_digest(start)
        retained = self._reader.record(digest, StageStart)
        indexed = self._db.execute(
            "SELECT case_id,stage,attempt FROM starts WHERE digest=?", (digest,)
        ).fetchone()
        expected_index = (
            retained.key.case.canonical_id,
            retained.key.stage,
            -1 if retained.key.attempt_id is None else retained.key.attempt_id,
        )
        if retained != start or indexed != expected_index:
            raise StoreIntegrityError("retained START differs from caller or index")
        prior = self._db.execute("SELECT digest FROM losses WHERE start_digest=?", (digest,)).fetchone()
        if prior is not None:
            loss = self._object(prior[0], OwnerLoss)
            if loss.start_sha256 != digest or loss.previous_owner_id != start.owner_id:
                raise StoreIntegrityError("owner loss START identity mismatch")
            return loss
        if (
            start.owner_id == self.owner_id
            or self._db.execute("SELECT 1 FROM completions WHERE start_digest=?", (digest,)).fetchone()
        ):
            raise StoreIntegrityError("live/completed stage has no owner loss")
        loss = OwnerLoss(
            format="b0h_owner_loss",
            version="1",
            start_sha256=digest,
            previous_owner_id=start.owner_id,
            observing_owner_id=self.owner_id,
            observed_unix_ns=time.time_ns(),
            evidence="prior_process_exclusion_released",
            surviving_receipts=(),
        )

        def write():
            self._db.execute("INSERT INTO losses VALUES(?,?)", (digest, self._put_object(loss)))

        def matches():
            row = self._db.execute("SELECT digest FROM losses WHERE start_digest=?", (digest,)).fetchone()
            if row != (record_digest(loss),):
                return False
            actual = self._object(row[0], OwnerLoss)
            return actual.start_sha256 == digest and actual.previous_owner_id == start.owner_id

        self._transaction(write, matches)
        return loss

    def _stage(self, digest: str) -> StoredStage:
        return self._reader.stage(digest)

    def stages(self, case: SbcCaseId) -> tuple[StoredStage, ...]:
        self._require_open()
        return self._reader.stages(case)

    def _integrity(self) -> None:
        self._require_open()
        self._reader.audit()

    def inventory(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        self._require_open()
        return self._reader.inventory()
