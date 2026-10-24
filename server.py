"""Web server: serves the Mini App page and its API, and runs the bot.

One process runs both (so it fits a single free-tier host):
  - FastAPI serves /app/ (the Mini App) and /api/* endpoints
  - the Telegram bot runs polling in a background asyncio task

Security notes:
  - Every Mini App request must carry Telegram WebApp initData, and the
    server verifies its HMAC signature with BOT_TOKEN. Never trust a bare
    user id sent by the page.
  - Points are credited ONLY in database.complete_ad_session, which checks
    a one-time ad token and the server-side cooldown. The page cannot
    credit itself.
  - Monetag server-to-server postback (/api/monetag/postback) is the
    strongest verification path when Monetag supports it for your account
    type: configure MONETAG_POSTBACK_SECRET and give Monetag that URL.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import config
import database as db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="Telegram Ads Bot — Mini App API")


def verify_init_data(init_data: str) -> int:
    """Verify Telegram WebApp initData signature. Returns the user id.

    Raises HTTPException if the signature is invalid or the user is missing.
    See https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not config.BOT_TOKEN:
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not configured")
    parsed = dict(urllib.parse.parse_qsl(init_data))
    received_hash = parsed.pop("hash", "")
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise HTTPException(status_code=401, detail="Invalid initData signature")
    try:
        user = json.loads(parsed["user"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="No user in initData")
    return int(user["id"])


def user_summary(user_id: int) -> dict:
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not registered; open /start first")
    return {
        "points": user["points"],
        "kyat_value": round(user["points"] * float(db.get_setting("kyat_per_point")), 2),
        "cooldown_remaining": db.cooldown_remaining(user_id),
        "cooldown_seconds": int(float(db.get_setting("cooldown_seconds"))),
        "points_per_ad": int(float(db.get_setting("points_per_ad"))),
    }


@app.get("/api/config")
def api_config():
    # Zone ID is a publisher identifier, not a secret — safe to expose.
    return {
        "monetag_zone_id": config.MONETAG_ZONE_ID,
        "demo_mode": config.MONETAG_DEMO_MODE,
    }


@app.get("/api/me")
def api_me(initData: str = ""):
    user_id = verify_init_data(initData)
    return user_summary(user_id)


@app.get("/api/history")
def api_history(initData: str = ""):
    user_id = verify_init_data(initData)
    return {"history": db.get_history(user_id)}


@app.post("/api/ad/start")
async def api_ad_start(request: Request):
    body = await request.json()
    user_id = verify_init_data(body.get("initData", ""))
    remaining = db.cooldown_remaining(user_id)
    if remaining > 0:
        return JSONResponse(
            status_code=429,
            content={"error": "cooldown", "cooldown_remaining": remaining},
        )
    token = db.start_ad_session(user_id)
    return {"ad_token": token, "demo_mode": config.MONETAG_DEMO_MODE}


@app.post("/api/ad/complete")
async def api_ad_complete(request: Request):
    body = await request.json()
    user_id = verify_init_data(body.get("initData", ""))
    ad_token = body.get("ad_token", "")
    ok, reason, points = db.complete_ad_session(user_id, ad_token)
    if not ok:
        return JSONResponse(
            status_code=400, content={"error": reason}
        )
    return {"ok": True, "points": points, **user_summary(user_id)}


@app.post("/api/monetag/postback")
async def api_monetag_postback(request: Request):
    """Optional stronger path: Monetag server-to-server postback.

    In your Monetag dashboard, set the postback URL to this endpoint and
    include the user id and a secret you choose. Monetag's exact parameter
    names vary by account type — map them here when you wire it up.
    Without a matching secret, the postback is rejected.
    """
    body = await request.json()
    secret = body.get("secret", "")
    if not config.MONETAG_POSTBACK_SECRET or secret != config.MONETAG_POSTBACK_SECRET:
        raise HTTPException(status_code=401, detail="Bad postback secret")
    user_id = int(body.get("user_id", 0))
    ad_token = body.get("ad_token", "")
    if not user_id or not ad_token:
        raise HTTPException(status_code=400, detail="user_id and ad_token required")
    ok, reason, points = db.complete_ad_session(user_id, ad_token)
    if not ok:
        return JSONResponse(status_code=400, content={"error": reason})
    return {"ok": True, "points": points}


# ---- Mini App static files ----
MINIAPP_DIR = os.path.join(os.path.dirname(__file__), "miniapp")
if os.path.isdir(MINIAPP_DIR):
    app.mount("/app", StaticFiles(directory=MINIAPP_DIR, html=True), name="miniapp")


@app.on_event("startup")
async def startup():
    db.init_db()
    if not config.BOT_TOKEN:
        log.warning("BOT_TOKEN is not set — bot polling disabled, API still runs.")
        return
    from bot import build_application

    application = build_application()
    await application.initialize()
    await application.start()
    asyncio.create_task(application.updater.start_polling())
    log.info("Telegram bot polling started.")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host=config.HOST, port=config.PORT)
