"""Order placement for Binance USD-M Futures."""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from binance.exceptions import BinanceAPIException, BinanceOrderException

from bot.client import BinanceFuturesClient
from bot.logging_config import get_logger
from bot.validators import OrderValidator, ValidationResult

logger = get_logger("trading_bot.orders")

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2
PERMANENT_ERROR_CODES = {-1111, -1121, -2010, -2011, -1013, -1021}
BINANCE_ORDER_TYPES = {"STOP_LIMIT": "STOP"}
PRICE_ORDER_TYPES = {"LIMIT", "STOP_LIMIT"}


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: str
    order_type: str
    quantity: str
    price: Optional[str] = None
    stop_price: Optional[str] = None
    time_in_force: Optional[str] = None
    reduce_only: bool = False

    @classmethod
    def build(cls, **kwargs) -> "OrderRequest":
        return cls(
            symbol=kwargs["symbol"].strip().upper(),
            side=kwargs["side"].strip().upper(),
            order_type=kwargs["order_type"].strip().upper(),
            quantity=kwargs["quantity"],
            price=kwargs.get("price"),
            stop_price=kwargs.get("stop_price"),
            time_in_force=(kwargs.get("time_in_force") or "").strip().upper() or None,
            reduce_only=kwargs.get("reduce_only", False),
        )

    def log_data(self) -> dict:
        return {
            "stop_price": self.stop_price,
            "time_in_force": self.time_in_force,
            "reduce_only": self.reduce_only,
        }


@dataclass
class OrderResult:
    success: bool = False
    order_id: Optional[str] = None
    status: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    order_type: Optional[str] = None
    executed_qty: Optional[str] = None
    avg_price: Optional[str] = None
    raw_response: Optional[dict] = None
    error_message: Optional[str] = None

    def __str__(self) -> str:
        if not self.success:
            return (
                f"Order FAILED | {self.symbol} {self.side} {self.order_type} | "
                f"Error: {self.error_message}"
            )
        return (
            f"Order SUCCESS | ID: {self.order_id} | "
            f"{self.symbol} {self.side} {self.order_type} | "
            f"Status: {self.status} | ExecutedQty: {self.executed_qty} | "
            f"AvgPrice: {self.avg_price}"
        )

    def to_display_dict(self) -> dict:
        if not self.success:
            return {
                "status": "FAILED",
                "symbol": self.symbol,
                "side": self.side,
                "type": self.order_type,
                "error": self.error_message,
            }

        result = {
            "status": "SUCCESS",
            "orderId": self.order_id,
            "orderStatus": self.status,
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
        }
        optional = {
            "executedQty": self.executed_qty,
            "avgPrice": self.avg_price,
        }
        result.update({key: value for key, value in optional.items() if value is not None})
        return result


