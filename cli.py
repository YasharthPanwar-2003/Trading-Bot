"""Typer CLI for the Binance Futures testnet bot."""

from __future__ import annotations

import os
import sys
from typing import Optional

import typer
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.client import BinanceFuturesClient
from bot.logging_config import setup_logger
from bot.orders import OrderManager, OrderResult

load_dotenv()

app = typer.Typer(
    name="trading-bot",
    help="Place orders on Binance USD-M Futures testnet.",
    add_completion=False,
)


def _normalize(value: str) -> str:
    return value.strip().upper()


def _get_client() -> BinanceFuturesClient:
    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        typer.secho(
            "\nERROR: API credentials not found.\n"
            "Create .env from .env.example or set BINANCE_API_KEY and "
            "BINANCE_API_SECRET in your shell.\n",
            fg=typer.colors.RED,
            bold=True,
        )
        raise typer.Exit(code=1)

    client = BinanceFuturesClient(
        api_key=api_key,
        api_secret=api_secret,
        testnet=True,
        use_demo_url=os.environ.get("BINANCE_USE_DEMO_URL", "false").lower() == "true",
    )

    try:
        client.connect()
    except (ConnectionError, ValueError) as exc:
        typer.secho(f"\nConnection failed: {exc}\n", fg=typer.colors.RED, bold=True)
        raise typer.Exit(code=1)

    return client


