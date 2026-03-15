import asyncio
import time
from unittest.mock import MagicMock

from bot.market.models import Direction, Market, Token
from bot.price.feed import PriceTick
from bot.strategy.momentum import MomentumStrategy


def make_market(up_price=0.5, down_price=0.5):
    return Market(
        slug="test-market",
        condition_id="0x123",
        question="Test?",
        up_token=Token(token_id="up1", outcome="Up", price=up_price),
        down_token=Token(token_id="dn1", outcome="Down", price=down_price),
        start_ts=int(time.time()),
        end_ts=int(time.time()) + 300,
    )


def make_feed(prices, tfi_buy=True):
    """Create a mock feed with prices and ticks.

    tfi_buy=True → all ticks are buyer-aggressor (TFI=+1.0)
    tfi_buy=False → all ticks are seller-aggressor (TFI=-1.0)
    """
    ticks = [
        PriceTick(
            price=p,
            timestamp=time.time() - len(prices) + i,
            volume=1.0,
            is_buyer_maker=not tfi_buy,  # m=False means buyer aggressor
        )
        for i, p in enumerate(prices)
    ]
    feed = MagicMock()
    feed.prices_since.return_value = prices
    feed.ticks_since.return_value = ticks
    feed.current_price = prices[-1] if prices else 0
    return feed


def test_no_signal_on_flat_market():
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.05)
    market = make_market()
    feed = make_feed([100.0] * 30)
    signal = asyncio.run(strategy.evaluate(market, feed))
    assert signal is None


def test_no_signal_on_small_move():
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.05)
    market = make_market()
    prices = [100.0 + i * 0.001 for i in range(30)]
    feed = make_feed(prices)
    signal = asyncio.run(strategy.evaluate(market, feed))
    assert signal is None


def test_signal_on_strong_up_move():
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.05, min_edge=0.0, fee_pct=0.0)
    market = make_market(up_price=0.45, down_price=0.55)
    prices = [100.0 + i * 0.025 for i in range(30)]
    feed = make_feed(prices, tfi_buy=True)  # TFI aligned with UP
    signal = asyncio.run(strategy.evaluate(market, feed))
    assert signal is not None
    assert signal.direction == Direction.UP
    assert signal.predicted_prob > 0.5
    assert signal.reasoning
    assert "TFI" in signal.reasoning


def test_signal_on_strong_down_move():
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.05, min_edge=0.0, fee_pct=0.0)
    market = make_market(up_price=0.55, down_price=0.45)
    prices = [100.0 - i * 0.025 for i in range(30)]
    feed = make_feed(prices, tfi_buy=False)  # TFI aligned with DOWN
    signal = asyncio.run(strategy.evaluate(market, feed))
    assert signal is not None
    assert signal.direction == Direction.DOWN


def test_not_enough_data():
    strategy = MomentumStrategy()
    market = make_market()
    feed = make_feed([100.0] * 5)
    signal = asyncio.run(strategy.evaluate(market, feed))
    assert signal is None


def test_tfi_opposing_kills_signal():
    """If price moves UP but TFI shows selling, signal should be killed."""
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.05, min_edge=0.0, fee_pct=0.0)
    market = make_market(up_price=0.45, down_price=0.55)
    prices = [100.0 + i * 0.025 for i in range(30)]
    feed = make_feed(prices, tfi_buy=False)  # TFI opposing UP move
    signal = asyncio.run(strategy.evaluate(market, feed))
    assert signal is None


def test_no_signal_on_inconsistent_move():
    """A spike followed by a fade should produce weaker or no signal."""
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.05, min_edge=0.02, fee_pct=0.0)
    market = make_market(up_price=0.45, down_price=0.55)
    prices = (
        [100.0 + i * 0.05 for i in range(10)]
        + [100.5 - i * 0.02 for i in range(10)]
        + [100.3 + i * 0.02 for i in range(10)]
    )
    feed = make_feed(prices)
    signal = asyncio.run(strategy.evaluate(market, feed))
    # Consistency dampening should reduce edge below threshold or produce no signal
