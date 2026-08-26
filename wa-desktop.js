/**
 * SafaiKaro desktop lead card.
 * Why: desktop visitors convert at ~9.5% vs ~21% mobile (PostHog 28d) —
 * wa.me deep links dump desktop users into web.whatsapp.com friction.
 * On desktop, clicking the WhatsApp float opens a card instead:
 * scan-QR (phone), copy phone number, or continue to WhatsApp Web.
 * Mobile behavior is untouched. Safe DOM only (no innerHTML).
 */
(function () {
  'use strict';
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  if (!window.matchMedia || !matchMedia('(min-width: 1024px) and (pointer: fine)').matches) return;

  var PHONE_DISPLAY = '0330 8652035';
  var PHONE_COPY = '+92 330 8652035';

  var style = document.createElement('style');
  style.textContent =
    '#wa-desk-card{position:fixed;bottom:170px;right:24px;width:280px;background:#fff;border:2px solid #0D4A2F;border-radius:16px;box-shadow:0 12px 40px rgba(0,0,0,.25);z-index:210;padding:20px;font-family:"DM Sans",sans-serif;display:none}' +
    '#wa-desk-card.open{display:block}' +
    '#wa-desk-card h4{font-family:Sora,sans-serif;color:#0D4A2F;font-size:1rem;margin:0 0 12px}' +
    '#wa-desk-card img{display:block;width:150px;height:150px;margin:0 auto 6px;border:1px solid #E5E7EB;border-radius:8px}' +
    '#wa-desk-card .wa-desk-scan{text-align:center;color:#6B7280;font-size:.8rem;margin:0 0 14px}' +
    '#wa-desk-card .wa-desk-phone{display:flex;align-items:center;justify-content:space-between;gap:8px;background:#F9F8F4;border:1px solid #E5E7EB;border-radius:8px;padding:10px 12px;margin-bottom:10px}' +
    '#wa-desk-card .wa-desk-phone strong{color:#0D4A2F;font-size:1.05rem;letter-spacing:.5px}' +
    '#wa-desk-card .wa-desk-copy{background:#0D4A2F;color:#fff;border:none;border-radius:6px;padding:6px 12px;font-size:.8rem;font-weight:700;cursor:pointer}' +
    '#wa-desk-card .wa-desk-copy.done{background:#6EE086;color:#0D4A2F}' +
    '#wa-desk-card .wa-desk-web{display:block;text-align:center;color:#0D4A2F;font-size:.85rem;text-decoration:underline}' +
    '#wa-desk-card .wa-desk-close{position:absolute;top:10px;right:12px;background:none;border:none;color:#6B7280;font-size:1.1rem;cursor:pointer;line-height:1}';
  document.head.appendChild(style);

  var card = document.createElement('div');
  card.id = 'wa-desk-card';
  card.setAttribute('role', 'dialog');
  card.setAttribute('aria-label', 'Contact SafaiKaro');

  var close = document.createElement('button');
  close.className = 'wa-desk-close';
  close.textContent = '×';
  close.setAttribute('aria-label', 'Close');
  card.appendChild(close);

  var h = document.createElement('h4');
  h.textContent = 'WhatsApp from your phone';
  card.appendChild(h);

  var qr = document.createElement('img');
  qr.src = '/images/wa-qr.png';
  qr.alt = 'Scan to WhatsApp SafaiKaro';
  qr.loading = 'lazy';
  card.appendChild(qr);

  var scan = document.createElement('p');
  scan.className = 'wa-desk-scan';
  scan.textContent = 'Scan with your phone camera';
  card.appendChild(scan);

  var row = document.createElement('div');
  row.className = 'wa-desk-phone';
  var num = document.createElement('strong');
  num.textContent = PHONE_DISPLAY;
  var copy = document.createElement('button');
  copy.className = 'wa-desk-copy';
  copy.textContent = 'Copy';
  row.appendChild(num);
  row.appendChild(copy);
  card.appendChild(row);

  var web = document.createElement('a');
  web.className = 'wa-desk-web';
  web.target = '_blank';
  web.rel = 'noopener';
  web.textContent = 'Or continue to WhatsApp Web →';
  card.appendChild(web);

  document.body.appendChild(card);

  function ph(event) {
    try {
      if (window.posthog && typeof posthog.capture === 'function') {
        posthog.capture(event, { path: location.pathname }, { transport: 'sendBeacon', send_instantly: true });
      }
    } catch (_) { /* tracking must never break the UI */ }
  }

  copy.addEventListener('click', function () {
    function done() {
      copy.textContent = 'Copied!';
      copy.className = 'wa-desk-copy done';
      setTimeout(function () { copy.textContent = 'Copy'; copy.className = 'wa-desk-copy'; }, 2000);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(PHONE_COPY).then(done, done);
    } else { done(); }
    ph('phone_copy');
  });

  close.addEventListener('click', function () { card.className = ''; });

  // Intercept the float (and any wa.me CTA) on desktop: show the card.
  // whatsapp_click still fires via the global delegate in prices.js.
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a') : null;
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (href.toLowerCase().indexOf('wa.me') === -1) return;
    if (a.className === 'wa-desk-web') return; // the card's own escape hatch
    e.preventDefault();
    web.href = href;
    card.className = 'open';
    ph('wa_desktop_card_open');
  });
})();
