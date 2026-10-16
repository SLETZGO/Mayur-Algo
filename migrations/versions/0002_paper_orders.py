"""Add broker-independent order, execution, and position records."""

from alembic import op
import sqlalchemy as sa


revision = "0002_paper_orders"
down_revision = "0001_signal_intake"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("client_order_id", sa.String(length=128), primary_key=True),
        sa.Column("signal_id", sa.String(length=256), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("order_type", sa.String(length=8), nullable=False),
        sa.Column("requested_quantity", sa.Integer(), nullable=False),
        sa.Column("limit_price", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("filled_quantity", sa.Integer(), nullable=False),
        sa.Column("average_fill_price", sa.String(length=64), nullable=True),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("requested_quantity > 0", name="ck_orders_requested_quantity_positive"),
        sa.CheckConstraint("filled_quantity >= 0 AND filled_quantity <= requested_quantity", name="ck_orders_filled_quantity_range"),
        sa.UniqueConstraint("broker_order_id", name="uq_orders_broker_order_id"),
    )
    op.create_index("ix_orders_signal_id", "orders", ["signal_id"])
    op.create_index("ix_orders_correlation_id", "orders", ["correlation_id"])
    op.create_table(
        "executions",
        sa.Column("execution_id", sa.String(length=128), primary_key=True),
        sa.Column("client_order_id", sa.String(length=128), sa.ForeignKey("orders.client_order_id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.String(length=64), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_executions_client_order_id", "executions", ["client_order_id"])
    op.create_table(
        "positions",
        sa.Column("symbol", sa.String(length=128), primary_key=True),
        sa.Column("net_quantity", sa.Integer(), nullable=False),
        sa.Column("average_price", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("positions")
    op.drop_index("ix_executions_client_order_id", table_name="executions")
    op.drop_table("executions")
    op.drop_index("ix_orders_correlation_id", table_name="orders")
    op.drop_index("ix_orders_signal_id", table_name="orders")
    op.drop_table("orders")
