#!/usr/bin/env python3
"""
📈 Stock News Telegram Bot
Verwaltet eine persönliche Watchlist und liefert aktuelle Aktien-News
"""

import logging
import json
import os
import sqlite3
import asyncio
import feedparser
import yfinance as yf
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ─── Konfiguration ──────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "DEIN_BOT_TOKEN_HIER")
CHAT_ID   = os.getenv("CHAT_ID", "")          # Optional: für automatische Reports

# News-RSS-Feeds (kostenlos, kein API-Key nötig)
RSS_FEEDS = {
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "Seeking Alpha":  "https://seekingalpha.com/market_currents.xml",
    "MarketWatch":    "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines",
    "Reuters":        "https://feeds.reuters.com/reuters/businessNews",
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Datenbank ───────────────────────────────────────────────────────────────
DB_PATH = "stocks.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            chat_id TEXT,
            ticker  TEXT,
            name    TEXT,
            added   TEXT,
            PRIMARY KEY (chat_id, ticker)
        )
    """)
    conn.commit()
    conn.close()

def get_watchlist(chat_id: str) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT ticker, name, added FROM watchlist WHERE chat_id=? ORDER BY ticker", (chat_id,))
    rows = [{"ticker": r[0], "name": r[1], "added": r[2]} for r in c.fetchall()]
    conn.close()
    return rows

def add_to_watchlist(chat_id: str, ticker: str, name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO watchlist VALUES (?,?,?,?)",
              (chat_id, ticker.upper(), name, datetime.now().strftime("%d.%m.%Y")))
    conn.commit()
    conn.close()

def remove_from_watchlist(chat_id: str, ticker: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM watchlist WHERE chat_id=? AND ticker=?", (chat_id, ticker.upper()))
    rows = c.rowcount
    conn.commit()
    conn.close()
    return rows > 0

# ─── Hilfsfunktionen ─────────────────────────────────────────────────────────
def get_stock_info(ticker: str) -> dict | None:
    """Ruft aktuelle Kursdaten via yfinance ab."""
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info
        if not info.get("regularMarketPrice") and not info.get("currentPrice"):
            return None
        price      = info.get("currentPrice") or info.get("regularMarketPrice", 0)
        prev_close = info.get("previousClose", price)
        change     = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0
        return {
            "name":         info.get("shortName", ticker),
            "ticker":       ticker.upper(),
            "price":        price,
            "change":       change,
            "change_pct":   change_pct,
            "currency":     info.get("currency", "USD"),
            "market_cap":   info.get("marketCap"),
            "pe_ratio":     info.get("trailingPE"),
            "52w_high":     info.get("fiftyTwoWeekHigh"),
            "52w_low":      info.get("fiftyTwoWeekLow"),
            "volume":       info.get("volume"),
            "sector":       info.get("sector", "–"),
        }
    except Exception as e:
        logger.warning(f"Fehler bei {ticker}: {e}")
        return None

def format_price(price: float, currency: str = "USD") -> str:
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "CHF": "CHF "}
    sym = symbols.get(currency, f"{currency} ")
    return f"{sym}{price:,.2f}"

def format_change(change: float, pct: float) -> str:
    arrow = "🟢 ▲" if change >= 0 else "🔴 ▼"
    sign  = "+" if change >= 0 else ""
    return f"{arrow} {sign}{change:.2f} ({sign}{pct:.2f}%)"

def get_stock_news(ticker: str, limit: int = 5) -> list[dict]:
    """Ruft News für eine spezifische Aktie via yfinance ab."""
    try:
        stock = yf.Ticker(ticker)
        news  = stock.news or []
        result = []
        for item in news[:limit]:
            content = item.get("content", {})
            title   = content.get("title") or item.get("title", "")
            summary = content.get("summary") or ""
            # Quelle
            provider = ""
            if "provider" in content:
                provider = content["provider"].get("displayName", "")
            url = ""
            if "canonicalUrl" in content:
                url = content["canonicalUrl"].get("url", "")
            if title:
                result.append({"title": title, "summary": summary,
                                "url": url, "source": provider})
        return result
    except Exception as e:
        logger.warning(f"News-Fehler {ticker}: {e}")
        return []

def get_general_news(limit: int = 8) -> list[dict]:
    """Allgemeine Finanz-News aus RSS-Feeds."""
    all_news = []
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                all_news.append({
                    "title":   entry.get("title", ""),
                    "url":     entry.get("link", ""),
                    "source":  source,
                    "summary": entry.get("summary", "")[:200],
                })
        except Exception as e:
            logger.warning(f"RSS Fehler {source}: {e}")
    return all_news[:limit]

def format_large_number(n: float | None) -> str:
    if not n:
        return "–"
    if n >= 1e12:
        return f"{n/1e12:.2f}T"
    if n >= 1e9:
        return f"{n/1e9:.2f}B"
    if n >= 1e6:
        return f"{n/1e6:.2f}M"
    return f"{n:,.0f}"

# ─── Command Handler ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📈 *Stock News Bot* – Willkommen!\n\n"
        "Ich halte dich über Aktien-News auf dem Laufenden "
        "und verwalte deine persönliche Watchlist.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *Befehle*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 /news – Top Finanz-News\n"
        "📊 /watchlist – Deine Watchlist\n"
        "➕ /add `<TICKER>` – Aktie hinzufügen\n"
        "➖ /remove `<TICKER>` – Aktie entfernen\n"
        "💹 /quote `<TICKER>` – Aktueller Kurs\n"
        "📰 /ticker\\_news `<TICKER>` – News für Aktie\n"
        "📋 /report – Watchlist-Report\n"
        "⏰ /schedule – Auto-Report einstellen\n\n"
        "_Beispiel:_ /add AAPL"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allgemeine Top Finanz-News."""
    await update.message.reply_text("⏳ Lade aktuelle News...", parse_mode="Markdown")
    news = get_general_news(limit=8)

    if not news:
        await update.message.reply_text("❌ Keine News verfügbar. Bitte später nochmals versuchen.")
        return

    text = f"📰 *Top Finanz-News*\n_{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n\n"
    for i, item in enumerate(news, 1):
        title = item["title"][:100]
        url   = item["url"]
        src   = item["source"]
        if url:
            text += f"*{i}.* [{title}]({url})\n   📡 _{src}_\n\n"
        else:
            text += f"*{i}.* {title}\n   📡 _{src}_\n\n"

    await update.message.reply_text(text, parse_mode="Markdown",
                                    disable_web_page_preview=True)


