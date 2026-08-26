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
 * Events: whatsapp_click, book_click, call_click  { path, text, href }
 */
(function () {
  if (typeof document === 'undefined') return;
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('a') : null;
    if (!a || !window.posthog || typeof posthog.capture !== 'function') return;
    var href = a.getAttribute('href') || '';
    var lower = href.toLowerCase();
    var event = null;
    if (lower.indexOf('wa.me') !== -1 || lower.indexOf('whatsapp') !== -1) {
      event = 'whatsapp_click';
    } else if (lower.indexOf('tel:') === 0) {
      event = 'call_click';
    } else if (href === '/book' || href.indexOf('/book') === 0 || /\/book(\/|\?|#|$)/.test(href)) {
      // matches /book, /book/, /book?..., and absolute https://safaikaro.pk/book
      event = 'book_click';
    }
    if (!event) return;
    var props = { path: location.pathname, text: (a.textContent || '').trim().slice(0, 60), href: href };
    try {
      posthog.capture(event, props, { transport: 'sendBeacon', send_instantly: true });
    } catch (_) {
      posthog.capture(event, props); // fallback: never let tracking throw into the click path
    }
  }, true);
})();
