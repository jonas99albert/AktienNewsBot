#!/bin/bash
# ─── Stock News Bot – Setup & Start ──────────────────────────────────────────

echo "📈 Stock News Bot Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━"

# .env erstellen falls nicht vorhanden
if [ ! -f .env ]; then
    cp .env.example .env
    echo "✅ .env Datei erstellt"
    echo ""
    echo "⚠️  Bitte BOT_TOKEN in .env eintragen:"
    echo "   nano .env"
    echo ""
    echo "Bot-Token bekommst du von @BotFather auf Telegram."
    exit 0
fi

# Abhängigkeiten installieren
echo "📦 Installiere Abhängigkeiten..."
pip install -r requirements.txt --quiet

echo ""
echo "🚀 Starte Bot..."
echo "   Drücke Ctrl+C zum Stoppen"
echo ""

# .env laden und Bot starten
export $(grep -v '^#' .env | xargs)
python bot.py