async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Zeigt die Watchlist mit aktuellen Kursen."""
    chat_id   = str(update.effective_chat.id)
    watchlist = get_watchlist(chat_id)

    if not watchlist:
        kb = [[InlineKeyboardButton("➕ Aktie hinzufügen", callback_data="help_add")]]
        await update.message.reply_text(
            "📋 Deine Watchlist ist leer.\n\nFüge Aktien hinzu mit:\n`/add AAPL`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    await update.message.reply_text("⏳ Lade Kursdaten...", parse_mode="Markdown")

    text = f"📊 *Deine Watchlist*\n_{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n\n"

    for item in watchlist:
        info = get_stock_info(item["ticker"])
        if info:
            price_str  = format_price(info["price"], info["currency"])
            change_str = format_change(info["change"], info["change_pct"])
            text += (
                f"*{info['name']}* (`{info['ticker']}`)\n"
                f"💰 {price_str}  {change_str}\n\n"
            )
        else:
            text += f"*{item['ticker']}* – ❌ Kurs nicht verfügbar\n\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "💡 /report für detaillierten Report"

    await update.message.reply_text(text, parse_mode="Markdown")


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aktie zur Watchlist hinzufügen."""
    if not context.args:
        await update.message.reply_text(
            "❌ Bitte Ticker angeben:\n`/add AAPL`\n`/add MSFT GOOGL NVDA`",
            parse_mode="Markdown"
        )
        return

    chat_id = str(update.effective_chat.id)
    results = []

    for ticker in context.args:
        ticker = ticker.upper().strip()
        info   = get_stock_info(ticker)

        if info:
            add_to_watchlist(chat_id, ticker, info["name"])
            price_str  = format_price(info["price"], info["currency"])
            change_str = format_change(info["change"], info["change_pct"])
            results.append(
                f"✅ *{info['name']}* (`{ticker}`) hinzugefügt\n"
                f"   {price_str}  {change_str}"
            )
        else:
            results.append(f"❌ `{ticker}` – Ticker nicht gefunden")

    await update.message.reply_text(
        "📋 *Watchlist Update*\n\n" + "\n\n".join(results),
        parse_mode="Markdown"
    )


