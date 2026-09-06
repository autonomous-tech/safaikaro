/**
 * SafaiKaro Centralized Pricing — Single Source of Truth
 *
 * To update prices: change the numbers below.
 * All pages auto-populate from this file via [data-price] attributes.
 *
 * Usage in HTML:
 *   <span data-price="fumigation-s">Rs 7,000</span>
 *   <span data-price="termite-ml">Rs 20,000</span>
 *   <span data-price="annual-s-monthly">Rs 1,833</span>
 *
 * The inner text is a fallback if JS doesn't load.
 */

// Five size tiers per service (all at 50% markup over cost):
//   -s  = up to 100 sq yd     -m  = 101–200 sq yd     -ml = 201–300 sq yd
//   -l  = 301–500 sq yd       -xl = 501–1,000 sq yd
var SAFAIKARO_PRICES = {
  // General Fumigation
  'fumigation-s':  7000,   // ≤100 sq yd — cost 3000
  'fumigation-m':  11000,  // 101–200 sq yd — cost 5000
  'fumigation-ml': 13000,  // 201–300 sq yd — cost 6000
  'fumigation-l':  16000,  // 301–500 sq yd — cost 7500
  'fumigation-xl': 20000,  // 501–1,000 sq yd — cost 9500

  // Termite Treatment
  'termite-s':  13000,  // ≤100 sq yd — cost 6000
  'termite-m':  17000,  // 101–200 sq yd — cost 8000
  'termite-ml': 20000,  // 201–300 sq yd — cost 9500
  'termite-l':  27000,  // 301–500 sq yd — cost 13000
  'termite-xl': 37000,  // 501–1,000 sq yd — cost 18000

  // Bed Bug Treatment
  'bedbug-s':  11000,  // ≤100 sq yd — cost 5000
  'bedbug-m':  14000,  // 101–200 sq yd — cost 6500
  'bedbug-ml': 17000,  // 201–300 sq yd — cost 8000
  'bedbug-l':  23000,  // 301–500 sq yd — cost 11000
  'bedbug-xl': 29000,  // 501–1,000 sq yd — cost 14000

  // Rodent Control (tiered by property size, 2 visits included)
  'rodent-s':  13000,  // ≤100 sq yd — cost 6000
  'rodent-m':  16000,  // 101–200 sq yd — cost 7500
  'rodent-ml': 18000,  // 201–300 sq yd — cost 8500
  'rodent-l':  21000,  // 301–500 sq yd — cost 10000
  'rodent-xl': 29000,  // 501–1,000 sq yd — cost 14000
  // Legacy alias — resolves to base tier so any missed old
  // data-price="rodent" reference still renders a valid price.
  'rodent': 13000,

  // Mosquito Control
  'mosquito-s':  6000,
  'mosquito-m':  8000,
  'mosquito-l':  12000,
  'mosquito-xl': 18000,

  // Annual Shield (competitive but profitable)
  'annual-s':  18000,
  'annual-m':  24000,
  'annual-l':  40000,
  'annual-xl': 65000,

  // Deposit
  'deposit': 500
};

(function() {
  function formatPrice(amount) {
    return 'Rs ' + amount.toLocaleString('en-PK');
  }

  function populatePrices() {
    // Update all [data-price] elements
    var els = document.querySelectorAll('[data-price]');
    for (var i = 0; i < els.length; i++) {
      var key = els[i].getAttribute('data-price');
      if (SAFAIKARO_PRICES[key] !== undefined) {
        els[i].textContent = formatPrice(SAFAIKARO_PRICES[key]);
      }
    }

    // Update JSON-LD schema prices if present
    var schemas = document.querySelectorAll('script[type="application/ld+json"]');
    for (var j = 0; j < schemas.length; j++) {
      try {
        var data = JSON.parse(schemas[j].textContent);
        var updated = updateSchemaPrice(data);
        if (updated) {
          schemas[j].textContent = JSON.stringify(data, null, 2);
        }
      } catch(e) { /* skip invalid JSON-LD */ }
    }
  }

  function updateSchemaPrice(obj) {
    var changed = false;
    // Update offers.price or priceRange
    if (obj && (obj['@type'] === 'LocalBusiness' || obj['@type'] === 'PestControlService')) {
      // Only re-sync the generic sitewide range (fumigation-s .. termite-xl).
      // Pages with a service-specific priceRange (e.g. bed bugs 11,000-29,000)
      // keep their own — overwriting them broke rich-result pricing on 9 pages.
      if (obj.priceRange && /7,?000/.test(obj.priceRange) && /37,?000/.test(obj.priceRange)) {
        obj.priceRange = 'Rs ' + SAFAIKARO_PRICES['fumigation-s'].toLocaleString('en-PK') + ' – Rs ' + SAFAIKARO_PRICES['termite-xl'].toLocaleString('en-PK');
        changed = true;
      }
    }
    return changed;
  }

  // Run on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', populatePrices);
  } else {
    populatePrices();
  }
})();

/**
 * Conversion tracking via PostHog (initialised on every page).
 * One delegated, capture-phase click listener records WhatsApp / Book / Call
 * intent across the whole site — no per-link wiring needed.
 *
 * WHY sendBeacon: these CTAs navigate the SAME tab (wa.me, /book). A normal
 * async capture() is cancelled when the browser unloads to WhatsApp / /book
 * before the request is sent, so the event is lost (this is why only the
 * target="_blank" float used to register). transport:'sendBeacon' +
 * send_instantly hands the event to the browser's beacon queue, which is
 * delivered even as the page unloads. No preventDefault — the link is never
 * blocked, so a tracking failure can never break a CTA.
 *
 * Events: whatsapp_click, book_click, call_click
 *   { path, text, href, cta, section, prefill, ref }
 *
 * cta = WHERE the click happened, derived from the DOM at click time so no
 * page markup needs tagging (35% of WhatsApp clicks used to arrive with empty
 * text because the float pill is icon-only, making placement unreadable).
 * An explicit data-cta="..." on the anchor or any ancestor wins.
 *
 * Micro-conversions (same listener, buttons not links):
 *   faq_open { question, path }   .faq-q
 *   price_tab_change { tab, path } .price-tab
 *   nav_menu_open { path }         .hamburger
 */
