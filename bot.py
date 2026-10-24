"""Telegram bot: balance, Mini App entry, KBZPay withdrawals, admin panel.

All user-facing text is in Burmese. Payouts are MANUAL by design:
the admin approves a request, sends the money with the KBZPay app by hand,
then marks the request as paid in this bot. There is no automatic transfer.
"""
import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import config
import database as db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Conversation states for the withdrawal flow
KPAY_NUMBER, KPAY_NAME, KPAY_POINTS, KPAY_CONFIRM = range(4)


def is_admin(user_id: int) -> bool:
    return config.ADMIN_TELEGRAM_ID != 0 and user_id == config.ADMIN_TELEGRAM_ID


def main_menu() -> InlineKeyboardMarkup:
    buttons = []
    if config.WEBAPP_URL:
        buttons.append(
            [InlineKeyboardButton("🎬 Mini App ဖွင့် (ကြော်ငြာကြည့်)",
                                  web_app=WebAppInfo(url=config.WEBAPP_URL))]
        )
    buttons.append([
        InlineKeyboardButton("💰 လက်ကျန်ကြည့်မယ်", callback_data="balance"),
        InlineKeyboardButton("💸 ထုတ်ယူမယ်", callback_data="withdraw"),
    ])
    buttons.append([InlineKeyboardButton("❓ အကူအညီ", callback_data="help")])
    return InlineKeyboardMarkup(buttons)


def balance_text(user_id: int) -> str:
    user = db.get_user(user_id)
    kyat_per_point = float(db.get_setting("kyat_per_point"))
    points = user["points"] if user else 0
    return (
        f"💰 သင့်လက်ကျန်\n\n"
        f"Points: {points}\n"
        f"ခန့်မှန်းတန်ဖိုး: {points * kyat_per_point:,.0f} ကျပ်\n"
        f"(၁ point = {kyat_per_point} ကျပ်)"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username or "", user.first_name or "")
    await update.message.reply_text(
        "မင်္ဂလာပါ! 🎬\n\n"
        "ကြော်ငြာကြည့်ပြီး point စုတဲ့ bot ပါ။\n"
        "• ၅ မိနစ်ခြား တစ်ခါ ကြော်ငြာကြည့်လို့ရတယ်\n"
        "• ကြော်ငြာတစ်ခါကြည့်တိုင်း point ရတယ်\n"
        "• Point တွေကို KBZPay နဲ့ ဆုကြေးအဖြစ် ထုတ်ယူလို့ရတယ်\n\n"
        "Mini App ကို ဖွင့်ပြီး ကြော်ငြာကြည့်ပါ 👇",
        reply_markup=main_menu(),
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "❓ အကူအညီ\n\n"
        "• ကြော်ငြာကြည့်ရန်: Mini App ဖွင့် → “ကြော်ငြာကြည့်” ကို နှိပ်ပါ\n"
        "• ၅ မိနစ်ခြား တစ်ခါပဲ ကြည့်လို့ရပါတယ်\n"
        "• Point ရဖို့ ကြော်ငြာကို အဆုံးထိ ကြည့်ရပါမယ်\n"
        "• ထုတ်ယူရန်: “ထုတ်ယူမယ်” ကို နှိပ်ပြီး KBZPay အကောင့်နံပါတ်၊\n"
        "  နာမည်နဲ့ point ပမာဏ ထည့်ပါ\n"
        "• ထုတ်ယူမှုကို admin က အတည်ပြုပြီးမှ KBZPay နဲ့ လူကိုယ်တိုင်\n"
        "  လွှဲပေးပါမယ်\n\n"
        "Commands: /start /balance /withdraw /help"
    )
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text(text)
    else:
        await update.message.reply_text(text)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data == "balance":
        await query.message.reply_text(balance_text(user_id), reply_markup=main_menu())
    elif data == "help":
        await query.message.reply_text(
            "❓ အကူအညီ\n\n"
            "• ကြော်ငြာကြည့်ရန်: Mini App ဖွင့် → “ကြော်ငြာကြည့်” ကို နှိပ်ပါ\n"
            "• ၅ မိနစ်ခြား တစ်ခါပဲ ကြည့်လို့ရပါတယ်\n"
            "• Point ရဖို့ ကြော်ငြာကို အဆုံးထိ ကြည့်ရပါမယ်\n"
            "• ထုတ်ယူရန်: “ထုတ်ယူမယ်” ကို နှိပ်ပြီး KBZPay အကောင့်နံပါတ်၊\n"
            "  နာမည်နဲ့ point ပမာဏ ထည့်ပါ\n"
            "• ထုတ်ယူမှုကို admin က အတည်ပြုပြီးမှ KBZPay နဲ့ လူကိုယ်တိုင်\n"
            "  လွှဲပေးပါမယ်"
        )
    elif data == "withdraw":
        await query.message.reply_text(
            "💸 ထုတ်ယူရန်\n\nKBZPay အကောင့်နံပါတ်ကို ပို့ပေးပါ (ဥပမာ 09xxxxxxxxx):"
        )
        return KPAY_NUMBER
    elif data.startswith("admin_approve:"):
        await admin_decide(update, context, "approved")
    elif data.startswith("admin_reject:"):
        await admin_decide(update, context, "rejected")
    elif data.startswith("admin_paid:"):
        await admin_decide(update, context, "paid")
    return ConversationHandler.END


