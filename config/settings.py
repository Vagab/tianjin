from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Polymarket
    polymarket_host: str = "https://clob.polymarket.com"
    polymarket_private_key: SecretStr = SecretStr("")
    polymarket_chain_id: int = 137
    polymarket_funder: str = ""

    # Binance
    binance_ws_url: str = "wss://stream.binance.com:9443/ws/btcusdt@trade"

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Trading
    paper_trading: bool = False
    market_interval: Literal["5m", "15m"] = "5m"
    order_type: str = "FOK"

    # Risk
    max_position_usd: float = 100.0
    max_exposure_usd: float = 500.0
    max_daily_loss_usd: float = 200.0
    kelly_fraction: float = 0.60
    min_edge: float = 0.03
    estimated_taker_fee_pct: float = 0.02

    # Strategy
    momentum_lookback_seconds: int = 45
    momentum_min_move_pct: float = 0.05

    @property
    def interval_seconds(self) -> int:
        return 300 if self.market_interval == "5m" else 900


settings = Settings()
