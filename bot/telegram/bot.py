"""Telegram bot for notifications and remote control."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

if TYPE_CHECKING:
    from bot.market.models import PortfolioState
    from bot.risk.manager import RiskManager
    from bot.utils.metrics import MetricsTracker

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self._bot: telegram.Bot | None = None
        self._app: Application | None = None
        self._portfolio_getter = None
        self._metrics: MetricsTracker | None = None
        self._risk_manager: RiskManager | None = None
        self._stop_callback = None

    def set_dependencies(
        self,
        portfolio_getter,
        metrics: MetricsTracker,
        risk_manager: RiskManager,
        stop_callback=None,
    ):
        self._portfolio_getter = portfolio_getter
        self._metrics = metrics
        self._risk_manager = risk_manager
        self._stop_callback = stop_callback

    async def start(self):
        if not self.token or not self.chat_id:
            logger.warning("Telegram not configured — notifications disabled")
            return

        self._bot = telegram.Bot(token=self.token)
        self._app = Application.builder().token(self.token).build()

        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("pnl", self._cmd_pnl))
        self._app.add_handler(CommandHandler("stop", self._cmd_stop))
        self._app.add_handler(CommandHandler("start", self._cmd_start))

        await self._app.initialize()
        await self._app.start()
        try:
            await self._app.updater.start_polling(drop_pending_updates=True)
        except telegram.error.Conflict:
            logger.warning("Telegram polling conflict — commands disabled, notifications still work")

        await self.send("🤖 Bot started")

    async def stop(self):
        if self._app:
            await self.send("🛑 Bot stopping")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def send(self, text: str):
        if not self._bot:
            return
        try:
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Telegram send failed: %s", e)

    async def notify_trade(self, direction: str, amount: float, edge: float, market: str):
        await self.send(
            f"🔔 <b>Trade Placed</b>\n"
            f"Direction: <code>{direction}</code>\n"
            f"Amount: <code>${amount:.2f}</code>\n"
            f"Edge: <code>{edge:.3f}</code>\n"
            f"Market: <code>{market}</code>"
        )

    async def notify_outcome(self, market: str, outcome: str, pnl: float, balance: float):
        emoji = "✅" if outcome == "win" else "❌"
        await self.send(
            f"{emoji} <b>{outcome.upper()}</b>\n"
            f"Market: <code>{market}</code>\n"
            f"PnL: <code>${pnl:+.2f}</code>\n"
            f"Balance: <code>${balance:.2f}</code>"
        )

    async def notify_error(self, error: str):
        await self.send(f"⚠️ <b>Error</b>\n<code>{error}</code>")

    async def notify_circuit_breaker(self, reason: str):
        await self.send(f"🚨 <b>Circuit Breaker</b>\n<code>{reason}</code>")

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != self.chat_id:
            return
        if self._portfolio_getter and self._metrics:
            portfolio = self._portfolio_getter()
            text = self._metrics.format_telegram(portfolio)
            await update.message.reply_text(text, parse_mode="HTML")
        else:
            await update.message.reply_text("Bot not fully initialized")

    async def _cmd_pnl(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != self.chat_id:
            return
        if self._portfolio_getter:
            portfolio = self._portfolio_getter()
            await update.message.reply_text(
                f"💰 Daily: <code>${portfolio.daily_pnl:+.2f}</code>\n"
                f"💰 Total: <code>${portfolio.total_pnl:+.2f}</code>\n"
                f"💰 Balance: <code>${portfolio.balance_usd:.2f}</code>",
                parse_mode="HTML",
            )

    async def _cmd_stop(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != self.chat_id:
            return
        if self._risk_manager:
            self._risk_manager.force_halt()
            await update.message.reply_text("🛑 Trading halted")
        if self._stop_callback:
            self._stop_callback()

    async def _cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != self.chat_id:
            return
        if self._risk_manager:
            self._risk_manager.resume()
            await update.message.reply_text("▶️ Trading resumed")