# ---------------- Withdrawal conversation ----------------

async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💸 ထုတ်ယူရန်\n\nKBZPay အကောင့်နံပါတ်ကို ပို့ပေးပါ (ဥပမာ 09xxxxxxxxx):"
    )
    return KPAY_NUMBER


async def kpay_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["kpay_number"] = update.message.text.strip()
    await update.message.reply_text("KBZPay အကောင့်နာမည်ကို ပို့ပေးပါ:")
    return KPAY_NAME


async def kpay_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["kpay_name"] = update.message.text.strip()
    min_points = db.get_setting("min_withdraw_points")
    await update.message.reply_text(
        f"ထုတ်ယူမယ့် point ပမာဏကို ပို့ပေးပါ (အနည်းဆုံး {min_points} points):"
    )
    return KPAY_POINTS


async def kpay_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        points = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("ဂဏန်းနဲ့ပဲ ရေးပေးပါ:")
        return KPAY_POINTS
    user = db.get_user(update.effective_user.id)
    min_points = int(float(db.get_setting("min_withdraw_points")))
    if points < min_points:
        await update.message.reply_text(f"အနည်းဆုံး {min_points} points မှ ထုတ်လို့ရပါတယ်:")
        return KPAY_POINTS
    if not user or user["points"] < points:
        await update.message.reply_text(
            f"လက်ကျန်မလောက်ပါဘူး။ သင့်လက်ကျန်က {user['points'] if user else 0} points ပါ:"
        )
        return KPAY_POINTS
    context.user_data["points"] = points
    kyat = round(points * float(db.get_setting("kyat_per_point")), 2)
    await update.message.reply_text(
        f"အတည်ပြုပါ:\n\n"
        f"KBZPay: {context.user_data['kpay_number']}\n"
        f"နာမည်: {context.user_data['kpay_name']}\n"
        f"Points: {points}\n"
        f"ရမယ့်ငွေ: {kyat:,.0f} ကျပ်\n\n"
        f"မှန်ရင် “အတည်ပြုမယ်”၊ ပြင်ချင်ရင် “မလုပ်တော့ဘူး” လို့ ပို့ပါ။"
    )
    return KPAY_CONFIRM


async def kpay_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text not in ("အတည်ပြုမယ်", "အတည်ပြုသည်", "yes", "Yes"):
        await update.message.reply_text("ထုတ်ယူမှုကို ပယ်ဖျက်လိုက်ပါပြီ။", reply_markup=main_menu())
        return ConversationHandler.END
    user_id = update.effective_user.id
    wid, kyat = db.create_withdrawal(
        user_id,
        context.user_data["kpay_number"],
        context.user_data["kpay_name"],
        context.user_data["points"],
    )
    await update.message.reply_text(
        f"✅ ထုတ်ယူတောင်းဆိုမှု တင်ပြီးပါပြီ (အမှတ် #{wid})။\n"
        f"Admin အတည်ပြုပြီးမှ KBZPay နဲ့ လွှဲပေးပါမယ်။",
        reply_markup=main_menu(),
    )
    if config.ADMIN_TELEGRAM_ID:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ အတည်ပြုမယ်", callback_data=f"admin_approve:{wid}"),
             InlineKeyboardButton("❌ ပယ်ချမယ်", callback_data=f"admin_reject:{wid}")],
        ])
        await context.bot.send_message(
            chat_id=config.ADMIN_TELEGRAM_ID,
            text=(
                f"💸 ထုတ်ယူတောင်းဆိုမှု အသစ် (#{wid})\n\n"
                f"User: {user_id}\n"
                f"KBZPay: {context.user_data['kpay_number']}\n"
                f"နာမည်: {context.user_data['kpay_name']}\n"
                f"Points: {context.user_data['points']}\n"
                f"ငွေ: {kyat:,.0f} ကျပ်"
            ),
            reply_markup=keyboard,
        )
    return ConversationHandler.END


