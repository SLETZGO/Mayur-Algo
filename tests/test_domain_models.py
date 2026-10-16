from datetime import datetime, timezone
from decimal import Decimal
import unittest

from nifty_algo.domain.models import (
    Fill,
    Order,
    OrderStatus,
    PriceLevel,
    ReferenceInstrument,
    Signal,
    SignalDirection,
)


class DomainModelTests(unittest.TestCase):
    def test_signal_requires_explicit_shared_reference_and_aware_timestamp(self):
        signal = Signal(
            signal_id="NIFTY-5-1-LONG",
            direction=SignalDirection.LONG,
            symbol="NSE:NIFTY50",
            timeframe="5",
            bar_time=datetime(2026, 10, 15, 9, 20, tzinfo=timezone.utc),
            entry_trigger=PriceLevel(Decimal("25000"), ReferenceInstrument.UNDERLYING, "NSE:NIFTY50"),
            stop=PriceLevel(Decimal("24950"), ReferenceInstrument.UNDERLYING, "NSE:NIFTY50"),
            reward_risk=Decimal("3"),
        )
        self.assertIs(signal.entry_trigger.reference, ReferenceInstrument.UNDERLYING)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            Signal(
                signal_id="x", direction=SignalDirection.LONG, symbol="X", timeframe="5",
                bar_time=datetime(2026, 10, 15),
                entry_trigger=PriceLevel(Decimal("2"), ReferenceInstrument.UNDERLYING, "X"),
                stop=PriceLevel(Decimal("1"), ReferenceInstrument.UNDERLYING, "X"),
                reward_risk=Decimal("3"),
            )

    def test_order_and_fill_validate_quantities_and_timestamps(self):
        order = Order("o1", "s1", OrderStatus.PARTIALLY_FILLED, 2, 1)
        self.assertEqual(order.filled_quantity, 1)
        with self.assertRaisesRegex(ValueError, "between zero and requested"):
            Order("o1", "s1", OrderStatus.FILLED, 1, 2)
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            Fill("f1", "o1", 1, Decimal("10"), datetime(2026, 10, 15))


if __name__ == "__main__":
    unittest.main()
