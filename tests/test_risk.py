from bot.market.models import PortfolioState
from bot.risk.manager import RiskManager
from bot.strategy.signal import Signal
from bot.market.models import Direction


def make_signal(edge=0.05, predicted=0.6, market=0.5, confidence=0.7):
    return Signal(
        direction=Direction.UP,
        confidence=confidence,
        predicted_prob=predicted,
        market_prob=market,
        edge=edge,
    )


def test_kelly_sizing_scales_with_balance():
    rm = RiskManager(kelly_fraction=0.25, max_position_usd=1000)
    signal = make_signal(predicted=0.65, market=0.5)

    size_50 = rm._kelly_size(signal, 50.0)
    size_500 = rm._kelly_size(signal, 500.0)
    size_1000 = rm._kelly_size(signal, 1000.0)

    assert size_500 > size_50
    assert size_1000 > size_500
    # 25% balance cap
    assert size_50 <= 50 * 0.25
    assert size_500 <= 500 * 0.25


def test_kelly_returns_zero_for_no_edge():
    rm = RiskManager()
    signal = make_signal(predicted=0.45, market=0.5, edge=-0.05)
    size = rm._kelly_size(signal, 1000.0)
    assert size == 0.0


def test_risk_blocks_below_min_edge():
    rm = RiskManager(min_edge=0.03)
    portfolio = PortfolioState(balance_usd=100)
    signal = make_signal(edge=0.02)
    check = rm.check(signal, portfolio)
    assert not check.allowed
    assert "Edge" in check.reason


def test_risk_blocks_when_halted():
    rm = RiskManager()
    rm.force_halt()
    portfolio = PortfolioState(balance_usd=100)
    signal = make_signal(edge=0.05)
    check = rm.check(signal, portfolio)
    assert not check.allowed
    assert "halted" in check.reason


def test_risk_blocks_on_daily_loss():
    rm = RiskManager(max_daily_loss_usd=50)
    portfolio = PortfolioState(balance_usd=100, daily_pnl=-51)
    signal = make_signal(edge=0.05)
    check = rm.check(signal, portfolio)
    assert not check.allowed


def test_risk_allows_good_signal():
    rm = RiskManager(min_edge=0.03, cooldown_seconds=0)
    portfolio = PortfolioState(balance_usd=100)
    signal = make_signal(edge=0.05, predicted=0.6, market=0.5)
    check = rm.check(signal, portfolio)
    assert check.allowed
    assert check.position_size > 0


def test_consecutive_losses_circuit_breaker():
    rm = RiskManager(max_consecutive_losses=3, cooldown_seconds=0)
    for _ in range(3):
        rm.record_outcome(False)

    portfolio = PortfolioState(balance_usd=100)
    signal = make_signal(edge=0.05)
    check = rm.check(signal, portfolio)
    assert not check.allowed
    assert "consecutive" in check.reason.lower()


def test_resume_clears_consecutive_losses():
    rm = RiskManager(max_consecutive_losses=3, cooldown_seconds=0)
    for _ in range(3):
        rm.record_outcome(False)
    rm.resume()

    portfolio = PortfolioState(balance_usd=100)
    signal = make_signal(edge=0.05, predicted=0.6, market=0.5)
    check = rm.check(signal, portfolio)
    assert check.allowed
