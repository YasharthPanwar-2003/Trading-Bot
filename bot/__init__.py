"""Core package for the Binance Futures testnet trading bot."""

from bot.client import BinanceFuturesClient
from bot.logging_config import get_logger, setup_logger
from bot.orders import OrderManager, OrderResult
from bot.validators import OrderValidator, ValidationResult

__version__ = "1.0.0"

__all__ = [
    "BinanceFuturesClient",
    "OrderManager",
    "OrderResult",
    "OrderValidator",
    "ValidationResult",
    "setup_logger",
    "get_logger",
]
