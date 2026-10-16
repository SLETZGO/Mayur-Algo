"""Add run-scoped shadow observation evidence."""

from alembic import op
import sqlalchemy as sa


revision = "0003_shadow_observations"
down_revision = "0002_paper_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shadow_runs",
        sa.Column("run_id", sa.String(length=64), primary_key=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("planned_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "shadow_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=64), sa.ForeignKey("shadow_runs.run_id"), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("event_key", sa.String(length=256), nullable=True),
        sa.Column("symbol", sa.String(length=128), nullable=True),
        sa.Column("source_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.String(length=64), nullable=True),
        sa.Column("bid_price", sa.String(length=64), nullable=True),
        sa.Column("ask_price", sa.String(length=64), nullable=True),
        sa.Column("comparison_price", sa.String(length=64), nullable=True),
        sa.Column("price_reference", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("comparison_quantity", sa.Integer(), nullable=True),
        sa.Column("metric_value", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=True),
    )
    op.create_index("ix_shadow_observations_run_time", "shadow_observations", ["run_id", "observed_at"])
    op.create_index("ix_shadow_observations_event_type", "shadow_observations", ["run_id", "event_type"])


def downgrade() -> None:
    op.drop_index("ix_shadow_observations_event_type", table_name="shadow_observations")
    op.drop_index("ix_shadow_observations_run_time", table_name="shadow_observations")
    op.drop_table("shadow_observations")
    op.drop_table("shadow_runs")
