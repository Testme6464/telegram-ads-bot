"""SQLite storage for the first version.

Tables:
  users        — one row per Telegram account (telegram_id is the identity)
  points_ledger— every points movement, so balances are always auditable
  ad_views     — one row per ad session (started -> completed)
  withdrawals  — KBZPay payout requests and their manual-payout status
  revenue      — ad revenue entered by the admin (manual, or Monetag import)
  settings     — admin-adjustable economy values

Switching to Postgres later: replace sqlite3 with psycopg and DATABASE_URL,
keep the same SQL (it is deliberately plain: no SQLite-only features except
AUTOINCREMENT, which Postgres spells as SERIAL — change that one keyword).
"""
import sqlite3
import time
import uuid

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    points INTEGER NOT NULL DEFAULT 0,
    last_ad_at INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS points_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    ref TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ad_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ad_token TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'started',
    points INTEGER NOT NULL DEFAULT 0,
    started_at INTEGER NOT NULL,
    completed_at INTEGER
);
CREATE TABLE IF NOT EXISTS withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    kpay_number TEXT NOT NULL,
    kpay_name TEXT NOT NULL,
    points INTEGER NOT NULL,
    kyat REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    decided_at INTEGER,
    paid_at INTEGER
);
CREATE TABLE IF NOT EXISTS revenue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount_kyat REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    note TEXT,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

DEFAULT_SETTINGS = {
    "points_per_ad": str(config.POINTS_PER_AD),
    "kyat_per_point": str(config.KYAT_PER_POINT),
    "min_withdraw_points": str(config.MIN_WITHDRAW_POINTS),
    "revenue_share_pct": str(config.REVENUE_SHARE_PCT),
    "cooldown_seconds": str(config.COOLDOWN_SECONDS),
}


def connect():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    for key, value in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
    conn.commit()
    conn.close()


def get_setting(key: str) -> str:
    conn = connect()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else DEFAULT_SETTINGS.get(key, "")


def set_setting(key: str, value: str):
    conn = connect()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def _now() -> int:
    return int(time.time())


def get_or_create_user(telegram_id: int, username: str = "", first_name: str = ""):
    conn = connect()
    conn.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, first_name, created_at)"
        " VALUES (?, ?, ?, ?)",
        (telegram_id, username, first_name, _now()),
    )
    conn.execute(
        "UPDATE users SET username = ?, first_name = ? WHERE telegram_id = ?",
        (username, first_name, telegram_id),
    )
    row = conn.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()
    conn.commit()
    conn.close()
    return dict(row)


def get_user(telegram_id: int):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_points(user_id: int, delta: int, reason: str, ref: str = ""):
    """Add (or subtract, if delta is negative) points with a ledger entry."""
    conn = connect()
    conn.execute(
        "UPDATE users SET points = points + ? WHERE telegram_id = ?", (delta, user_id)
    )
    conn.execute(
        "INSERT INTO points_ledger (user_id, delta, reason, ref, created_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (user_id, delta, reason, ref, _now()),
    )
    conn.commit()
    conn.close()


def cooldown_remaining(user_id: int) -> int:
    """Seconds left before this user may watch another ad (0 = allowed)."""
    user = get_user(user_id)
    if not user:
        return 0
    cooldown = int(float(get_setting("cooldown_seconds")))
    left = (user["last_ad_at"] + cooldown) - _now()
    return max(0, left)


def start_ad_session(user_id: int) -> str:
    """Create a one-time ad token. Credit is only possible with this token."""
    token = uuid.uuid4().hex
    conn = connect()
    conn.execute(
        "INSERT INTO ad_views (user_id, ad_token, started_at) VALUES (?, ?, ?)",
        (user_id, token, _now()),
    )
    conn.commit()
    conn.close()
    return token


def complete_ad_session(user_id: int, ad_token: str):
    """Credit points for a finished ad. Returns (ok, message_key, points).

    Rules enforced here, server-side, never in the Mini App page:
      - the token must exist, belong to this user, and be unused
      - the 5-minute cooldown must have passed since the last credited ad
    """
    conn = connect()
    row = conn.execute(
        "SELECT * FROM ad_views WHERE ad_token = ? AND user_id = ?",
        (ad_token, user_id),
    ).fetchone()
    if not row or row["status"] != "started":
        conn.close()
        return False, "invalid_token", 0
    user = conn.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (user_id,)
    ).fetchone()
    cooldown = int(float(get_setting("cooldown_seconds")))
    if user and (user["last_ad_at"] + cooldown) > _now():
        conn.close()
        return False, "cooldown", 0
    points = int(float(get_setting("points_per_ad")))
    conn.execute(
        "UPDATE ad_views SET status = 'completed', points = ?, completed_at = ?"
        " WHERE ad_token = ?",
        (points, _now(), ad_token),
    )
    conn.execute(
        "UPDATE users SET points = points + ?, last_ad_at = ? WHERE telegram_id = ?",
        (points, _now(), user_id),
    )
    conn.execute(
        "INSERT INTO points_ledger (user_id, delta, reason, ref, created_at)"
        " VALUES (?, ?, 'ad_view', ?, ?)",
        (user_id, points, ad_token, _now()),
    )
    conn.commit()
    conn.close()
    return True, "ok", points


