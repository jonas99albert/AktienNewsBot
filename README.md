# 📈 Stock News Telegram Bot

Ein Telegram Bot für aktuelle Aktien-News und persönliche Watchlist-Verwaltung.

## ✨ Features

- 📰 **Allgemeine News** – Top Finanz-News aus mehreren Quellen (Yahoo Finance, Reuters, MarketWatch)
- 📊 **Watchlist** – Eigene Aktien verwalten mit Live-Kursen
- 💹 **Kursdetails** – Aktueller Kurs, KGV, Marktkapitalisierung, 52W-Hoch/Tief
- 📰 **Aktien-News** – News für eine spezifische Aktie
- 🌅 **Täglicher Report** – Automatisch um 08:00 Uhr (optional)
- 🔘 **Inline-Buttons** – Aktien direkt aus dem Kurs-Menü zur Watchlist hinzufügen

## 🚀 Setup

### 1. Bot bei @BotFather erstellen

1. Öffne Telegram und schreibe `@BotFather`
2. Sende `/newbot`
3. Wähle einen Namen und Username
4. Kopiere den **Bot Token**

### 2. Bot einrichten

```bash
# Repository klonen / Dateien in einen Ordner legen
cd stock_news_bot

# Setup-Script ausführen
chmod +x start.sh
./start.sh
```

Beim ersten Start wird eine `.env` Datei erstellt. Trage dort deinen Token ein:

```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### 3. Bot starten

```bash
./start.sh
```

### 4. Chat-ID für automatische Reports

Sende `/schedule` im Bot – er zeigt dir deine Chat-ID an.  
Trage sie in `.env` ein:

```
CHAT_ID=123456789
```

## 📋 Befehle

| Befehl | Beschreibung |
|--------|-------------|
| `/start` | Willkommen & Hilfe |
| `/news` | Top Finanz-News |
| `/watchlist` | Watchlist mit Kursen |
| `/add AAPL` | Aktie hinzufügen (mehrere möglich: `/add AAPL MSFT NVDA`) |
| `/remove AAPL` | Aktie entfernen |
| `/quote AAPL` | Detaillierter Kurs |
| `/ticker_news AAPL` | News für Aktie |
| `/report` | Vollständiger Watchlist-Report mit News |
| `/schedule` | Automatischen Report einrichten |

## 🔧 Technologie

- `python-telegram-bot` – Bot Framework
- `yfinance` – Kostenlose Kurs- und Newsdaten (kein API-Key nötig)
- `feedparser` – RSS-Feeds (Yahoo Finance, Reuters, MarketWatch)
- `APScheduler` – Täglicher automatischer Report
- `SQLite` – Watchlist-Speicherung

## 💡 Ticker-Beispiele

| Aktie | Ticker |
|-------|--------|
| Apple | `AAPL` |
| Microsoft | `MSFT` |
| NVIDIA | `NVDA` |
| SAP | `SAP` |
| Siemens | `SIE.DE` |
| Deutsche Bank | `DBK.DE` |
| BMW | `BMW.DE` |
| Amazon | `AMZN` |
| Tesla | `TSLA` |
| Alphabet (Google) | `GOOGL` |

> 💡 Deutsche Aktien haben das Suffix `.DE`, Schweizer `.SW`
