/* Mini App logic.
 *
 * Ad flow (credit is decided by the SERVER, never here):
 *   1. POST /api/ad/start  -> server checks the 5-minute cooldown and
 *      returns a one-time ad_token (or 429 if cooling down).
 *   2. Show the Monetag rewarded ad for that session.
 *   3. Only when the ad SDK reports completion, POST /api/ad/complete
 *      with the token. The server verifies the token + cooldown again
 *      and only then credits points.
 *
 * MONETAG WIRING (live since 2026-10-25):
 *   - Monetag Telegram Mini App SDK <script> tag is in index.html
 *     (zone 12117255, Rewarded Interstitial).
 *   - showMonetagAd() below calls the SDK's global show_<zoneId>()
 *     function. Its on-complete resolution is where step 3 fires —
 *     and nowhere else. Never credit points from a button click alone.
 *
 * DEMO MODE: if the server says demo_mode is on, step 2 is simulated
 * with a short countdown so you can test the flow with no Monetag
 * account. Turn it OFF before real users arrive.
 */
(function () {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) tg.expand();
  const initData = tg ? tg.initData : "";

  const $ = (id) => document.getElementById(id);
  let cooldownTimer = null;

  async function api(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ initData, ...(body || {}) }),
    });
    return { ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) };
  }

  async function apiGet(path) {
    const res = await fetch(path + "?initData=" + encodeURIComponent(initData));
    return { ok: res.ok, status: res.status, data: await res.json().catch(() => ({})) };
  }

  function fmtSecs(s) {
    const m = Math.floor(s / 60), r = s % 60;
    return m + " မိနစ် " + r + " စက္ကန့်";
  }

  function startCooldown(seconds) {
    const btn = $("watchBtn");
    btn.disabled = true;
    clearInterval(cooldownTimer);
    let left = seconds;
    $("cooldown").textContent = "နောက်တစ်ခါ ကြည့်လို့ရဖို့: " + fmtSecs(left);
    cooldownTimer = setInterval(() => {
      left -= 1;
      if (left <= 0) {
        clearInterval(cooldownTimer);
        btn.disabled = false;
        $("cooldown").textContent = "ကြည့်လို့ရပါပြီ ✅";
      } else {
        $("cooldown").textContent = "နောက်တစ်ခါ ကြည့်လို့ရဖို့: " + fmtSecs(left);
      }
    }, 1000);
  }

  async function refresh() {
    const me = await apiGet("/api/me");
    if (!me.ok) {
      $("status").textContent = "Bot ထဲမှာ /start အရင် နှိပ်ပေးပါ။";
      return;
    }
    $("points").textContent = me.data.points;
    $("kyatValue").textContent = "≈ " + me.data.kyat_value + " ကျပ်";
    if (me.data.cooldown_remaining > 0) startCooldown(me.data.cooldown_remaining);
    else { $("watchBtn").disabled = false; $("cooldown").textContent = "ကြည့်လို့ရပါပြီ ✅"; }
    const h = await apiGet("/api/history");
    if (h.ok) {
      $("history").innerHTML = h.data.history.map((row) => {
        const d = new Date(row.created_at * 1000).toLocaleString();
        const sign = row.delta > 0 ? "+" : "";
        return "<li>" + sign + row.delta + " — " + row.reason + " (" + d + ")</li>";
      }).join("") || "<li>မှတ်တမ်း မရှိသေးပါ</li>";
    }
  }

  // Real Monetag SDK call. The script tag in index.html exposes a global
  // show_<zoneId>() function. It resolves when the rewarded interstitial
  // finishes (with Monetag's reward postback enabled, only after Monetag
  // confirms the show); it rejects on close/skip/error — a skipped ad
  // must never reach /api/ad/complete.
  function showMonetagAd(zoneId) {
    const fnName = "show_" + zoneId;
    return new Promise((resolve, reject) => {
      const started = Date.now();
      (function waitForSdk() {
        const fn = window[fnName];
        if (typeof fn === "function") {
          try {
            const r = fn();
            if (r && typeof r.then === "function") r.then(resolve).catch(reject);
            else resolve();
          } catch (e) { reject(e); }
        } else if (Date.now() - started < 5000) {
          setTimeout(waitForSdk, 200);
        } else {
          reject(new Error("Monetag SDK ကို load မဖြစ်သေးပါ။ ခဏနေမှ ပြန်နှိပ်ပါ။"));
        }
      })();
    });
  }

  function showDemoAd() {
    // Test-only simulation: 5-second fake ad.
    return new Promise((resolve) => {
      $("status").textContent = "🧪 Demo ကြော်ငြာ ပြနေတယ်… (၅ စက္ကန့်)";
      setTimeout(resolve, 5000);
    });
  }

  $("watchBtn").addEventListener("click", async () => {
    $("status").textContent = "";
    $("watchBtn").disabled = true;
    const start = await api("/api/ad/start");
    if (!start.ok) {
      if (start.status === 429) {
        startCooldown(start.data.cooldown_remaining || 300);
        $("status").textContent = "၅ မိနစ် မပြည့်သေးပါ။ ခဏစောင့်ပါ။";
      } else {
        $("status").textContent = "Error: " + (start.data.error || "ad start failed");
        $("watchBtn").disabled = false;
      }
      return;
    }
    try {
      const cfg = await (await fetch("/api/config")).json();
      if (cfg.demo_mode) await showDemoAd();
      else await showMonetagAd(cfg.monetag_zone_id);
      const done = await api("/api/ad/complete", { ad_token: start.data.ad_token });
      if (done.ok) {
        $("status").textContent = "🎉 Point " + done.data.points + " ရပါပြီ!";
      } else {
        $("status").textContent = "Point မရပါ: " + (done.data.error || "failed");
      }
    } catch (e) {
      $("status").textContent = "ကြော်ငြာ မပြီးပါ (ကျော်သွားတာ/အမှား) — point မရပါ။";
    }
    await refresh();
  });

  refresh();
})();
