"""Input validation for Binance USD-M Futures orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Optional

from binance.client import Client

from bot.logging_config import get_logger

logger = get_logger("trading_bot.validators")

VALID_ORDER_TYPES = {"MARKET", "LIMIT", "STOP_LIMIT"}
VALID_SIDES = {"BUY", "SELL"}
VALID_TIME_IN_FORCE = {"GTC", "IOC", "FOK"}
PRICE_ORDER_TYPES = {"LIMIT", "STOP_LIMIT"}
STOP_PRICE_ORDER_TYPES = {"STOP_LIMIT"}


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    formatted_quantity: Optional[str] = None
    formatted_price: Optional[str] = None
    formatted_stop_price: Optional[str] = None

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.is_valid = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def __str__(self) -> str:
        sections = [f"Valid: {self.is_valid}"]
        if self.errors:
            sections.extend(["Errors:", *[f"  - {item}" for item in self.errors]])
        if self.warnings:
            sections.extend(["Warnings:", *[f"  - {item}" for item in self.warnings]])
        return "\n".join(sections)


class OrderValidator:
    def __init__(self, client: Client) -> None:
        self.client = client
        self._exchange_info: Optional[dict] = None
        self._symbol_info_cache: dict[str, dict] = {}

    def validate(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str,
        price: Optional[str] = None,
        stop_price: Optional[str] = None,
        time_in_force: Optional[str] = None,
        reduce_only: bool = False,
    ) -> ValidationResult:
        result = ValidationResult()
        symbol = self._normalize(symbol)
        side = self._normalize(side)
        order_type = self._normalize(order_type)
        time_in_force = self._normalize(time_in_force)

        self._validate_basic_fields(result, symbol, side, order_type, time_in_force)

        qty_value = self._parse_positive_decimal(result, quantity, "Quantity")
        price_value = self._required_decimal(result, order_type, PRICE_ORDER_TYPES, price, "Price")
        stop_value = self._required_decimal(
            result,
            order_type,
            STOP_PRICE_ORDER_TYPES,
            stop_price,
            "Stop price",
        )

        if reduce_only and side == "BUY":
            result.add_warning("reduce_only with BUY only reduces an existing short position.")

        self._validate_stop_limit_prices(result, side, price_value, stop_value)

        if not result.is_valid:
            logger.warning(
                "Local validation failed",
                extra={
                    "symbol": symbol,
                    "side": side,
                    "order_type": order_type,
                    "data": {"errors": result.errors},
                },
            )
            return result

        return self._with_exchange_rules(
            result=result,
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty_value=qty_value,
            price_value=price_value,
            stop_value=stop_value,
        )

    def clear_cache(self) -> None:
        self._exchange_info = None
        self._symbol_info_cache = {}
        logger.info("Exchange info cache cleared")

    def _validate_basic_fields(
        self,
        result: ValidationResult,
        symbol: str,
        side: str,
        order_type: str,
        time_in_force: str,
    ) -> None:
        checks = (
            (not symbol, "Symbol is required"),
            (bool(symbol) and not symbol.isalnum(), f"Symbol must be alphanumeric, got: '{symbol}'"),
            (side not in VALID_SIDES, f"Invalid side '{side}'. Must be BUY or SELL"),
            (
                order_type not in VALID_ORDER_TYPES,
                f"Invalid order type '{order_type}'. Must be MARKET, LIMIT, or STOP_LIMIT",
            ),
            (
                order_type in PRICE_ORDER_TYPES and time_in_force not in VALID_TIME_IN_FORCE,
                f"Invalid timeInForce '{time_in_force}'. Must be GTC, IOC, or FOK",
            ),
        )

        for failed, message in checks:
            if failed:
                result.add_error(message)

    def _with_exchange_rules(
        self,
        *,
        result: ValidationResult,
        symbol: str,
        side: str,
        order_type: str,
        qty_value: Optional[Decimal],
        price_value: Optional[Decimal],
        stop_value: Optional[Decimal],
    ) -> ValidationResult:
        try:
            self._apply_exchange_rules(
                result=result,
                symbol=symbol,
                side=side,
                order_type=order_type,
                qty_value=qty_value,
                price_value=price_value,
                stop_value=stop_value,
            )
        except Exception as exc:
            logger.error(
                "Exchange-level validation failed: %s",
                exc,
                extra={"symbol": symbol, "error_code": "VALIDATION_EXCHANGE_ERROR"},
            )
            result.add_error(f"Could not validate against exchange rules: {exc}")

        return result

    def _apply_exchange_rules(
        self,
        *,
        result: ValidationResult,
        symbol: str,
        side: str,
        order_type: str,
        qty_value: Optional[Decimal],
        price_value: Optional[Decimal],
        stop_value: Optional[Decimal],
    ) -> None:
        symbol_info = self._get_symbol_info(symbol)
        if not symbol_info:
            result.add_error(f"Symbol '{symbol}' not found on Binance USD-M Futures testnet.")
            return

        if symbol_info.get("status") != "TRADING":
            result.add_error(
                f"Symbol '{symbol}' is not currently trading "
                f"(status: {symbol_info.get('status')})."
            )

        lot_size = self._filter(symbol_info, "LOT_SIZE")
        price_filter = self._filter(symbol_info, "PRICE_FILTER")
        step_size = self._decimal(lot_size, "stepSize")
        min_qty = self._decimal(lot_size, "minQty")
        tick_size = self._decimal(price_filter, "tickSize")

        result.formatted_quantity = self._format_optional(qty_value, step_size)
        result.formatted_price = self._format_optional(price_value, tick_size)
        result.formatted_stop_price = self._format_optional(stop_value, tick_size)

        if min_qty and result.formatted_quantity and Decimal(result.formatted_quantity) < min_qty:
            result.add_error(f"Quantity {qty_value} is below minimum {min_qty} for {symbol}.")

        logger.info(
            "Validation passed",
            extra={
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "data": {
                    "formatted_quantity": result.formatted_quantity,
                    "formatted_price": result.formatted_price,
                    "formatted_stop_price": result.formatted_stop_price,
                },
            },
        )

    def _validate_stop_limit_prices(
        self,
        result: ValidationResult,
        side: str,
        price_value: Optional[Decimal],
        stop_value: Optional[Decimal],
    ) -> None:
        if price_value is None or stop_value is None:
            return

        invalid = {
            "BUY": price_value < stop_value,
            "SELL": price_value > stop_value,
        }.get(side, False)
        if invalid:
            direction = "greater than or equal to" if side == "BUY" else "less than or equal to"
            result.add_error(
                f"{side} STOP_LIMIT limit price should be {direction} stop price."
            )

    def _required_decimal(
        self,
        result: ValidationResult,
        order_type: str,
        required_types: set[str],
        value: Optional[str],
        field_name: str,
    ) -> Optional[Decimal]:
        if order_type not in required_types:
            return None
        return self._parse_positive_decimal(result, value, field_name)

    def _parse_positive_decimal(
        self,
        result: ValidationResult,
        value: Optional[str],
        field_name: str,
    ) -> Optional[Decimal]:
        if value is None or str(value).strip() == "":
            result.add_error(f"{field_name} is required")
            return None

        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError):
            result.add_error(f"{field_name} must be a valid decimal number")
            return None

        if parsed <= 0:
            result.add_error(f"{field_name} must be positive")
            return None

        return parsed

    def _fetch_exchange_info(self) -> dict:
        if self._exchange_info is None:
            logger.info("Fetching Binance Futures exchange info")
            self._exchange_info = self.client.futures_exchange_info()
            logger.info(
                "Exchange info fetched",
                extra={"data": {"symbols_count": len(self._exchange_info.get("symbols", []))}},
            )
        return self._exchange_info

    def _get_symbol_info(self, symbol: str) -> Optional[dict]:
        if symbol not in self._symbol_info_cache:
            self._symbol_info_cache[symbol] = next(
                (
                    item
                    for item in self._fetch_exchange_info().get("symbols", [])
                    if item.get("symbol") == symbol
                ),
                None,
            )
        return self._symbol_info_cache[symbol]

    def _filter(self, symbol_info: dict, filter_type: str) -> dict:
        return next(
            (
                item
                for item in symbol_info.get("filters", [])
                if item.get("filterType") == filter_type
            ),
            {},
        )

    def _decimal(self, data: dict, key: str) -> Optional[Decimal]:
        return Decimal(str(data[key])) if key in data else None

    def _format_optional(
        self,
        value: Optional[Decimal],
        increment: Optional[Decimal],
    ) -> Optional[str]:
        if value is None:
            return None
        if increment is None:
            return self._clean_decimal(value)
        return self._format_to_increment(value, increment)

    def _format_to_increment(self, value: Decimal, increment: Decimal) -> str:
        rounded = (value // increment) * increment
        exponent = max(abs(increment.as_tuple().exponent), 0)
        quantized = rounded.quantize(increment, rounding=ROUND_DOWN)
        return f"{quantized:.{exponent}f}"

    def _clean_decimal(self, value: Decimal) -> str:
        return format(value.normalize(), "f")

    def _normalize(self, value: Optional[str]) -> str:
        return (value or "").strip().upper()