async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aktie aus Watchlist entfernen."""
    if not context.args:
        await update.message.reply_text(
            "❌ Bitte Ticker angeben:\n`/remove AAPL`",
            parse_mode="Markdown"
        )
        return

    chat_id = str(update.effective_chat.id)
    results = []

    for ticker in context.args:
        ticker = ticker.upper().strip()
        if remove_from_watchlist(chat_id, ticker):
            results.append(f"✅ `{ticker}` aus Watchlist entfernt")
        else:
            results.append(f"❌ `{ticker}` war nicht in deiner Watchlist")

    await update.message.reply_text("\n".join(results), parse_mode="Markdown")


async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detaillierter Kurs für eine Aktie."""
    if not context.args:
        await update.message.reply_text("❌ Bitte Ticker angeben:\n`/quote AAPL`", parse_mode="Markdown")
        return

    ticker = context.args[0].upper()
    await update.message.reply_text(f"⏳ Lade Kursdaten für `{ticker}`...", parse_mode="Markdown")

    info = get_stock_info(ticker)
    if not info:
        await update.message.reply_text(f"❌ `{ticker}` nicht gefunden.", parse_mode="Markdown")
        return

    price_str  = format_price(info["price"], info["currency"])
    change_str = format_change(info["change"], info["change_pct"])
    emoji      = "📈" if info["change"] >= 0 else "📉"

    text = (
        f"{emoji} *{info['name']}* (`{ticker}`)\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Kurs:       `{price_str}`\n"
        f"📊 Änderung: {change_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 52W Hoch:  `{format_price(info['52w_high'] or 0, info['currency'])}`\n"
        f"📅 52W Tief:   `{format_price(info['52w_low'] or 0, info['currency'])}`\n"
        f"📦 Marktk.:    `{format_large_number(info['market_cap'])}`\n"
        f"📉 KGV:        `{'{:.1f}'.format(info['pe_ratio']) if info['pe_ratio'] else '–'}`\n"
        f"📊 Volumen:  `{format_large_number(info['volume'])}`\n"
        f"🏭 Sektor:     `{info['sector']}`\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_{datetime.now().strftime('%d.%m.%Y %H:%M')}_"
    )

    chat_id   = str(update.effective_chat.id)
    watchlist = [w["ticker"] for w in get_watchlist(chat_id)]
    in_wl     = ticker in watchlist

    kb = [[
        InlineKeyboardButton(
            "➖ Aus Watchlist" if in_wl else "➕ Zur Watchlist",
            callback_data=f"{'remove' if in_wl else 'add'}_{ticker}"
        ),
        InlineKeyboardButton("📰 News", callback_data=f"news_{ticker}")
    ]]

    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(kb))


