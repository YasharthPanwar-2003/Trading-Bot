import logging
import unittest

from bot.orders import OrderManager
from bot.validators import OrderValidator


logging.getLogger("trading_bot").addHandler(logging.NullHandler())


class FakeBinanceApi:
    def __init__(self):
        self.created_orders = []

    def futures_exchange_info(self):
        return {
            "symbols": [
                {
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "filters": [
                        {
                            "filterType": "LOT_SIZE",
                            "minQty": "0.001",
                            "stepSize": "0.001",
                        },
                        {
                            "filterType": "PRICE_FILTER",
                            "tickSize": "0.10",
                        },
                    ],
                }
            ]
        }

    def futures_create_order(self, **params):
        self.created_orders.append(params)
        return {
            "symbol": params["symbol"],
            "orderId": 12345,
            "status": "NEW",
            "executedQty": "0",
            "avgPrice": "0",
        }


class FakeFuturesClient:
    def __init__(self):
        self.api = FakeBinanceApi()

    @property
    def client(self):
        return self.api


class OrderValidatorTests(unittest.TestCase):
    def test_limit_order_requires_price(self):
        validator = OrderValidator(FakeBinanceApi())

        result = validator.validate(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="0.001",
            time_in_force="GTC",
        )

        self.assertFalse(result.is_valid)
        self.assertIn("Price is required", "; ".join(result.errors))

    def test_quantity_and_price_are_formatted_to_exchange_rules(self):
        validator = OrderValidator(FakeBinanceApi())

        result = validator.validate(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity="0.0019",
            price="120000.123",
            time_in_force="GTC",
        )

        self.assertTrue(result.is_valid)
        self.assertEqual(result.formatted_quantity, "0.001")
        self.assertEqual(result.formatted_price, "120000.10")


class OrderManagerTests(unittest.TestCase):
    def test_market_order_requests_result_response(self):
        futures_client = FakeFuturesClient()
        manager = OrderManager(futures_client)

        result = manager.place_market_order(
            symbol="BTCUSDT",
            side="BUY",
            quantity="0.001",
        )

        self.assertTrue(result.success)
        self.assertEqual(
            futures_client.api.created_orders[-1],
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "MARKET",
                "quantity": "0.001",
                "newOrderRespType": "RESULT",
            },
        )

    def test_limit_order_sends_expected_binance_params(self):
        futures_client = FakeFuturesClient()
        manager = OrderManager(futures_client)

        result = manager.place_limit_order(
            symbol="btcusdt",
            side="buy",
            quantity="0.0019",
            price="120000.123",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.order_id, "12345")
        self.assertEqual(
            futures_client.api.created_orders[-1],
            {
                "symbol": "BTCUSDT",
                "side": "BUY",
                "type": "LIMIT",
                "quantity": "0.001",
                "timeInForce": "GTC",
                "price": "120000.10",
            },
        )

    def test_stop_limit_order_maps_to_binance_stop_type(self):
        futures_client = FakeFuturesClient()
        manager = OrderManager(futures_client)

        result = manager.place_stop_limit_order(
            symbol="BTCUSDT",
            side="SELL",
            quantity="0.001",
            price="109000",
            stop_price="110000",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.order_type, "STOP_LIMIT")
        self.assertEqual(futures_client.api.created_orders[-1]["type"], "STOP")
        self.assertEqual(futures_client.api.created_orders[-1]["stopPrice"], "110000.00")


if __name__ == "__main__":
    unittest.main()