def _run_order(
    *,
    method_name: str,
    order_type: str,
    yes: bool,
    log_file: Optional[str],
    **order_kwargs,
) -> None:
    if log_file:
        setup_logger(
            "trading_bot",
            log_file=log_file,
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            force=True,
        )

    order_kwargs["symbol"] = _normalize(order_kwargs["symbol"])
    order_kwargs["side"] = _normalize(order_kwargs["side"])
    if "time_in_force" in order_kwargs:
        order_kwargs["time_in_force"] = _normalize(order_kwargs["time_in_force"])

    _print_request_summary(order_type=order_type, **order_kwargs)

    if not yes and not typer.confirm("Place this order?", default=False):
        typer.secho("Order cancelled.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    manager = OrderManager(_get_client())
    result = getattr(manager, method_name)(**order_kwargs)
    _print_order_result(result)

    if not result.success:
        raise typer.Exit(code=1)


def _print_request_summary(order_type: str, **order) -> None:
    side = order["side"]
    side_color = typer.colors.GREEN if side == "BUY" else typer.colors.RED
    rows = [
        ("Symbol", order["symbol"]),
        ("Side", typer.style(side, fg=side_color, bold=True)),
        ("Type", order_type),
        ("Quantity", order["quantity"]),
        ("Price", order.get("price")),
        ("Stop Price", order.get("stop_price")),
        ("Time in Force", order.get("time_in_force")),
        ("Reduce Only", "YES" if order.get("reduce_only") else None),
    ]

    typer.echo("\n" + "=" * 55)
    typer.secho("  ORDER REQUEST SUMMARY", bold=True, fg=typer.colors.CYAN)
    typer.echo("=" * 55)
    for label, value in rows:
        if value is not None:
            typer.echo(f"  {label + ':':<16}{value}")
    typer.echo("=" * 55)


def _print_order_result(result: OrderResult) -> None:
    title = "ORDER PLACED SUCCESSFULLY" if result.success else "ORDER FAILED"
    color = typer.colors.GREEN if result.success else typer.colors.RED

    typer.echo("\n" + "=" * 55)
    typer.secho(f"  {title}", bold=True, fg=color)
    typer.echo("=" * 55)

    if result.success:
        rows = [
            ("Order ID", typer.style(str(result.order_id), bold=True)),
            ("Status", result.status),
            ("Symbol", result.symbol),
            ("Side", result.side),
            ("Type", result.order_type),
            ("Executed Qty", result.executed_qty),
            ("Avg Price", result.avg_price),
        ]
    else:
        rows = [
            ("Error", typer.style(str(result.error_message), fg=typer.colors.RED)),
            ("Symbol", result.symbol),
            ("Side", result.side),
            ("Type", result.order_type),
        ]

    for label, value in rows:
        if value is not None:
            typer.echo(f"  {label + ':':<16}{value}")
    typer.echo("=" * 55 + "\n")


@app.callback()
def main(
    log_level: str = typer.Option(
        os.environ.get("LOG_LEVEL", "INFO"),
        "--log-level",
        "-l",
        help="Logging level: DEBUG, INFO, WARNING, ERROR.",
    ),
    log_file: Optional[str] = typer.Option(
        os.environ.get("LOG_FILE"),
        "--log-file",
        "-f",
        help="Path to log file. Default: logs/trading_bot.log.",
    ),
) -> None:
    setup_logger("trading_bot", log_file=log_file, log_level=log_level)


@app.command()
def market(
    symbol: str = typer.Option(..., "--symbol", "-s", help="Trading pair, e.g. BTCUSDT."),
    side: str = typer.Option(..., "--side", "-S", help="BUY or SELL."),
    quantity: str = typer.Option(..., "--quantity", "-q", help="Order quantity."),
    reduce_only: bool = typer.Option(
        False,
        "--reduce-only",
        "-r",
        help="Only reduce an existing position.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    log_file: Optional[str] = typer.Option(
        None,
        "--log-file",
        help="Write this command's JSON logs to a specific file.",
    ),
) -> None:
    """Place a MARKET order."""
    _run_order(
        method_name="place_market_order",
        order_type="MARKET",
        yes=yes,
        log_file=log_file,
        symbol=symbol,
        side=side,
        quantity=quantity,
        reduce_only=reduce_only,
    )


@app.command()
def limit(
    symbol: str = typer.Option(..., "--symbol", "-s", help="Trading pair, e.g. BTCUSDT."),
    side: str = typer.Option(..., "--side", "-S", help="BUY or SELL."),
    quantity: str = typer.Option(..., "--quantity", "-q", help="Order quantity."),
    price: str = typer.Option(..., "--price", "-p", help="Limit price."),
    time_in_force: str = typer.Option(
        "GTC",
        "--time-in-force",
        "-t",
        help="GTC, IOC, or FOK.",
    ),
    reduce_only: bool = typer.Option(
        False,
        "--reduce-only",
        "-r",
        help="Only reduce an existing position.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    log_file: Optional[str] = typer.Option(
        None,
        "--log-file",
        help="Write this command's JSON logs to a specific file.",
    ),
) -> None:
    """Place a LIMIT order."""
    _run_order(
        method_name="place_limit_order",
        order_type="LIMIT",
        yes=yes,
        log_file=log_file,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        time_in_force=time_in_force,
        reduce_only=reduce_only,
    )


@app.command("stop-limit")
def stop_limit(
    symbol: str = typer.Option(..., "--symbol", "-s", help="Trading pair, e.g. BTCUSDT."),
    side: str = typer.Option(..., "--side", "-S", help="BUY or SELL."),
    quantity: str = typer.Option(..., "--quantity", "-q", help="Order quantity."),
    price: str = typer.Option(..., "--price", "-p", help="Limit price after trigger."),
    stop_price: str = typer.Option(..., "--stop-price", help="Stop trigger price."),
    time_in_force: str = typer.Option(
        "GTC",
        "--time-in-force",
        "-t",
        help="GTC, IOC, or FOK.",
    ),
    reduce_only: bool = typer.Option(
        False,
        "--reduce-only",
        "-r",
        help="Only reduce an existing position.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    log_file: Optional[str] = typer.Option(
        None,
        "--log-file",
        help="Write this command's JSON logs to a specific file.",
    ),
) -> None:
    """Place a STOP-LIMIT order."""
    _run_order(
        method_name="place_stop_limit_order",
        order_type="STOP_LIMIT",
        yes=yes,
        log_file=log_file,
        symbol=symbol,
        side=side,
        quantity=quantity,
        price=price,
        stop_price=stop_price,
        time_in_force=time_in_force,
        reduce_only=reduce_only,
    )


@app.command("test-connection")
def test_connection() -> None:
    """Test Binance Futures testnet connectivity."""
    typer.secho("\nTesting Binance USD-M Futures testnet connection...", fg=typer.colors.CYAN)
    result = _get_client().test_connection()

    if result["connected"]:
        typer.secho("\nConnection SUCCESSFUL!", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"  Base URL:     {result.get('base_url')}")
        typer.echo(f"  Server Time:  {result.get('server_time', {}).get('serverTime', 'N/A')}")
        return

    typer.secho("\nConnection FAILED!", fg=typer.colors.RED, bold=True)
    typer.echo(f"  Base URL: {result.get('base_url')}")
    typer.echo(f"  Error:    {result.get('error', 'Unknown error')}")


@app.command()
def balance(
    asset: str = typer.Option("USDT", "--asset", "-a", help="Asset to check."),
) -> None:
    """Show Futures account balance."""
    asset = _normalize(asset)
    try:
        result = _get_client().get_balance(asset)
    except Exception as exc:
        typer.secho(f"\nFailed to get balance: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not result:
        typer.secho(f"\nNo balance found for asset: {asset}", fg=typer.colors.YELLOW)
        return

    typer.echo("\n" + "=" * 45)
    typer.secho(f"  {asset} Balance", bold=True, fg=typer.colors.CYAN)
    typer.echo("=" * 45)
    typer.echo(f"  Total:       {result.get('balance', 'N/A')}")
    typer.echo(f"  Available:   {result.get('availableBalance', 'N/A')}")
    typer.echo(f"  Cross UnPnl: {result.get('crossUnPnl', 'N/A')}")
    typer.echo("=" * 45 + "\n")


@app.command("open-orders")
def open_orders(
    symbol: Optional[str] = typer.Option(None, "--symbol", "-s", help="Optional symbol filter."),
) -> None:
    """Show open Futures orders."""
    symbol = _normalize(symbol) if symbol else None
    try:
        orders = _get_client().get_open_orders(symbol)
    except Exception as exc:
        typer.secho(f"\nFailed to get open orders: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not orders:
        typer.secho("\nNo open orders found.", fg=typer.colors.YELLOW)
        return

    typer.echo("\nOpen Orders")
    typer.echo("=" * 90)
    for order in orders:
        typer.echo(
            f"{order.get('symbol')} | id={order.get('orderId')} | "
            f"{order.get('side')} {order.get('type')} | "
            f"qty={order.get('origQty')} | price={order.get('price')} | "
            f"status={order.get('status')}"
        )
    typer.echo("=" * 90 + "\n")


@app.command("order-status")
def order_status(
    symbol: str = typer.Option(..., "--symbol", "-s", help="Trading pair, e.g. BTCUSDT."),
    order_id: int = typer.Option(..., "--order-id", help="Binance order id."),
) -> None:
    """Show one order's current status."""
    symbol = _normalize(symbol)
    try:
        order = _get_client().get_order_status(symbol, order_id)
    except Exception as exc:
        typer.secho(f"\nFailed to get order status: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo("\nOrder Status")
    typer.echo("=" * 50)
    typer.echo(f"  Symbol:       {order.get('symbol')}")
    typer.echo(f"  Order ID:     {order.get('orderId')}")
    typer.echo(f"  Side:         {order.get('side')}")
    typer.echo(f"  Type:         {order.get('type')}")
    typer.echo(f"  Status:       {order.get('status')}")
    typer.echo(f"  Orig Qty:     {order.get('origQty')}")
    typer.echo(f"  Executed Qty: {order.get('executedQty')}")
    typer.echo(f"  Avg Price:    {order.get('avgPrice')}")
    typer.echo("=" * 50 + "\n")


@app.command("cancel-order")
def cancel_order(
    symbol: str = typer.Option(..., "--symbol", "-s", help="Trading pair, e.g. BTCUSDT."),
    order_id: int = typer.Option(..., "--order-id", help="Binance order id."),
) -> None:
    """Cancel an open Futures order."""
    symbol = _normalize(symbol)
    try:
        result = _get_client().cancel_order(symbol, order_id)
    except Exception as exc:
        typer.secho(f"\nFailed to cancel order: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho("\nOrder cancelled.", fg=typer.colors.GREEN, bold=True)
    typer.echo(f"  Symbol:   {result.get('symbol')}")
    typer.echo(f"  Order ID: {result.get('orderId')}")
    typer.echo(f"  Status:   {result.get('status')}")


@app.command()
def positions() -> None:
    """Show open Futures positions."""
    try:
        positions_list = _get_client().get_positions(open_only=True)
    except Exception as exc:
        typer.secho(f"\nFailed to get positions: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if not positions_list:
        typer.secho("\nNo open positions found.", fg=typer.colors.YELLOW)
        return

    typer.echo("\nOpen Positions")
    typer.echo("=" * 90)
    for position in positions_list:
        typer.echo(
            f"{position.get('symbol')} | amount={position.get('positionAmt')} | "
            f"entry={position.get('entryPrice')} | mark={position.get('markPrice')} | "
            f"unrealizedPnL={position.get('unRealizedProfit')}"
        )
    typer.echo("=" * 90 + "\n")


@app.command("close-position")
def close_position(
    symbol: str = typer.Option(..., "--symbol", "-s", help="Trading pair, e.g. BTCUSDT."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Close one open position with a reduce-only market order."""
    symbol = _normalize(symbol)
    client = _get_client()
    position = client.get_position(symbol)

    if not position:
        typer.secho(f"\nNo open position found for {symbol}.", fg=typer.colors.YELLOW)
        return

    amount = position.get("positionAmt", "0")
    amount_float = float(amount)
    side = "SELL" if amount_float > 0 else "BUY"
    quantity = str(abs(amount_float))

    typer.echo("\n" + "=" * 55)
    typer.secho("  CLOSE POSITION SUMMARY", bold=True, fg=typer.colors.CYAN)
    typer.echo("=" * 55)
    typer.echo(f"  Symbol:         {symbol}")
    typer.echo(f"  Position Amt:   {amount}")
    typer.echo(f"  Entry Price:    {position.get('entryPrice')}")
    typer.echo(f"  Close Side:     {side}")
    typer.echo(f"  Quantity:       {quantity}")
    typer.echo("=" * 55)

    if not yes and not typer.confirm("Close this position?", default=False):
        typer.secho("Close cancelled.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    manager = OrderManager(client)
    result = manager.place_market_order(
        symbol=symbol,
        side=side,
        quantity=quantity,
        reduce_only=True,
    )
    _print_order_result(result)

    if not result.success:
        raise typer.Exit(code=1)


@app.command("set-leverage")
def set_leverage(
    symbol: str = typer.Option(..., "--symbol", "-s", help="Trading pair, e.g. BTCUSDT."),
    leverage: int = typer.Option(
        ...,
        "--leverage",
        "-l",
        min=1,
        max=125,
        help="Leverage from 1 to 125.",
    ),
) -> None:
    """Set Futures leverage for a symbol."""
    symbol = _normalize(symbol)
    try:
        _get_client().set_leverage(symbol, leverage)
    except Exception as exc:
        typer.secho(f"\nFailed to set leverage: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.secho(
        f"\nLeverage set to {leverage}x for {symbol}",
        fg=typer.colors.GREEN,
        bold=True,
    )


@app.command()
def price(
    symbol: str = typer.Option(..., "--symbol", "-s", help="Trading pair, e.g. BTCUSDT."),
) -> None:
    """Show the current mark price."""
    symbol = _normalize(symbol)
    try:
        mark_price = _get_client().get_symbol_price(symbol)
    except Exception as exc:
        typer.secho(f"\nFailed to get price: {exc}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    if mark_price:
        typer.secho(f"\n{symbol} Mark Price: {mark_price}", fg=typer.colors.GREEN, bold=True)
    else:
        typer.secho(f"\nPrice not available for {symbol}", fg=typer.colors.YELLOW)


if __name__ == "__main__":
    app()
