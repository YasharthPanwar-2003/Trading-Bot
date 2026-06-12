"""Binance USD-M Futures API wrapper."""

from __future__ import annotations

import os
from typing import Callable, Optional, TypeVar

from binance.client import Client
from binance.exceptions import BinanceAPIException

from bot.logging_config import get_logger

logger = get_logger("trading_bot.client")

T = TypeVar("T")

TESTNET_REST_BASE_URL = "https://testnet.binancefuture.com"
TESTNET_FUTURES_URL = f"{TESTNET_REST_BASE_URL}/fapi"
DEMO_REST_BASE_URL = "https://demo-fapi.binance.com"
DEMO_FUTURES_URL = f"{DEMO_REST_BASE_URL}/fapi"
MAINNET_REST_BASE_URL = "https://fapi.binance.com"
MAINNET_FUTURES_URL = f"{MAINNET_REST_BASE_URL}/fapi"


class BinanceFuturesClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = True,
        use_demo_url: bool = False,
    ) -> None:
        self._api_key = api_key or os.environ.get("BINANCE_API_KEY", "")
        self._api_secret = api_secret or os.environ.get("BINANCE_API_SECRET", "")
        self._testnet = testnet
        self._use_demo_url = use_demo_url
        self._client: Optional[Client] = None

        if not self._api_key or not self._api_secret:
            logger.warning("API credentials not found")

    @property
    def rest_base_url(self) -> str:
        if not self._testnet:
            return MAINNET_REST_BASE_URL
        return DEMO_REST_BASE_URL if self._use_demo_url else TESTNET_REST_BASE_URL

    @property
    def futures_url(self) -> str:
        if not self._testnet:
            return MAINNET_FUTURES_URL
        return DEMO_FUTURES_URL if self._use_demo_url else TESTNET_FUTURES_URL

    @property
    def client(self) -> Client:
        if self._client is None:
            self.connect()
        return self._client

    def connect(self) -> Client:
        if not self._api_key or not self._api_secret:
            raise ValueError("Set BINANCE_API_KEY and BINANCE_API_SECRET first.")

        logger.info(
            "Connecting to Binance USD-M Futures",
            extra={"data": {"testnet": self._testnet, "base_url": self.rest_base_url}},
        )

        try:
            self._client = Client(self._api_key, self._api_secret, testnet=self._testnet)
            self._client.FUTURES_URL = self.futures_url
            self._client.futures_ping()
            server_time = self._client.futures_time()
        except BinanceAPIException as exc:
            self._log_api_error("Connection failed", exc)
            raise ConnectionError(f"Failed to connect: {exc.message}") from exc
        except Exception as exc:
            logger.error("Connection failed: %s", exc)
            raise ConnectionError(f"Failed to connect: {exc}") from exc

        logger.info(
            "Connected to Binance USD-M Futures",
            extra={
                "data": {
                    "base_url": self.rest_base_url,
                    "server_time": server_time.get("serverTime"),
                }
            },
        )
        return self._client

    def test_connection(self) -> dict:
        try:
            self.client.futures_ping()
            server_time = self.client.futures_time()
            self.client.futures_account_balance()
            return {
                "connected": True,
                "base_url": self.rest_base_url,
                "server_time": server_time,
                "credentials_valid": True,
            }
        except BinanceAPIException as exc:
            self._log_api_error("Futures connection test failed", exc)
            return {
                "connected": False,
                "base_url": self.rest_base_url,
                "credentials_valid": False,
                "error": f"API Error (code={exc.code}): {exc.message}",
            }
        except Exception as exc:
            logger.error("Futures connection test failed: %s", exc)
            return {"connected": False, "base_url": self.rest_base_url, "error": str(exc)}

    def get_balance(self, asset: str = "USDT") -> Optional[dict]:
        balances = self._call_api(
            "Failed to get balance",
            self.client.futures_account_balance,
        )
        balance = next((item for item in balances if item.get("asset") == asset), None)

        if not balance:
            logger.warning("Asset %s not found in Futures balances", asset)
            return None

        logger.info(
            "Balance retrieved",
            extra={
                "data": {
                    "asset": asset,
                    "balance": balance.get("balance"),
                    "available": balance.get("availableBalance"),
                }
            },
        )
        return balance

    def get_account_info(self) -> dict:
        return self._call_api("Failed to get account info", self.client.futures_account)

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        if not 1 <= leverage <= 125:
            raise ValueError(f"Leverage must be between 1 and 125, got {leverage}")

        result = self._call_api(
            f"Failed to set leverage for {symbol}",
            self.client.futures_change_leverage,
            symbol=symbol,
            leverage=leverage,
        )
        logger.info("Leverage set", extra={"symbol": symbol, "data": {"leverage": leverage}})
        return result

    def set_margin_type(self, symbol: str, isolated: bool = True) -> dict:
        margin_type = "ISOLATED" if isolated else "CROSSED"

        try:
            result = self.client.futures_change_margin_type(
                symbol=symbol,
                marginType=margin_type,
            )
        except BinanceAPIException as exc:
            if exc.code != -4028:
                self._log_api_error(f"Failed to set margin type for {symbol}", exc, symbol)
                raise
            logger.info("Margin type already set", extra={"symbol": symbol})
            return {"symbol": symbol, "marginType": margin_type, "noChange": True}

        logger.info(
            "Margin type set",
            extra={"symbol": symbol, "data": {"margin_type": margin_type}},
        )
        return result

    def get_position(self, symbol: str) -> Optional[dict]:
        positions = self._call_api(
            f"Failed to get position for {symbol}",
            self.client.futures_position_information,
            symbol=symbol,
        )
        position = next(
            (
                item
                for item in positions
                if item.get("symbol") == symbol and float(item.get("positionAmt", 0)) != 0
            ),
            None,
        )

        if not position:
            logger.info("No open position", extra={"symbol": symbol})
            return None

        logger.info(
            "Position retrieved",
            extra={
                "symbol": symbol,
                "data": {
                    "positionAmt": position.get("positionAmt"),
                    "entryPrice": position.get("entryPrice"),
                    "unrealizedProfit": position.get("unRealizedProfit"),
                },
            },
        )
        return position

    def get_positions(self, open_only: bool = True) -> list[dict]:
        positions = self._call_api(
            "Failed to get positions",
            self.client.futures_position_information,
        )
        if not open_only:
            return positions
        return [
            position
            for position in positions
            if float(position.get("positionAmt", 0)) != 0
        ]

    def get_open_orders(self, symbol: Optional[str] = None) -> list[dict]:
        kwargs = {"symbol": symbol} if symbol else {}
        return self._call_api(
            "Failed to get open orders",
            self.client.futures_get_open_orders,
            **kwargs,
        )

    def get_order_status(self, symbol: str, order_id: int) -> dict:
        return self._call_api(
            f"Failed to get order status for {symbol}",
            self.client.futures_get_order,
            symbol=symbol,
            orderId=order_id,
        )

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        result = self._call_api(
            f"Failed to cancel order for {symbol}",
            self.client.futures_cancel_order,
            symbol=symbol,
            orderId=order_id,
        )
        logger.info(
            "Order cancelled",
            extra={"symbol": symbol, "order_id": order_id, "data": result},
        )
        return result

    def get_symbol_price(self, symbol: str) -> Optional[str]:
        ticker = self._call_api(
            f"Failed to get price for {symbol}",
            self.client.futures_mark_price,
            symbol=symbol,
        )
        price = ticker.get("markPrice")
        logger.info("Mark price retrieved", extra={"symbol": symbol, "data": {"price": price}})
        return price

    def _call_api(self, error_message: str, func: Callable[..., T], **kwargs) -> T:
        try:
            return func(**kwargs)
        except BinanceAPIException as exc:
            self._log_api_error(error_message, exc, kwargs.get("symbol"))
            raise

    def _log_api_error(
        self,
        message: str,
        exc: BinanceAPIException,
        symbol: Optional[str] = None,
    ) -> None:
        logger.error(
            "%s: code=%s msg=%s",
            message,
            exc.code,
            exc.message,
            extra={"symbol": symbol, "error_code": exc.code},
        )
