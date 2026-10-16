import unittest
from decimal import Decimal

from nifty_algo.config import AppConfig, RiskLimits, UnsafeConfigurationError, config_from_environment
from nifty_algo.domain.models import ExecutionMode


class ConfigTests(unittest.TestCase):
    def test_default_configuration_is_paper_and_live_disabled(self):
        config = config_from_environment({})
        self.assertIs(config.execution_mode, ExecutionMode.PAPER)
        self.assertFalse(config.live_trading_enabled)
        self.assertFalse(config.manual_live_armed)

    def test_non_live_modes_do_not_require_live_readiness(self):
        for mode in (ExecutionMode.BACKTEST, ExecutionMode.PAPER, ExecutionMode.SHADOW):
            self.assertIs(AppConfig(execution_mode=mode).execution_mode, mode)

    def test_live_mode_fails_closed_by_default(self):
        with self.assertRaisesRegex(UnsafeConfigurationError, "LIVE mode is blocked"):
            AppConfig(execution_mode=ExecutionMode.LIVE)

    def test_live_mode_requires_all_gates_and_limits(self):
        limits = RiskLimits(
            max_risk_per_trade_inr=Decimal("500"),
            max_daily_loss_inr=Decimal("1000"),
        )
        config = AppConfig(
            execution_mode=ExecutionMode.LIVE,
            live_trading_enabled=True,
            manual_live_armed=True,
            account_configured=True,
            compliance_checks_passed=True,
            broker_app_activated=True,
            static_ip_verified=True,
            daily_authentication_complete=True,
            risk_limits=limits,
        )
        config.assert_live_ready()

    def test_environment_cannot_assert_account_or_compliance_proof(self):
        with self.assertRaisesRegex(UnsafeConfigurationError, "account_configured"):
            config_from_environment({
                "NIFTY_ALGO_EXECUTION_MODE": "LIVE",
                "NIFTY_ALGO_LIVE_TRADING_ENABLED": "true",
                "NIFTY_ALGO_MANUAL_LIVE_ARMED": "true",
            })

    def test_invalid_mode_and_boolean_rejected(self):
        with self.assertRaisesRegex(UnsafeConfigurationError, "invalid execution mode"):
            config_from_environment({"NIFTY_ALGO_EXECUTION_MODE": "AUTO"})
        with self.assertRaisesRegex(UnsafeConfigurationError, "must be 'true' or 'false'"):
            config_from_environment({"NIFTY_ALGO_LIVE_TRADING_ENABLED": "yes"})

    def test_risk_limits_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "max_lots must be positive"):
            RiskLimits(max_lots=0)
        with self.assertRaisesRegex(ValueError, "max_daily_loss_inr must be positive"):
            RiskLimits(max_daily_loss_inr=Decimal("-1"))

    def test_webhook_secret_must_have_minimum_length(self):
        with self.assertRaisesRegex(ValueError, "at least 32 UTF-8 bytes"):
            AppConfig(webhook_secret="short")
        with self.assertRaisesRegex(ValueError, "URL-safe"):
            AppConfig(webhook_secret="unsafe/path-token-unsafe/path-token-unsafe/path-token")


if __name__ == "__main__":
    unittest.main()
