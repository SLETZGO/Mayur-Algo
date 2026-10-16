"""Create durable webhook signal queue and audit events."""

from alembic import op
import sqlalchemy as sa

revision = "0001_signal_intake"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signal_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("signal_id", sa.String(length=256), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("underlying", sa.String(length=128), nullable=False),
        sa.Column("entry_trigger", sa.String(length=64), nullable=False),
        sa.Column("stop_level", sa.String(length=64), nullable=False),
        sa.Column("reward_risk", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("queue_status", sa.String(length=24), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=256), nullable=True),
        sa.UniqueConstraint("signal_id", name="uq_signal_events_signal_id"),
    )
    op.create_index("ix_signal_events_queue", "signal_events", ["queue_status", "created_at"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_correlation_id", "audit_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_correlation_id", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_signal_events_queue", table_name="signal_events")
    op.drop_table("signal_events")
