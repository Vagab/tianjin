"""Discover active BTC up/down markets on Polymarket via Gamma API."""

from __future__ import annotations

import json
import logging
import time

import httpx

from bot.market.models import Market, Token

logger = logging.getLogger(__name__)

GAMMA_API = "https://gamma-api.polymarket.com"


class MarketDiscovery:
    def __init__(self, interval_seconds: int = 300):
        self.interval_seconds = interval_seconds
        self._client = httpx.AsyncClient(timeout=10)

    def _window_ts(self, ts: float | None = None) -> int:
        now = int(ts or time.time())
        return now - (now % self.interval_seconds)

    def _slug_for_window(self, window_ts: int) -> str:
        interval = "5m" if self.interval_seconds == 300 else "15m"
        return f"btc-updown-{interval}-{window_ts}"

    async def get_current_market(self) -> Market | None:
        window_ts = self._window_ts()
        return await self._fetch_market(window_ts)

    async def get_next_market(self) -> Market | None:
        window_ts = self._window_ts() + self.interval_seconds
        return await self._fetch_market(window_ts)

    async def _fetch_market(self, window_ts: int) -> Market | None:
        slug = self._slug_for_window(window_ts)
        logger.info("Fetching market: %s", slug)

        try:
            resp = await self._client.get(
                f"{GAMMA_API}/events", params={"slug": slug}
            )
            resp.raise_for_status()
            events = resp.json()

            if not events:
                # Try alternative slug patterns
                return await self._try_alternative_slugs(window_ts)

            return self._parse_event(events[0], window_ts)
        except httpx.HTTPError as e:
            logger.error("Failed to fetch market %s: %s", slug, e)
            return None

    async def _try_alternative_slugs(self, window_ts: int) -> Market | None:
        """Try alternative slug patterns if the primary one doesn't work."""
        alternatives = [
            f"bitcoin-up-or-down-5-minutes-{window_ts}",
            f"btc-5min-{window_ts}",
        ]
        for slug in alternatives:
            try:
                resp = await self._client.get(
                    f"{GAMMA_API}/events", params={"slug": slug}
                )
                resp.raise_for_status()
                events = resp.json()
                if events:
                    logger.info("Found market with alternative slug: %s", slug)
                    return self._parse_event(events[0], window_ts)
            except httpx.HTTPError:
                continue

        # Fallback: search by tag
        return await self._search_by_tag(window_ts)

    async def _search_by_tag(self, window_ts: int) -> Market | None:
        """Search for BTC short-term markets by tag/keyword."""
        try:
            resp = await self._client.get(
                f"{GAMMA_API}/events",
                params={
                    "tag": "crypto",
                    "active": "true",
                    "limit": 50,
                },
            )
            resp.raise_for_status()
            events = resp.json()

            for event in events:
                title = event.get("title", "").lower()
                if "bitcoin" in title and ("5 min" in title or "up or down" in title):
                    return self._parse_event(event, window_ts)

        except httpx.HTTPError as e:
            logger.error("Tag search failed: %s", e)

        return None

    def _parse_event(self, event: dict, window_ts: int) -> Market:
        """Parse a Gamma API event into a Market object.

        The Gamma API returns clobTokenIds and outcomePrices as JSON-encoded strings.
        For a binary market, outcomes are ["Up", "Down"] with corresponding token IDs
        and prices at matching indices.
        """
        markets = event.get("markets", [])
        up_token = Token(token_id="", outcome="Up")
        down_token = Token(token_id="", outcome="Down")

        if markets:
            m = markets[0]  # Single market with two outcomes
            # Parse JSON-encoded strings
            token_ids = json.loads(m.get("clobTokenIds", "[]"))
            prices = json.loads(m.get("outcomePrices", "[]"))
            outcomes = m.get("outcomes", '["Up", "Down"]')
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)

            for i, outcome in enumerate(outcomes):
                tid = token_ids[i] if i < len(token_ids) else ""
                price = float(prices[i]) if i < len(prices) else 0.5

                if "up" in outcome.lower():
                    up_token = Token(token_id=tid, outcome="Up", price=price)
                elif "down" in outcome.lower():
                    down_token = Token(token_id=tid, outcome="Down", price=price)

        condition_id = markets[0].get("conditionId", "") if markets else ""

        return Market(
            slug=event.get("slug", ""),
            condition_id=condition_id,
            question=event.get("title", ""),
            up_token=up_token,
            down_token=down_token,
            start_ts=window_ts,
            end_ts=window_ts + self.interval_seconds,
        )

    async def get_resolved_outcome(self, slug: str) -> str | None:
        """Fetch the resolved outcome ("Up" or "Down") from Gamma API.

        Returns None if the market hasn't resolved yet.
        """
        try:
            resp = await self._client.get(
                f"{GAMMA_API}/events", params={"slug": slug}
            )
            resp.raise_for_status()
            events = resp.json()
            if not events:
                return None

            markets = events[0].get("markets", [])
            if not markets:
                return None

            m = markets[0]
            prices = json.loads(m.get("outcomePrices", "[]"))
            outcomes = m.get("outcomes", '["Up", "Down"]')
            if isinstance(outcomes, str):
                outcomes = json.loads(outcomes)

            for i, outcome in enumerate(outcomes):
                price = float(prices[i]) if i < len(prices) else 0.0
                if price == 1.0:
                    return outcome  # "Up" or "Down"

            return None  # not resolved yet (prices still between 0-1)
        except Exception as e:
            logger.warning("Failed to fetch resolved outcome for %s: %s", slug, e)
            return None

    async def close(self):
        await self._client.aclose()


if __name__ == "__main__":
    import asyncio

    async def _demo():
        discovery = MarketDiscovery()
        market = await discovery.get_current_market()
        if market:
            print(f"Market: {market.question}")
            print(f"Slug: {market.slug}")
            print(f"Up price: {market.up_price:.4f}")
            print(f"Down price: {market.down_price:.4f}")
            print(f"Up token: {market.up_token.token_id}")
            print(f"Down token: {market.down_token.token_id}")
        else:
            print("No active market found")
        await discovery.close()

    asyncio.run(_demo())
