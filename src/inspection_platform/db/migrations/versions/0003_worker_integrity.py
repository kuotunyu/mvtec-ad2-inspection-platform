"""Add worker liveness and idempotency constraints."""

import json
from collections import defaultdict
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0003_worker_integrity"
down_revision = "0002_product_api"
branch_labels = None
depends_on = None


def _decoded_payload(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        decoded = json.loads(value)
        return dict(decoded) if isinstance(decoded, dict) else {}
    return {}


def _reconcile_predictions(bind: sa.Connection) -> None:
    rows = bind.execute(
        sa.text("SELECT id, image_id, payload FROM predictions ORDER BY image_id, id")
    ).mappings()
    grouped: dict[str, list[sa.RowMapping]] = defaultdict(list)
    for row in rows:
        grouped[str(row["image_id"])].append(row)
    evidence_keys = {
        "anomaly_map_artifact_key",
        "anomaly_map_sha256",
        "anomaly_score",
        "model_bundle_id",
        "model_outcome",
        "overlay_artifact_key",
        "overlay_sha256",
        "threshold",
    }
    for image_id, candidates in grouped.items():
        if len(candidates) < 2:
            continue
        decoded = [(row, _decoded_payload(row["payload"])) for row in candidates]

        def rank(item: tuple[sa.RowMapping, dict[str, Any]]) -> tuple[int, int, int, str]:
            row, payload = item
            return (
                int("error" not in payload),
                sum(key in payload and payload[key] is not None for key in evidence_keys),
                sum(value is not None for value in payload.values()),
                str(row["id"]),
            )

        ordered = sorted(decoded, key=rank)
        keeper, keeper_payload = ordered[-1]
        merged: dict[str, Any] = {}
        for _, payload in ordered:
            merged.update(payload)
        if "error" not in keeper_payload:
            merged.pop("error", None)
        bind.execute(
            sa.text("UPDATE predictions SET payload = :payload WHERE id = :id"),
            {"id": keeper["id"], "payload": json.dumps(merged, sort_keys=True)},
        )
        bind.execute(
            sa.text("DELETE FROM predictions WHERE image_id = :image_id AND id != :id"),
            {"image_id": image_id, "id": keeper["id"]},
        )


def _backfill_audit_dedupe_keys(bind: sa.Connection) -> None:
    rows = list(
        bind.execute(
            sa.text(
                "SELECT id, action, resource_id, created_at, dedupe_key FROM audit_events "
                "ORDER BY action, resource_id, created_at, id"
            )
        ).mappings()
    )
    canonical_actions = {"job.artifacts_deleted", "job.completed", "job.created"}
    grouped: dict[tuple[str, str], list[sa.RowMapping]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["action"]), str(row["resource_id"]))].append(row)
    used: set[str] = set()
    for (action, resource_id), events in grouped.items():
        for index, row in enumerate(events):
            current = row["dedupe_key"]
            if index == 0 and action in canonical_actions:
                desired = f"{action}:{resource_id}"
            elif isinstance(current, str) and current and current not in used:
                desired = current
            else:
                desired = f"legacy:{action}:{resource_id}:{row['id']}"
            if desired in used:
                desired = f"legacy:{action}:{resource_id}:{row['id']}"
            used.add(desired)
            if current != desired:
                bind.execute(
                    sa.text("UPDATE audit_events SET dedupe_key = :key WHERE id = :id"),
                    {"id": row["id"], "key": desired},
                )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _reconcile_predictions(bind)
    prediction_indexes = {item["name"] for item in inspector.get_indexes("predictions")}
    if "uq_predictions_image_id" not in prediction_indexes:
        op.create_index("uq_predictions_image_id", "predictions", ["image_id"], unique=True)
    audit_columns = {item["name"] for item in inspector.get_columns("audit_events")}
    if "dedupe_key" not in audit_columns:
        op.add_column("audit_events", sa.Column("dedupe_key", sa.String(length=255)))
    _backfill_audit_dedupe_keys(bind)
    audit_indexes = {item["name"] for item in inspector.get_indexes("audit_events")}
    if "uq_audit_events_dedupe_key" not in audit_indexes:
        op.create_index("uq_audit_events_dedupe_key", "audit_events", ["dedupe_key"], unique=True)
    if "worker_heartbeats" not in inspector.get_table_names():
        op.create_table(
            "worker_heartbeats",
            sa.Column("worker_id", sa.String(length=128), primary_key=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
    op.drop_index("uq_audit_events_dedupe_key", table_name="audit_events")
    op.drop_column("audit_events", "dedupe_key")
    op.drop_index("uq_predictions_image_id", table_name="predictions")