def get_history(user_id: int, limit: int = 20):
    conn = connect()
    rows = conn.execute(
        "SELECT delta, reason, created_at FROM points_ledger"
        " WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_withdrawal(user_id: int, kpay_number: str, kpay_name: str, points: int):
    """Deduct points immediately (held in the pending request) and record it.
    On reject, the points are refunded. On approve, the admin pays by hand.
    """
    kyat_per_point = float(get_setting("kyat_per_point"))
    kyat = round(points * kyat_per_point, 2)
    conn = connect()
    conn.execute(
        "UPDATE users SET points = points - ? WHERE telegram_id = ?", (points, user_id)
    )
    conn.execute(
        "INSERT INTO points_ledger (user_id, delta, reason, created_at)"
        " VALUES (?, ?, 'withdrawal_hold', ?)",
        (user_id, -points, _now()),
    )
    cur = conn.execute(
        "INSERT INTO withdrawals (user_id, kpay_number, kpay_name, points, kyat,"
        " status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (user_id, kpay_number, kpay_name, points, kyat, _now()),
    )
    wid = cur.lastrowid
    conn.commit()
    conn.close()
    return wid, kyat


def list_pending_withdrawals():
    conn = connect()
    rows = conn.execute(
        "SELECT * FROM withdrawals WHERE status = 'pending' ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_withdrawal(wid: int):
    conn = connect()
    row = conn.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_withdrawal_status(wid: int, status: str, refund: bool = False):
    conn = connect()
    row = conn.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()
    if not row:
        conn.close()
        return None
    now = _now()
    if status == "paid":
        conn.execute(
            "UPDATE withdrawals SET status = 'paid', paid_at = ? WHERE id = ?",
            (now, wid),
        )
    elif status == "approved":
        conn.execute(
            "UPDATE withdrawals SET status = 'approved', decided_at = ? WHERE id = ?",
            (now, wid),
        )
    elif status == "rejected":
        conn.execute(
            "UPDATE withdrawals SET status = 'rejected', decided_at = ? WHERE id = ?",
            (now, wid),
        )
        if refund:
            conn.execute(
                "UPDATE users SET points = points + ? WHERE telegram_id = ?",
                (row["points"], row["user_id"]),
            )
            conn.execute(
                "INSERT INTO points_ledger (user_id, delta, reason, ref, created_at)"
                " VALUES (?, ?, 'withdrawal_refund', ?, ?)",
                (row["user_id"], row["points"], str(wid), now),
            )
    conn.commit()
    conn.close()
    return dict(row)


def add_revenue(amount_kyat: float, source: str = "manual", note: str = ""):
    conn = connect()
    conn.execute(
        "INSERT INTO revenue (amount_kyat, source, note, created_at)"
        " VALUES (?, ?, ?, ?)",
        (amount_kyat, source, note, _now()),
    )
    conn.commit()
    conn.close()


def get_stats():
    """Totals for the admin panel, including the 70% reward pool math."""
    conn = connect()
    users = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    issued = conn.execute(
        "SELECT COALESCE(SUM(delta),0) s FROM points_ledger WHERE delta > 0"
    ).fetchone()["s"]
    revenue = conn.execute(
        "SELECT COALESCE(SUM(amount_kyat),0) s FROM revenue"
    ).fetchone()["s"]
    paid = conn.execute(
        "SELECT COALESCE(SUM(kyat),0) s FROM withdrawals WHERE status = 'paid'"
    ).fetchone()["s"]
    pending = conn.execute(
        "SELECT COUNT(*) c FROM withdrawals WHERE status = 'pending'"
    ).fetchone()["c"]
    conn.close()
    share = float(get_setting("revenue_share_pct"))
    pool = round(revenue * share / 100.0, 2)
    return {
        "users": users,
        "points_issued": issued,
        "revenue_kyat": revenue,
        "reward_pool_kyat": pool,
        "paid_kyat": paid,
        "pool_remaining_kyat": round(pool - paid, 2),
        "pending_withdrawals": pending,
        "revenue_share_pct": share,
    }
