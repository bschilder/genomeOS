"""Offline B0H admit/prepare/run/reduce/collect (design §§5,7–8,12; runner §§4–8)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections.abc import Sequence
from pathlib import Path

from genomeos.validation.heterogeneity_codec import B0HCodecLimits, EncodedB0HEvidence
from genomeos.validation.heterogeneity_reduction import reduce_b0h_study, reduction_bytes
from genomeos.validation.heterogeneity_runner import execute_b0h_case, load_b0h_case
from genomeos.validation.heterogeneity_runner_admission import observe_b0h_admission
from genomeos.validation.heterogeneity_runner_reader import read_collected_b0h_snapshot
from genomeos.validation.heterogeneity_runner_records import (
    AdmissionReceipt,
    CampaignManifest,
    EvidenceReceipt,
    PreparedNull,
    StageCompletion,
    StageExecutionFailure,
    StageStart,
    prepared_null,
    restore_null,
)
from genomeos.validation.heterogeneity_runner_store import LocalB0HStore, PendingPublication
from genomeos.validation.heterogeneity_runner_wire import (
    build_manifest,
    read_runner_record,
    record_digest,
    runner_record_bytes,
    sha256,
)
from genomeos.validation.sbc_ranks import simulate_rank_null


def _emit_timing(record: dict) -> None:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
    try:
        print(payload, flush=True)
    except (OSError, ValueError):
        try:
            print(
                json.dumps(
                    {
                        "format": "b0h_timing_report_unavailable",
                        "version": "1",
                        "reason": "stdout_write_failed",
                    },
                    separators=(",", ":"),
                ),
                file=sys.stderr,
                flush=True,
            )
        except (OSError, ValueError):
            pass


class _TimedStore(LocalB0HStore):
    _operation_sequence = 0

    def _observe(self, phase, start_sha256, call):
        self._operation_sequence += 1
        sequence = self._operation_sequence
        started = time.monotonic_ns()

        def report(event, elapsed, outcome, exception_class, unavailable_reason):
            _emit_timing(
                {
                    "format": "b0h_storage_interval",
                    "version": "1",
                    "operation_sequence": sequence,
                    "owner_id": self.owner_id,
                    "phase": phase,
                    "start_sha256": start_sha256,
                    "interval": "before_begin_report_to_store_method_return_or_raise",
                    "started_monotonic_ns": started,
                    "event": event,
                    "elapsed_ns": elapsed,
                    "outcome": outcome,
                    "exception_class": exception_class,
                    "unavailable_reason": unavailable_reason,
                }
            )

        report("begin", None, "unresolved", None, "end_not_observed")
        try:
            value = call()
        except BaseException as error:
            report(
                "end",
                time.monotonic_ns() - started,
                "raised",
                type(error).__module__ + "." + type(error).__qualname__,
                None,
            )
            raise
        report("end", time.monotonic_ns() - started, "returned", None, None)
        return value

    def __enter__(self):
        return self._observe("store_open", None, super().__enter__)

    def start(self, record: StageStart) -> None:
        method = super().start
        return self._observe("start_publication", record_digest(record), lambda: method(record))

    def complete(
        self,
        start: StageStart,
        completion: StageCompletion,
        *,
        receipt: EvidenceReceipt | None,
        encoded: EncodedB0HEvidence | None,
        failure: StageExecutionFailure | None,
    ) -> None:
        method = super().complete
        return self._observe(
            "result_publication",
            record_digest(start),
            lambda: method(start, completion, receipt=receipt, encoded=encoded, failure=failure),
        )

    def collect(self, destination: Path) -> tuple[str, str]:
        method = super().collect
        return self._observe("closed_collection", None, lambda: method(destination))


def frozen_file(path: Path, raw: bytes) -> None:
    if path.exists():
        if path.is_symlink() or path.read_bytes() != raw:
            raise ValueError("immutable output conflict: " + str(path))
        return
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def read_record(path: Path, cls):
    value = read_runner_record(path.read_bytes())
    if type(value) is not cls:
        raise ValueError("wrong input root: " + str(path))
    return value


def reconcile_publication(store: LocalB0HStore, pending: PendingPublication) -> None:
    packet = pending.packet
    origin = time.monotonic()
    while time.monotonic() - origin < 1800:
        remaining = 1800 - (time.monotonic() - origin)
        if remaining <= 0:
            break
        time.sleep(min(60, remaining))
        if time.monotonic() - origin >= 1800:
            break
        try:
            store.publish_pending(packet)
        except PendingPublication as still_pending:
            if still_pending.packet != packet:
                raise ValueError("publication retry changed retained packet") from still_pending
        else:
            return
    raise pending


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline frozen B0H campaign")
    commands = parser.add_subparsers(dest="command", required=True)
    admit = commands.add_parser("admit")
    admit.add_argument("--source-root", type=Path, required=True)
    admit.add_argument("--database-parent", type=Path, required=True)
    admit.add_argument("--out", type=Path, required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--admission", type=Path, required=True)
    prepare.add_argument("--source-root", type=Path, required=True)
    prepare.add_argument("--null", type=Path, required=True)
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--worker-id", required=True)
    prepare.add_argument("--max-metadata-bytes", type=int, required=True)
    prepare.add_argument("--max-payload-bytes", type=int, required=True)
    reduce = commands.add_parser("reduce")
    reduce.add_argument("--collection", type=Path, required=True)
    reduce.add_argument("--expected-database-sha256", required=True)
    reduce.add_argument("--expected-inventory-sha256", required=True)
    reduce.add_argument("--out", type=Path, required=True)
    for name in ("run", "collect"):
        child = commands.add_parser(name)
        child.add_argument("--admission", type=Path, required=True)
        child.add_argument("--manifest", type=Path, required=True)
        child.add_argument("--null", type=Path, required=True)
        child.add_argument("--database", type=Path, required=True)
        if name == "run":
            child.add_argument("--source-root", type=Path, required=True)
        else:
            child.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if (
            args.command in ("admit", "prepare", "run")
            and Path(__file__).resolve() != (args.source_root / "scripts/run_b0h_calibration.py").resolve()
        ):
            raise ValueError("executing command differs from attested source_root")
        if args.command == "admit":
            frozen_file(
                args.out, runner_record_bytes(observe_b0h_admission(args.source_root, args.database_parent))
            )
            return 0
        if args.command == "reduce":
            snapshot = read_collected_b0h_snapshot(
                args.collection,
                expected_database_sha256=args.expected_database_sha256,
                expected_inventory_sha256=args.expected_inventory_sha256,
            )
            output = reduce_b0h_study(snapshot.manifest, snapshot.cases, restore_null(snapshot.null))
            raw = reduction_bytes(output)
            frozen_file(args.out, raw)
            print(
                json.dumps(
                    {
                        "format": "b0h_reduction_receipt",
                        "version": "1",
                        "sha256": sha256(raw),
                        "inventory_sha256": output.inventory_sha256,
                    },
                    separators=(",", ":"),
                )
            )
            return 0 if output.unconditional_claim_eligible else 1
        admission = read_record(args.admission, AdmissionReceipt)
        if args.command in ("prepare", "run"):
            actual = observe_b0h_admission(args.source_root, Path(admission.storage.database_parent))
            if (
                actual.source != admission.source
                or actual.runtime != admission.runtime
                or actual.storage.database_parent != admission.storage.database_parent
                or actual.storage.device_id != admission.storage.device_id
                or actual.storage.mount_type != admission.storage.mount_type
                or actual.storage.mount_options != admission.storage.mount_options
            ):
                raise ValueError("runtime/source/storage differs from frozen admission")
        if args.command == "prepare":
            null = prepared_null(simulate_rank_null(sample_size=512, replicates=100000, seed=1653499886))
            frozen_file(args.null, runner_record_bytes(null))
            manifest = build_manifest(
                admission,
                null,
                worker_id=args.worker_id,
                limits=B0HCodecLimits(args.max_metadata_bytes, args.max_payload_bytes),
            )
            frozen_file(args.manifest, runner_record_bytes(manifest))
            database = Path(admission.storage.database_parent) / "study.sqlite3"
            open_store = _TimedStore if database.exists() else _TimedStore.create
            with open_store(
                database, manifest=manifest, admission=admission, null=null, owner_id=str(uuid.uuid4())
            ):
                pass
            return 0
        manifest = read_record(args.manifest, CampaignManifest)
        null = read_record(args.null, PreparedNull)
        if not args.database.is_file():
            raise ValueError("prepared campaign database is missing; no recreation on run/reduce")
        with _TimedStore(
            args.database, manifest=manifest, admission=admission, null=null, owner_id=str(uuid.uuid4())
        ) as store:
            if args.command == "run":
                for case in manifest.cases:
                    while True:
                        try:
                            execute_b0h_case(manifest, case, store)
                        except PendingPublication as pending:
                            reconcile_publication(store, pending)
                        else:
                            break
                return 0
            for case in manifest.cases:
                load_b0h_case(manifest, case, store)
            database_digest, inventory_digest = store.collect(args.out)
            receipt = {
                "format": "b0h_collection",
                "version": "1",
                "database_sha256": database_digest,
                "inventory_sha256": inventory_digest,
            }
            frozen_file(
                args.out / "collection.json",
                json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("ascii"),
            )
            print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
            return 0
    except PendingPublication as error:
        print(
            json.dumps(
                {"status": "unresolved_publication", "message": str(error), "redelivery_permitted": False}
            ),
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print(
            json.dumps({"status": "interrupted_unresolved", "redelivery_permitted": False}), file=sys.stderr
        )
        return 130
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "adapter_refusal",
                    "exception_class": type(error).__module__ + "." + type(error).__qualname__,
                    "message_utf8hex": str(error).encode("utf-8", "surrogatepass").hex(),
                }
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
