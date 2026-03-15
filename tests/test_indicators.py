from bot.price.feed import PriceTick
from bot.price.indicators import (
    momentum,
    momentum_consistency,
    rsi,
    trade_flow_imbalance,
    volatility,
    vwap,
    vwap_deviation,
)


def test_momentum_positive():
    prices = [100, 101, 102, 103]
    assert momentum(prices) == 3.0  # 3% up


def test_momentum_negative():
    prices = [100, 99, 98]
    assert momentum(prices) == -2.0


def test_momentum_empty():
    assert momentum([]) == 0.0
    assert momentum([100]) == 0.0


def test_rsi_neutral_on_short_data():
    prices = [100, 101, 102]
    assert rsi(prices) == 50.0  # default when not enough data


def test_rsi_overbought():
    # Steadily rising prices
    prices = [100 + i for i in range(20)]
    assert rsi(prices) == 100.0


def test_rsi_oversold():
    # Steadily falling prices
    prices = [100 - i for i in range(20)]
    assert rsi(prices) == 0.0


def test_volatility_zero_for_flat():
    prices = [100, 100, 100, 100]
    assert volatility(prices) == 0.0


def test_volatility_positive_for_movement():
    prices = [100, 102, 98, 101, 99]
    assert volatility(prices) > 0


# --- TFI tests ---

def test_tfi_all_buying():
    ticks = [PriceTick(price=100, timestamp=0, volume=1.0, is_buyer_maker=False) for _ in range(10)]
    assert trade_flow_imbalance(ticks) == 1.0


def test_tfi_all_selling():
    ticks = [PriceTick(price=100, timestamp=0, volume=1.0, is_buyer_maker=True) for _ in range(10)]
    assert trade_flow_imbalance(ticks) == -1.0


def test_tfi_balanced():
    ticks = [
        PriceTick(price=100, timestamp=0, volume=1.0, is_buyer_maker=False),
        PriceTick(price=100, timestamp=0, volume=1.0, is_buyer_maker=True),
    ]
    assert trade_flow_imbalance(ticks) == 0.0


def test_tfi_volume_weighted():
    ticks = [
        PriceTick(price=100, timestamp=0, volume=3.0, is_buyer_maker=False),  # 3 buy
        PriceTick(price=100, timestamp=0, volume=1.0, is_buyer_maker=True),   # 1 sell
    ]
    assert trade_flow_imbalance(ticks) == 0.5  # (3-1)/4


def test_tfi_empty():
    assert trade_flow_imbalance([]) == 0.0


# --- VWAP tests ---

def test_vwap_simple():
    ticks = [
        PriceTick(price=100, timestamp=0, volume=1.0),
        PriceTick(price=102, timestamp=1, volume=1.0),
    ]
    assert vwap(ticks) == 101.0


def test_vwap_volume_weighted():
    ticks = [
        PriceTick(price=100, timestamp=0, volume=3.0),
        PriceTick(price=110, timestamp=1, volume=1.0),
    ]
    # (100*3 + 110*1) / 4 = 410/4 = 102.5
    assert vwap(ticks) == 102.5


def test_vwap_deviation_above():
    ticks = [
        PriceTick(price=100, timestamp=0, volume=1.0),
        PriceTick(price=100, timestamp=1, volume=1.0),
        PriceTick(price=102, timestamp=2, volume=1.0),  # last price above VWAP
    ]
    dev = vwap_deviation(ticks)
    assert dev > 0  # price above VWAP


def test_vwap_deviation_below():
    ticks = [
        PriceTick(price=100, timestamp=0, volume=1.0),
        PriceTick(price=100, timestamp=1, volume=1.0),
        PriceTick(price=98, timestamp=2, volume=1.0),  # last price below VWAP
    ]
    dev = vwap_deviation(ticks)
    assert dev < 0  # price below VWAP
