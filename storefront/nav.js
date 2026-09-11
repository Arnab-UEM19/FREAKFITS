// ==========================================================
// FreakFits — Shared Navigation Logic
// Renders consistent tab bar across all pages
// ==========================================================

const NAV_TABS = [
  { id: 'home', label: 'Football Jerseys', href: 'index.html' },
  { id: 'handcrafted', label: 'Handcrafted Arena', href: 'category.html?cat=home' },
  { id: 'traveller', label: "Traveller's Pick", href: 'category.html?cat=away' },
  { id: 'fashion', label: 'Fashion & More', href: 'category.html?cat=kit' },
  { id: 'sale', label: 'Clearance', href: 'category.html?cat=sale', class: 'nav-sale' },
];

function getCurrentTabId() {
  const path = window.location.pathname;
  const search = window.location.search;

  // index.html or root -> home
  if (path.endsWith('index.html') || path === '/' || path.endsWith('/')) {
    return 'home';
  }

  // category.html with cat param
  if (path.endsWith('category.html')) {
    const params = new URLSearchParams(search);
    const cat = params.get('cat');
    switch (cat) {
      case 'home': return 'handcrafted';
      case 'away': return 'traveller';
      case 'kit': return 'fashion';
      case 'sale': return 'sale';
      default: return 'home';
    }
  }

  // Other pages default to home
  return 'home';
}

function renderNav() {
  const nav = document.getElementById('mainNav');
  if (!nav) return;

  const currentTabId = getCurrentTabId();

  nav.innerHTML = NAV_TABS.map(tab => {
    const isActive = tab.id === currentTabId;
    const className = [
      isActive ? 'active' : '',
      tab.class || '',
    ].filter(Boolean).join(' ');

    return `<a href="${tab.href}" data-tab="${tab.id}"${className ? ` class="${className}"` : ''}>${tab.label}</a>`;
  }).join('');

  // Re-attach mobile nav toggle listeners
  initMobileNav();

  // auth-store.js appends the mobile Search/Account/Cart rows into
  // #mainNav, but it must do so AFTER the tab links above are in place —
  // otherwise this innerHTML assignment wipes out what it added. Signal
  // that tabs are ready so it can (re-)append safely.
  window.dispatchEvent(new Event('freakfits:nav-rendered'));
}

function initMobileNav() {
  const burger = document.getElementById('burgerBtn');
  const nav = document.getElementById('mainNav');
  if (!burger || !nav) return;

  // Remove existing listeners by cloning
  const newBurger = burger.cloneNode(true);
  burger.parentNode.replaceChild(newBurger, burger);

  newBurger.addEventListener('click', () => {
    nav.classList.toggle('is-open');
    newBurger.classList.toggle('is-active');
  });

  nav.querySelectorAll('a').forEach(link => {
    link.addEventListener('click', () => {
      nav.classList.remove('is-open');
      newBurger.classList.remove('is-active');
    });
  });
}

// Auto-initialize on DOM ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', renderNav);
} else {
  renderNav();
}

// Export for manual initialization if needed
window.FreakFitsNav = { renderNav, initMobileNav, NAV_TABS };