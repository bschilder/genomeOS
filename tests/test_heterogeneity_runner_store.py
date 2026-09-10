"""SQLite publication fixtures; no filesystem durability or science claim."""

from __future__ import annotations

import importlib
from dataclasses import replace

import pytest
from heterogeneity_runner_fixtures import campaign, dataset

from genomeos.validation.heterogeneity_codec import encode_b0h_evidence
from genomeos.validation.heterogeneity_runner_records import StageCompletion, StageKey, StageStart
from genomeos.validation.heterogeneity_runner_wire import evidence_receipt, record_digest


def start_record(manifest, data, owner="fixture-owner"):
    return StageStart(
        format="b0h_start",
        version="1",
        key=StageKey(
            campaign_sha256=record_digest(manifest), case=data.case_id, stage="generation", attempt_id=None
        ),
        worker_id=manifest.worker_id,
        owner_id=owner,
        source=manifest.source,
        runtime=manifest.runtime,
        cdf_backend="cupy",
        prerequisites=(),
        started_unix_ns=2,
        started_monotonic_ns=3,
    )


def packet(manifest, start, data):
    from genomeos.validation.heterogeneity_runner_records import PublicationPacket

    encoded = encode_b0h_evidence(data, limits=manifest.limits)
    receipt = evidence_receipt(start, encoded, limits=manifest.limits)
    completion = StageCompletion(
        format="b0h_completion",
        version="1",
        start_sha256=record_digest(start),
        receipt_sha256=record_digest(receipt),
        failure_sha256=None,
        whole_call_elapsed_ns=7,
        process_peak_rss_bytes=None,
        resource_unavailable_reason="fixture_not_measured",
    )
    return PublicationPacket(start, completion, receipt, encoded, None)


def publish(store, retained):
    store.complete(
        retained.start,
        retained.completion,
        receipt=retained.receipt,
        encoded=retained.encoded,
        failure=retained.failure,
    )