async def withdraw_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ပယ်ဖျက်လိုက်ပါပြီ။", reply_markup=main_menu())
    return ConversationHandler.END


# ---------------- Admin ----------------

async def admin_decide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.message.reply_text("Admin မှသာ လုပ်လို့ရပါတယ်။")
        return
    action, wid = query.data.split(":")
    wid = int(wid)
    w = db.get_withdrawal(wid)
    if not w:
        await query.message.reply_text("တောင်းဆိုမှု မတွေ့ပါ။")
        return
    if action == "admin_approve":
        db.set_withdrawal_status(wid, "approved")
        await context.bot.send_message(
            chat_id=w["user_id"],
            text=f"✅ သင့်ထုတ်ယူမှု (#{wid}) ကို admin က အတည်ပြုလိုက်ပါပြီ။\n"
                 f"KBZPay နဲ့ မကြာခင် လွှဲပေးပါလိမ့်မယ်။",
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("💰 လွှဲပြီးပြီ (Paid အဖြစ် မှတ်မယ်)",
                                 callback_data=f"admin_paid:{wid}")
        ]])
        await query.message.reply_text(
            f"#{wid} ကို အတည်ပြုပြီးပါပြီ။ KBZPay app နဲ့ လူကိုယ်တိုင် "
            f"{w['kyat']:,.0f} ကျပ် လွှဲပြီးမှ အောက်က ခလုတ်ကို နှိပ်ပါ။",
            reply_markup=keyboard,
        )
    elif action == "admin_reject":
        db.set_withdrawal_status(wid, "rejected", refund=True)
        await context.bot.send_message(
            chat_id=w["user_id"],
            text=f"❌ သင့်ထုတ်ယူမှု (#{wid}) ကို ပယ်ချလိုက်ပါတယ်။ "
                 f"Points {w['points']} ကို ပြန်ထည့်ပေးပြီးပါပြီ။",
        )
        await query.message.reply_text(f"#{wid} ကို ပယ်ချပြီး points ပြန်ထည့်ပေးပါပြီ။")
    elif action == "admin_paid":
        db.set_withdrawal_status(wid, "paid")
        await context.bot.send_message(
            chat_id=w["user_id"],
            text=f"💰 သင့်ထုတ်ယူမှု (#{wid}) အတွက် {w['kyat']:,.0f} ကျပ်ကို "
                 f"KBZPay နဲ့ လွှဲပြီးပါပြီ။ ကျေးဇူးပါ!",
        )
        await query.message.reply_text(f"#{wid} ကို Paid အဖြစ် မှတ်လိုက်ပါပြီ။")


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Admin မှသာ ကြည့်လို့ရပါတယ်။")
        return
    stats = db.get_stats()
    pending = db.list_pending_withdrawals()
    lines = [
        "📊 Admin စာရင်း",
        f"• Users: {stats['users']}",
        f"• ထုတ်ပေးပြီး point: {stats['points_issued']}",
        f"• ကြော်ငြာဝင်ငွေ စုစုပေါင်း: {stats['revenue_kyat']:,.0f} ကျပ်",
        f"• ဆုကြေးရန်ပုံငွေ ({stats['revenue_share_pct']:.0f}%): "
        f"{stats['reward_pool_kyat']:,.0f} ကျပ်",
        f"• ပေးပြီးသား: {stats['paid_kyat']:,.0f} ကျပ်",
        f"• ရန်ပုံငွေ ကျန်: {stats['pool_remaining_kyat']:,.0f} ကျပ်",
        f"• စောင့်နေတဲ့ ထုတ်ယူမှု: {stats['pending_withdrawals']} ခု",
        "",
        "Commands:",
        "/pending — စောင့်နေတဲ့ ထုတ်ယူမှုများ",
        "/add_revenue <kyat> — ကြော်ငြာဝင်ငွေ ထည့်ရန်",
        "/set_points_per_ad <n> — ကြော်ငြာတစ်ခါရတဲ့ point",
        "/set_kyat_rate <kyat> — ၁ point = ဘယ်နှစ်ကျပ်",
        "/set_share <pct> — ဆုကြေးရန်ပုံငွေ %",
        "/set_min_withdraw <points> — အနည်းဆုံး ထုတ်ယူမှု",
    ]
    if pending:
        lines.append("")
        lines.append("စောင့်နေတာများ:")
        for w in pending:
            lines.append(
                f"#{w['id']} — user {w['user_id']}, {w['points']} pts, "
                f"{w['kyat']:,.0f} ကျပ်, {w['kpay_number']} ({w['kpay_name']})"
            )
    await update.message.reply_text("\n".join(lines))


