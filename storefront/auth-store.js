// ==========================================================
// FreakFits — Shared Auth Store (localStorage-based)
// ==========================================================

const AuthStore = (function () {
  const SESSION_KEY = "freakfits_user_session";
  const USERS_KEY = "freakfits_registered_users";

  function _getUsers() {
    try {
      return JSON.parse(localStorage.getItem(USERS_KEY)) || [];
    } catch {
      return [];
    }
  }

  function _saveUsers(users) {
    localStorage.setItem(USERS_KEY, JSON.stringify(users));
  }

  function _cleanName(name, email) {
    if (name && name.trim()) {
      let str = name.trim();
      // Remove trailing digits
      str = str.replace(/[0-9]+$/g, "").trim();
      return str;
    }

    const handle = (email || "").split("@")[0].toLowerCase();

    // Strip trailing digits & symbols
    let stripped = handle.replace(/[0-9_.-]+$/g, "");
    let parts = stripped.split(/[._-]/).filter(Boolean);
    if (parts.length === 0) parts = [handle.replace(/[0-9]/g, "") || "FreakFan"];
    return parts.map((p) => p.charAt(0).toUpperCase() + p.slice(1)).join(" ");
  }

  function getCurrentUser() {
    try {
      const user = JSON.parse(localStorage.getItem(SESSION_KEY));
      if (user) {
        if (!user.name && user.full_name) {
          user.name = user.full_name;
        }
        if (!user.phone && user.mobile_number) {
          user.phone = user.mobile_number;
        }
        user.name = _cleanName(user.name, user.email);
      }
      return user;
    } catch {
      return null;
    }
  }

  function login(email, password) {
    const trimmedEmail = (email || "").trim().toLowerCase();
    const users = _getUsers();

    // Find user in registered list or create session for demo
    let user = users.find(
      (u) => u.email.toLowerCase() === trimmedEmail && u.password === password
    );

    if (!user) {
      const emailExists = users.some((u) => u.email.toLowerCase() === trimmedEmail);
      if (emailExists) {
        return { success: false, message: "Incorrect password. Please try again." };
      }
      return { success: false, message: "No account found with this email. Please sign up first." };
    } else {
      user.name = _cleanName(user.name, user.email);
    }

    localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    updateHeaderUI();
    return { success: true, user };
  }

  function register({ name, phone, email, password }) {
    const trimmedEmail = (email || "").trim().toLowerCase();
    const users = _getUsers();

    if (users.some((u) => u.email.toLowerCase() === trimmedEmail)) {
      return { success: false, message: "An account with this email already exists." };
    }

    const newUser = {
      name: _cleanName(name, trimmedEmail),
      phone: (phone || "").trim(),
      email: trimmedEmail,
      password: password,
    };

    users.push(newUser);
    _saveUsers(users);
    localStorage.setItem(SESSION_KEY, JSON.stringify(newUser));
    
    // Sync local cart to backend
    if (typeof CartStore !== 'undefined' && typeof CartStore.syncLocalToBackend === 'function') {
      CartStore.syncLocalToBackend().catch(err => console.error("Cart sync failed:", err));
    }
    
    updateHeaderUI();
    return { success: true, user: newUser };
  }

  function logout() {
    localStorage.removeItem(SESSION_KEY);
    updateHeaderUI();
  }

  function saveSession(user) {
    if (user) {
      localStorage.setItem(SESSION_KEY, JSON.stringify(user));
      if (typeof CartStore !== "undefined" && typeof CartStore.syncLocalToBackend === "function") {
        CartStore.syncLocalToBackend();
      }
    } else {
      localStorage.removeItem(SESSION_KEY);
    }
    updateHeaderUI();
  }

  function updateHeaderUI() {
    const user = getCurrentUser();
    const greetingEl = document.getElementById("userGreeting");
    const nameEl = document.getElementById("userNameDisplay");
    const accountBtn = document.getElementById("accountBtn");

    if (user && user.name) {
      if (greetingEl) {
        greetingEl.style.display = "inline-flex";
        // Also wrap the welcome greeting to be a link to profile.html
        greetingEl.style.cursor = "pointer";
        greetingEl.onclick = () => { window.location.href = "profile.html"; };
      }
      if (nameEl) nameEl.textContent = user.name;
      if (accountBtn) {
        accountBtn.href = "profile.html";
        accountBtn.title = "My Profile";
        accountBtn.style.display = "inline-flex";
      }
    } else {
      if (greetingEl) {
        greetingEl.style.display = "none";
        greetingEl.onclick = null;
      }
      if (accountBtn) {
        accountBtn.href = "auth.html";
        accountBtn.title = "Sign In";
        accountBtn.style.display = "inline-flex";
      }
    }
  }

  function init() {
    document.addEventListener("DOMContentLoaded", () => {
      updateHeaderUI();
      setupMobileMenuExtraLinks();

      // Attach logout listener if present
      const logoutBtn = document.getElementById("logoutBtn");
      if (logoutBtn) {
        logoutBtn.addEventListener("click", (e) => {
          e.preventDefault();
          logout();
          if (typeof showToast === "function") {
            showToast("Logged out successfully");
          }
        });
      }

      // Inject and Setup Global Search Overlay
      setupSearchOverlay();
    });
  }

  function setupMobileMenuExtraLinks() {
    const mainNav = document.getElementById("mainNav");
    if (!mainNav) return;

    if (mainNav.querySelector(".mobile-menu-extra")) return;

    const extraContainer = document.createElement("div");
    extraContainer.className = "mobile-menu-extra";
    extraContainer.innerHTML = `
      <div class="mobile-menu-divider" style="height: 1px; background: var(--line); margin: 8px 12px;"></div>
      <a href="#" id="mobileMenuSearch" style="display: flex; align-items: center; gap: 10px; padding: 8px 12px; font-size: 14.5px;">
        <svg viewBox="0 0 24 24" fill="none" width="16" height="16" style="stroke: currentColor; stroke-width: 2; stroke-linecap: round;"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
        Search
      </a>
      <a href="auth.html" id="mobileMenuAccount" style="display: flex; align-items: center; gap: 10px; padding: 8px 12px; font-size: 14.5px;">
        <svg viewBox="0 0 24 24" fill="none" width="16" height="16" style="stroke: currentColor; stroke-width: 2; stroke-linecap: round;"><circle cx="12" cy="8" r="4"/><path d="M4 20c1.5-4 5-6 8-6s6.5 2 8 6"/></svg>
        Account
      </a>
      <a href="cart.html" style="display: flex; align-items: center; gap: 10px; padding: 8px 12px; font-size: 14.5px; color: var(--green); font-weight: 700;">
        <svg viewBox="0 0 24 24" fill="none" width="16" height="16" style="stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;"><path d="M4 6h2l1.5 11h11L20 8H7.5"/><circle cx="10" cy="20" r="1.4" fill="currentColor"/><circle cx="17" cy="20" r="1.4" fill="currentColor"/></svg>
        Cart (<span data-cart-count>0</span>)
      </a>
    `;
    mainNav.appendChild(extraContainer);

    // Bind Search click
    const searchLink = document.getElementById("mobileMenuSearch");
    if (searchLink) {
      searchLink.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        mainNav.classList.remove("is-open");
        const burgerBtn = document.getElementById("burgerBtn");
        if (burgerBtn) burgerBtn.classList.remove("is-active");
        
        const overlay = document.getElementById("searchOverlay");
        const input = document.getElementById("searchOverlayInput");
        if (overlay) {
          overlay.classList.add("is-active");
          if (input) setTimeout(() => input.focus(), 50);
        }
      });
    }

    // Update Account details
    function updateMobileAccount() {
      const accountLink = document.getElementById("mobileMenuAccount");
      if (!accountLink) return;
      const user = getCurrentUser();
      if (user && user.name) {
        accountLink.href = "profile.html";
        accountLink.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" width="18" height="18" style="stroke: currentColor; stroke-width: 2; stroke-linecap: round;"><circle cx="12" cy="8" r="4"/><path d="M4 20c1.5-4 5-6 8-6s6.5 2 8 6"/></svg>
          Profile (${escapeHtml(user.name)})
        `;
      } else {
        accountLink.href = "auth.html";
        accountLink.innerHTML = `
          <svg viewBox="0 0 24 24" fill="none" width="18" height="18" style="stroke: currentColor; stroke-width: 2; stroke-linecap: round;"><circle cx="12" cy="8" r="4"/><path d="M4 20c1.5-4 5-6 8-6s6.5 2 8 6"/></svg>
          Account / Sign In
        `;
      }
    }

    updateMobileAccount();

    // Listen to click on extra container links to close menu drawer
    extraContainer.querySelectorAll("a").forEach(link => {
      link.addEventListener("click", () => {
        mainNav.classList.remove("is-open");
        const burgerBtn = document.getElementById("burgerBtn");
        if (burgerBtn) burgerBtn.classList.remove("is-active");
      });
    });

    // Make sure cart count badge is updated inside drawer
    if (typeof CartStore !== "undefined" && typeof CartStore.getTotal === "function") {
      const count = CartStore.getTotal().count;
      const badge = extraContainer.querySelector("[data-cart-count]");
      if (badge) badge.textContent = count;
    }
  }

  function setupSearchOverlay() {
    // 1. Create overlay if not present
    let overlay = document.getElementById("searchOverlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.id = "searchOverlay";
      overlay.className = "search-overlay";
      overlay.innerHTML = `
        <div class="search-overlay__inner">
          <button class="search-overlay__close" id="closeSearchBtn" aria-label="Close search">&times;</button>
          <form class="search-overlay__form" id="searchOverlayForm">
            <input type="text" placeholder="Search for clubs, countries, colors..." id="searchOverlayInput" autofocus autocomplete="off">
            <button type="submit">Search</button>
          </form>
        </div>
      `;
      document.body.appendChild(overlay);
    }

    const input = document.getElementById("searchOverlayInput");
    const form = document.getElementById("searchOverlayForm");
    const closeBtn = document.getElementById("closeSearchBtn");

    // 2. Open search when clicking ANY search button in header
    document.querySelectorAll('button[aria-label="Search"], .icon-btn[aria-label="Search"]').forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        overlay.classList.add("is-active");
        setTimeout(() => input.focus(), 50);
      });
    });

    // 3. Close search
    const closeSearch = () => {
      overlay.classList.remove("is-active");
      input.value = "";
    };

    closeBtn.addEventListener("click", closeSearch);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeSearch();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && overlay.classList.contains("is-active")) {
        closeSearch();
      }
    });

    // 4. Handle Search Submission
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const val = input.value.trim();
      if (val) {
        window.location.href = "category.html?q=" + encodeURIComponent(val);
      }
    });
  }

  return {
    getCurrentUser,
    login,
    register,
    logout,
    updateHeaderUI,
    saveSession,
    init,
  };
})();

AuthStore.init();
