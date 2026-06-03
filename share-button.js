/**
 * SafaiKaro internal SHARE button (Autonomous Proposals).
 * Renders only for authenticated team members (Cloudflare Access cookie).
 * Externalised so pages can reference <script src="/share-button.js"></script>.
 * Built with safe DOM methods (no innerHTML).
 */
(function () {
  'use strict';

  function isAuthenticated() {
    return document.cookie.split(';').some(function (c) {
      return c.trim().startsWith('CF_Authorization=');
    });
  }

  if (!isAuthenticated()) return;

  var container = document.getElementById('share-button-container');
  if (!container) return;

  var style = document.createElement('style');
  style.textContent =
    '#share-btn{position:fixed;top:20px;right:20px;padding:10px 20px;background:linear-gradient(135deg,#00d5ff 0%,#b42aff 100%);color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:500;cursor:pointer;box-shadow:0 2px 8px rgba(180,42,255,.3);transition:all .2s;z-index:9999;font-family:system-ui,-apple-system,sans-serif}' +
    '#share-btn:hover{box-shadow:0 4px 12px rgba(180,42,255,.5);transform:translateY(-1px)}' +
    '#share-btn:disabled{background:#94a3b8;cursor:not-allowed;transform:none}' +
    '.share-toast{position:fixed;top:80px;right:20px;padding:12px 20px;background:#10b981;color:#fff;border-radius:6px;font-size:14px;font-weight:500;box-shadow:0 4px 12px rgba(16,185,129,.3);z-index:10000;font-family:system-ui,-apple-system,sans-serif}' +
    '.share-error{background:#ef4444}';
  container.appendChild(style);

  var btn = document.createElement('button');
  btn.id = 'share-btn';
  btn.textContent = '📤 SHARE';
  container.appendChild(btn);

  function showToast(message, isError) {
    var toast = document.createElement('div');
    toast.className = 'share-toast' + (isError ? ' share-error' : '');
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 3000);
  }

  btn.addEventListener('click', function () {
    btn.disabled = true;
    btn.textContent = '⏳ Generating...';
    var cfToken = (document.cookie.split(';').find(function (c) {
      return c.trim().startsWith('CF_Authorization=');
    }) || '').split('=')[1];

    if (!cfToken) {
      showToast('❌ Not authenticated', true);
      btn.disabled = false;
      btn.textContent = '📤 SHARE';
      return;
    }

    fetch('https://share.autonomoustech.ca/api/share', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CF-Authorization': cfToken },
      body: JSON.stringify({ path: window.location.pathname })
    })
      .then(function (r) { if (!r.ok) throw new Error('Failed to generate share link'); return r.json(); })
      .then(function (data) { return navigator.clipboard.writeText(data.url); })
      .then(function () { showToast('✅ Link copied to clipboard!'); })
      .catch(function (err) { console.error('Share error:', err); showToast('❌ Failed to generate link', true); })
      .finally(function () { btn.disabled = false; btn.textContent = '📤 SHARE'; });
  });
})();
