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
 * MONETAG WIRING (do this once you have a Monetag account):
 *   - Paste Monetag's current Telegram Mini App SDK <script> tag into
 *     index.html (their dashboard gives you the exact snippet).
 *   - Replace the placeholder showMonetagAd() below with the SDK's
 *     rewarded-ad call, using the zone id from /api/config.
 *   - The SDK's on-complete callback is where step 3 must fire — and
 *     nowhere else. Never credit points from a button click alone.
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

  // TODO: replace with the real Monetag SDK call (see header comment).
  // Must resolve only when the ad actually completed, and reject on
  // close/skip/error — a skipped ad must never reach /api/ad/complete.
  function showMonetagAd(zoneId) {
    return new Promise((resolve, reject) => {
      if (window.MonetagMiniApp && typeof window.MonetagMiniApp.showRewarded === "function") {
        window.MonetagMiniApp.showRewarded(zoneId).then(resolve).catch(reject);
      } else {
        reject(new Error("Monetag SDK ကို index.html ထဲမှာ မထည့်ရသေးပါ။"));
      }
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