async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    pending = db.list_pending_withdrawals()
    if not pending:
        await update.message.reply_text("စောင့်နေတဲ့ ထုတ်ယူမှု မရှိပါ။")
        return
    for w in pending:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ အတည်ပြုမယ်", callback_data=f"admin_approve:{w['id']}"),
             InlineKeyboardButton("❌ ပယ်ချမယ်", callback_data=f"admin_reject:{w['id']}")],
        ])
        await update.message.reply_text(
            f"#{w['id']} — user {w['user_id']}\n"
            f"KBZPay: {w['kpay_number']} ({w['kpay_name']})\n"
            f"{w['points']} pts = {w['kyat']:,.0f} ကျပ်",
            reply_markup=keyboard,
        )


async def _admin_set(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     key: str, label: str):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(f"သုံးပုံ: /{label} <တန်ဖိုး>")
        return
    db.set_setting(key, context.args[0])
    await update.message.reply_text(f"✅ {label} ကို {context.args[0]} အဖြစ် ပြင်လိုက်ပါပြီ။")


async def set_points_per_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _admin_set(update, context, "points_per_ad", "set_points_per_ad")


async def set_kyat_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _admin_set(update, context, "kyat_per_point", "set_kyat_rate")


async def set_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _admin_set(update, context, "revenue_share_pct", "set_share")


async def set_min_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _admin_set(update, context, "min_withdraw_points", "set_min_withdraw")


async def add_revenue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("သုံးပုံ: /add_revenue <kyat> [မှတ်ချက်]")
        return
    try:
        amount = float(context.args[0])
    except ValueError:
        await update.message.reply_text("ဂဏန်းနဲ့ ရေးပေးပါ။")
        return
    note = " ".join(context.args[1:])
    db.add_revenue(amount, source="manual", note=note)
    stats = db.get_stats()
    await update.message.reply_text(
        f"✅ ဝင်ငွေ {amount:,.0f} ကျပ် ထည့်ပြီးပါပြီ။\n"
        f"ဆုကြေးရန်ပုံငွေ ({stats['revenue_share_pct']:.0f}%) ကျန်: "
        f"{stats['pool_remaining_kyat']:,.0f} ကျပ်"
    )


def build_application() -> Application:
    # Sandbox quirk: some environments export no_proxy entries like
    # "[fd8b:...::1]" that httpx's proxy parser rejects. Strip bracketed
    # entries before PTB builds its HTTP client. Harmless elsewhere.
    import os

    for var in ("no_proxy", "NO_PROXY"):
        val = os.environ.get(var)
        if val and "[" in val:
            os.environ[var] = ",".join(p for p in val.split(",") if "[" not in p)
    app = Application.builder().token(config.BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("balance",
                                   lambda u, c: u.message.reply_text(
                                       balance_text(u.effective_user.id),
                                       reply_markup=main_menu())))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("pending", pending_cmd))
    app.add_handler(CommandHandler("add_revenue", add_revenue_cmd))
    app.add_handler(CommandHandler("set_points_per_ad", set_points_per_ad))
    app.add_handler(CommandHandler("set_kyat_rate", set_kyat_rate))
    app.add_handler(CommandHandler("set_share", set_share))
    app.add_handler(CommandHandler("set_min_withdraw", set_min_withdraw))
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("withdraw", withdraw_start),
            CallbackQueryHandler(on_button, pattern="^withdraw$"),
        ],
        states={
            KPAY_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, kpay_number)],
            KPAY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, kpay_name)],
            KPAY_POINTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, kpay_points)],
            KPAY_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, kpay_confirm)],
        },
        fallbacks=[CommandHandler("cancel", withdraw_cancel)],
    )
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(on_button))
    return app
