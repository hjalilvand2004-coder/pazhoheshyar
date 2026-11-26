/*!
 * دانشگاه هوشمند من — ویجت دستیار هوشمند (نماینده در زیرسامانه‌های دانشجویار۳۶۰/پژوهشیار۳۶۰)
 * نسخه 1.2.1 | قرارداد هسته: POST /api/chat و GET /api/widget/config
 *
 * استفاده در پژوهشیار۳۶۰ (index.html):
 *   <script src="/agent-widget.js" data-position="bl" data-origin="pazhoheshyar360"
 *           data-token-key="py_token"></script>
 *
 * توکن دانشجو از کلید توکن سامانهٔ میزبان خوانده می‌شود (py_token) — پس از ورود، پاسخ‌ها
 * شخصی و بر اساس آخرین وضعیت دانشجو است؛ بدون توکن فقط راهنمایی عمومی داده می‌شود.
 */
(function () {
  "use strict";
  var s = document.currentScript;
  var cfg = {
    url: (s && s.getAttribute("data-agent-url")) || location.origin,
    origin: (s && s.getAttribute("data-origin")) || "pazhoheshyar360",
    title: (s && s.getAttribute("data-title")) || "دستیار هوشمند پژوهشیار۳۶۰",
    subtitle: (s && s.getAttribute("data-subtitle")) || "متصل به هستهٔ «دانشگاه هوشمند من»",
    accent: (s && s.getAttribute("data-accent")) || "#4f46e5",
    accent2: (s && s.getAttribute("data-accent2")) || "#0f766e",
    position: (s && s.getAttribute("data-position")) || "bl",   // bl = پایین‌چپ (پیش‌فرض) | br = پایین‌راست
    tokenKey: (s && s.getAttribute("data-token-key")) || "py_token",
    greeting: (s && s.getAttribute("data-greeting")) ||
      "سلام! دستیار هوشمند «دانشگاه هوشمند من» در پژوهشیار۳۶۰ هستم؛ از وضعیت پژوهشی، کارآموزی و گزارش کار، درس‌پروژه، پروژه‌ها و درخواست‌هایتان بپرسید تا بر اساس آخرین داده‌های همین سامانه راهنمایی‌تان کنم.",
  };
  var QUICK = ["وضعیت من را خلاصه کن", "وضعیت کارآموزی من", "گزارش کار بعدی من", "پروژه‌های من", "راهنمای سامانه"];
  var sid = null;
  var msgs = [];
  var open = false;
  var unread = 0;
  var busy = false;

  function token() {
    try {
      if (window.__MSU_AGENT_TOKEN) return window.__MSU_AGENT_TOKEN;
      return localStorage.getItem(cfg.tokenKey) || "";
    } catch (e) { return ""; }
  }

  function el(tag, cls, html) {
    var d = document.createElement(tag);
    if (cls) d.className = cls;
    if (html != null) d.innerHTML = html;
    return d;
  }

  function esc(t) {
    return String(t == null ? "" : t)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  /* ── استایل‌های محصور (prefix msu-) ── */
  var css = [
    ".msu-widget *{box-sizing:border-box;font-family:Vazirmatn,Tahoma,'Segoe UI',sans-serif}",
    ".msu-fab{position:fixed;z-index:2147483000;width:60px;height:60px;border-radius:50%;border:none;cursor:pointer;",
    "background:linear-gradient(135deg," + cfg.accent2 + "," + cfg.accent + ");color:#fff;font-size:26px;",
    "box-shadow:0 8px 24px rgba(15,23,42,.35);display:grid;place-items:center;transition:transform .15s,box-shadow .15s}",
    ".msu-fab:hover{transform:scale(1.07)}",
    ".msu-fab.msu-br{bottom:22px;right:22px}.msu-fab.msu-bl{bottom:22px;left:22px}",
    ".msu-badge{position:absolute;top:-4px;inset-inline-start:-4px;min-width:20px;height:20px;border-radius:999px;",
    "background:#dc2626;color:#fff;font-size:11px;display:none;place-items:center;padding:0 5px}",
    ".msu-panel{position:fixed;z-index:2147483001;bottom:96px;width:min(380px,calc(100vw - 24px));height:min(560px,72vh);",
    "display:none;flex-direction:column;border-radius:18px;overflow:hidden;direction:rtl;text-align:right;",
    "background:#f8fafc;box-shadow:0 24px 64px rgba(15,23,42,.4);border:1px solid #e2e8f0}",
    ".msu-panel.msu-open{display:flex;animation:msuPop .18s ease-out}",
    ".msu-panel.msu-br{right:22px}.msu-panel.msu-bl{left:22px}",
    "@keyframes msuPop{from{opacity:0;transform:translateY(14px) scale(.97)}to{opacity:1;transform:none}}",
    ".msu-head{background:linear-gradient(120deg," + cfg.accent2 + "," + cfg.accent + ");color:#fff;padding:12px 14px;display:flex;gap:10px;align-items:center;flex-shrink:0}",
    ".msu-logo{width:38px;height:38px;border-radius:11px;background:rgba(255,255,255,.18);display:grid;place-items:center;font-size:19px;flex-shrink:0}",
    ".msu-head b{font-size:.92rem;display:block;line-height:1.4}",
    ".msu-head small{opacity:.85;font-size:.68rem;display:block}",
    ".msu-close{margin-inline-start:auto;background:rgba(255,255,255,.16);border:none;color:#fff;width:30px;height:30px;border-radius:9px;cursor:pointer;font-size:15px}",
    ".msu-close:hover{background:rgba(255,255,255,.3)}",
    ".msu-msgs{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px;background:linear-gradient(180deg,#f1f5f9,#f8fafc)}",
    ".msu-msg{display:flex;gap:8px;align-items:flex-start}",
    ".msu-msg.user{flex-direction:row-reverse}",
    ".msu-av{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;font-size:15px;flex-shrink:0;background:#e0e7ff}",
    ".msu-msg.agent .msu-av{background:linear-gradient(135deg," + cfg.accent2 + "," + cfg.accent + ");color:#fff}",
    ".msu-bubble{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:9px 12px;max-width:min(30ch,80%);font-size:.82rem;line-height:1.7;white-space:pre-wrap;box-shadow:0 1px 3px rgba(15,23,42,.06)}",
    ".msu-msg.user .msu-bubble{background:" + cfg.accent + ";color:#fff;border-color:" + cfg.accent + "}",
    ".msu-chips{display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 8px}",
    ".msu-chip{font-size:.7rem;background:#fff;border:1px solid #cbd5e1;color:" + cfg.accent2 + ";padding:4px 10px;border-radius:999px;cursor:pointer}",
    ".msu-chip:hover{border-color:" + cfg.accent + ";background:#eef2ff}",
    ".msu-composer{display:flex;gap:6px;padding:10px 12px;background:#fff;border-top:1px solid #e2e8f0;flex-shrink:0}",
    ".msu-composer input{flex:1;border:1px solid #cbd5e1;border-radius:12px;padding:9px 12px;font-size:.84rem;direction:rtl;min-width:0}",
    ".msu-composer input:focus{outline:2px solid " + cfg.accent + "}",
    ".msu-send{border:none;border-radius:12px;padding:9px 14px;cursor:pointer;color:#fff;font-weight:700;font-size:.8rem;",
    "background:linear-gradient(135deg," + cfg.accent2 + "," + cfg.accent + ")}",
    ".msu-send:disabled{opacity:.55;cursor:not-allowed}",
    ".msu-foot{font-size:.62rem;color:#64748b;text-align:center;padding:0 0 8px;background:#fff}",
    ".msu-typing{font-size:.78rem;color:#64748b;padding:2px 4px}"
  ].join("");
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  /* ── ساخت DOM ── */
  var side = cfg.position === "bl" ? "msu-bl" : "msu-br";
  var fab = el("button", "msu-fab " + side);
  fab.innerHTML = "🧭<span class='msu-badge'></span>";
  fab.setAttribute("aria-label", "دستیار هوشمند دانشگاه هوشمند من");
  var badge = fab.querySelector(".msu-badge");

  var panel = el("div", "msu-panel " + side);
  panel.innerHTML =
    "<div class='msu-head'><div class='msu-logo'>🧭</div>" +
    "<div><b>" + esc(cfg.title) + "</b><small>" + esc(cfg.subtitle) + "</small></div>" +
    "<button class='msu-close' title='بستن'>✕</button></div>" +
    "<div class='msu-msgs'></div>" +
    "<div class='msu-chips'></div>" +
    "<div class='msu-composer'><input type='text' placeholder='سؤال یا درخواست خود را بنویسید…'/>" +
    "<button class='msu-send'>ارسال</button></div>" +
    "<div class='msu-foot'>قدرت‌گرفته از هسته عامل «دانشگاه هوشمند من» • دانشجویار۳۶۰</div>";
  var msgsEl = panel.querySelector(".msu-msgs");
  var input = panel.querySelector("input");
  var sendBtn = panel.querySelector(".msu-send");
  var headTitle = panel.querySelector(".msu-head b");
  var headSub = panel.querySelector(".msu-head small");

  QUICK.forEach(function (q) {
    var c = el("button", "msu-chip", esc(q));
    c.onclick = function () { send(q); };
    panel.querySelector(".msu-chips").appendChild(c);
  });

  function addMsg(role, text) {
    msgs.push({ role: role, text: text });
    var m = el("div", "msu-msg " + role);
    m.innerHTML = "<div class='msu-av'>" + (role === "user" ? "👤" : "🤖") + "</div>" +
      "<div class='msu-bubble'>" + esc(text) + "</div>";
    msgsEl.appendChild(m);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    if (role === "agent" && !open) {
      unread++;
      badge.style.display = "grid";
      badge.textContent = unread > 9 ? "۹+" : unread;
    }
  }

  function addTyping() {
    var t = el("div", "msu-typing", "دستیار در حال بررسی وضعیت شماست…");
    msgsEl.appendChild(t);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    return t;
  }

  function send(text) {
    text = (text || input.value || "").trim();
    if (!text || busy) return;
    input.value = "";
    addMsg("user", text);
    busy = true;
    sendBtn.disabled = true;
    var t = addTyping();
    var headers = { "Content-Type": "application/json" };
    var tk = token();
    if (tk) headers.Authorization = "Bearer " + tk;
    fetch(cfg.url + "/api/chat", {
      method: "POST", headers: headers,
      body: JSON.stringify({ message: text, session_id: sid, origin: cfg.origin, page: location.pathname }),
    }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (res) {
      t.remove();
      sid = res.session_id || sid;
      addMsg("agent", res.reply || "پاسخی دریافت نشد.");
    }).catch(function (e) {
      t.remove();
      addMsg("agent", "⚠ ارتباط با هسته دستیار برقرار نشد (" + e.message + "). بعداً تلاش کنید.");
    }).then(function () {
      busy = false;
      sendBtn.disabled = false;
    });
  }

  sendBtn.onclick = function () { send(); };
  input.addEventListener("keydown", function (ev) { if (ev.key === "Enter") send(); });

  function setOpen(v) {
    open = v;
    panel.classList.toggle("msu-open", v);
    if (v) { unread = 0; badge.style.display = "none"; setTimeout(function () { input.focus(); }, 80); }
  }
  fab.onclick = function () { setOpen(!open); };
  panel.querySelector(".msu-close").onclick = function () { setOpen(false); };

  function boot() {
    addMsg("agent", cfg.greeting);
    document.body.appendChild(fab);
    document.body.appendChild(panel);
    // پیکربندی مرکزی از هستهٔ دستیار — عنوان/سلام/پرسش‌های سریع/سمت را هماهنگ می‌کند
    fetch(cfg.url + "/api/widget/config").then(function (r) { return r.json(); })
      .then(function (c) {
        if (!c) return;
        if (c.title) { cfg.title = c.title; headTitle.textContent = cfg.title; }
        if (c.subtitle) { cfg.subtitle = c.subtitle; headSub.textContent = cfg.subtitle; }
        if (c.greeting && msgs.length <= 1) { msgsEl.innerHTML = ""; msgs = []; addMsg("agent", c.greeting); }
        if (c.quick_questions && c.quick_questions.length) {
          var chips = panel.querySelector(".msu-chips");
          chips.innerHTML = "";
          c.quick_questions.forEach(function (q) {
            var el2 = el("button", "msu-chip", esc(q));
            el2.onclick = function () { send(q); };
            chips.appendChild(el2);
          });
        }
        if (c.position === "bl" || c.position === "br") {
          var side2 = c.position === "bl" ? "msu-bl" : "msu-br";
          if (side2 !== side) { fab.classList.remove(side); panel.classList.remove(side); fab.classList.add(side2); panel.classList.add(side2); side = side2; }
        }
      })
      .catch(function () { /* هسته در دسترس نیست؛ ویجت با پیش‌فرض‌ها باز می‌شود */ });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else { boot(); }

  /* API عمومی برای سامانه میزبان (React/Vue/…) */
  window.MSUAgent = {
    open: function () { setOpen(true); },
    close: function () { setOpen(false); },
    toggle: function () { setOpen(!open); },
    setToken: function (jwt) { try { localStorage.setItem(cfg.tokenKey, jwt); } catch (e) { window.__MSU_AGENT_TOKEN = jwt; } },
    clearToken: function () { try { localStorage.removeItem(cfg.tokenKey); } catch (e) { window.__MSU_AGENT_TOKEN = ""; } },
    version: "1.2.1",
  };
})();
