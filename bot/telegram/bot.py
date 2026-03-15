"""Telegram bot for notifications and remote control."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

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
        balance_refresher=None,
    ):
        self._portfolio_getter = portfolio_getter
        self._metrics = metrics
        self._risk_manager = risk_manager
        self._stop_callback = stop_callback
        self._balance_refresher = balance_refresher

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
        self._app.add_handler(CallbackQueryHandler(self._handle_button))

        await self._app.initialize()
        await self._app.start()
        try:
            await self._app.updater.start_polling(drop_pending_updates=True)
        except telegram.error.Conflict:
            logger.warning("Telegram polling conflict — commands disabled, notifications still work")

        await self.send("🤖 Bot started", with_buttons=True)

    async def stop(self):
        if self._app:
            await self.send("🛑 Bot stopping")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    @staticmethod
    def _keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 Status", callback_data="status"),
                InlineKeyboardButton("💰 PnL", callback_data="pnl"),
            ],
            [
                InlineKeyboardButton("🛑 Stop", callback_data="stop"),
                InlineKeyboardButton("▶️ Start", callback_data="start"),
            ],
        ])

    async def send(self, text: str, with_buttons: bool = False):
        if not self._bot:
            return
        try:
            await self._bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=self._keyboard() if with_buttons else None,
            )
        except Exception as e:
            logger.error("Telegram send failed: %s", e)

    async def notify_trade(
        self,
        direction: str,
        amount: float,
        edge: float,
        market: str,
        reasoning: str = "",
    ):
        text = (
            f"🔔 <b>Trade Placed</b>\n"
            f"Direction: <code>{direction}</code>\n"
            f"Amount: <code>${amount:.2f}</code>\n"
            f"Edge: <code>{edge:.3f}</code>\n"
            f"Market: <code>{market}</code>"
        )
        if reasoning:
            text += f"\n\n💡 <b>Why:</b> {reasoning}"
        await self.send(text, with_buttons=True)

    async def notify_outcome(self, market: str, outcome: str, pnl: float, balance: float):
        emoji = "✅" if outcome == "win" else "❌"
        await self.send(
            f"{emoji} <b>{outcome.upper()}</b>\n"
            f"Market: <code>{market}</code>\n"
            f"PnL: <code>${pnl:+.2f}</code>\n"
            f"Balance: <code>${balance:.2f}</code>",
            with_buttons=True,
        )

    async def notify_error(self, error: str):
        await self.send(f"⚠️ <b>Error</b>\n<code>{error}</code>")

    async def notify_circuit_breaker(self, reason: str):
        await self.send(f"🚨 <b>Circuit Breaker</b>\n<code>{reason}</code>")

    async def _handle_button(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if str(query.message.chat.id) != self.chat_id:
            return
        await query.answer()

        if query.data == "status":
            await self._reply_status(query.message)
        elif query.data == "pnl":
            await self._reply_pnl(query.message)
        elif query.data == "stop":
            if self._risk_manager:
                self._risk_manager.force_halt()
            await query.message.reply_text("🛑 Trading halted")
        elif query.data == "start":
            if self._risk_manager:
                self._risk_manager.resume()
            await query.message.reply_text("▶️ Trading resumed")

    async def _reply_status(self, message):
        if self._portfolio_getter and self._metrics:
            # Refresh balance from Polymarket before reporting
            if self._balance_refresher:
                try:
                    await self._balance_refresher()
                except Exception:
                    pass
            portfolio = self._portfolio_getter()
            text = self._metrics.format_telegram(portfolio)
            await message.reply_text(text, parse_mode="HTML", reply_markup=self._keyboard())
        else:
            await message.reply_text("Bot not fully initialized")

    async def _reply_pnl(self, message):
        if self._portfolio_getter:
            if self._balance_refresher:
                try:
                    await self._balance_refresher()
                except Exception:
                    pass
            portfolio = self._portfolio_getter()
            await message.reply_text(
                f"💰 Daily: <code>${portfolio.daily_pnl:+.2f}</code>\n"
                f"💰 Total: <code>${portfolio.total_pnl:+.2f}</code>\n"
                f"💰 Balance: <code>${portfolio.balance_usd:.2f}</code>",
                parse_mode="HTML",
                reply_markup=self._keyboard(),
            )

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != self.chat_id:
            return
        await self._reply_status(update.message)

    async def _cmd_pnl(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if str(update.effective_chat.id) != self.chat_id:
            return
        await self._reply_pnl(update.message)

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