class OrderManager:
    def __init__(self, futures_client: BinanceFuturesClient) -> None:
        self.futures_client = futures_client
        self.validator = OrderValidator(futures_client.client)

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        reduce_only: bool = False,
    ) -> OrderResult:
        return self._place(
            OrderRequest.build(
                symbol=symbol,
                side=side,
                order_type="MARKET",
                quantity=quantity,
                reduce_only=reduce_only,
            )
        )

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> OrderResult:
        return self._place(
            OrderRequest.build(
                symbol=symbol,
                side=side,
                order_type="LIMIT",
                quantity=quantity,
                price=price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
            )
        )

    def place_stop_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: str,
        price: str,
        stop_price: str,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
    ) -> OrderResult:
        return self._place(
            OrderRequest.build(
                symbol=symbol,
                side=side,
                order_type="STOP_LIMIT",
                quantity=quantity,
                price=price,
                stop_price=stop_price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
            )
        )

    def _place(self, request: OrderRequest) -> OrderResult:
        logger.info(
            "Order request received",
            extra={
                "symbol": request.symbol,
                "side": request.side,
                "order_type": request.order_type,
                "quantity": request.quantity,
                "price": request.price,
                "data": request.log_data(),
            },
        )

        validation = self._validate(request)
        if not validation.is_valid:
            message = f"Validation failed: {'; '.join(validation.errors)}"
            return self._failure(request, message)

        self._log_warnings(request, validation)
        params = self._build_order_params(request, validation)

        try:
            response = self._place_order_with_retry(params)
        except BinanceAPIException as exc:
            return self._failure(request, f"API Error (code={exc.code}): {exc.message}")
        except Exception as exc:
            return self._failure(request, f"Unexpected error: {exc}")

        result = self._success(response, request)
        logger.info(
            "Order placement finished",
            extra={
                "symbol": request.symbol,
                "side": request.side,
                "order_type": request.order_type,
                "order_id": result.order_id,
                "status": result.status,
            },
        )
        return result

    def _validate(self, request: OrderRequest) -> ValidationResult:
        return self.validator.validate(
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            quantity=request.quantity,
            price=request.price,
            stop_price=request.stop_price,
            time_in_force=request.time_in_force,
            reduce_only=request.reduce_only,
        )

    def _build_order_params(
        self,
        request: OrderRequest,
        validation: ValidationResult,
    ) -> dict:
        params = {
            "symbol": request.symbol,
            "side": request.side,
            "type": BINANCE_ORDER_TYPES.get(request.order_type, request.order_type),
            "quantity": validation.formatted_quantity,
        }

        if request.order_type == "MARKET":
            params["newOrderRespType"] = "RESULT"

        if request.order_type in PRICE_ORDER_TYPES:
            params.update(
                timeInForce=request.time_in_force or "GTC",
                price=validation.formatted_price,
            )

        if request.order_type == "STOP_LIMIT":
            params.update(
                stopPrice=validation.formatted_stop_price,
                workingType="CONTRACT_PRICE",
            )

        if request.reduce_only:
            params["reduceOnly"] = "true"

        return params

    def _place_order_with_retry(self, params: dict) -> dict:
        last_error: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self._log_order_attempt(params, attempt)
                response = self.futures_client.client.futures_create_order(**params)
                self._log_order_response(params, response)
                return response
            except BinanceAPIException as exc:
                last_error = exc
                if not self._is_retryable_api_error(exc, attempt):
                    raise
            except BinanceOrderException as exc:
                logger.error("Order exception: %s", exc, extra={"symbol": params.get("symbol")})
                raise
            except Exception as exc:
                last_error = exc
                logger.error(
                    "Unexpected order error on attempt %s/%s: %s",
                    attempt,
                    MAX_RETRIES,
                    exc,
                    extra={"symbol": params.get("symbol"), "attempt": attempt},
                )
                if attempt == MAX_RETRIES:
                    raise

            self._sleep_before_retry(attempt)

        raise RuntimeError(
            f"Failed to place order after {MAX_RETRIES} attempts. Last error: {last_error}"
        )

    def _is_retryable_api_error(self, exc: BinanceAPIException, attempt: int) -> bool:
        if exc.status_code == 503 and "Unknown error" in str(exc):
            logger.error(
                "503 unknown execution status. Verify order status before retrying.",
                extra={"error_code": exc.code},
            )
            return False

        retryable = exc.status_code in {408, 429} or exc.status_code >= 500 or exc.code == -1008
        permanent = exc.code in PERMANENT_ERROR_CODES or exc.status_code in {400, 401, 403}

        if retryable and not permanent and attempt < MAX_RETRIES:
            logger.warning(
                "Retryable Binance API error: code=%s status=%s msg=%s",
                exc.code,
                exc.status_code,
                exc.message,
                extra={"error_code": exc.code, "attempt": attempt},
            )
            return True

        logger.error(
            "Binance API error: code=%s status=%s msg=%s",
            exc.code,
            exc.status_code,
            exc.message,
            extra={"error_code": exc.code, "attempt": attempt},
        )
        return False

    def _success(self, response: dict, request: OrderRequest) -> OrderResult:
        avg_price = response.get("avgPrice")
        executed_qty = response.get("executedQty")

        if self._needs_fill_summary(avg_price, response):
            executed_qty, avg_price = self._fills_summary(response["fills"])

        return OrderResult(
            success=True,
            order_id=str(response.get("orderId", "")),
            status=response.get("status", ""),
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            executed_qty=executed_qty,
            avg_price=avg_price,
            raw_response=response,
        )

    def _failure(self, request: OrderRequest, message: str) -> OrderResult:
        logger.error(
            message,
            extra={
                "symbol": request.symbol,
                "side": request.side,
                "order_type": request.order_type,
            },
        )
        return OrderResult(
            success=False,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            error_message=message,
        )

    def _fills_summary(self, fills: list[dict]) -> tuple[Optional[str], Optional[str]]:
        total_qty = Decimal("0")
        total_cost = Decimal("0")

        for fill in fills:
            qty = Decimal(str(fill.get("qty", "0")))
            price = Decimal(str(fill.get("price", "0")))
            total_qty += qty
            total_cost += qty * price

        if total_qty <= 0:
            return None, None

        return str(total_qty.normalize()), str((total_cost / total_qty).normalize())

    def _needs_fill_summary(self, avg_price: Optional[str], response: dict) -> bool:
        return bool(response.get("fills")) and (
            not avg_price or Decimal(str(avg_price)) == 0
        )

    def _log_warnings(self, request: OrderRequest, validation: ValidationResult) -> None:
        for warning in validation.warnings:
            logger.warning(
                "Validation warning: %s",
                warning,
                extra={
                    "symbol": request.symbol,
                    "side": request.side,
                    "order_type": request.order_type,
                },
            )

    def _log_order_attempt(self, params: dict, attempt: int) -> None:
        logger.info(
            "Sending order to Binance",
            extra={
                "symbol": params.get("symbol"),
                "side": params.get("side"),
                "order_type": params.get("type"),
                "attempt": attempt,
                "max_retries": MAX_RETRIES,
                "data": dict(params),
            },
        )

    def _log_order_response(self, params: dict, response: dict) -> None:
        logger.info(
            "Order accepted by Binance",
            extra={
                "symbol": params.get("symbol"),
                "side": params.get("side"),
                "order_type": params.get("type"),
                "order_id": response.get("orderId"),
                "data": response,
            },
        )

    def _sleep_before_retry(self, attempt: int) -> None:
        wait = BASE_BACKOFF_SECONDS ** attempt
        logger.info("Retrying after %s seconds", wait, extra={"attempt": attempt})
        time.sleep(wait)
