import json
import os
import sqlite3
from typing import Dict, Optional, Tuple
import io
from datetime import datetime

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
BULK_API_BASE = os.getenv("BULK_API_BASE", "https://exchange-api.bulk.trade/api/v1").rstrip("/")
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()

DB_PATH = os.path.join(os.path.dirname(__file__), "bulk_sim.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            chat_id TEXT PRIMARY KEY,
            recipient TEXT NOT NULL,
            fee_bps INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS balances (
            recipient TEXT PRIMARY KEY,
            balance REAL NOT NULL DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            market TEXT,
            side TEXT,
            size REAL,
            price REAL,
            recipient TEXT,
            fee_bps INTEGER,
            notional REAL,
            fee_paid REAL,
            ts TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def set_approval(chat_id: str, recipient: str, fee_bps: int) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO approvals(chat_id, recipient, fee_bps) VALUES (?, ?, ?)"
        " ON CONFLICT(chat_id) DO UPDATE SET recipient=excluded.recipient, fee_bps=excluded.fee_bps",
        (chat_id, recipient, fee_bps),
    )
    conn.commit()
    conn.close()


def get_approval(chat_id: str) -> Optional[Tuple[str, int]]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT recipient, fee_bps FROM approvals WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return (row["recipient"], row["fee_bps"])


def delete_approval(chat_id: str) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM approvals WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def add_balance(recipient: str, amount: float) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO balances(recipient, balance) VALUES (?, ?)"
                " ON CONFLICT(recipient) DO UPDATE SET balance = balances.balance + excluded.balance",
                (recipient, amount))
    conn.commit()
    conn.close()


def get_balances() -> Dict[str, float]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT recipient, balance FROM balances")
    rows = cur.fetchall()
    conn.close()
    return {r["recipient"]: r["balance"] for r in rows}


def save_order(chat_id: str, market: str, side: str, size: float, price: float, recipient: Optional[str], fee_bps: Optional[int], notional: float, fee_paid: float) -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO orders(chat_id, market, side, size, price, recipient, fee_bps, notional, fee_paid, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (chat_id, market, side, size, price, recipient, fee_bps, notional, fee_paid, datetime.utcnow().isoformat() + 'Z')
    )
    conn.commit()
    conn.close()


def is_allowed(update: Update) -> bool:
    if not ALLOWED_CHAT_ID:
        return True
    return str(update.effective_chat.id) == ALLOWED_CHAT_ID


def build_approval_payload(recipient: str, fee_bps: int) -> dict:
    return {"abc": {"to": recipient, "fee": fee_bps}}


def build_order_payload(market: str, side: str, size: float, price: float, recipient: Optional[str] = None, fee_bps: Optional[int] = None) -> dict:
    payload = {
        "m": {
            "c": market,
            "b": side.lower() in {"buy", "b", "long"},
            "sz": size,
            "r": False,
            "i": False,
        }
    }
    if recipient and fee_bps is not None:
        payload["m"]["builderCode"] = {"to": recipient, "fee": fee_bps}
    return payload


def format_payload(payload: dict) -> str:
    return json.dumps(payload, indent=2)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "BULK Builder Codes MVP is live.\n\n"
        "Use /approve_builder <recipient_pubkey> <fee_bps>\n"
        "Use /preview_order <market> <side> <size> <price>\n"
        "Use /status to check your active builder setup"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "Commands:\n"
        "• /start - welcome message\n"
        "• /approve_builder <recipient_pubkey> <fee_bps> - store a builder approval payload\n"
        "• /preview_order <market> <side> <size> <price> - build a BULK order payload\n"
        "• /status - show current builder-code setup"
    )


async def approve_builder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: /approve_builder <recipient_pubkey> <fee_bps>")
        return

    recipient = args[0]
    try:
        fee_bps = int(args[1])
    except ValueError:
        await update.message.reply_text("Fee must be an integer between 1 and 15.")
        return

    if not 1 <= fee_bps <= 15:
        await update.message.reply_text("Fee must be between 1 and 15 basis points.")
        return

    chat_key = str(update.effective_chat.id)
    set_approval(chat_key, recipient, fee_bps)

    payload = build_approval_payload(recipient, fee_bps)
    await update.message.reply_text(
        "Builder approval payload prepared.\n\n"
        f"```json\n{format_payload(payload)}\n```",
        parse_mode="Markdown"
    )


