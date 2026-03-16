"""Gasless redemption of winning Polymarket positions via relayer."""

from __future__ import annotations

import logging

from poly_web3 import ProxyWeb3Service, RelayClient, RELAYER_URL
from py_builder_signing_sdk.config import BuilderApiKeyCreds, BuilderConfig
from py_clob_client.client import ClobClient

logger = logging.getLogger(__name__)


class Redeemer:
    """Redeems winning Polymarket positions using the gasless relayer."""

    def __init__(
        self,
        private_key: str,
        funder: str,
        builder_api_key: str,
        builder_secret: str,
        builder_passphrase: str,
    ):
        # CLOB client with signature_type=1 (PROXY) for redemption
        self._clob = ClobClient(
            host="https://clob.polymarket.com",
            key=private_key,
            chain_id=137,
            funder=funder,
            signature_type=1,
        )
        creds = self._clob.create_or_derive_api_creds()
        self._clob.set_api_creds(creds)

        builder_creds = BuilderApiKeyCreds(
            key=builder_api_key,
            secret=builder_secret,
            passphrase=builder_passphrase,
        )
        builder_config = BuilderConfig(local_builder_creds=builder_creds)

        relay = RelayClient(
            relayer_url=RELAYER_URL,
            chain_id=137,
            private_key=private_key,
            builder_config=builder_config,
        )

        self._svc = ProxyWeb3Service(
            clob_client=self._clob,
            relayer_client=relay,
            rpc_url="https://polygon-bor-rpc.publicnode.com",
        )
        self._funder = funder

    def redeem_all(self) -> list[dict]:
        """Redeem all winning positions. Returns list of tx results."""
        try:
            results = self._svc.redeem_all()
            for r in results:
                tx_hash = r.get("transactionHash", "")
                logger.info("Redeemed via relayer: tx=%s", tx_hash)
            return results
        except Exception as e:
            logger.error("Redeem failed: %s", e)
            return []

    def redeem(self, condition_ids: str | list[str]) -> list[dict]:
        """Redeem specific condition IDs."""
        try:
            results = self._svc.redeem(condition_ids)
            for r in results:
                tx_hash = r.get("transactionHash", "")
                logger.info("Redeemed via relayer: tx=%s", tx_hash)
            return results
        except Exception as e:
            logger.error("Redeem failed: %s", e)
            return []

    def get_redeemable_positions(self) -> list[dict]:
        """Fetch positions that can be redeemed."""
        return self._svc.fetch_positions(self._funder)
