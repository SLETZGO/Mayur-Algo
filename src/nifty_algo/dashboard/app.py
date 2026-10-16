"""Streamlit read-only UI. Every interaction in this app performs database reads only."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from nifty_algo.config import config_from_environment
from nifty_algo.dashboard.data import DashboardSnapshot, load_snapshot
from nifty_algo.data.database import create_database_engine, create_session_factory


def _rows(values: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [asdict(value) for value in values]


def _table(st: Any, values: tuple[Any, ...], *, empty_message: str) -> None:
    if values:
        st.dataframe(_rows(values), hide_index=True)
    else:
        st.info(empty_message)


def _overview(st: Any, snapshot: DashboardSnapshot) -> None:
    st.subheader("Execution status")
    first, second, third, fourth = st.columns(4)
    first.metric("Mode", snapshot.execution_mode)
    second.metric("Live enabled", "YES" if snapshot.live_trading_enabled else "NO")
    third.metric("Manual live arm", "ARMED" if snapshot.manual_live_armed else "OFF")
    fourth.metric("Database", "Connected" if snapshot.database_healthy else "Unavailable")
    st.caption("The execution mode is application configuration. Dashboard refreshes do not submit orders.")
    st.subheader("Current positions")
    _table(st, snapshot.positions, empty_message="No persisted positions.")
    st.subheader("Recent alerts")
    _table(st, snapshot.signals[:10], empty_message="No persisted signal alerts.")


def _signals(st: Any, snapshot: DashboardSnapshot) -> None:
    st.subheader("TradingView signal intake")
    st.caption("Entry and stop values below are in the Pine chart symbol's price units (for an index, index points).")
    _table(st, snapshot.signals, empty_message="No persisted signal alerts.")


def _orders(st: Any, snapshot: DashboardSnapshot) -> None:
    st.subheader("Orders")
    st.caption("Fill and limit prices are per listed broker instrument. They are not underlying index-point levels.")
    _table(st, snapshot.orders, empty_message="No persisted orders.")
    st.subheader("Executions / fills")
    _table(st, snapshot.executions, empty_message="No persisted executions. Broker acknowledgements are not fills.")


def _history(st: Any, snapshot: DashboardSnapshot) -> None:
    st.subheader("Persisted event history")
    _table(st, snapshot.audit_events, empty_message="No persisted audit events.")
    st.subheader("Backtest reports")
    st.info(
        "No backtest report is persisted in this project yet. Stage 4 currently replays supplied CSVs "
        "to in-memory signal events only; no CSV or option dataset was supplied, and no P&L result is available."
    )


def _shadow(st: Any, snapshot: DashboardSnapshot) -> None:
    st.subheader("Shadow observation runs")
    _table(st, snapshot.shadow_runs, empty_message="No shadow run has been started.")
    st.subheader("Observation tape")
    st.caption("Shadow entries are observations/proposals only; fill estimates are not actual executions.")
    _table(st, snapshot.shadow_events, empty_message="No shadow observations have been recorded.")
    active = sum(run.state == "ACTIVE" for run in snapshot.shadow_runs)
    if active:
        st.warning(f"{active} shadow observation window(s) currently active; this dashboard still cannot submit orders.")
    else:
        st.info("No shadow operation is active until a user-defined observation window and required feeds are configured.")


def _health(st: Any, snapshot: DashboardSnapshot) -> None:
    st.subheader("Application health snapshot")
    st.write({
        "dashboard": "running",
        "database": "connected" if snapshot.database_healthy else "unavailable",
        "execution_mode": snapshot.execution_mode,
        "live_trading_enabled": snapshot.live_trading_enabled,
        "manual_live_armed": snapshot.manual_live_armed,
    })
    if snapshot.database_error:
        st.error(f"Database read failed ({snapshot.database_error}); details are hidden from the UI.")
    st.subheader("Recent audit events")
    _table(st, snapshot.audit_events, empty_message="No audit events.")
    st.caption("This view shows persisted audit events, not host or web-server logs.")


def _risk_and_settings(st: Any, config: Any, snapshot: DashboardSnapshot) -> None:
    st.subheader("Risk limits")
    st.dataframe([
        {"Setting": "Max risk per trade (INR)", "Value": str(config.risk_limits.max_risk_per_trade_inr or "Not configured")},
        {"Setting": "Max daily loss (INR)", "Value": str(config.risk_limits.max_daily_loss_inr or "Not configured")},
        {"Setting": "Max lots", "Value": config.risk_limits.max_lots},
        {"Setting": "Max open positions", "Value": config.risk_limits.max_open_positions},
        {"Setting": "Max trades per day", "Value": config.risk_limits.max_trades_per_day},
    ], hide_index=True)
    st.subheader("Execution and intake settings")
    st.write({
        "execution_mode": snapshot.execution_mode,
        "live_trading_enabled": snapshot.live_trading_enabled,
        "manual_live_armed": snapshot.manual_live_armed,
        "webhook_secret_configured": config.webhook_secret is not None,
        "webhook_max_payload_bytes": config.webhook_max_payload_bytes,
        "database_url": "configured (value hidden)",
    })
    st.caption("Settings are view-only. Secrets and database connection strings are never displayed.")


def main() -> None:
    """Launch with Streamlit. This function has no broker or mutation calls."""
    try:
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError("Install the optional dashboard dependencies: pip install -e '.[dashboard]'") from exc
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        raise RuntimeError("Install the optional dashboard dependencies: pip install -e '.[dashboard]'") from exc
    load_dotenv(override=False)

    st.set_page_config(page_title="Nifty Algo — Operations", layout="wide")
    st.title("Nifty Algo Operations")
    st.caption("Read-only dashboard · PAPER is the default · live trading remains disabled")

    config = config_from_environment()
    engine = create_database_engine(config.database_url)
    try:
        with engine.connect():
            pass
        database_ok = True
    except Exception:
        database_ok = False
    factory = create_session_factory(engine)
    snapshot = load_snapshot(factory, config)
    if not database_ok:
        snapshot = DashboardSnapshot(
            execution_mode=snapshot.execution_mode,
            live_trading_enabled=snapshot.live_trading_enabled,
            manual_live_armed=snapshot.manual_live_armed,
            database_healthy=False,
            database_error=snapshot.database_error or "DatabaseUnavailable",
            signals=(), orders=(), executions=(), positions=(), audit_events=(),
        )

    pages = ("Overview", "Signals", "Orders & fills", "History & backtest", "Shadow runs", "Health & audit", "Risk & settings")
    page = st.sidebar.radio("Read-only views", pages)
    if st.sidebar.button("Refresh snapshot"):
        st.rerun()
    if page == "Overview":
        _overview(st, snapshot)
    elif page == "Signals":
        _signals(st, snapshot)
    elif page == "Orders & fills":
        _orders(st, snapshot)
    elif page == "History & backtest":
        _history(st, snapshot)
    elif page == "Shadow runs":
        _shadow(st, snapshot)
    elif page == "Health & audit":
        _health(st, snapshot)
    elif page == "Risk & settings":
        _risk_and_settings(st, config, snapshot)
    engine.dispose()


if __name__ == "__main__":
    main()
