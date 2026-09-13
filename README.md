# Bulk Builder Codes Telegram Simulator

A lightweight Telegram bot for simulating BULK Builder Codes flows without using real funds, real wallets, or live execution.

This project is intentionally a sandbox MVP. It helps you:

- preview a BULK-style order payload
- approve or revoke a builder recipient
- simulate fee settlement with virtual balances
- track simulated orders in SQLite
- export the bot state as JSON for review

It is designed as a simple demo and proof-of-concept for BULK-style builder routing and fee logic, not a production trading system.

## What the bot does

The bot can:

- accept a builder recipient and fee in basis points
- generate a builder approval payload
- preview an order payload for a market and side
- simulate execution locally with virtual balance updates
- log all orders to SQLite
- show a simple leaderboard of builder fee totals
- export the full state of approvals, balances, and orders

## Tech stack

- Python 3.11+
- python-telegram-bot
- python-dotenv
- SQLite
- JSON export for state inspection

## Repository structure

- `bot.py` — Telegram bot and simulator logic
- `.env.example` — example environment variables
- `.env` — local environment file (not committed)
- `requirements.txt` — Python dependencies
- `bulk_sim.db` — local SQLite database created at runtime

## Setup

1. Create a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

   On Windows PowerShell:

   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

   On Windows PowerShell:

   ```powershell
   Copy-Item .env.example .env
   ```

4. Fill in the values in `.env`:

   ```env
   TELEGRAM_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
   BULK_API_BASE=https://exchange-api.bulk.trade/api/v1
   ALLOWED_CHAT_ID=
   DEFAULT_BUILDER_RECIPIENT=7bSjpMQ1DzrhPJArPzoR5uVYcWJSwCFGXR1TBWrf6Zoe
   DEFAULT_BUILDER_FEE_BPS=5
   ```

   Notes:
   - `TELEGRAM_TOKEN` is the bot token from BotFather.
   - `ALLOWED_CHAT_ID` can be left blank for public demo use.
   - `DEFAULT_BUILDER_RECIPIENT` is a mock builder wallet/public key used in the simulator.
   - `DEFAULT_BUILDER_FEE_BPS` is the default fee in basis points.

5. Start the bot:

   ```bash
   python bot.py
   ```

## Telegram commands

### `/start`
Shows the welcome message and available commands.

### `/approve_builder <recipient> <fee_bps>`
Store a builder approval for the current chat.

Example:

```text
/approve_builder 7bSjpMQ1DzrhPJArPzoR5uVYcWJSwCFGXR1TBWrf6Zoe 5
```

### `/status`
Shows the active builder recipient and fee for the current chat.

### `/preview_order <market> <side> <size> <price> [recipient] [fee_bps]`
Builds a simulated BULK-like order payload.

Example:

```text
/preview_order SOL/USDC buy 1 100
```

### `/export_order <market> <side> <size> <price> [recipient] [fee_bps]`
Exports the generated order payload as a JSON file.

### `/revoke_builder`
Removes the saved builder approval for the current chat.

### `/submit_order_sim <market> <side> <size> <price> [recipient] [fee_bps]`
Simulates an order fill and updates the virtual balance for the builder recipient.

Example:

```text
/submit_order_sim SOL/USDC buy 1 100
```

### `/leaderboard`
Shows the current virtual fee totals by recipient.

### `/export_state [chat=<chat_id>] [from=YYYY-MM-DD] [to=YYYY-MM-DD] [full]`
Exports approvals, balances, and historical orders as a JSON file.

Examples:

```text
/export_state
/export_state chat=123456789
/export_state from=2026-09-01 to=2026-09-13
/export_state full
```

## Demo behavior

This bot intentionally does not move funds, submit signed transactions, or connect to a live exchange.

Instead, it demonstrates the workflow of:

1. setting a builder approval
2. preparing an order payload
3. simulating execution
4. paying a virtual builder fee
5. exporting the state for review

This makes it useful for concept validation, demos, and educational walkthroughs around BULK-style builder routing.

## Security note

- Do not commit your real `.env` file.
- Keep your Telegram token private.
- This project is a simulator, not a production wallet or exchange integration.

## License

This project is provided as a simple demo and is intended for educational and prototyping use.

## Future ideas

Possible next steps include:

- richer order validation rules
- more realistic mock market data
- better formatting for exported JSON
- a web dashboard for the simulator state
- optional wallet signing demos or payload signing examples

## Summary

This repo is a no-funds BULK Builder Codes Telegram simulator designed for simple demos, iterations, and idea validation. It is intentionally small, readable, and easy to run locally or in a cloud environment such as GitHub Codespaces.
