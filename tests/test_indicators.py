from bot.price.indicators import momentum, rsi, volatility


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
