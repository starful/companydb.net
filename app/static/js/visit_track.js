/* Starful visit log → POST /events (HQ「이용자 보기»). Anonymous sf_vid cookie from the server. */
(function () {
  "use strict";
  if (navigator.webdriver && !window.StarfulVisitLogInTests) return;

  const path = location.pathname;
  const lang = (document.documentElement.lang || "").slice(0, 5);
  const queue = [];
  let flushTimer = 0;

  function utmParams() {
    const out = {};
    try {
      const q = new URLSearchParams(location.search);
      ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"].forEach((k) => {
        const v = q.get(k);
        if (v) out[k] = v.slice(0, 80);
      });
    } catch (e) { /* ignore */ }
    return out;
  }

  function screenOf(p) {
    if (p === "/" || p === "/index.html") return "home";
    if (p.startsWith("/blog/")) return "post";
    if (p.startsWith("/category/")) return "category";
    if (p.startsWith("/guide/") || p.startsWith("/item/")) return "guide";
    if (p.startsWith("/wall")) return "wall";
    if (p.startsWith("/about")) return "about";
    if (p.startsWith("/contact") || p.startsWith("/privacy")) return "legal";
    return "other";
  }

  function flush() {
    flushTimer = 0;
    if (!queue.length) return;
    const body = JSON.stringify({ events: queue.splice(0, 20), path: path, lang: lang });
    try {
      if (!(navigator.sendBeacon && navigator.sendBeacon("/events", new Blob([body], { type: "application/json" })))) {
        fetch("/events", { method: "POST", headers: { "Content-Type": "application/json" }, body: body, keepalive: true }).catch(function () {});
      }
    } catch (e) { /* offline */ }
    if (queue.length) flush();
  }

  function log(event, params, ref) {
    const row = { e: event, p: Object.assign({}, params || {}) };
    if (ref) row.ref = ref;
    queue.push(row);
    if (!flushTimer) flushTimer = setTimeout(flush, 1200);
  }

  addEventListener("pagehide", flush);
  addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flush();
  });

  let ref = "";
  try {
    const r = document.referrer ? new URL(document.referrer) : null;
    if (r && r.host !== location.host) ref = r.origin;
  } catch (e) { /* bad url */ }

  const utm = utmParams();
  log("pv", Object.assign({ screen: screenOf(path) }, utm), ref);

  function isAffiliate(href) {
    if (!href) return false;
    try {
      const u = new URL(href, location.origin);
      if (u.pathname.indexOf("/go/") === 0) return true;
      const h = u.hostname;
      return /(amazon\.|amzn\.|rakuten\.|a8\.net|agoda\.|travel\.rakuten)/i.test(h);
    } catch (e) {
      return false;
    }
  }

  document.addEventListener("click", function (ev) {
    const a = ev.target && ev.target.closest ? ev.target.closest("a[href], [data-track]") : null;
    if (!a) return;
    const href = a.getAttribute("href") || "";
    const label = a.getAttribute("data-track-label") || a.getAttribute("data-track") || (a.textContent || "").trim().slice(0, 60);
    const tracked = a.getAttribute("data-track");
    if (isAffiliate(href)) {
      log("affiliate", { href: href.slice(0, 80), label: label, kind: "affiliate" });
    } else if (tracked) {
      log("cta", { href: href.slice(0, 80), label: tracked || label, kind: "cta" });
    } else if (href && /^https?:\/\//i.test(href)) {
      try {
        if (new URL(href).host !== location.host) log("outbound", { href: href.slice(0, 80), label: label });
      } catch (e) { /* ignore */ }
    } else if (href && href.charAt(0) === "/" && !href.startsWith("/#")) {
      log("click", { href: href.slice(0, 80), label: label, kind: "nav" });
    }
  }, true);

  window.StarfulVisitTrack = function (event, params) {
    log(event, params || {});
  };
})();