def test_atomic_completion_reuse_and_exclusion(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
        publish(store, retained)
        before = store.inventory()
        publish(store, retained)
        assert store.inventory() == before
        (stage,) = store.stages(data.case_id)
        assert stage.encoded == retained.encoded
        assert stage.receipt == retained.receipt
        assert stage.completion.whole_call_elapsed_ns == 7
        with pytest.raises(storage.StoreIntegrityError):
            publish(
                store,
                replace(
                    retained, completion=retained.completion.model_copy(update={"whole_call_elapsed_ns": 8})
                ),
            )
        with pytest.raises(storage.StoreUnavailable):
            with storage.LocalB0HStore(
                path, manifest=manifest, admission=admission, null=null, owner_id="other-owner"
            ):
                pytest.fail("second owner acquired the lock")


def test_start_only_owner_loss_is_not_absence(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
    with storage.LocalB0HStore(
        path, manifest=manifest, admission=admission, null=null, owner_id="new-owner"
    ) as store:
        loss = store.record_owner_loss(start)
        assert loss.previous_owner_id == "fixture-owner"
        (stage,) = store.stages(data.case_id)
        assert stage.completion is None
        assert stage.loss == loss
        with pytest.raises(storage.StoreIntegrityError):
            store.start(start.model_copy(update={"owner_id": "new-owner"}))


@pytest.mark.parametrize("existing", [False, True])
def test_open_never_creates_missing_or_initializes_empty(tmp_path, existing):
    import sqlite3

    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError

    manifest, admission, null = campaign(tmp_path)
    path = tmp_path / "study.sqlite3"
    if existing:
        path.write_bytes(b"")
    with pytest.raises(StoreIntegrityError):
        with LocalB0HStore(path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"):
            pytest.fail("open admitted a missing/empty campaign")
    assert path.exists() is existing
    if existing:
        with sqlite3.connect(path) as check:
            assert check.execute("SELECT name FROM sqlite_master").fetchall() == []


def test_create_refuses_existing_file_and_symlink(tmp_path):
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, StoreIntegrityError

    manifest, admission, null = campaign(tmp_path)
    path = tmp_path / "study.sqlite3"
    path.write_bytes(b"")
    with pytest.raises(FileExistsError):
        with LocalB0HStore.create(
            path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
        ):
            pytest.fail("exclusive create replaced an existing file")
    path.unlink()
    target = tmp_path / "unrelated.sqlite3"
    target.write_bytes(b"literal unrelated bytes")
    path.symlink_to(target)
    with pytest.raises(StoreIntegrityError, match="symlink"):
        with LocalB0HStore.create(
            path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
        ):
            pytest.fail("symlink campaign admitted")
    assert target.read_bytes() == b"literal unrelated bytes"


def test_uninspectable_commit_keeps_same_live_packet(tmp_path, monkeypatch):
    import sqlite3

    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, PendingPublication

    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    with LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        store.start(start)
        original_commit = store._commit
        connection = store._db
        fail_inspection = [False]

        def io_failure():
            error = sqlite3.OperationalError("literal unavailable fixture")
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            return error

        class Uninspectable:
            @property
            def in_transaction(self):
                return connection.in_transaction

            def execute(self, sql, parameters=()):
                if fail_inspection[0] and sql.startswith("SELECT"):
                    raise io_failure()
                return connection.execute(sql, parameters)

        def failed_commit():
            fail_inspection[0] = True
            raise io_failure()

        monkeypatch.setattr(store, "_db", Uninspectable())
        monkeypatch.setattr(store, "_commit", failed_commit)
        with pytest.raises(PendingPublication) as pending:
            publish(store, retained)
        assert pending.value.packet == retained
        assert pending.value.packet.completion.whole_call_elapsed_ns == 7
        monkeypatch.setattr(store, "_db", connection)
        monkeypatch.setattr(store, "_commit", original_commit)
        store.publish_pending(pending.value.packet)
        (stage,) = store.stages(data.case_id)
        assert stage.completion == retained.completion
        assert stage.encoded == retained.encoded


def test_inventory_performs_one_global_audit(tmp_path, monkeypatch):
    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore

    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        calls = []
        original = store._reader.audit

        def audited():
            calls.append("whole-store")
            original()

        monkeypatch.setattr(store._reader, "audit", audited)
        assert len(store.inventory()) == 1938
        assert calls == ["whole-store"]


def test_commit_ack_loss_and_live_publication_retry(tmp_path, monkeypatch):
    import sqlite3

    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    with storage.LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        commit = store._commit

        def ack_lost():
            commit()
            error = sqlite3.OperationalError("literal acknowledgement loss")
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            raise error

        monkeypatch.setattr(store, "_commit", ack_lost)
        store.start(start)
        assert store.stages(data.case_id)[0].completion is None

        def before_commit():
            error = sqlite3.OperationalError("literal precommit I/O failure")
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            raise error

        monkeypatch.setattr(store, "_commit", before_commit)
        with pytest.raises(storage.PendingPublication) as pending:
            publish(store, retained)
        assert pending.value.packet == retained
        assert store.stages(data.case_id)[0].completion is None
        monkeypatch.setattr(store, "_commit", ack_lost)
        store.publish_pending(pending.value.packet)
        assert store.stages(data.case_id)[0].encoded == retained.encoded
        monkeypatch.setattr(store, "_commit", commit)
        assert store.stages(data.case_id)[0].completion.whole_call_elapsed_ns == 7


def test_receipt_without_complete_is_refused(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    with storage.LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        store.start(start)
        store._put_object(retained.receipt)
        with pytest.raises(storage.StoreIntegrityError, match="orphan"):
            store.inventory()


@pytest.mark.parametrize("mutation", ("flip", "remove", "metadata"))
def test_corrupt_exact_evidence_is_never_absence(tmp_path, mutation):
    from heterogeneity_runner_fixtures import accepted

    from genomeos.validation.heterogeneity_runner_records import StageKey

    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    generation = start_record(manifest, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(generation)
        generation_packet = packet(manifest, generation, data)
        publish(store, generation_packet)
        fit_start = generation.model_copy(
            update={
                "key": StageKey(
                    campaign_sha256=record_digest(manifest), case=data.case_id, stage="fit", attempt_id=0
                ),
                "prerequisites": (record_digest(generation_packet.completion),),
            }
        )
        store.start(fit_start)
        fit_packet = packet(manifest, fit_start, accepted(data))
        publish(store, fit_packet)
        digest, raw = fit_packet.encoded.payloads[0]
        if mutation == "flip":
            altered = bytes([raw[0] ^ 1]) + raw[1:]
            store._db.execute("UPDATE payloads SET body=? WHERE digest=?", (altered, digest))
        elif mutation == "remove":
            store._db.execute("PRAGMA foreign_keys=OFF")
            store._db.execute("DELETE FROM payloads WHERE digest=?", (digest,))
            store._db.execute("PRAGMA foreign_keys=ON")
        else:
            altered = fit_packet.encoded.metadata.replace(b"3ff028f5c28f5c29", b"3ff051eb851eb852", 1)
            assert altered != fit_packet.encoded.metadata
            store._db.execute(
                "UPDATE metadata SET body=? WHERE receipt=?", (altered, record_digest(fit_packet.receipt))
            )
        with pytest.raises(ValueError):
            store.stages(data.case_id)


def test_start_rejects_unmet_case_dependency(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    generation = start_record(manifest, data)
    fit = generation.model_copy(
        update={
            "key": StageKey(
                campaign_sha256=record_digest(manifest), case=data.case_id, stage="fit", attempt_id=0
            ),
        }
    )
    with storage.LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        store.start(generation)
        with pytest.raises(storage.StoreIntegrityError):
            store.start(fit)


def test_orphan_null_completion_is_refused(tmp_path):

    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
        store._put_object(retained.completion)
        store._put_object(retained.receipt)
        store._db.execute("PRAGMA foreign_keys=OFF")
        store._db.execute(
            "INSERT INTO completions VALUES(NULL,?,?,NULL)",
            (record_digest(retained.completion), record_digest(retained.receipt)),
        )
        store._db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(storage.StoreIntegrityError):
            store.inventory()


def test_transaction_corruption_during_inspection_is_not_retryable(tmp_path):
    import sqlite3

    from genomeos.validation.heterogeneity_runner_store import LocalB0HStore

    manifest, admission, null = campaign(tmp_path)
    with LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:

        def write():
            error = sqlite3.OperationalError("original I/O")
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            raise error

        def matches():
            error = sqlite3.DatabaseError("corrupt inspection")
            error.sqlite_errorcode = sqlite3.SQLITE_CORRUPT
            raise error

        with pytest.raises(sqlite3.DatabaseError, match="corrupt inspection"):
            store._transaction(write, matches)


def test_receipt_only_publication_is_refused_before_mutation(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    with storage.LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        store.start(start)
        store._put_object(retained.receipt)
        with pytest.raises(storage.StoreIntegrityError):
            publish(store, retained)


def test_loss_creation_refuses_corrupt_retained_start_index(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
    with storage.LocalB0HStore(
        path, manifest=manifest, admission=admission, null=null, owner_id="new-owner"
    ) as store:
        store._db.execute("UPDATE starts SET case_id=? WHERE digest=?", ("wrong-case", record_digest(start)))
        with pytest.raises(storage.StoreIntegrityError, match="retained START"):
            store.record_owner_loss(start)


def test_loss_null_and_unmatched_start_references_are_refused(tmp_path):
    from genomeos.validation.heterogeneity_runner_records import OwnerLoss

    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    loss = OwnerLoss(
        format="b0h_owner_loss",
        version="1",
        start_sha256=record_digest(start),
        previous_owner_id=start.owner_id,
        observing_owner_id="new-owner",
        observed_unix_ns=1,
        evidence="prior_process_exclusion_released",
        surviving_receipts=(),
    )
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
        loss_digest = store._put_object(loss)
        store._db.execute("PRAGMA foreign_keys=OFF")
        store._db.execute("INSERT INTO losses VALUES(NULL,?)", (loss_digest,))
        store._db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(storage.StoreIntegrityError):
            store.inventory()


def test_loss_unmatched_start_reference_is_refused(tmp_path):
    from genomeos.validation.heterogeneity_runner_records import OwnerLoss

    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    loss = OwnerLoss(
        format="b0h_owner_loss",
        version="1",
        start_sha256=record_digest(start),
        previous_owner_id=start.owner_id,
        observing_owner_id="new-owner",
        observed_unix_ns=1,
        evidence="prior_process_exclusion_released",
        surviving_receipts=(),
    )
    with storage.LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        store.start(start)
        loss_digest = store._put_object(loss)
        store._db.execute("PRAGMA foreign_keys=OFF")
        store._db.execute("INSERT INTO losses VALUES(?,?)", ("missing-start", loss_digest))
        store._db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(storage.StoreIntegrityError):
            store.inventory()


def test_loss_stage_read_binds_indexed_start(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    first, second = dataset(study=0, case_index=0), dataset(study=1, case_index=0)
    start1, start2 = start_record(manifest, first), start_record(manifest, second)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start1)
        store.start(start2)
    with storage.LocalB0HStore(
        path, manifest=manifest, admission=admission, null=null, owner_id="new-owner"
    ) as store:
        loss = store.record_owner_loss(start1)
        store._db.execute(
            "UPDATE losses SET start_digest=? WHERE start_digest=?",
            (record_digest(start2), record_digest(start1)),
        )
        with pytest.raises(storage.StoreIntegrityError):
            store.stages(second.case_id)
        assert loss.start_sha256 == record_digest(start1)


def test_orphan_object_rejected_on_completed_reuse(tmp_path):
    from genomeos.validation.heterogeneity_runner_records import OwnerLoss

    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    with storage.LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        store.start(start)
        publish(store, retained)
        store._put_object(
            OwnerLoss(
                format="b0h_owner_loss",
                version="1",
                start_sha256=record_digest(start),
                previous_owner_id="other-owner",
                observing_owner_id="third-owner",
                observed_unix_ns=1,
                evidence="prior_process_exclusion_released",
                surviving_receipts=(),
            )
        )
        with pytest.raises(storage.StoreIntegrityError):
            publish(store, retained)


@pytest.mark.parametrize("start_ref", [None, "unmatched-start"])
def test_complete_packet_with_null_or_unmatched_start_is_refused(tmp_path, start_ref):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
        publish(store, retained)
        assert store.stages(data.case_id)[0].receipt == retained.receipt
        store._db.execute("PRAGMA foreign_keys=OFF")
        store._db.execute(
            "UPDATE completions SET start_digest=? WHERE start_digest=?", (start_ref, record_digest(start))
        )
        store._db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(storage.StoreIntegrityError):
            store.inventory()


def test_existing_loss_reuse_refuses_corrupt_retained_start(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
    with storage.LocalB0HStore(
        path, manifest=manifest, admission=admission, null=null, owner_id="new-owner"
    ) as store:
        store.record_owner_loss(start)
        row = store._db.execute("SELECT body FROM objects WHERE digest=?", (record_digest(start),)).fetchone()
        store._db.execute(
            "UPDATE objects SET body=? WHERE digest=?",
            (bytes([row[0][0] ^ 1]) + row[0][1:], record_digest(start)),
        )
        with pytest.raises(storage.StoreIntegrityError):
            store.record_owner_loss(start)


def test_loss_creation_refuses_corrupt_retained_start_bytes(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    start = start_record(manifest, dataset())
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
    with storage.LocalB0HStore(
        path, manifest=manifest, admission=admission, null=null, owner_id="new-owner"
    ) as store:
        row = store._db.execute("SELECT body FROM objects WHERE digest=?", (record_digest(start),)).fetchone()
        store._db.execute(
            "UPDATE objects SET body=? WHERE digest=?",
            (bytes([row[0][0] ^ 1]) + row[0][1:], record_digest(start)),
        )
        with pytest.raises(storage.StoreIntegrityError):
            store.record_owner_loss(start)


def test_loss_reuse_refuses_corrupt_retained_start_index(tmp_path):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    start = start_record(manifest, dataset())
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
    with storage.LocalB0HStore(
        path, manifest=manifest, admission=admission, null=null, owner_id="new-owner"
    ) as store:
        store.record_owner_loss(start)
        store._db.execute("UPDATE starts SET case_id=? WHERE digest=?", ("wrong-case", record_digest(start)))
        with pytest.raises(storage.StoreIntegrityError):
            store.record_owner_loss(start)


def test_loss_readback_refuses_start_corruption_injected_after_entry(tmp_path, monkeypatch):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
    with storage.LocalB0HStore(
        path, manifest=manifest, admission=admission, null=null, owner_id="new-owner"
    ) as store:
        original = store._transaction

        def corrupt_then_transaction(write, matches):
            row = store._db.execute(
                "SELECT body FROM objects WHERE digest=?", (record_digest(start),)
            ).fetchone()
            store._db.execute(
                "UPDATE objects SET body=? WHERE digest=?",
                (bytes([row[0][0] ^ 1]) + row[0][1:], record_digest(start)),
            )
            return original(write, matches)

        monkeypatch.setattr(store, "_transaction", corrupt_then_transaction)
        with pytest.raises(storage.StoreIntegrityError):
            store.record_owner_loss(start)


def test_loss_readback_refuses_start_index_corruption_injected_after_entry(tmp_path, monkeypatch):
    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    start = start_record(manifest, dataset())
    path = tmp_path / "study.sqlite3"
    with storage.LocalB0HStore.create(
        path, manifest=manifest, admission=admission, null=null, owner_id="fixture-owner"
    ) as store:
        store.start(start)
    with storage.LocalB0HStore(
        path, manifest=manifest, admission=admission, null=null, owner_id="new-owner"
    ) as store:
        original = store._transaction

        def corrupt_then_transaction(write, matches):
            store._db.execute(
                "UPDATE starts SET case_id=? WHERE digest=?", ("wrong-case", record_digest(start))
            )
            return original(write, matches)

        monkeypatch.setattr(store, "_transaction", corrupt_then_transaction)
        with pytest.raises(storage.StoreIntegrityError):
            store.record_owner_loss(start)


def test_uncertain_absent_publication_checks_orphan_before_pending(tmp_path, monkeypatch):
    import sqlite3

    from genomeos.validation.heterogeneity_runner_records import OwnerLoss

    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    with storage.LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        store.start(start)
        orphan = OwnerLoss(
            format="b0h_owner_loss",
            version="1",
            start_sha256=record_digest(start),
            previous_owner_id="other-owner",
            observing_owner_id="third-owner",
            observed_unix_ns=1,
            evidence="prior_process_exclusion_released",
            surviving_receipts=(),
        )
        injected = []
        original = store._commit

        def ack_lost():
            error = sqlite3.OperationalError("acknowledgment unavailable")
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            raise error

        original_transaction = store._transaction

        def inject_at_inspection(write, matches):
            def inspect():
                store._put_object(orphan)
                injected.append(
                    store._db.execute(
                        "SELECT 1 FROM completions WHERE start_digest=?", (record_digest(start),)
                    ).fetchone()
                    is None
                )
                return matches()

            return original_transaction(write, inspect)

        monkeypatch.setattr(store, "_transaction", inject_at_inspection)
        monkeypatch.setattr(store, "_commit", ack_lost)
        with pytest.raises(storage.StoreIntegrityError):
            publish(store, retained)
        assert injected == [True]
        monkeypatch.setattr(store, "_commit", original)


def test_uncertain_present_publication_checks_orphan_at_inspection(tmp_path, monkeypatch):
    import sqlite3

    from genomeos.validation.heterogeneity_runner_records import OwnerLoss

    storage = importlib.import_module("genomeos.validation.heterogeneity_runner_store")
    manifest, admission, null = campaign(tmp_path)
    data = dataset()
    start = start_record(manifest, data)
    retained = packet(manifest, start, data)
    with storage.LocalB0HStore.create(
        tmp_path / "study.sqlite3",
        manifest=manifest,
        admission=admission,
        null=null,
        owner_id="fixture-owner",
    ) as store:
        store.start(start)
        original_transaction = store._transaction
        injected = []
        orphan = OwnerLoss(
            format="b0h_owner_loss",
            version="1",
            start_sha256=record_digest(start),
            previous_owner_id="other-owner",
            observing_owner_id="third-owner",
            observed_unix_ns=1,
            evidence="prior_process_exclusion_released",
            surviving_receipts=(),
        )

        def inject_at_inspection(write, matches):
            def inspect():
                store._put_object(orphan)
                injected.append(
                    store._db.execute(
                        "SELECT 1 FROM completions WHERE start_digest=?", (record_digest(start),)
                    ).fetchone()
                    is not None
                )
                return matches()

            return original_transaction(write, inspect)

        def ack_lost():
            store._db.execute("COMMIT")
            error = sqlite3.OperationalError("acknowledgment unavailable")
            error.sqlite_errorcode = sqlite3.SQLITE_IOERR
            raise error

        monkeypatch.setattr(store, "_transaction", inject_at_inspection)
        monkeypatch.setattr(store, "_commit", ack_lost)
        with pytest.raises(storage.StoreIntegrityError):
            publish(store, retained)
        assert injected == [True]
