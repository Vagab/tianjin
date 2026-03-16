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
    polygon_rpc_url: str = "https://polygon-bor-rpc.publicnode.com"

    # Builder API (for gasless redemption via relayer)
    polymarket_builder_api_key: str = ""
    polymarket_builder_secret: str = ""
    polymarket_builder_passphrase: str = ""

    # Binance (BTC price feed)
    binance_ws_url: str = "wss://stream.binance.com:9443/ws/btcusdt@trade"

    # Polymarket WebSocket (fill confirmation)
    polymarket_ws_url: str = "wss://ws-subscriptions-clob.polymarket.com/ws"
    order_fill_timeout_seconds: int = 30

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Trading
    paper_trading: bool = False
    market_interval: Literal["5m", "15m"] = "5m"
    order_type: str = "GTC"

    # Risk
    max_position_usd: float = 300.0
    max_exposure_usd: float = 1000.0
    max_daily_loss_usd: float = 200.0
    kelly_fraction: float = 0.60
    min_edge: float = 0.03
    estimated_taker_fee_pct: float = 0.02

    # Strategy
    momentum_lookback_seconds: int = 45
    momentum_min_move_pct: float = 0.05
    max_entry_window_pct: float = 0.75

    @property
    def interval_seconds(self) -> int:
        return 300 if self.market_interval == "5m" else 900


settings = Settings()