async def preview_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return

    args = context.args
    if len(args) < 4:
        await update.message.reply_text("Usage: /preview_order <market> <side> <size> <price> [recipient] [fee_bps]")
        return

    market = args[0]
    side = args[1]
    try:
        size = float(args[2])
        price = float(args[3])
    except ValueError:
        await update.message.reply_text("Size and price must be numeric values.")
        return

    chat_key = str(update.effective_chat.id)
    recipient = None
    fee_bps = None

    if len(args) >= 6:
        recipient = args[4]
        try:
            fee_bps = int(args[5])
        except ValueError:
            await update.message.reply_text("Fee must be an integer between 1 and 15.")
            return
    else:
        apr = get_approval(chat_key)
        if apr:
            recipient, fee_bps = apr

    payload = build_order_payload(market, side, size, price, recipient, fee_bps)
    await update.message.reply_text(
        "Order payload ready for BULK routing.\n\n"
        f"```json\n{format_payload(payload)}\n```\n\n"
        f"Endpoint hint: {BULK_API_BASE}",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    chat_key = str(update.effective_chat.id)
    apr = get_approval(chat_key)
    if apr:
        recipient, fee = apr
        await update.message.reply_text(
            "Active builder setup:\n"
            f"Recipient: {recipient}\n"
            f"Fee: {fee} bps"
        )
    else:
        await update.message.reply_text("No builder setup saved for this chat yet. Use /approve_builder first.")


if not TELEGRAM_TOKEN:
    raise SystemExit("Please set TELEGRAM_TOKEN in your environment before running the bot.")


async def export_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return

    args = context.args
    if len(args) < 4:
        await update.message.reply_text("Usage: /export_order <market> <side> <size> <price> [recipient] [fee_bps]")
        return

    market = args[0]
    side = args[1]
    try:
        size = float(args[2])
        price = float(args[3])
    except ValueError:
        await update.message.reply_text("Size and price must be numeric values.")
        return

    chat_key = str(update.effective_chat.id)
    recipient = None
    fee_bps = None

    if len(args) >= 6:
        recipient = args[4]
        try:
            fee_bps = int(args[5])
        except ValueError:
            await update.message.reply_text("Fee must be an integer between 1 and 15.")
            return
    elif chat_key in STATE:
        recipient = STATE[chat_key]["recipient"]
        fee_bps = STATE[chat_key]["fee"]

    payload = build_order_payload(market, side, size, price, recipient, fee_bps)

    # Create a JSON file in-memory and send as a document
    filename = f"order_{chat_key}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    bio = io.BytesIO()
    bio.write(json.dumps(payload, indent=2).encode())
    bio.seek(0)

    await update.message.reply_text("Prepared order payload; sending JSON file...")
    await update.message.reply_document(document=bio, filename=filename)

    # Also show the payload preview
    await update.message.reply_text(
        "Order payload (preview):\n\n"
        f"```json\n{format_payload(payload)}\n```\n\n"
        f"Endpoint hint: {BULK_API_BASE}",
        parse_mode="Markdown"
    )

 


async def revoke_builder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    chat_key = str(update.effective_chat.id)
    apr = get_approval(chat_key)
    if apr:
        delete_approval(chat_key)
        await update.message.reply_text("Builder approval revoked for this chat.")
    else:
        await update.message.reply_text("No builder approval found for this chat.")


async def submit_order_sim(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Simulate order execution locally and settle builder fees to virtual balances."""
    if not is_allowed(update):
        return

    args = context.args
    if len(args) < 4:
        await update.message.reply_text("Usage: /submit_order_sim <market> <side> <size> <price> [recipient] [fee_bps]")
        return

    market = args[0]
    side = args[1]
    try:
        size = float(args[2])
        price = float(args[3])
    except ValueError:
        await update.message.reply_text("Size and price must be numeric values.")
        return

    chat_key = str(update.effective_chat.id)
    recipient = None
    fee_bps = None
    if len(args) >= 6:
        recipient = args[4]
        try:
            fee_bps = int(args[5])
        except ValueError:
            await update.message.reply_text("Fee must be an integer between 1 and 15.")
            return
    else:
        apr = get_approval(chat_key)
        if apr:
            recipient, fee_bps = apr

    payload = build_order_payload(market, side, size, price, recipient, fee_bps)

    # Simple immediate-fill simulation
    notional = size * price
    fee_paid = 0.0
    if recipient and fee_bps:
        fee_paid = (notional * fee_bps) / 10000.0
        add_balance(recipient, fee_paid)

    save_order(chat_key, market, side, size, price, recipient, fee_bps, notional, fee_paid)

    # Respond with simulated execution details
    await update.message.reply_text(
        "Order simulated and executed (sim):\n"
        f"Market: {market}\n"
        f"Side: {side}\n"
        f"Size: {size}\n"
        f"Price: {price}\n"
        f"Notional: {notional:.6f}\n"
        f"Builder fee paid: {fee_paid:.6f}\n"
        f"Builder recipient: {recipient or 'none'}\n"
    )


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_allowed(update):
        return
    balances = get_balances()
    if not balances:
        await update.message.reply_text("No builder fees settled yet.")
        return
    lines = [f"{acct}: {bal:.6f}" for acct, bal in sorted(balances.items(), key=lambda x: -x[1])]
    await update.message.reply_text("Builder leaderboard:\n" + "\n".join(lines))


 


async def export_state(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Export all DB state (approvals, balances, orders) as a JSON file."""
    if not is_allowed(update):
        return
    # Parse optional args: chat=<chat_id> from=YYYY-MM-DD to=YYYY-MM-DD full
    args = context.args
    opts = { }
    for a in args:
        if "=" in a:
            k, v = a.split("=", 1)
            opts[k.lower()] = v
        elif a.lower() == "full":
            opts["full"] = True

    conn = get_db()
    cur = conn.cursor()

    # Approvals: filter by chat if provided
    approvals = []
    if "chat" in opts:
        cur.execute("SELECT chat_id, recipient, fee_bps FROM approvals WHERE chat_id = ?", (opts["chat"],))
        approvals = [dict(r) for r in cur.fetchall()]
    else:
        cur.execute("SELECT chat_id, recipient, fee_bps FROM approvals")
        approvals = [dict(r) for r in cur.fetchall()]

    # Balances: if chat filter provided, map to that chat's recipient and return only that recipient's balance
    balances = []
    if "chat" in opts and approvals:
        # show balance for recipient(s) of this chat
        recipients = [a["recipient"] for a in approvals]
        cur.execute("SELECT recipient, balance FROM balances WHERE recipient IN ({seq})".format(seq=','.join('?'*len(recipients))), tuple(recipients))
        balances = [dict(r) for r in cur.fetchall()]
    else:
        cur.execute("SELECT recipient, balance FROM balances")
        balances = [dict(r) for r in cur.fetchall()]

    # Orders: apply chat and date filters unless 'full' provided
    orders_query = "SELECT id, chat_id, market, side, size, price, recipient, fee_bps, notional, fee_paid, ts FROM orders WHERE 1=1"
    params = []
    if not opts.get("full"):
        if "chat" in opts:
            orders_query += " AND chat_id = ?"
            params.append(opts["chat"])
        if "from" in opts:
            # inclusive
            orders_query += " AND ts >= ?"
            params.append(opts["from"] + "T00:00:00Z")
        if "to" in opts:
            orders_query += " AND ts <= ?"
            params.append(opts["to"] + "T23:59:59Z")
        orders_query += " ORDER BY id DESC LIMIT 1000"
    else:
        orders_query += " ORDER BY id DESC"

    cur.execute(orders_query, tuple(params))
    orders = [dict(r) for r in cur.fetchall()]

    conn.close()

    state = {
        "exportedAt": datetime.utcnow().isoformat() + 'Z',
        "filters": opts,
        "approvals": approvals,
        "balances": balances,
        "orders": orders,
    }

    bio = io.BytesIO()
    bio.write(json.dumps(state, indent=2).encode())
    bio.seek(0)

    filename = f"bulk_sim_state_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    await update.message.reply_document(document=bio, filename=filename)
    await update.message.reply_text(f"Exported state: {len(approvals)} approvals, {len(balances)} balances, {len(orders)} orders. Filters: {opts}")


 

def build_app() -> 'ApplicationBuilder':
    app_local = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app_local.add_handler(CommandHandler("start", start))
    app_local.add_handler(CommandHandler("help", help_command))
    app_local.add_handler(CommandHandler("approve_builder", approve_builder))
    app_local.add_handler(CommandHandler("preview_order", preview_order))
    app_local.add_handler(CommandHandler("status", status))
    app_local.add_handler(CommandHandler("export_order", export_order))
    app_local.add_handler(CommandHandler("revoke_builder", revoke_builder))
    app_local.add_handler(CommandHandler("submit_order_sim", submit_order_sim))
    app_local.add_handler(CommandHandler("leaderboard", leaderboard))
    app_local.add_handler(CommandHandler("export_state", export_state))
    return app_local

init_db()
app = build_app()


def main() -> None:
    print("BULK Builder Codes MVP bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()