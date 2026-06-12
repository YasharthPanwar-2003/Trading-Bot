# Binance Futures Testnet Trading Bot

Python CLI app for placing Binance USD-M Futures testnet/demo orders with validation, structured logging, error handling, and a reusable code structure.

## Features

- Place MARKET orders.
- Place LIMIT orders.
- Bonus: place STOP-LIMIT orders.
- Supports BUY and SELL sides.
- Validates CLI input before sending an order.
- Formats quantity and price using Binance exchange rules.
- Writes structured JSON logs.
- Provides utility commands for balance, price, positions, open orders, order status, cancellation, and position closing.
- Includes unit tests that do not require Binance credentials.

## Project Structure

```text
trading_bot/
  bot/
    __init__.py
    client.py          # Binance Futures API wrapper
    orders.py          # Order placement and retry logic
    validators.py      # Input and exchange-rule validation
    logging_config.py  # Console and JSON file logging
  tests/
    test_orders.py
  cli.py
  .env.example
  .gitignore
  README.md
  requirements.txt
```

## How It Works

1. User runs a Typer CLI command in PowerShell.
2. `cli.py` prints an order summary and asks for confirmation unless `--yes` is passed.
3. `OrderManager` validates the request.
4. `OrderValidator` checks symbol, side, order type, quantity, price, and Binance tick/step size rules.
5. `BinanceFuturesClient` sends the request to Binance USD-M Futures testnet/demo.
6. The CLI prints `orderId`, status, executed quantity, average price when available, and success/failure.
7. JSON logs are written to the selected log file.

## Prerequisites

- PowerShell
- `uv` installed
- Binance Futures Testnet/Demo API key and secret
- Testnet/demo USDT balance

On this machine, `python` is not available directly on PATH, so the recommended commands use `uv`.

## Binance API Keys

Do not use a normal Binance Spot/Mainnet API key.

Use a Binance Futures Testnet/Demo key. Current Binance Futures demo keys use:

```text
https://demo-fapi.binance.com
```

The assignment mentions:

```text
https://testnet.binancefuture.com
```

This project supports both:

- `BINANCE_USE_DEMO_URL=true` for current Binance Demo/Futures keys.
- `BINANCE_USE_DEMO_URL=false` only for legacy `testnet.binancefuture.com` keys.

If Binance returns this error:

```text
API Error (code=-2015): Invalid API-key, IP, or permissions for action
```

check that:

- The key was created for Futures Testnet/Demo, not Spot/Mainnet.
- API/Futures trading permission is enabled.
- IP restriction allows your current IP, or is disabled while testing.
- API key and secret are on separate `.env` lines.

## Setup

From this project folder:

```powershell
cd C:\Users\vish9\Downloads\trading_bot_project_full\trading_bot
```

Check the CLI:

```powershell
uv run --with-requirements requirements.txt python cli.py --help
```

Create your `.env`:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```env
BINANCE_API_KEY=your_testnet_or_demo_key
BINANCE_API_SECRET=your_testnet_or_demo_secret
BINANCE_USE_DEMO_URL=true
LOG_LEVEL=INFO
LOG_FILE=logs/trading_bot.log
```

Never commit `.env`.

## Required Commands

Test signed Binance connectivity:

```powershell
uv run --with-requirements requirements.txt python cli.py test-connection
```

Check balance:

```powershell
uv run --with-requirements requirements.txt python cli.py balance
```

Place a MARKET order:

```powershell
uv run --with-requirements requirements.txt python cli.py market --symbol BTCUSDT --side BUY --quantity 0.001
```

Place a LIMIT order:

```powershell
uv run --with-requirements requirements.txt python cli.py limit --symbol BTCUSDT --side SELL --quantity 0.001 --price 120000
```

Skip confirmation for repeatable testing:

```powershell
uv run --with-requirements requirements.txt python cli.py market --symbol BTCUSDT --side BUY --quantity 0.001 --yes
```

## Bonus Command

Place a STOP-LIMIT order:

```powershell
uv run --with-requirements requirements.txt python cli.py stop-limit --symbol BTCUSDT --side SELL --quantity 0.001 --price 109000 --stop-price 110000
```

## Useful Utility Commands

Get mark price:

```powershell
uv run --with-requirements requirements.txt python cli.py price --symbol BTCUSDT
```

Set leverage:

```powershell
uv run --with-requirements requirements.txt python cli.py set-leverage --symbol BTCUSDT --leverage 5
```

Show open orders:

```powershell
uv run --with-requirements requirements.txt python cli.py open-orders --symbol BTCUSDT
```

Check one order:

```powershell
uv run --with-requirements requirements.txt python cli.py order-status --symbol BTCUSDT --order-id 123456789
```

Cancel an open order:

```powershell
uv run --with-requirements requirements.txt python cli.py cancel-order --symbol BTCUSDT --order-id 123456789
```

Show open positions:

```powershell
uv run --with-requirements requirements.txt python cli.py positions
```

Close an open position safely with a reduce-only MARKET order:

```powershell
uv run --with-requirements requirements.txt python cli.py close-position --symbol BTCUSDT
```

## Logs

Logs are ignored by Git because they can contain account/order details.

Default log file:

```text
logs/trading_bot.log
```

Generate the required evaluator logs locally:

```powershell
uv run --with-requirements requirements.txt python cli.py market --symbol BTCUSDT --side BUY --quantity 0.001 --yes --log-file logs/market_order.log
```

```powershell
uv run --with-requirements requirements.txt python cli.py limit --symbol BTCUSDT --side SELL --quantity 0.001 --price 120000 --yes --log-file logs/limit_order.log
```

For a public GitHub repo, keep logs ignored. If the evaluator requires logs, attach sanitized copies separately or include them in a private zip submission.

Example log entry:

```json
{
  "timestamp": "2026-06-12T10:30:00+00:00",
  "level": "INFO",
  "logger": "trading_bot.orders",
  "message": "Order accepted by Binance",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "order_type": "MARKET",
  "order_id": 123456789
}
```

## Tests

Run tests:

```powershell
uv run --with-requirements requirements.txt python -m unittest discover -s tests
```

The tests use fake Binance clients, so they do not need real API keys.

Current coverage checks:

- LIMIT orders require price.
- Quantity is formatted using `LOT_SIZE.stepSize`.
- Price is formatted using `PRICE_FILTER.tickSize`.
- MARKET orders request `newOrderRespType=RESULT`.
- STOP-LIMIT maps to Binance order type `STOP`.

## Cleanup After Testing

Check account state:

```powershell
uv run --with-requirements requirements.txt python cli.py open-orders --symbol BTCUSDT
uv run --with-requirements requirements.txt python cli.py positions
```

If there is an open order, cancel it:

```powershell
uv run --with-requirements requirements.txt python cli.py cancel-order --symbol BTCUSDT --order-id 123456789
```

If there is an open position, close it:

```powershell
uv run --with-requirements requirements.txt python cli.py close-position --symbol BTCUSDT --yes
```

## GitHub Submission

Initialize Git locally:

```powershell
git init
git add .
git status
```

Before committing, confirm `.env` and `logs/` are not staged.

Commit:

```powershell
git commit -m "Build Binance Futures testnet trading bot"
```

Create an empty GitHub repo, then connect it:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

## Assumptions

- This app is for Binance USD-M Futures testnet/demo only.
- It does not use Binance mainnet.
- Current Binance Demo/Futures keys should use `BINANCE_USE_DEMO_URL=true`.
- Logs are generated locally and ignored by Git by default.
