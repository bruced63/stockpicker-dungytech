// StockPicker Web — Theme Toggle & Utilities

document.addEventListener('DOMContentLoaded', function() {
    // Theme toggle
    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
        const savedTheme = localStorage.getItem('sp-theme') || 'dark';
        document.documentElement.setAttribute('data-bs-theme', savedTheme);
        updateThemeIcon(savedTheme);

        themeBtn.addEventListener('click', function() {
            const current = document.documentElement.getAttribute('data-bs-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-bs-theme', next);
            localStorage.setItem('sp-theme', next);
            updateThemeIcon(next);
        });
    }

    function updateThemeIcon(theme) {
        const icon = themeBtn.querySelector('i');
        if (icon) {
            icon.className = theme === 'dark' ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
        }
    }

    // Auto-dismiss flash messages after 5 seconds
    document.querySelectorAll('.alert-dismissible').forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });

    // Initialize ticker popovers for any tickers present on initial page render
    initTickerPopovers();
});

// ── Ticker hover popups (custom, lightweight — no Bootstrap Popover) ──
const _tickerCache = new Map();
const _tickerPending = new Map();
let _tickerPopup = null;
let _tickerHideTimer = null;
let _tickerCurrentTarget = null;

function _escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function _fetchCompany(ticker) {
    if (_tickerCache.has(ticker)) return Promise.resolve(_tickerCache.get(ticker));
    if (_tickerPending.has(ticker)) return _tickerPending.get(ticker);
    const p = fetch(`/api/company/${encodeURIComponent(ticker)}`)
        .then(r => r.json())
        .then(data => { _tickerCache.set(ticker, data); _tickerPending.delete(ticker); return data; })
        .catch(() => { _tickerPending.delete(ticker); return {error: 'Unable to load'}; });
    _tickerPending.set(ticker, p);
    return p;
}

function _buildCompanyHtml(d) {
    if (d.error) return `<div class="text-muted small">No information available.</div>`;
    const meta = [d.sector, d.industry].filter(Boolean).join(' · ');
    const metaHtml = meta ? `<div class="text-muted small fst-italic mb-1">${_escapeHtml(meta)}</div>` : '';
    const summary = d.summary
        ? `<div class="small">${_escapeHtml(d.summary)}</div>`
        : `<div class="text-muted small">No summary available.</div>`;
    const site = d.website
        ? `<div class="small mt-2"><a href="${_escapeHtml(d.website)}" target="_blank" rel="noopener">${_escapeHtml(d.website)}</a></div>`
        : '';
    return `${metaHtml}${summary}${site}`;
}

function _getTickerPopup() {
    if (_tickerPopup) return _tickerPopup;
    const el = document.createElement('div');
    el.className = 'ticker-popup';
    el.style.display = 'none';
    document.body.appendChild(el);
    el.addEventListener('mouseenter', () => clearTimeout(_tickerHideTimer));
    el.addEventListener('mouseleave', _scheduleHideTickerPopup);
    _tickerPopup = el;
    return el;
}

function _positionTickerPopup(target) {
    const popup = _tickerPopup;
    if (!popup) return;
    const rect = target.getBoundingClientRect();
    const pRect = popup.getBoundingClientRect();
    let top = rect.top - pRect.height - 8;
    let left = rect.left + rect.width / 2 - pRect.width / 2;
    if (top < 8) top = rect.bottom + 8;
    if (left < 8) left = 8;
    if (left + pRect.width > window.innerWidth - 8) left = window.innerWidth - pRect.width - 8;
    popup.style.top = top + 'px';
    popup.style.left = left + 'px';
}

function _renderTickerPopup(target, ticker, data) {
    const popup = _getTickerPopup();
    const title = (data && data.name) || ticker;
    const body = data ? _buildCompanyHtml(data) : '<div class="text-muted small">Loading…</div>';
    popup.innerHTML = `<div class="ticker-popup-header">${_escapeHtml(title)}</div><div class="ticker-popup-body">${body}</div>`;
    popup.style.display = 'block';
    _positionTickerPopup(target);
}

function _scheduleHideTickerPopup() {
    clearTimeout(_tickerHideTimer);
    _tickerHideTimer = setTimeout(() => {
        if (_tickerPopup) _tickerPopup.style.display = 'none';
        _tickerCurrentTarget = null;
    }, 150);
}

document.addEventListener('mouseover', (e) => {
    const target = e.target.closest('.ticker-popover');
    if (!target || target === _tickerCurrentTarget) return;
    _tickerCurrentTarget = target;
    clearTimeout(_tickerHideTimer);
    const ticker = (target.getAttribute('data-ticker') || target.textContent || '').trim().toUpperCase();
    if (!ticker) return;
    _renderTickerPopup(target, ticker, _tickerCache.get(ticker) || null);
    if (!_tickerCache.has(ticker)) {
        _fetchCompany(ticker).then(d => {
            if (_tickerCurrentTarget === target) _renderTickerPopup(target, ticker, d);
        });
    }
});

document.addEventListener('mouseout', (e) => {
    const target = e.target.closest('.ticker-popover');
    if (!target) return;
    const related = e.relatedTarget;
    if (related && (related.closest('.ticker-popover') === target || related.closest('.ticker-popup'))) return;
    _scheduleHideTickerPopup();
});

// Kept for template compatibility — sets cursor hint on dynamically-added tickers
function initTickerPopovers(root) {
    (root || document).querySelectorAll('.ticker-popover').forEach(el => {
        el.style.cursor = 'help';
    });
}