(function () {
  if (typeof document === 'undefined') return;

  function ph(event, props, urgent) {
    if (!window.posthog || typeof posthog.capture !== 'function') return;
    props.path = location.pathname;
    try {
      posthog.capture(event, props, urgent ? { transport: 'sendBeacon', send_instantly: true } : undefined);
    } catch (_) {
      posthog.capture(event, props); // fallback: never let tracking throw into the click path
    }
  }

  // Placement, most specific first. Order matters: the float sits inside <body>
  // not a section; the desktop card is injected at body level too.
  var PLACEMENTS = [
    ['[data-cta]', function (el) { return el.getAttribute('data-cta'); }],
    ['#wa-desk-card', 'desktop-card'],
    ['.wa-float', 'float'],
    ['.mobile-bar, .mobile-price-sticky', 'sticky'],
    ['nav, header', 'nav'],
    ['footer', 'footer'],
    ['.hero, .cert-hero, .price-hero, [class*="hero"]', 'hero'],
    ['.faq-item', 'faq'],
    ['.price-finder, .price-table, .price-panel, [class*="price"]', 'price-row'],
    ['article', 'article']
  ];
  function placementOf(a) {
    for (var i = 0; i < PLACEMENTS.length; i++) {
      var hit = a.closest(PLACEMENTS[i][0]);
      if (hit) { var v = PLACEMENTS[i][1]; return typeof v === 'function' ? v(hit) : v; }
    }
    return 'inline';
  }
  function sectionOf(a) {
    var sec = a.closest('section[id], section');
    if (!sec) return '';
    if (sec.id) return sec.id;
    var h = sec.querySelector('h2, h3');
    return h ? (h.textContent || '').trim().slice(0, 50) : (sec.className || '').split(' ')[0];
  }
  function prefillOf(href) {
    var m = /[?&]text=([^&]*)/.exec(href);
    if (!m) return '';
    try { return decodeURIComponent(m[1].replace(/\+/g, ' ')).replace(/^Hi SafaiKaro,?\s*/i, '').slice(0, 80); }
    catch (_) { return ''; }
  }

  // Short page/placement key, e.g. home/sticky, rodent-control/hero,
  // blog-khatmal-ka-ilaj/article. Event-only: the founder ruled out putting
  // it in the customer's WhatsApp message (2026-09-06).
  function refOf(a) {
    var seg = location.pathname.replace(/\/$/, '').split('/').filter(Boolean);
    var page = seg.length ? seg[seg.length - 1].replace(/\.html$/, '').replace(/-karachi$/, '') : 'home';
    if (seg[0] === 'blog' && seg.length > 1) page = 'blog-' + page;
    return page + '/' + placementOf(a);
  }

  // One tap can arrive as two or three click events a few ms apart (touch +
  // synthetic click, or a nested element bubbling twice): the same href within
  // a second is counted once, so lead_events stops overstating lead_persons.
  var lastClick = { href: '', at: 0 };

  document.addEventListener('click', function (e) {
    var t = e.target;
    if (!t || !t.closest) return;

    var a = t.closest('a');
    if (a) {
      var href = a.getAttribute('href') || '';
      var lower = href.toLowerCase();
      var event = null;
      var ref = '';
      if (lower.indexOf('wa.me') !== -1 || lower.indexOf('whatsapp') !== -1) {
        // On desktop wa-desktop.js intercepts every wa.me link and opens the
        // QR card instead (it fires wa_desktop_card_open). That open is not a
        // contact: whatsapp_click fires only from the card's own WhatsApp Web
        // link, and phone_copy from its copy button, so desktop lead counts
        // mean an action, not a card impression.
        if (document.getElementById('wa-desk-card') && !a.classList.contains('wa-desk-web')) return;
        var now = Date.now();
        if (href === lastClick.href && now - lastClick.at < 1000) return;
        lastClick.href = href; lastClick.at = now;
        event = 'whatsapp_click';
        ref = refOf(a);
      } else if (lower.indexOf('tel:') === 0) {
        event = 'call_click';
      } else if (href === '/book' || href.indexOf('/book') === 0 || /\/book(\/|\?|#|$)/.test(href)) {
        // matches /book, /book/, /book?..., and absolute https://safaikaro.pk/book
        event = 'book_click';
      }
      if (!event) return;
      ph(event, {
        text: ((a.textContent || '').trim() || a.getAttribute('aria-label') || '').slice(0, 60),
        href: href,
        cta: placementOf(a),
        section: sectionOf(a),
        prefill: event === 'whatsapp_click' ? prefillOf(href) : '',
        ref: ref
      }, true);
      return;
    }

    var faq = t.closest('.faq-q');
    if (faq && faq.getAttribute('aria-expanded') !== 'true') {
      ph('faq_open', { question: (faq.textContent || '').trim().slice(0, 120) });
      return;
    }
    var tab = t.closest('.price-tab');
    if (tab && !tab.classList.contains('active')) {
      ph('price_tab_change', { tab: tab.dataset.tab || (tab.textContent || '').trim().slice(0, 40) });
      return;
    }
    var burger = t.closest('.hamburger');
    if (burger && burger.getAttribute('aria-expanded') !== 'true') {
      ph('nav_menu_open', {});
    }
  }, true);
})();
