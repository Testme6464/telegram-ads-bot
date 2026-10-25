"""Configuration — every secret comes from environment variables.
Nothing secret is ever hard-coded in this file or anywhere in the repo.
Copy .env.example to .env and fill in your own values.
"""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_TELEGRAM_ID = _int("ADMIN_TELEGRAM_ID", 0)
# Public username of the bot, used to build referral links.
BOT_USERNAME = os.environ.get("BOT_USERNAME", "adsrewardmmbot")
DATABASE_PATH = os.environ.get("DATABASE_PATH", "bot.db")
# Postgres connection string (production). When set, database.py uses
# Postgres instead of the local SQLite file — required on Render, where
# the filesystem is wiped on every restart and SQLite points vanish.
# Example: postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Mini App / ads
WEBAPP_URL = os.environ.get("WEBAPP_URL", "")  # e.g. https://your-app.onrender.com/app/
MONETAG_ZONE_ID = os.environ.get("MONETAG_ZONE_ID", "")
# Demo mode simulates an ad completion for testing WITHOUT Monetag.
# NEVER leave this on in production: it would credit points with no ad watched.
MONETAG_DEMO_MODE = os.environ.get("MONETAG_DEMO_MODE", "false").lower() == "true"
# Optional shared secret Monetag sends with server-to-server postbacks.
MONETAG_POSTBACK_SECRET = os.environ.get("MONETAG_POSTBACK_SECRET", "")

# Economy defaults (admin can change all of these from inside the bot)
COOLDOWN_SECONDS = _int("COOLDOWN_SECONDS", 300)        # 5 minutes
POINTS_PER_AD = _int("POINTS_PER_AD", 10)               # points per watched ad
KYAT_PER_POINT = _float("KYAT_PER_POINT", 1.0)          # kyat value of 1 point
MIN_WITHDRAW_POINTS = _int("MIN_WITHDRAW_POINTS", 1000) # minimum withdrawal
REVENUE_SHARE_PCT = _float("REVENUE_SHARE_PCT", 70.0)   # % of ad revenue for rewards
REFERRAL_PCT = _float("REFERRAL_PCT", 10.0)             # % of a referee's ad points paid to the referrer, lifetime, minted on top

PORT = _int("PORT", 8000)
HOST = os.environ.get("HOST", "0.0.0.0")
