# SafaiKaro Shared Build Context

## Brand Colors (override Energetic tokens)
- Primary: #0D4A2F (deep forest green)
- Accent: #6EE086 (bright lime) — CTA buttons
- Background: #F9F8F4 (off-white)
- Text: #1A1A1A
- Muted: #6B7280
- WhatsApp: #25D366

## Fonts (Google Fonts)
- Sora — headings
- DM Sans — body

## Energetic Design System Adaptation
Use thick 4px borders (Energetic signature) but with SafaiKaro green palette.
Typography: bold, large, punchy — Sora at display sizes.
Animations: snappy, not slow. Spring-based hovers.
Cards: thick green border on hover, subtle shadow default.

## CSS Variables (use in every file)
```css
:root {
  --green: #0D4A2F;
  --lime: #6EE086;
  --bg: #F9F8F4;
  --text: #1A1A1A;
  --muted: #6B7280;
  --wa: #25D366;
  --shadow: 0 2px 12px rgba(13,74,47,0.08);
  --border: 2px solid #0D4A2F;
  --radius: 8px;
}
```

## Shared HTML Snippets

### Google Fonts import (put in every <head>)
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700;800&family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
```

### Nav (sticky)
```html
<nav class="nav" id="nav">
  <div class="nav-inner">
    <a href="index.html" class="logo">SafaiKaro</a>
    <div class="nav-links">
      <a href="pest-control-dha-karachi.html">DHA</a>
      <a href="pest-control-clifton-karachi.html">Clifton</a>
      <a href="pest-control-price-list-karachi.html">Pricing</a>
      <a href="commercial.html">For Businesses</a>
    </div>
    <a href="book.html" class="btn-lime nav-cta">Book Now</a>
    <button class="hamburger" aria-label="Menu">☰</button>
  </div>
</nav>
```

### WhatsApp Float Button (every page, before </body>)
```html
<a href="https://wa.me/923000000000?text=Hi%20SafaiKaro%2C%20I%27m%20interested%20in%20pest%20control" 
   class="wa-float" aria-label="WhatsApp SafaiKaro" target="_blank">
  <svg width="28" height="28" viewBox="0 0 24 24" fill="white">
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
  </svg>
</a>
```

### Mobile Sticky Bottom Bar (every page, before </body>)
```html
<div class="mobile-bar">
  <span>📱 WhatsApp Karo — Free Quote</span>
  <a href="book.html" class="btn-lime">Book Now</a>
</div>
```

### Footer
```html
<footer class="footer">
  <div class="footer-inner">
    <div class="footer-brand">
      <span class="logo">SafaiKaro</span>
      <p>Karachi ka trusted pest control.</p>
      <a href="https://wa.me/923000000000" class="footer-wa">📱 +92-XXX-XXXXXXX</a>
    </div>
    <div class="footer-links">
      <h4>Services</h4>
      <a href="index.html#services">General Fumigation</a>
      <a href="termite-treatment-new-construction-karachi.html">Termite Treatment</a>
      <a href="annual-pest-control-karachi.html">Annual Plan</a>
      <a href="pest-control-price-list-karachi.html">All Prices</a>
    </div>
    <div class="footer-links">
      <h4>Areas</h4>
      <a href="pest-control-dha-karachi.html">DHA Karachi</a>
      <a href="pest-control-clifton-karachi.html">Clifton</a>
      <a href="pest-control-dha-karachi.html">Phase 1–8</a>
      <a href="pest-control-clifton-karachi.html">Block 1–9</a>
    </div>
    <div class="footer-links">
      <h4>Certifications</h4>
      <p>PPCP Certified</p>
      <p>Sindh EPA Registered</p>
      <p>FBR Registered</p>
      <p>WHO-Approved Chemicals</p>
    </div>
  </div>
  <div class="footer-bottom">
    <p>© 2025 SafaiKaro. All rights reserved. | DHA Phase 1–8 | Clifton Block 1–9 | Bath Island | PECHS</p>
  </div>
</footer>
```

## Pricing Data
- General fumigation up to 150 sq yds: Rs 8,500
- General fumigation 150-300 sq yds: Rs 14,000
- Full home package up to 300 sq yds: Rs 18,000
- Bed bug per room: Rs 7,000
- Bed bug full home: Rs 22,000
- Termite treatment: Rs 1,100/sq yd (min Rs 20,000)
- Rodent control: Rs 9,000–15,000
- Mosquito control: Rs 8,000
- Annual Shield (4 visits + 1 emergency): Rs 35,000/yr

## Reviews
1. "Bahut professional service thi. Technician time pe aaya, kaam bahut acha kiya. Cockroach problem completely solve ho gayi." — Ayesha R., DHA Phase 6 ⭐⭐⭐⭐⭐
2. "Prices bilkul clear the — koi surprise nahi. Bed bug treatment ne 3 din mein results diye." — Kamran M., Clifton Block 5 ⭐⭐⭐⭐⭐
3. "Annual plan le liya hai, 4 visits mein ghar ekdam pest free. Highly recommend!" — Sana T., DHA Phase 5 ⭐⭐⭐⭐⭐
4. "Termite treatment ke liye call kiya, same day inspection arrange ho gayi. Bohot acha service." — Bilal A., Bath Island ⭐⭐⭐⭐⭐
5. "SafaiKaro ne hamare restaurant ka bhi kaam kiya. Regular service reliable hai." — Nadia K., PECHS ⭐⭐⭐⭐⭐
6. "Mosquito problem especially garden mein thi. Treatment ke baad itna better hai. Worth every rupee." — Hassan F., DHA Phase 8 ⭐⭐⭐⭐⭐

## Image paths (relative from pages/)
../images/hero-tech-dha-villa.png
../images/termite-pre-construction-before.png
../images/termite-after-foundation.png
../images/warranty-card.png
../images/before-cockroach.png
../images/after-fumigation-clean.png
../images/before-termite-damage.png
../images/after-termite-treated.png
../images/bed-bug-treatment.png
../images/rodent-sealing.png

## WhatsApp link
https://wa.me/923000000000?text=Hi%20SafaiKaro%2C%20I%27m%20interested%20in%20pest%20control
## Termite-specific WA link
https://wa.me/923000000000?text=Hi%20SafaiKaro%2C%20I%20need%20termite%20treatment%20for%20new%20construction%20in%20Karachi
