/**
 * SafaiKaro Centralized Pricing — Single Source of Truth
 *
 * To update prices: change the numbers below.
 * All pages auto-populate from this file via [data-price] attributes.
 *
 * Usage in HTML:
 *   <span data-price="fumigation-s">Rs 7,500</span>
 *   <span data-price="termite-l">Rs 50,000</span>
 *   <span data-price="annual-s-monthly">Rs 1,833</span>
 *
 * The inner text is a fallback if JS doesn't load.
 */

var SAFAIKARO_PRICES = {
  // General Fumigation
  'fumigation-s':  7500,   // ≤100 sq yd
  'fumigation-m':  9500,   // 101–200 sq yd
  'fumigation-l':  14000,  // 201–500 sq yd
  'fumigation-xl': 20000,  // 501–1,000 sq yd

  // Termite Treatment
  'termite-s':  20000,
  'termite-m':  30000,
  'termite-l':  50000,
  'termite-xl': 85000,

  // Bed Bug Treatment
  'bedbug-s':  9500,
  'bedbug-m':  12000,
  'bedbug-l':  17000,
  'bedbug-xl': 25000,

  // Rodent Control (flat rate)
  'rodent': 8500,

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
    if (obj && obj['@type'] === 'LocalBusiness' || obj && obj['@type'] === 'PestControlService') {
      if (obj.priceRange) {
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
