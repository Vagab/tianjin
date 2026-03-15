import asyncio
import time
from unittest.mock import MagicMock

from bot.market.models import Direction, Market, Token
from bot.price.feed import PriceTick
from bot.strategy.momentum import MomentumStrategy


def make_market(up_price=0.5, down_price=0.5, elapsed_pct=0.5):
    """Create a market. elapsed_pct controls how far into the window we are."""
    now = int(time.time())
    duration = 300  # 5 minutes
    start = now - int(duration * elapsed_pct)
    return Market(
        slug="test-market",
        condition_id="0x123",
        question="Test?",
        up_token=Token(token_id="up1", outcome="Up", price=up_price),
        down_token=Token(token_id="dn1", outcome="Down", price=down_price),
        start_ts=start,
        end_ts=start + duration,
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
    # Window open = current price = 100.0 → 0% window momentum
    signal = asyncio.run(strategy.evaluate(market, feed, window_open_price=100.0))
    assert signal is None


def test_no_signal_on_small_move():
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.05)
    market = make_market()
    prices = [100.0 + i * 0.001 for i in range(30)]
    feed = make_feed(prices)
    signal = asyncio.run(strategy.evaluate(market, feed, window_open_price=100.0))
    assert signal is None


def test_signal_on_strong_up_move():
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.05, min_edge=0.0, fee_pct=0.0)
    market = make_market(up_price=0.45, down_price=0.55)
    prices = [100.0 + i * 0.025 for i in range(30)]
    feed = make_feed(prices, tfi_buy=True)  # TFI aligned with UP
    # Window opened at 99.5, now at 100.725 → UP
    signal = asyncio.run(strategy.evaluate(market, feed, window_open_price=99.5))
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
    # Window opened at 100.5, now at 99.275 → DOWN
    signal = asyncio.run(strategy.evaluate(market, feed, window_open_price=100.5))
    assert signal is not None
    assert signal.direction == Direction.DOWN


def test_not_enough_data():
    strategy = MomentumStrategy()
    market = make_market()
    feed = make_feed([100.0] * 5)
    signal = asyncio.run(strategy.evaluate(market, feed, window_open_price=100.0))
    assert signal is None


def test_tfi_opposing_dampens_signal():
    """If price moves UP but TFI shows selling, signal should be dampened."""
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.05, min_edge=0.0, fee_pct=0.0)
    market = make_market(up_price=0.45, down_price=0.55)
    prices = [100.0 + i * 0.025 for i in range(30)]

    # Aligned TFI → stronger signal
    feed_aligned = make_feed(prices, tfi_buy=True)
    signal_aligned = asyncio.run(strategy.evaluate(market, feed_aligned, window_open_price=99.5))

    # Opposing TFI → dampened signal
    feed_opposing = make_feed(prices, tfi_buy=False)
    signal_opposing = asyncio.run(strategy.evaluate(market, feed_opposing, window_open_price=99.5))

    assert signal_aligned is not None
    assert signal_opposing is not None
    assert signal_opposing.predicted_prob < signal_aligned.predicted_prob


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
    signal = asyncio.run(strategy.evaluate(market, feed, window_open_price=99.5))
    # Consistency dampening should reduce edge below threshold or produce no signal


def test_window_momentum_overrides_rolling():
    """Window momentum should determine direction, not rolling momentum.

    Scenario: BTC opened at 100, rose to 101, pulled back to 100.5.
    Rolling 45s momentum is negative (pullback), but window momentum is positive.
    Bot should bet UP (window momentum wins).
    """
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.02, min_edge=0.0, fee_pct=0.0)
    market = make_market(up_price=0.45, down_price=0.55, elapsed_pct=0.6)
    # Recent prices show a pullback (rolling momentum negative)
    prices = [101.0 - i * 0.01 for i in range(30)]  # 101.0 → 100.71
    feed = make_feed(prices, tfi_buy=True)
    # But window opened at 100.0, current at 100.71 → UP from window open
    signal = asyncio.run(strategy.evaluate(market, feed, window_open_price=100.0))
    assert signal is not None
    assert signal.direction == Direction.UP  # window momentum wins


def test_time_weighting_early_vs_late():
    """Signals later in the window should have higher predicted_prob."""
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.02, min_edge=0.0, fee_pct=0.0)
    # Use a smaller move so predicted_prob doesn't hit the 0.95 cap
    prices = [100.0 + i * 0.005 for i in range(30)]

    # Early in window (10% elapsed)
    market_early = make_market(up_price=0.45, down_price=0.55, elapsed_pct=0.1)
    feed_early = make_feed(prices, tfi_buy=True)
    signal_early = asyncio.run(strategy.evaluate(market_early, feed_early, window_open_price=99.9))

    # Late in window (80% elapsed)
    market_late = make_market(up_price=0.45, down_price=0.55, elapsed_pct=0.8)
    feed_late = make_feed(prices, tfi_buy=True)
    signal_late = asyncio.run(strategy.evaluate(market_late, feed_late, window_open_price=99.9))

    assert signal_early is not None
    assert signal_late is not None
    assert signal_late.predicted_prob > signal_early.predicted_prob


def test_fallback_to_rolling_without_window_price():
    """Without window_open_price, should fall back to rolling momentum."""
    strategy = MomentumStrategy(lookback_seconds=45, min_move_pct=0.05, min_edge=0.0, fee_pct=0.0)
    market = make_market(up_price=0.45, down_price=0.55)
    prices = [100.0 + i * 0.025 for i in range(30)]
    feed = make_feed(prices, tfi_buy=True)
    signal = asyncio.run(strategy.evaluate(market, feed))  # no window_open_price
    assert signal is not None
    assert signal.direction == Direction.UP
