"""Storage for the bot. Two modes, chosen by environment:

  - DATABASE_URL set  -> Postgres (production). Required on Render: free
    instances have an ephemeral filesystem, so a SQLite file is wiped on
    every redeploy/restart/spin-down and all points vanish with it. A hosted
    Postgres (e.g. Supabase free tier) survives restarts, so points do too.
  - DATABASE_URL unset -> SQLite file (local development only).

The same call sites serve both modes through a thin connection wrapper.
Postgres differences handled here, in one place:
  - placeholders: sqlite3 uses ?, psycopg uses %s (translated in _Conn)
  - AUTOINCREMENT -> SERIAL, telegram_id/user_id -> BIGINT
  - INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING (2 call sites)
  - cursor.lastrowid -> INSERT ... RETURNING id (create_withdrawal)

Tables:
  users        — one row per Telegram account (telegram_id is the identity)
  points_ledger— every points movement, so balances are always auditable
  ad_views     — one row per ad session (started -> completed)
  withdrawals  — KBZPay payout requests and their manual-payout status
  revenue      — ad revenue entered by the admin (manual, or Monetag import)
  settings     — admin-adjustable economy values
"""
import time
import uuid

import config

USE_POSTGRES = bool(config.DATABASE_URL)

if USE_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row
else:
    import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    points INTEGER NOT NULL DEFAULT 0,
    last_ad_at INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL,
    referrer_id INTEGER
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
    "referral_pct": str(config.REFERRAL_PCT),
}


def _postgres_schema() -> str:
    s = SCHEMA
    s = s.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    s = s.replace("telegram_id INTEGER PRIMARY KEY", "telegram_id BIGINT PRIMARY KEY")
    s = s.replace("user_id INTEGER NOT NULL", "user_id BIGINT NOT NULL")
    s = s.replace("referrer_id INTEGER", "referrer_id BIGINT")
    return s


class _Conn:
    """sqlite3/psycopg connection wrapper with one shared interface.

    execute() translates ? placeholders to %s for Postgres. Returned
    cursors support fetchone()/fetchall() and dict-style row access in
    both modes (sqlite3.Row / psycopg dict_row).
    """

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=None):
        if USE_POSTGRES:
            sql = sql.replace("?", "%s")
        if params is None:
            return self._raw.execute(sql)
        return self._raw.execute(sql, params)

    def executescript(self, sql):
        # SQLite-only path (init_db branches for Postgres).
        self._raw.executescript(sql)

    def commit(self):
        self._raw.commit()

    def close(self):
        self._raw.close()


def connect():
    if USE_POSTGRES:
        url = config.DATABASE_URL
        if "sslmode" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        raw = psycopg.connect(url, row_factory=dict_row)
    else:
        raw = sqlite3.connect(config.DATABASE_PATH)
        raw.row_factory = sqlite3.Row
    return _Conn(raw)


def init_db():
    conn = connect()
    if USE_POSTGRES:
        conn.execute(_postgres_schema())
        # Migration for databases created before referrals existed.
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS referrer_id BIGINT")
    else:
        conn.executescript(SCHEMA)
        cols = conn.execute("PRAGMA table_info(users)").fetchall()
        if "referrer_id" not in [c["name"] for c in cols]:
            conn.execute("ALTER TABLE users ADD COLUMN referrer_id INTEGER")
    for key, value in DEFAULT_SETTINGS.items():
        if USE_POSTGRES:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT (key) DO NOTHING",
                (key, value),
            )
        else:
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
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
    if USE_POSTGRES:
        conn.execute(
            "INSERT INTO users (telegram_id, username, first_name, created_at)"
            " VALUES (?, ?, ?, ?) ON CONFLICT (telegram_id) DO NOTHING",
            (telegram_id, username, first_name, _now()),
        )
    else:
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


def set_referrer(user_id: int, referrer_id: int) -> bool:
    """Attach a referrer once. Returns True if attached.

    Ignored when: self-referral, the user already has a referrer,
    or the referrer is not a registered user. First registration wins;
    a later referral link never overwrites the stored referrer.
    """
    if user_id == referrer_id:
        return False
    conn = connect()
    row = conn.execute(
        "SELECT referrer_id FROM users WHERE telegram_id = ?", (user_id,)
    ).fetchone()
    if not row or row["referrer_id"] is not None:
        conn.close()
        return False
    ref = conn.execute(
        "SELECT 1 AS one FROM users WHERE telegram_id = ?", (referrer_id,)
    ).fetchone()
    if not ref:
        conn.close()
        return False
    conn.execute(
        "UPDATE users SET referrer_id = ? WHERE telegram_id = ?",
        (referrer_id, user_id),
    )
    conn.commit()
    conn.close()
    return True


def get_referral_stats(user_id: int):
    """How many users this user referred, and total bonus earned."""
    conn = connect()
    count = conn.execute(
        "SELECT COUNT(*) c FROM users WHERE referrer_id = ?", (user_id,)
    ).fetchone()["c"]
    bonus = conn.execute(
        "SELECT COALESCE(SUM(delta),0) s FROM points_ledger"
        " WHERE user_id = ? AND reason = 'referral_bonus'",
        (user_id,),
    ).fetchone()["s"]
    conn.close()
    return {"referred_count": count, "bonus_total": bonus}


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
    # Referral bonus (lifetime, minted on top — the referee keeps every
    # point). The referrer gets referral_pct % of each completed ad view.
    ref_row = conn.execute(
        "SELECT referrer_id FROM users WHERE telegram_id = ?", (user_id,)
    ).fetchone()
    referrer_id = ref_row["referrer_id"] if ref_row else None
    if referrer_id and referrer_id != user_id:
        exists = conn.execute(
            "SELECT 1 AS one FROM users WHERE telegram_id = ?", (referrer_id,)
        ).fetchone()
        if exists:
            try:
                pct = float(get_setting("referral_pct"))
            except (TypeError, ValueError):
                pct = 10.0
            bonus = int(points * pct // 100)
            if bonus > 0:
                conn.execute(
                    "UPDATE users SET points = points + ? WHERE telegram_id = ?",
                    (bonus, referrer_id),
                )
                conn.execute(
                    "INSERT INTO points_ledger (user_id, delta, reason, ref, created_at)"
                    " VALUES (?, ?, 'referral_bonus', ?, ?)",
                    (referrer_id, bonus, ad_token, _now()),
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
    if USE_POSTGRES:
        cur = conn.execute(
            "INSERT INTO withdrawals (user_id, kpay_number, kpay_name, points, kyat,"
            " status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?) RETURNING id",
            (user_id, kpay_number, kpay_name, points, kyat, _now()),
        )
        wid = cur.fetchone()["id"]
    else:
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
    row = conn.execute(
        "SELECT * FROM withdrawals WHERE id = ?", (wid,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_withdrawal_status(wid: int, status: str, refund: bool = False):
    conn = connect()
    row = conn.execute(
        "SELECT * FROM withdrawals WHERE id = ?", (wid,)
    ).fetchone()
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
