# Telegram ကြော်ငြာ Point Bot 🎬

ကြော်ငြာကြည့်ပြီး point စုမယ်။ Point ကို KBZPay နဲ့ ဆုကြေးအဖြစ် ထုတ်ယူမယ်။
**KBZPay ထုတ်ပေးမှုက လူကိုယ်တိုင် လုပ်တာပါ** — အလိုအလျောက် လွှဲပေးတာ မဟုတ်ပါဘူး။

## အလုပ်လုပ်ပုံ

1. User က bot မှာ `/start` နှိပ်ပြီး Mini App ဖွင့်တယ်။
2. Mini App မှာ “ကြော်ငြာကြည့်” ကို နှိပ်တယ် (၅ မိနစ်ခြား တစ်ခါ)။
3. Monetag ကြော်ငြာ အဆုံးထိ ကြည့်ပြီးမှ point တက်တယ်။
4. Point ပြည့်ရင် bot ထဲမှာ ထုတ်ယူတောင်းဆိုတယ် (KBZPay နံပါတ် + နာမည် + point)။
5. Admin က အတည်ပြုတယ် → KBZPay app နဲ့ လူကိုယ်တိုင် လွှဲတယ် →
   bot ထဲမှာ “လွှဲပြီးပြီ” လို့ မှတ်တယ်။
6. ကြော်ငြာဝင်ငွေရဲ့ 70% (admin ပြင်လို့ရ) ကို ဆုကြေးရန်ပုံငွေအဖြစ် ထားတယ်။
   Admin panel မှာ ဝင်ငွေ၊ ရန်ပုံငွေ၊ ပေးပြီးသားကို အမြဲ ကြည့်လို့ရတယ်။

## ဖြည့်ရမယ့်အရာများ

| Variable | ဘယ်ကယူမလဲ |
|---|---|
| `BOT_TOKEN` | Telegram မှာ @BotFather ကနေ bot ဖွင့်ပြီး ယူပါ |
| `ADMIN_TELEGRAM_ID` | @userinfobot ကနေ ကိုယ့် Telegram ID ယူပါ |
| `MONETAG_ZONE_ID` | Monetag publisher dashboard ကနေ Mini App rewarded ad zone ဖွင့်ပြီး ယူပါ |
| `WEBAPP_URL` | Host လုပ်ပြီးရင် ရတဲ့ URL + `/app/` (ဥပမာ `https://your-app.onrender.com/app/`) |

`.env.example` ကို `.env` အဖြစ် ကူးပြီး ဒါတွေဖြည့်ပါ။ **Token တွေကို GitHub မှာ ဘယ်တော့မှ မတင်ပါနဲ့။**

## ကိုယ့်ကွန်ပျူတာမှာ run ရန်

```bash
pip install -r requirements.txt
cp .env.example .env   # ပြီးရင် .env ထဲမှာ တန်ဖိုးတွေ ဖြည့်ပါ
python server.py
```

Bot ကို Telegram မှာ ရှာပြီး `/start` နှိပ်ပါ။

## Host မှာ တင်ရန် (Render / Railway အခမဲ့)

1. ဒီ repo ကို Render (သို့မဟုတ် Railway) နဲ့ ချိတ်ပါ — `render.yaml` /
   `Procfile` ပါပြီးသားမို့ auto-deploy ရပါတယ်။
2. Host ရဲ့ Environment Variables နေရာမှာ `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`,
   `MONETAG_ZONE_ID`, `WEBAPP_URL` တို့ကို ထည့်ပါ။
3. Deploy ပြီးရင် ရတဲ့ URL ကို `WEBAPP_URL` အဖြစ် ပြန်ထည့်ပါ
   (ဥပမာ `https://telegram-ads-bot.onrender.com/app/`)။
4. BotFather မှာ bot ရဲ့ Menu Button ကို Mini App URL နဲ့ ချိတ်လို့လည်း ရပါတယ်။

## Monetag ကြော်ငြာ ချိတ်ရန် (အရေးကြီး)

`miniapp/app.js` ထဲက `showMonetagAd()` နေရာမှာ Monetag dashboard က ပေးတဲ့
လက်ရှိ Mini App SDK snippet ကို ထည့်ရပါမယ်။ SDK ရဲ့ on-complete callback
ကနေမှ `/api/ad/complete` ကို ခေါ်ရပါမယ် — ကြော်ငြာမပြီးဘဲ point ပေးလို့ မရပါဘူး။
ပိုခိုင်မာတဲ့နည်းက Monetag ရဲ့ server-to-server postback ကို
`/api/monetag/postback` နဲ့ ချိတ်တာပါ (README အသေးစိတ်ကို `server.py`
ထဲက မှတ်ချက်မှာ ကြည့်ပါ)။

စမ်းသပ်ဖို့အတွက် `MONETAG_DEMO_MODE=true` ထားရင် ကြော်ငြာကို အတုပြပြီး
point ပေးပါတယ်။ **အသုံးပြုသူအစစ်နဲ့ မသုံးခင် false ပြန်ထားဖို့ မမေ့ပါနဲ့။**

## ရိုးရိုးသားသား ပြောရမယ့် ကန့်သတ်ချက်များ

- **Monetag approval က သင့်တာဝန်ပါ** — publisher အကောင့်ဖွင့်တာ၊ zone
  ရတာ၊ incentivized traffic စည်းမျဉ်းတွေက သူတို့ဘက်က ဆုံးဖြတ်တာပါ။
- **KBZPay ထုတ်ပေးမှုက manual ပါ** — KBZPay မှာ အလိုအလျောက် လွှဲပေးတဲ့
  public API မရှိလို့ admin က app နဲ့ ကိုယ်တိုင် လွှဲရပါတယ်။
- **အခမဲ့ host က အိပ်ပါတယ်** — Render/Railway free tier က သုံးမရှိရင်
  အိပ်သွားပြီး ပြန်နိုးဖို့ စက္ကန့်အနည်းငယ် ကြာပါတယ်။ ၂၄ နာရီ မအိပ်ချင်ရင်
  paid instance (သို့မဟုတ် VPS) လိုပါတယ်။
- **Database က Postgres ဖြစ်ရမယ် (production မှာ)** — Render free
  instance ရဲ့ filesystem က restart/redeploy တိုင်း ပျက်သွားလို့ SQLite
  ဖိုင်ထဲက point တွေ အကုန် ပျောက်ပါတယ် (၂၀၂၆-၁၀-၂၅ မှာ တကယ်
  ကြုံခဲ့ရပါတယ်)။ ဒါကြောင့် production မှာ `DATABASE_URL` (ဥပမာ
  Supabase free tier) ပေးရပြီး code က အဲ့ဒါရှိရင် Postgres သုံးပါတယ်။
  Local မှာပဲ စမ်းရင် `DATABASE_URL` မပေးဘဲ SQLite သုံးလို့ရပါတယ်။
- **Bot အစစ်က မလည်သေးပါ** — ဒီ code ကို host မှာ deploy လုပ်ပြီး
  အပေါ်က variable တွေ ဖြည့်ပြီးမှ bot အလုပ်လုပ်ပါမယ်။

## Admin Commands (bot ထဲမှာ)

`/admin` `/pending` `/add_revenue <kyat>` `/set_points_per_ad <n>`
`/set_kyat_rate <kyat>` `/set_share <pct>` `/set_min_withdraw <points>`