async def ticker_news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """News für eine spezifische Aktie."""
    if not context.args:
        await update.message.reply_text("❌ Bitte Ticker angeben:\n`/ticker_news AAPL`", parse_mode="Markdown")
        return

    ticker = context.args[0].upper()
    await update.message.reply_text(f"⏳ Lade News für `{ticker}`...", parse_mode="Markdown")

    news = get_stock_news(ticker, limit=6)
    if not news:
        await update.message.reply_text(f"❌ Keine News für `{ticker}` gefunden.", parse_mode="Markdown")
        return

    info  = get_stock_info(ticker)
    name  = info["name"] if info else ticker
    emoji = "📈" if (info and info["change"] >= 0) else "📉"

    text = f"{emoji} *{name} ({ticker}) – News*\n_{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n\n"
    for i, item in enumerate(news, 1):
        title = item["title"][:120]
        url   = item["url"]
        src   = item.get("source", "")
        if url:
            text += f"*{i}.* [{title}]({url})\n"
        else:
            text += f"*{i}.* {title}\n"
        if src:
            text += f"   📡 _{src}_\n"
        text += "\n"

    await update.message.reply_text(text, parse_mode="Markdown",
                                    disable_web_page_preview=True)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Vollständiger Report mit Kursen und News für alle Watchlist-Aktien."""
    chat_id   = str(update.effective_chat.id)
    watchlist = get_watchlist(chat_id)

    if not watchlist:
        await update.message.reply_text("📋 Watchlist ist leer. Füge Aktien hinzu mit `/add AAPL`",
                                        parse_mode="Markdown")
        return

    await update.message.reply_text(
        f"⏳ Erstelle Report für {len(watchlist)} Aktien...", parse_mode="Markdown"
    )

    # Kurs-Übersicht
    text = (
        f"📊 *Watchlist Report*\n"
        f"_{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n\n"
        f"{'━'*22}\n"
        f"💹 *KURSE*\n"
        f"{'━'*22}\n"
    )

    for item in watchlist:
        info = get_stock_info(item["ticker"])
        if info:
            price_str  = format_price(info["price"], info["currency"])
            change_str = format_change(info["change"], info["change_pct"])
            emoji      = "🟢" if info["change"] >= 0 else "🔴"
            text += f"{emoji} *{info['name']}* ({item['ticker']})\n   {price_str}  {change_str}\n\n"
        else:
            text += f"❓ `{item['ticker']}` – nicht verfügbar\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")

    # News pro Aktie
    for item in watchlist:
        news = get_stock_news(item["ticker"], limit=3)
        if news:
            news_text = f"📰 *{item['name'] or item['ticker']} – News*\n\n"
            for i, n in enumerate(news, 1):
                title = n["title"][:100]
                url   = n["url"]
                if url:
                    news_text += f"*{i}.* [{title}]({url})\n\n"
                else:
                    news_text += f"*{i}.* {title}\n\n"
            await update.message.reply_text(news_text, parse_mode="Markdown",
                                            disable_web_page_preview=True)
            await asyncio.sleep(0.5)  # Rate-Limit


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Info über automatische Reports."""
    text = (
        "⏰ *Automatische Reports*\n\n"
        "Setze die Umgebungsvariable `CHAT_ID` auf deine Telegram Chat-ID, "
        "um täglich um *08:00 Uhr* einen Watchlist-Report zu erhalten.\n\n"
        "💡 *Deine Chat-ID:*\n"
        f"`{update.effective_chat.id}`\n\n"
        "In der `.env` Datei:\n"
        f"`CHAT_ID={update.effective_chat.id}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── Callback Handler (Inline-Buttons) ───────────────────────────────────────
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    chat_id = str(query.message.chat_id)
    data    = query.data
    await query.answer()

    if data == "help_add":
        await query.message.reply_text(
            "➕ Aktien hinzufügen:\n`/add AAPL`\n`/add MSFT NVDA GOOGL`",
            parse_mode="Markdown"
        )
    elif data.startswith("add_"):
        ticker = data[4:]
        info   = get_stock_info(ticker)
        if info:
            add_to_watchlist(chat_id, ticker, info["name"])
            await query.message.reply_text(
                f"✅ *{info['name']}* zur Watchlist hinzugefügt!",
                parse_mode="Markdown"
            )
    elif data.startswith("remove_"):
        ticker = data[7:]
        remove_from_watchlist(chat_id, ticker)
        await query.message.reply_text(f"✅ `{ticker}` aus Watchlist entfernt.", parse_mode="Markdown")
    elif data.startswith("news_"):
        ticker = data[5:]
        news   = get_stock_news(ticker, limit=5)
        if news:
            text = f"📰 *{ticker} – News*\n\n"
            for i, n in enumerate(news, 1):
                title = n["title"][:100]
                url   = n["url"]
                text += f"*{i}.* [{title}]({url})\n\n" if url else f"*{i}.* {title}\n\n"
            await query.message.reply_text(text, parse_mode="Markdown",
                                           disable_web_page_preview=True)
        else:
            await query.message.reply_text(f"❌ Keine News für `{ticker}` gefunden.", parse_mode="Markdown")


# ─── Automatischer täglicher Report ──────────────────────────────────────────
async def daily_report(app: Application):
    """Wird täglich um 08:00 Uhr automatisch gesendet."""
    if not CHAT_ID:
        return

    from telegram import Bot
    chat_id   = CHAT_ID
    watchlist = get_watchlist(chat_id)
    if not watchlist:
        return

    text = (
        f"🌅 *Guten Morgen! Watchlist-Report*\n"
        f"_{datetime.now().strftime('%d.%m.%Y')}_\n\n"
    )

    for item in watchlist:
        info = get_stock_info(item["ticker"])
        if info:
            price_str  = format_price(info["price"], info["currency"])
            change_str = format_change(info["change"], info["change_pct"])
            emoji      = "🟢" if info["change"] >= 0 else "🔴"
            text += f"{emoji} *{info['name']}*: {price_str} {change_str}\n"

    await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")

    # Top News
    news = get_general_news(limit=5)
    if news:
        news_text = "📰 *Top Finanz-News heute*\n\n"
        for i, item in enumerate(news, 1):
            title = item["title"][:100]
            url   = item["url"]
            news_text += f"*{i}.* [{title}]({url})\n\n" if url else f"*{i}.* {title}\n\n"
        await app.bot.send_message(chat_id=chat_id, text=news_text,
                                   parse_mode="Markdown", disable_web_page_preview=True)


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    init_db()

    if BOT_TOKEN == "DEIN_BOT_TOKEN_HIER":
        print("❌ Bitte BOT_TOKEN in der .env Datei setzen!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Handler registrieren
    app.add_handler(CommandHandler("start",        start))
    app.add_handler(CommandHandler("news",         news_command))
    app.add_handler(CommandHandler("watchlist",    watchlist_command))
    app.add_handler(CommandHandler("add",          add_command))
    app.add_handler(CommandHandler("remove",       remove_command))
    app.add_handler(CommandHandler("quote",        quote_command))
    app.add_handler(CommandHandler("ticker_news",  ticker_news_command))
    app.add_handler(CommandHandler("report",       report_command))
    app.add_handler(CommandHandler("schedule",     schedule_command))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Scheduler für täglichen Report
    scheduler = AsyncIOScheduler(timezone="Europe/Berlin")
    scheduler.add_job(
        daily_report,
        trigger="cron",
        hour=8, minute=0,
        args=[app]
    )
    scheduler.start()
    logger.info("✅ Scheduler gestartet (täglich 08:00 Uhr)")

    logger.info("🚀 Bot gestartet!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()