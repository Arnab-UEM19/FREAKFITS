/**
 * FreakFits — Admin Portal Engine (admin.js)
 * Connected to FastAPI Backend & MySQL Database
 * Single Page Application router, Auth Gate, Order Fulfillment & Inventory Management
 */

(function () {
  "use strict";

  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    if (typeof str !== "string") str = String(str);
    return str.replace(/[&<>'"]/g, 
      tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
  }

  const API_BASE = "http://127.0.0.1:8000/api";
  const STORAGE_KEY_TOKEN = "freakfits_admin_jwt";
  const STORAGE_KEY_ADMIN = "freakfits_admin_profile";

  // In-memory state synchronized with MySQL backend
  let products = [];
  let orders = [];
  let currentFilter = "all";
  let activeTab = localStorage.getItem("freakfits_admin_active_tab") || "dashboard";

  // ============ API CLIENT HELPER ============
  async function apiFetch(endpoint, options = {}) {
    const token = localStorage.getItem(STORAGE_KEY_TOKEN);
    const headers = {
      "Content-Type": "application/json",
      ...(options.headers || {})
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const method = (options.method || "GET").toUpperCase();
    let url = `${API_BASE}${endpoint}`;
    if (method === "GET") {
      const sep = url.indexOf("?") === -1 ? "?" : "&";
      url = url + sep + "_t=" + Date.now();
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers
      });

      if (response.status === 401 || response.status === 403) {
        if (!endpoint.includes("/login")) {
          // Session expired or unauthorized
          localStorage.removeItem(STORAGE_KEY_TOKEN);
          localStorage.removeItem(STORAGE_KEY_ADMIN);
          checkAuthView();
          throw new Error("Session expired. Please log in again.");
        }
      }

      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "API request failed");
      }
      return data;
    } catch (err) {
      console.error(`[API Error: ${endpoint}]`, err);
      throw err;
    }
  }

  // ============ AUTHENTICATION ============
  function isAuthenticated() {
    return !!localStorage.getItem(STORAGE_KEY_TOKEN);
  }

  function checkAuthView() {
    const loginScreen = document.getElementById("loginScreen");
    const adminShell = document.getElementById("adminShell");

    if (isAuthenticated()) {
      loginScreen.style.display = "none";
      adminShell.style.display = "grid";

      // Render Admin Name and Role
      try {
        const adminProfile = JSON.parse(localStorage.getItem(STORAGE_KEY_ADMIN) || "{}");
        const nameEl = document.getElementById("currentAdminName");
        const roleEl = document.getElementById("currentAdminRole");
        if (nameEl && adminProfile.full_name) {
          nameEl.textContent = adminProfile.full_name;
        }
        if (roleEl && adminProfile.role) {
          roleEl.textContent = adminProfile.role === "super_admin" ? "Super Admin" : (adminProfile.role === "manager" ? "Manager" : "Viewer");
        }

        // Toggle access requests nav link
        const navReq = document.getElementById("nav-access-requests");
        if (navReq) {
          navReq.style.display = adminProfile.role === "super_admin" ? "flex" : "none";
        }
      } catch (_) {}

      enforceRolePermissions();
      switchTab(activeTab);
    } else {
      loginScreen.style.display = "flex";
      adminShell.style.display = "none";
    }
  }

  function enforceRolePermissions() {
    let adminProfile = {};
    try {
      adminProfile = JSON.parse(localStorage.getItem(STORAGE_KEY_ADMIN) || "{}");
    } catch (_) {}
    
    const role = adminProfile.role || "viewer";

    // 1. Locks/Permissions for VIEWER role (Read-only access)
    if (role === "viewer") {
      const addSubmit = document.querySelector("#addProductForm button[type='submit']");
      if (addSubmit) {
        addSubmit.disabled = true;
        addSubmit.title = "Viewers cannot create products";
        addSubmit.style.opacity = "0.5";
        addSubmit.style.cursor = "not-allowed";
      }
    }

    // 2. Locks/Permissions for MANAGER role (Cannot change pricing)
    if (role === "manager" || role === "viewer") {
      const priceInps = ["newPriceS", "newPriceM", "newPriceL", "newPriceXL", "newPriceXXL", 
                         "newWasPriceS", "newWasPriceM", "newWasPriceL", "newWasPriceXL", "newWasPriceXXL"];
      priceInps.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          el.disabled = true;
          el.style.opacity = "0.6";
        }
      });
      const copyPricesBtn = document.getElementById("btnCopySizePrices");
      const copyWasPricesBtn = document.getElementById("btnCopySizeWasPrices");
      if (copyPricesBtn) copyPricesBtn.style.display = "none";
      if (copyWasPricesBtn) copyWasPricesBtn.style.display = "none";
    }
  }

  async function handleLogin(email, password) {
    try {
      const res = await apiFetch("/admin/login", {
        method: "POST",
        body: JSON.stringify({ email, password })
      });

      localStorage.setItem(STORAGE_KEY_TOKEN, res.access_token);
      localStorage.setItem(STORAGE_KEY_ADMIN, JSON.stringify(res.admin));

      showToast(`✓ Welcome, ${res.admin.full_name}!`);
      checkAuthView();
    } catch (err) {
      showToast(`Login failed: ${err.message}`);
    }
  }

  function handleLogout() {
    localStorage.removeItem(STORAGE_KEY_TOKEN);
    localStorage.removeItem(STORAGE_KEY_ADMIN);
    showToast("Logged out of Admin Portal");
    checkAuthView();
  }

  // ============ SPA NAVIGATION ============
  function switchTab(tabId) {
    activeTab = tabId;
    localStorage.setItem("freakfits_admin_active_tab", tabId);
    document.querySelectorAll(".nav-link").forEach((link) => {
      link.classList.toggle("is-active", link.dataset.tab === tabId);
    });

    document.querySelectorAll(".view-section").forEach((sec) => {
      sec.style.display = sec.id === `view-${tabId}` ? "block" : "none";
    });

    // Update Topbar Title
    const titleMap = {
      dashboard: "System Overview",
      orders: "Order Fulfillment",
      "add-product": "Add New Jersey",
      inventory: "Inventory & Price Editor",
      returns: "Returns & Claims Desk",
      reviews: "Customer Reviews Moderation",
      messages: "Support Messages",
      coupons: "Coupons Management",
      newsletter: "Newsletter Subscribers",
      "access-requests": "Employee Access Requests"
    };
    const titleEl = document.getElementById("topbarTitle");
    if (titleEl) titleEl.textContent = titleMap[tabId] || "Dashboard";

    renderActiveView();
  }

  function renderActiveView() {
    if (!isAuthenticated()) return;
    if (activeTab === "dashboard") loadDashboard();
    else if (activeTab === "orders") loadOrders();
    else if (activeTab === "inventory") loadInventory();
    else if (activeTab === "returns") loadReturns();
    else if (activeTab === "reviews") loadReviews();
    else if (activeTab === "messages") loadMessages();
    else if (activeTab === "coupons") loadCoupons();
    else if (activeTab === "newsletter") loadNewsletter();
    else if (activeTab === "access-requests") loadAccessRequests();
  }

  // ============ VIEW 1: DASHBOARD ============
  async function loadDashboard() {
    try {
      const promises = [
        apiFetch("/admin/stats"),
        apiFetch("/admin/orders")
      ];
      if (products.length === 0) {
        promises.push(apiFetch("/admin/products"));
      }

      const results = await Promise.all(promises);
      const stats = results[0];
      orders = results[1];
      if (results[2]) {
        products = results[2];
      }

      document.getElementById("statRevenue").textContent = `₹${stats.today_revenue.toLocaleString("en-IN")}`;
      document.getElementById("statActiveOrders").textContent = stats.active_orders;
      document.getElementById("statLowStock").textContent = stats.low_stock_count;
      document.getElementById("statCatalogTotal").textContent = stats.total_products;

      // Render Recent Orders panel
      const recentListEl = document.getElementById("dashboardRecentOrders");
      if (recentListEl) {
        if (orders.length === 0) {
          recentListEl.innerHTML = `<div style="color:var(--admin-text-dim); padding:16px 0;">No recent orders recorded.</div>`;
        } else {
          recentListEl.innerHTML = orders.slice(0, 4).map((o) => `
            <div style="display:flex; align-items:center; justify-content:space-between; padding:12px 0; border-bottom:1px solid var(--admin-line);">
              <div>
                <div style="font-weight:700; font-size:13.5px;">${escapeHtml(o.customer_name)} <span style="font-family:var(--font-mono); color:var(--admin-text-faint); font-size:11px;">(${escapeHtml(o.order_code)})</span></div>
                <div style="color:var(--admin-text-dim); font-size:12px; margin-top:2px;">${o.items.length} item(s) • ${o.payment_method.toUpperCase()}</div>
              </div>
              <div style="text-align:right;">
                <div style="font-family:var(--font-mono); font-weight:700; color:var(--admin-green);">₹${o.total.toLocaleString("en-IN")}</div>
                <span class="status-select ${(o.order_status || "Pending").toLowerCase()}" style="padding:2px 8px; font-size:10px; display:inline-block; margin-top:4px;">${o.order_status || "Pending"}</span>
              </div>
            </div>
          `).join("");
        }
      }
    } catch (err) {
      showToast(`Error loading stats: ${err.message}`);
    }
  }

  // ============ VIEW 2: ORDER MANAGEMENT ============
  async function loadOrders() {
    const tbody = document.getElementById("ordersTableBody");
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:32px; color:var(--admin-text-dim);">Loading orders from database...</td></tr>`;

    try {
      const promises = [apiFetch("/admin/orders")];
      if (products.length === 0) {
        promises.push(apiFetch("/admin/products"));
      }

      const results = await Promise.all(promises);
      orders = results[0];
      if (results[1]) {
        products = results[1];
      }
      renderOrdersTable();
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:32px; color:var(--admin-pink);">Failed to load orders: ${err.message}</td></tr>`;
    }
  }

  function renderOrdersTable() {
    const tbody = document.getElementById("ordersTableBody");
    const searchQuery = (document.getElementById("orderSearchInput")?.value || "").toLowerCase().trim();

    let filtered = orders;
    if (currentFilter !== "all") {
      filtered = filtered.filter((o) => (o.order_status || "Pending").toLowerCase() === currentFilter.toLowerCase());
    }
    if (searchQuery) {
      filtered = filtered.filter(
        (o) =>
          o.order_code.toLowerCase().includes(searchQuery) ||
          o.customer_name.toLowerCase().includes(searchQuery) ||
          o.customer_email.toLowerCase().includes(searchQuery)
      );
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:32px; color:var(--admin-text-dim);">No orders found matching criteria.</td></tr>`;
      return;
    }

    let adminProfile = {};
    try {
      adminProfile = JSON.parse(localStorage.getItem(STORAGE_KEY_ADMIN) || "{}");
    } catch (_) {}
    const isViewer = adminProfile.role === "viewer";

    tbody.innerHTML = filtered.map((o) => {
      const itemsHtml = o.items.map((it) => `
        <div style="margin-bottom:4px;">
          <strong>${escapeHtml(it.product_name)}</strong> <span style="color:var(--admin-green); font-family:var(--font-mono);">[${escapeHtml(it.size)}]</span>
          ${it.custom_name || it.custom_number ? `<span class="kit-custom-tag">👕 ${escapeHtml(it.custom_name || "—")} #${escapeHtml(it.custom_number || "—")}</span>` : ""}
        </div>
      `).join("");

      const currentStatus = o.order_status || "Pending";
      let statusClass = currentStatus.toLowerCase().replace(/\s+/g, '-');
      if (statusClass === "confirmed") statusClass = "pending";

      return `
        <tr data-order-code="${escapeHtml(o.order_code)}">
          <td style="font-family:var(--font-mono); font-weight:700; color:var(--admin-text);">${escapeHtml(o.order_code)}</td>
          <td>
            <div style="font-weight:700;">${escapeHtml(o.customer_name)}</div>
            <div style="color:var(--admin-text-faint); font-size:12px;">${escapeHtml(o.customer_email)}</div>
          </td>
          <td>${itemsHtml}</td>
          <td>
            <div style="font-family:var(--font-mono); font-weight:700; color:var(--admin-green);">₹${o.total.toLocaleString("en-IN")}</div>
            <div style="color:var(--admin-text-faint); font-size:11px;">${o.payment_method.toUpperCase()}</div>
          </td>
          <td>
            <select class="status-select ${statusClass}" data-action="change-status" data-code="${escapeHtml(o.order_code)}" ${isViewer ? 'disabled' : ''}>
              ${currentStatus === "Cancelled" ? `
                <option value="Cancelled" selected>🚫 Cancelled (Not Refunded)</option>
                <option value="Refunded">💰 Refunded</option>
              ` : `
                <option value="Pending" ${currentStatus === "Pending" || currentStatus === "Confirmed" ? "selected" : ""}>⏳ Pending</option>
                <option value="Preparing Kit" ${currentStatus === "Preparing Kit" ? "selected" : ""}>👕 Preparing Kit</option>
                <option value="Packing" ${currentStatus === "Packing" ? "selected" : ""}>📦 Packing</option>
                <option value="Shipped" ${currentStatus === "Shipped" ? "selected" : ""}>🚚 Shipped</option>
                <option value="Delivered" ${currentStatus === "Delivered" ? "selected" : ""}>✓ Delivered</option>
                <option value="Cancelled">🚫 Cancelled</option>
                <option value="Refunded">💰 Refunded</option>
              `}
            </select>
          </td>
          <td>
            <button class="btn-secondary" style="padding:4px 10px; font-size:11px;" onclick="window.FreakFitsAdmin.viewOrderDetails('${escapeHtml(o.order_code)}')">View</button>
          </td>
        </tr>
      `;
    }).join("");

    // Attach status dropdown change listeners to backend PATCH API
    tbody.querySelectorAll("[data-action='change-status']").forEach((select) => {
      select.addEventListener("change", async (e) => {
        const orderCode = e.target.dataset.code;
        const newStatus = e.target.value;

        try {
          const res = await apiFetch(`/admin/orders/${orderCode}/status`, {
            method: "PATCH",
            body: JSON.stringify({ order_status: newStatus })
          });

          if (res.order_status === "REFUNDED_DELETED" || newStatus === "Refunded") {
            orders = orders.filter((o) => o.order_code !== orderCode);
            showToast(`✓ Order ${orderCode} refunded and completed`);
            renderOrdersTable();
            return;
          }

          e.target.className = `status-select ${newStatus.toLowerCase()}`;
          showToast(`✓ Order ${orderCode} marked as ${newStatus}`);

          const ord = orders.find((o) => o.order_code === orderCode);
          if (ord) ord.order_status = newStatus;
        } catch (err) {
          showToast(`Failed to update status: ${err.message}`);
        }
      });
    });
  }

  // ============ VIEW 3: ADD PRODUCT ============
  async function handleAddProduct(e) {
    e.preventDefault();

    const name = document.getElementById("newProdName").value.trim();
    const club = document.getElementById("newProdClub").value.trim();
    const category = document.getElementById("newProdCat").value;
    
    // Per-size pricing (Selling + Strikethrough Was)
    const priceS = parseFloat(document.getElementById("newPriceS")?.value) || 1499;
    const priceM = parseFloat(document.getElementById("newPriceM")?.value) || priceS;
    const priceL = parseFloat(document.getElementById("newPriceL")?.value) || priceS;
    const priceXL = parseFloat(document.getElementById("newPriceXL")?.value) || priceS;
    const priceXXL = parseFloat(document.getElementById("newPriceXXL")?.value) || priceS;
    const sizePrices = { S: priceS, M: priceM, L: priceL, XL: priceXL, XXL: priceXXL };

    const wasS = parseFloat(document.getElementById("newWasPriceS")?.value) || (priceS + 400);
    const wasM = parseFloat(document.getElementById("newWasPriceM")?.value) || wasS;
    const wasL = parseFloat(document.getElementById("newWasPriceL")?.value) || wasS;
    const wasXL = parseFloat(document.getElementById("newWasPriceXL")?.value) || wasS;
    const wasXXL = parseFloat(document.getElementById("newWasPriceXXL")?.value) || wasS;
    const sizeWasPrices = { S: wasS, M: wasM, L: wasL, XL: wasXL, XXL: wasXXL };

    const imgUrlInput = document.getElementById("newProdImgUrl").value.trim();
    const previewEl = document.getElementById("newProdImgPreview");

    const imgUrl = imgUrlInput || ((previewEl.src.startsWith("http") || previewEl.src.startsWith("data:image/")) ? previewEl.src : "https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300483/freakfits/Argentina_Home.jpg");

    const isNew = document.getElementById("toggleNew").checked;
    const isVault = document.getElementById("toggleVault").checked;
    const isClearance = document.getElementById("toggleClearance").checked;
    const isBestseller = document.getElementById("toggleBestseller").checked;

    let badge = null;
    if (isNew) badge = "NEW DROP";
    else if (isBestseller) badge = "BESTSELLER";
    else if (isVault) badge = "VAULT";
    else if (isClearance) badge = "CLEARANCE";

    const payload = {
      name,
      club,
      category,
      price: priceS,
      was_price: wasS,
      size_prices: sizePrices,
      size_was_prices: sizeWasPrices,
      badge,
      images: [imgUrl],
      stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
    };

    try {
      const createdProd = await apiFetch("/admin/products", {
        method: "POST",
        body: JSON.stringify(payload)
      });

      showToast(`✓ Kit "${createdProd.name}" published with custom size pricing!`);
      document.getElementById("addProductForm").reset();
      previewEl.style.display = "none";

      switchTab("inventory");
    } catch (err) {
      showToast(`Error creating product: ${err.message}`);
    }
  }

  // ============ VIEW 4: INVENTORY EDITING ============
  async function loadInventory() {
    const tbody = document.getElementById("inventoryTableBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:32px; color:var(--admin-text-dim);">Loading products from database...</td></tr>`;

    try {
      products = await apiFetch("/admin/products");
      renderInventoryTable();
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:32px; color:var(--admin-pink);">Failed to load inventory: ${err.message}</td></tr>`;
    }
  }

  function renderInventoryTable() {
    const tbody = document.getElementById("inventoryTableBody");
    if (!tbody) return;

    let adminProfile = {};
    try {
      adminProfile = JSON.parse(localStorage.getItem(STORAGE_KEY_ADMIN) || "{}");
    } catch (_) {}
    const role = adminProfile.role || "viewer";

    const isPriceDisabled = (role === "manager" || role === "viewer") ? "disabled" : "";
    const isStockDisabled = (role === "viewer") ? "disabled" : "";

    tbody.innerHTML = products.map((p) => {
      const stock = p.stock || { S: 10, M: 10, L: 10, XL: 5, XXL: 5 };
      const sizePrices = p.size_prices || { S: p.price, M: p.price, L: p.price, XL: p.price, XXL: p.price };
      const sizeWasPrices = p.size_was_prices || {
        S: p.was_price || (p.price + 400),
        M: p.was_price || (p.price + 400),
        L: p.was_price || (p.price + 400),
        XL: p.was_price || (p.price + 400),
        XXL: p.was_price || (p.price + 400)
      };
      const mainImage = (p.images && p.images.length > 0) ? p.images[0] : "https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300483/freakfits/Argentina_Home.jpg";

      return `
        <tr data-prod-id="${p.id}">
          <td style="width:50px;">
            <img src="${mainImage}" alt="${p.name}" style="width:44px; height:44px; border-radius:6px; object-fit:contain; background:var(--admin-bg);">
          </td>
          <td>
            <strong>${p.name}</strong>
            <div style="color:var(--admin-text-faint); font-size:12px;">${p.club} • <span style="text-transform:uppercase;">${p.category}</span></div>
          </td>
          <td>
            <div class="price-badge-group">
              ${["S", "M", "L", "XL", "XXL"].map((sz) => {
                const pr = (sizePrices && sizePrices[sz] !== undefined) ? sizePrices[sz] : (p.price || 1499);
                const wasPr = (sizeWasPrices && sizeWasPrices[sz] !== undefined) ? sizeWasPrices[sz] : (p.was_price || (pr + 400));
                return `
                  <div class="price-pill" title="Size ${sz}: [Green: Sell Price] | [Strikethrough: MRP / Was Price]">
                    <strong>${sz}:</strong>
                    <span style="color:var(--admin-green);">₹</span>
                    <input type="number" class="quick-price-input" value="${pr}" min="1" step="1" title="${sz} Selling Price" data-id="${p.id}" data-size-price="${sz}" ${isPriceDisabled}>
                    <span style="opacity:0.35; font-size:9px;">~</span>
                    <input type="number" class="quick-was-price-input" value="${wasPr}" min="1" step="1" title="${sz} Strikethrough / Was Price" data-id="${p.id}" data-size-was-price="${sz}" ${isPriceDisabled}>
                  </div>
                `;
              }).join("")}
            </div>
          </td>
          <td>
            <div class="stock-badge-group">
              ${["S", "M", "L", "XL", "XXL"].map((sz) => {
                const qty = stock[sz] || 0;
                return `
                  <div class="stock-pill ${qty <= 2 ? "low-stock" : ""}">
                    <strong>${sz}:</strong>
                    <input type="number" class="quick-stock-input" value="${qty}" min="0" max="999" data-id="${p.id}" data-size="${sz}" ${isStockDisabled}>
                  </div>
                `;
              }).join("")}
            </div>
          </td>
          <td>
            ${role === "super_admin" 
              ? `<button class="btn-danger" data-action="delete-prod" data-id="${p.id}">Delete</button>` 
              : `<button class="btn-danger" disabled style="opacity:0.3; cursor:not-allowed;" title="Requires Super Admin">Delete</button>`
            }
          </td>
        </tr>
      `;
    }).join("");

    // Quick Size-Specific Price update handler
    tbody.querySelectorAll("input[data-size-price]").forEach((inp) => {
      inp.addEventListener("change", async (e) => {
        const prodId = parseInt(e.target.dataset.id);
        const size = e.target.dataset.sizePrice;
        const newPrice = parseFloat(e.target.value);
        if (isNaN(newPrice) || newPrice <= 0) {
          showToast("Please enter a valid price");
          return;
        }

        const inputEl = e.target;
        inputEl.style.outline = "2px solid #D4A054";

        try {
          const res = await apiFetch(`/admin/products/${prodId}`, {
            method: "PATCH",
            body: JSON.stringify({ size_prices: { [size]: newPrice } })
          });

          // Keep in-memory cache synchronized
          const p = products.find((x) => x.id === prodId);
          if (p) {
            if (!p.size_prices) p.size_prices = {};
            p.size_prices[size] = newPrice;
            p.price = res.price;
            p.was_price = res.was_price;
          }

          inputEl.style.outline = "2px solid #8CFF3B";
          setTimeout(() => { inputEl.style.outline = "none"; }, 1500);
          showToast(`✓ [${size}] price for Product #${prodId} updated to ₹${newPrice}`);
        } catch (err) {
          inputEl.style.outline = "2px solid #FF3E7A";
          showToast(`Failed to update price: ${err.message}`);
        }
      });
    });

    // Quick Size-Specific Strikethrough (Was) Price update handler
    tbody.querySelectorAll("input[data-size-was-price]").forEach((inp) => {
      inp.addEventListener("change", async (e) => {
        const prodId = parseInt(e.target.dataset.id);
        const size = e.target.dataset.sizeWasPrice;
        const newWasPrice = parseFloat(e.target.value);
        if (isNaN(newWasPrice) || newWasPrice <= 0) {
          showToast("Please enter a valid strikethrough price");
          return;
        }

        const inputEl = e.target;
        inputEl.style.outline = "2px solid #D4A054";

        try {
          const res = await apiFetch(`/admin/products/${prodId}`, {
            method: "PATCH",
            body: JSON.stringify({ size_was_prices: { [size]: newWasPrice } })
          });

          // Keep in-memory cache synchronized
          const p = products.find((x) => x.id === prodId);
          if (p) {
            if (!p.size_was_prices) p.size_was_prices = {};
            p.size_was_prices[size] = newWasPrice;
            p.was_price = res.was_price;
          }

          inputEl.style.outline = "2px solid #8CFF3B";
          setTimeout(() => { inputEl.style.outline = "none"; }, 1500);
          showToast(`✓ [${size}] strikethrough price for Product #${prodId} updated to ₹${newWasPrice}`);
        } catch (err) {
          inputEl.style.outline = "2px solid #FF3E7A";
          showToast(`Failed to update strikethrough price: ${err.message}`);
        }
      });
    });

    // Quick Size Stock update handler
    tbody.querySelectorAll("input[data-size]").forEach((inp) => {
      inp.addEventListener("change", async (e) => {
        const prodId = parseInt(e.target.dataset.id);
        const size = e.target.dataset.size;
        const newQty = parseInt(e.target.value) || 0;

        try {
          const res = await apiFetch(`/admin/products/${prodId}`, {
            method: "PATCH",
            body: JSON.stringify({ stock: { [size]: newQty } })
          });

          // Keep in-memory cache synchronized
          const p = products.find((x) => x.id === prodId);
          if (p && res.stock) {
            p.stock = res.stock;
          }

          showToast(`✓ Updated [${size}] stock to ${newQty}`);
          
          // Update visual highlight
          const pill = e.target.closest(".stock-pill");
          if (pill) {
            pill.classList.toggle("low-stock", newQty <= 2);
          }
        } catch (err) {
          showToast(`Failed to update stock: ${err.message}`);
        }
      });
    });

    // Delete Product handler
    tbody.querySelectorAll("[data-action='delete-prod']").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const prodId = parseInt(e.target.dataset.id);
        const prod = products.find((p) => p.id === prodId);
        if (confirm(`Are you sure you want to delete "${prod?.name || prodId}" from MySQL database?`)) {
          try {
            await apiFetch(`/admin/products/${prodId}`, {
              method: "DELETE"
            });
            showToast(`✓ Product #${prodId} deleted.`);
            loadInventory();
          } catch (err) {
            showToast(`Failed to delete product: ${err.message}`);
          }
        }
      });
    });
  }

  // ============ VIEW 5: RETURNS & CLAIMS ============
  let returnsList = [];
  let currentReturnFilter = "all";

  async function loadReturns() {
    const tbody = document.getElementById("returnsTableBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--admin-text-dim);">Loading return requests from database...</td></tr>`;

    try {
      returnsList = await apiFetch("/admin/returns");
      renderReturnsTable();
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--admin-pink);">Failed to load return requests: ${err.message}</td></tr>`;
    }
  }

  function renderReturnsTable() {
    const tbody = document.getElementById("returnsTableBody");
    if (!tbody) return;
    const searchQuery = (document.getElementById("returnSearchInput")?.value || "").toLowerCase().trim();

    let filtered = returnsList;
    if (currentReturnFilter !== "all") {
      filtered = filtered.filter((r) => (r.status || "PENDING_REVIEW").toLowerCase() === currentReturnFilter.toLowerCase());
    }
    if (searchQuery) {
      filtered = filtered.filter(
        (r) =>
          r.return_code.toLowerCase().includes(searchQuery) ||
          r.order_code.toLowerCase().includes(searchQuery) ||
          r.customer_name.toLowerCase().includes(searchQuery) ||
          r.customer_email.toLowerCase().includes(searchQuery)
      );
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--admin-text-dim);">No return claims found matching criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map((r) => {
      const isExchange = r.return_type === "size_exchange";
      const typeBadge = isExchange
        ? `<span style="background:rgba(41,197,246,0.12); color:var(--admin-blue); border:1px solid rgba(41,197,246,0.3); padding:2px 8px; border-radius:4px; font-family:var(--font-mono); font-size:10px; font-weight:700;">🔄 SIZE EXCHANGE</span>`
        : `<span style="background:rgba(255,62,122,0.12); color:var(--admin-pink); border:1px solid rgba(255,62,122,0.3); padding:2px 8px; border-radius:4px; font-family:var(--font-mono); font-size:10px; font-weight:700;">🛡️ FACTORY DEFECT</span>`;

      const detailsHtml = isExchange
        ? `<div>Exchange <strong>${escapeHtml(r.current_size || "—")}</strong> &rarr; <strong style="color:var(--admin-green);">${escapeHtml(r.requested_size || "—")}</strong></div>`
        : `<div style="font-size:12px; color:var(--admin-text-dim); max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${r.reason_details || "Manufacturing defect reported."}</div>`;

      const videoLink = r.video_proof.startsWith("http")
        ? `<a href="${escapeHtml(r.video_proof)}" target="_blank" style="color:var(--admin-green); text-decoration:none; font-family:var(--font-mono); font-size:11px; display:inline-flex; align-items:center; gap:4px;">📹 External Link &rarr;</a>`
        : `<span style="color:var(--admin-green); font-family:var(--font-mono); font-size:11px; cursor:pointer; text-decoration:underline; font-weight:600;" onclick="window.FreakFitsAdmin.viewReturnDetails('${r.return_code}')">📁 Play Video</span>`;

      const currentStatus = r.status || "PENDING_REVIEW";
      let statusClass = "pending";
      if (currentStatus === "APPROVED") statusClass = "shipped";
      else if (currentStatus === "REFUNDED") statusClass = "delivered";
      else if (currentStatus === "REJECTED") statusClass = "low-stock";

      return `
        <tr data-return-code="${r.return_code}">
          <td style="font-family:var(--font-mono); font-weight:700; color:var(--admin-text);">${r.return_code}</td>
          <td>
            <div style="font-weight:700;">${r.customer_name}</div>
            <div style="color:var(--admin-text-faint); font-size:11px; font-family:var(--font-mono);">Order: ${r.order_code}</div>
            <div style="color:var(--admin-text-faint); font-size:11px;">${r.customer_email}</div>
          </td>
          <td>${typeBadge}</td>
          <td>${detailsHtml}</td>
          <td>${videoLink}</td>
          <td>
            <select class="status-select ${statusClass}" data-action="change-return-status" data-code="${r.return_code}">
              <option value="PENDING_REVIEW" ${currentStatus === "PENDING_REVIEW" ? "selected" : ""}>⏳ Pending Review</option>
              <option value="APPROVED" ${currentStatus === "APPROVED" ? "selected" : ""}>✓ Approved</option>
              <option value="REFUNDED" ${currentStatus === "REFUNDED" ? "selected" : ""}>💰 Refunded (48h)</option>
              <option value="REJECTED" ${currentStatus === "REJECTED" ? "selected" : ""}>✗ Rejected</option>
            </select>
          </td>
          <td>
            <button class="btn-secondary" style="padding:4px 10px; font-size:11px;" onclick="window.FreakFitsAdmin.viewReturnDetails('${r.return_code}')">Review</button>
          </td>
        </tr>
      `;
    }).join("");

    // Attach status dropdown change listeners
    tbody.querySelectorAll("[data-action='change-return-status']").forEach((select) => {
      select.addEventListener("change", async (e) => {
        const returnCode = e.target.dataset.code;
        const newStatus = e.target.value;

        try {
          const res = await apiFetch(`/admin/returns/${returnCode}/status`, {
            method: "PATCH",
            body: JSON.stringify({ status: newStatus })
          });

          if (res.status === "REJECTED_DELETED" || res.status === "REFUNDED_DELETED" || newStatus === "REJECTED" || newStatus === "REFUNDED") {
            const actionText = newStatus === "REFUNDED" ? "refunded & completed" : "rejected";
            showToast(`✗ Return claim ${returnCode} was ${actionText} and automatically removed from database and storage.`);
            returnsList = returnsList.filter((r) => r.return_code !== returnCode);
            renderReturnsTable();
            
            // Close return details modal if open for this return code
            const openModalRetCode = document.getElementById("modalReturnCode")?.textContent;
            if (openModalRetCode === returnCode) {
              const returnModal = document.getElementById("returnDetailsModal");
              if (returnModal) returnModal.style.display = "none";
            }
            return;
          }

          let statusClass = "pending";
          if (newStatus === "APPROVED") statusClass = "shipped";
          else if (newStatus === "REFUNDED") statusClass = "delivered";
          else if (newStatus === "REJECTED") statusClass = "low-stock";

          e.target.className = `status-select ${statusClass}`;
          showToast(`✓ Return claim ${returnCode} marked as ${newStatus}`);

          const ret = returnsList.find((r) => r.return_code === returnCode);
          if (ret) ret.status = newStatus;
        } catch (err) {
          showToast(`Failed to update return status: ${err.message}`);
        }
      });
    });
  }

  async function viewReturnDetails(returnCode) {
    const r = returnsList.find((item) => item.return_code === returnCode);
    if (!r) return;

    const modal = document.getElementById("returnDetailsModal");
    if (!modal) return;

    document.getElementById("modalReturnCode").textContent = r.return_code;
    document.getElementById("modalRetCustomerName").textContent = r.customer_name;
    document.getElementById("modalRetCustomerEmail").textContent = r.customer_email;
    document.getElementById("modalRetOrderCode").textContent = r.order_code;
    document.getElementById("modalRetType").innerHTML = r.return_type === "size_exchange"
      ? `<span style="color:var(--admin-blue); font-weight:700;">🔄 SIZE EXCHANGE</span>`
      : `<span style="color:var(--admin-pink); font-weight:700;">🚨 FACTORY DEFECT</span>`;
    document.getElementById("modalRetDate").textContent = r.created_at;

    const detailsText = r.return_type === "size_exchange"
      ? `Exchange <strong>${escapeHtml(r.current_size || "—")}</strong> &rarr; <strong style="color:var(--admin-green);">${escapeHtml(r.requested_size || "—")}</strong>`
      : `Manufacturing defect reported`;
    document.getElementById("modalRetDetails").innerHTML = detailsText;
    document.getElementById("modalRetReason").textContent = r.reason_details || "No additional comments provided by user.";

    // Render Video Proof View
    const videoContainer = document.getElementById("modalRetVideoContainer");
    if (videoContainer) {
      if (r.video_proof.startsWith("http://") || r.video_proof.startsWith("https://")) {
        videoContainer.innerHTML = `
          <div style="display:flex; flex-direction:column; gap:12px;">
            <a href="${escapeHtml(r.video_proof)}" target="_blank" class="btn-primary" style="display:inline-flex; align-items:center; justify-content:center; gap:8px; padding:12px 20px; font-weight:700; text-decoration:none; background:var(--admin-pink); color:#fff; border:none; border-radius:4px; font-family:var(--font-mono); text-transform:uppercase; font-size:12px; cursor:pointer;">
              🎥 Open Video Proof Link &rarr;
            </a>
            <p style="font-size:11px; color:var(--admin-text-faint);">Link: <a href="${escapeHtml(r.video_proof)}" target="_blank" style="color:var(--admin-green); word-break:break-all;">${escapeHtml(r.video_proof)}</a></p>
          </div>
        `;
      } else {
        // Render playable video element pointing to our backend server
        const videoSrc = r.video_proof.startsWith("/") ? `http://127.0.0.1:8000${r.video_proof}` : r.video_proof;
        videoContainer.innerHTML = `
          <div style="background:rgba(255,255,255,0.03); border:1px solid var(--admin-border); padding:16px; border-radius:6px; display:flex; flex-direction:column; gap:12px;">
            <div style="font-weight:700; color:var(--admin-text); font-family:var(--font-mono); font-size:13px;">📁 Play Uploaded Video Proof</div>
            <video src="${escapeHtml(videoSrc)}" controls style="width:100%; max-height:300px; border-radius:4px; outline:none; border:1px solid rgba(255,255,255,0.1); background:#000;"></video>
            <p style="font-size:11px; color:var(--admin-text-faint); margin:0;">File: <a href="${escapeHtml(videoSrc)}" target="_blank" style="color:var(--admin-green);">${escapeHtml(r.video_proof)}</a></p>
          </div>
        `;
      }
    }

    // Populate Items List for this order
    const itemsListContainer = document.getElementById("modalRetItemsList");
    if (itemsListContainer) {
      itemsListContainer.innerHTML = `<div style="color:var(--admin-text-dim);">Loading order products list...</div>`;
      try {
        const order = await apiFetch("/orders/" + r.order_code);
        if (order && order.items && order.items.length > 0) {
          itemsListContainer.innerHTML = order.items.map(item => `
            <div style="display:flex; justify-content:space-between; align-items:center; background:rgba(255,255,255,0.02); border:1px solid var(--admin-border); padding:10px 14px; border-radius:6px; margin-bottom:8px;">
              <div>
                <strong style="color:var(--admin-text);">${escapeHtml(item.product_name)}</strong>
                <div style="font-size:11px; color:var(--admin-text-dim); margin-top:2px;">
                  Size: <span style="color:var(--admin-green);">${escapeHtml(item.size)}</span> | Qty: ${item.quantity}
                  ${item.custom_name ? ` | Print: <strong>${escapeHtml(item.custom_name)} (${escapeHtml(item.custom_number)})</strong>` : ""}
                </div>
              </div>
              <strong style="color:var(--admin-text);">₹${Math.round(item.line_total).toLocaleString("en-IN")}</strong>
            </div>
          `).join("");
        } else {
          itemsListContainer.innerHTML = `<div style="color:var(--admin-pink);">No items found in this order.</div>`;
        }
      } catch (err) {
        console.error(err);
        itemsListContainer.innerHTML = `<div style="color:var(--admin-pink);">Failed to load order products: ${err.message}</div>`;
      }
    }

    modal.style.display = "flex";
  }

  // Toast Helper
  let toastTimer = null;
  function showToast(msg) {
    const toast = document.getElementById("adminToast");
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2600);
  }

  // Modal Order Details Viewer
  function viewOrderDetails(orderCode) {
    const order = orders.find((o) => o.order_code === orderCode);
    if (!order) return;

    // Set text contents
    document.getElementById("modalOrderCode").textContent = order.order_code;
    document.getElementById("modalCustomerName").textContent = order.customer_name;
    document.getElementById("modalCustomerEmail").textContent = order.customer_email;
    document.getElementById("modalCustomerPhone").textContent = order.customer_phone || "N/A";
    document.getElementById("modalCustomerAddress").textContent = order.shipping_address || "India (Fan Deliveries)";
    document.getElementById("modalFulfillmentStatus").textContent = order.order_status || "Pending";
    document.getElementById("modalPaymentStatus").textContent = order.payment_status;
    document.getElementById("modalPaymentMethod").textContent = order.payment_method.toUpperCase();
    
    const dateStr = new Date(order.created_at || new Date()).toLocaleDateString("en-IN", {
      day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"
    });
    document.getElementById("modalOrderDate").textContent = dateStr;

    // Pricing breakdowns
    document.getElementById("modalSubtotal").textContent = `₹${order.subtotal.toLocaleString("en-IN")}`;
    document.getElementById("modalCoupon").textContent = order.coupon_code || "None";
    document.getElementById("modalDiscount").textContent = `₹${order.discount.toLocaleString("en-IN")}`;
    document.getElementById("modalShipping").textContent = order.shipping_fee > 0 ? `₹${order.shipping_fee}` : "FREE";
    document.getElementById("modalGrandTotal").textContent = `₹${Math.round(order.total).toLocaleString("en-IN")}`;

    // Render items list
    const itemsList = document.getElementById("modalItemsList");
    itemsList.innerHTML = order.items.map(it => {
      // Find image from our cached products list
      const matchedProd = products.find(p => p.id === it.product_id);
      const imgUrl = matchedProd && matchedProd.images && matchedProd.images[0] 
        ? matchedProd.images[0] 
        : 'https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300492/freakfits/logo_final.png';

      // Check customization preview
      const isCustomized = it.custom_name || it.custom_number;
      const customPreviewHtml = isCustomized 
        ? `
          <div class="jersey-print-preview">
            <span class="jersey-print-preview__name">${escapeHtml(it.custom_name || "")}</span>
            <span class="jersey-print-preview__number">${escapeHtml(it.custom_number || "")}</span>
          </div>
        ` 
        : "";

      return `
        <div class="modal-item-card">
          <img src="${imgUrl}" class="modal-item-card__img" alt="${escapeHtml(it.product_name)}">
          <div class="modal-item-card__desc">
            <div class="modal-item-card__title">${escapeHtml(it.product_name)}</div>
            <div class="modal-item-card__meta">
              Size: <strong>${escapeHtml(it.size)}</strong> &middot; Quantity: <strong>${it.quantity}</strong> &middot; Price: <strong>₹${it.unit_price}</strong>
            </div>
            ${isCustomized ? `
              <div style="margin-top: 8px; color: var(--admin-pink); font-size:12px; font-weight:700;">
                👕 CUSTOM PRINTING: "${escapeHtml(it.custom_name || '—')}" #${escapeHtml(it.custom_number || '—')}
              </div>
            ` : ""}
          </div>
          ${customPreviewHtml}
        </div>
      `;
    }).join("");

    // Admin Actions
    const actionsContainer = document.getElementById("modalAdminActions");
    if (actionsContainer) {
      if (order.order_status === "Pending" || order.order_status === "Confirmed") {
        actionsContainer.innerHTML = `<button id="btnAdminCancelOrder" class="btn-primary" style="background:var(--admin-pink); color:#fff; border:none; padding:10px 16px;">Cancel Order</button>`;
        document.getElementById("btnAdminCancelOrder").addEventListener("click", async () => {
          if (!confirm(`Are you sure you want to cancel order ${order.order_code}? This will restore stock and refund the customer.`)) return;
          
          const btn = document.getElementById("btnAdminCancelOrder");
          btn.disabled = true;
          btn.textContent = "Cancelling...";
          try {
            const res = await apiFetch(`/orders/${order.order_code}/cancel`, { method: "POST" });
            showToast(res.message || "Order cancelled successfully!");
            modal.style.display = "none";
            loadOrders(); // Refresh table
          } catch (err) {
            showToast("Failed to cancel order: " + err.message);
            btn.disabled = false;
            btn.textContent = "Cancel Order";
          }
        });
      } else {
        actionsContainer.innerHTML = "";
      }
    }

    // Show modal overlay
    const modal = document.getElementById("orderDetailsModal");
    if (modal) modal.style.display = "flex";
  }

  // ============ VIEW 6: CUSTOMER REVIEWS MODERATION ============
  let reviewsList = [];

  async function loadReviews() {
    const tbody = document.getElementById("reviewsTableBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--admin-text-dim);">Loading fan reviews from database...</td></tr>`;

    try {
      reviewsList = await apiFetch("/admin/reviews");
      renderReviewsTable();
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--admin-pink);">Failed to load reviews: ${err.message}</td></tr>`;
    }
  }

  function renderReviewsTable() {
    const tbody = document.getElementById("reviewsTableBody");
    if (!tbody) return;
    const searchQuery = (document.getElementById("reviewSearchInput")?.value || "").toLowerCase().trim();

    let filtered = reviewsList;
    if (searchQuery) {
      filtered = filtered.filter(
        (r) =>
          (r.user_name || "").toLowerCase().includes(searchQuery) ||
          (r.comment || "").toLowerCase().includes(searchQuery) ||
          (r.product_name || "").toLowerCase().includes(searchQuery)
      );
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:32px; color:var(--admin-text-dim);">No customer reviews found.</td></tr>`;
      return;
    }

    let adminProfile = {};
    try {
      adminProfile = JSON.parse(localStorage.getItem(STORAGE_KEY_ADMIN) || "{}");
    } catch (_) {}
    const isSuperAdmin = adminProfile.role === "super_admin";

    tbody.innerHTML = filtered.map((r) => {
      const starsHtml = "★".repeat(r.rating) + "☆".repeat(5 - r.rating);
      
      let imgSrc = "";
      if (r.image_url) {
        imgSrc = r.image_url.startsWith("http") ? r.image_url : `${API_BASE.replace('/api', '')}${r.image_url}`;
      }
      const photoHtml = r.image_url
        ? `<a href="${escapeHtml(imgSrc)}" target="_blank" title="View Full Image">
             <img src="${escapeHtml(imgSrc)}" style="width: 80px; height: 50px; object-fit: cover; border-radius: 4px; border: 1px solid var(--admin-line);" alt="Review Photo">
           </a>`
        : `<span style="color:var(--admin-text-faint); font-size:11px;">No Photo</span>`;

      const displayAuthor = (r.user_name && r.user_name !== "undefined") ? r.user_name : "FreakFits Fan";

      return `
        <tr data-review-id="${r.id}">
          <td style="font-family:var(--font-mono); color:var(--admin-text-dim);">${r.id}</td>
          <td>
            <div style="font-weight:700;">${escapeHtml(r.product_name)}</div>
            <div style="color:var(--admin-text-faint); font-size:11px; font-family:var(--font-mono);">${escapeHtml(r.product_club)} (ID: ${escapeHtml(r.product_id)})</div>
          </td>
          <td style="font-weight:600; color:var(--admin-text);">${escapeHtml(displayAuthor)}</td>
          <td style="color:var(--admin-green); letter-spacing: 1px;">${starsHtml}</td>
          <td style="font-size:12.5px; line-height:1.4; color:var(--admin-text-dim); max-width:320px; white-space:normal; word-break:break-word;">
            ${r.comment ? escapeHtml(r.comment) : `<em style="color:var(--admin-text-faint);">No comment text.</em>`}
          </td>
          <td>${photoHtml}</td>
          <td>
            ${isSuperAdmin ? `
              <button style="background:none; border:none; color:var(--admin-pink); cursor:pointer; font-size:1.2rem; padding:4px; line-height:1; opacity:0.85; transition:opacity 0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.85" data-action="delete-review" data-id="${r.id}" title="Delete Review #${r.id}">
                🗑️
              </button>
            ` : `<span style="color:var(--admin-text-faint); font-size:11px;">🔒 Locked</span>`}
          </td>
        </tr>
      `;
    }).join("");

    // Attach deletion handlers
    tbody.querySelectorAll("[data-action='delete-review']").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const reviewId = parseInt(btn.dataset.id);
        if (confirm(`Are you sure you want to delete review #${reviewId}? This will automatically remove it from the database and Cloudinary storage.`)) {
          try {
            await apiFetch(`/admin/reviews/${reviewId}`, {
              method: "DELETE"
            });
            showToast(`✓ Review #${reviewId} deleted successfully.`);
            
            // Instantly remove row from UI
            const row = tbody.querySelector(`tr[data-review-id="${reviewId}"]`);
            if (row) row.remove();
            
            // Sync with local array cache
            reviewsList = reviewsList.filter((x) => x.id !== reviewId);
            if (reviewsList.length === 0) {
              renderReviewsTable();
            }
          } catch (err) {
            showToast(`Failed to delete review: ${err.message}`);
          }
        }
      });
    });
  }

  // ============ VIEW 7: SUPPORT MESSAGES ============
  async function loadMessages() {
    const tbody = document.getElementById("messagesTableBody");
    if (!tbody) return;
    
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:32px; color:var(--admin-text-dim);">Loading messages...</td></tr>`;
    
    try {
      const messages = await apiFetch("/admin/messages");
      
      let adminProfile = {};
      try {
        adminProfile = JSON.parse(localStorage.getItem(STORAGE_KEY_ADMIN) || "{}");
      } catch (_) {}
      const isSuperAdmin = adminProfile.role === "super_admin";

      if (messages.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:32px; color:var(--admin-text-dim);">No customer messages found.</td></tr>`;
        return;
      }
      
      tbody.innerHTML = messages.map((m) => {
        const dateStr = new Date(m.created_at).toLocaleString("en-IN", {
          dateStyle: "medium",
          timeStyle: "short"
        });
        return `
          <tr data-message-id="${m.id}">
            <td style="font-family:var(--font-mono); font-size:12px; color:var(--admin-text-dim);">${escapeHtml(dateStr)}</td>
            <td style="font-weight:700;">${escapeHtml(m.name)}</td>
            <td><a href="mailto:${escapeHtml(m.email)}" style="color:var(--admin-green); text-decoration:none;">${escapeHtml(m.email)}</a></td>
            <td><span class="status-select pending" style="padding:2px 8px; font-size:11px; display:inline-block;">${escapeHtml(m.reason)}</span></td>
            <td style="white-space:pre-wrap; font-size:13px; line-height:1.5; color:var(--admin-text-light);">${escapeHtml(m.message || "—")}</td>
            <td>
              ${isSuperAdmin ? `
                <button style="background:none; border:none; color:var(--admin-pink); cursor:pointer; font-size:1.2rem; padding:4px; line-height:1; opacity:0.85; transition:opacity 0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.85" data-action="delete-message" data-id="${m.id}" title="Delete Message #${m.id}">
                  🗑️
                </button>
              ` : `<span style="color:var(--admin-text-faint); font-size:11px;">🔒 Locked</span>`}
            </td>
          </tr>
        `;
      }).join("");

      // Attach deletion event listeners
      tbody.querySelectorAll("[data-action='delete-message']").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
          const messageId = parseInt(btn.dataset.id);
          if (confirm(`Are you sure you want to delete support message #${messageId}?`)) {
            try {
              await apiFetch(`/admin/messages/${messageId}`, {
                method: "DELETE"
              });
              showToast(`✓ Message #${messageId} deleted successfully.`);
              
              // Remove from UI
              const row = tbody.querySelector(`tr[data-message-id="${messageId}"]`);
              if (row) row.remove();
              
              // If empty, show fallback message
              if (tbody.querySelectorAll("tr").length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:32px; color:var(--admin-text-dim);">No customer messages found.</td></tr>`;
              }
            } catch (err) {
              showToast(`Failed to delete message: ${err.message}`);
            }
          }
        });
      });
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:32px; color:var(--admin-pink);">Failed to load messages: ${err.message}</td></tr>`;
    }
  }

  // ============ VIEW 8: EMPLOYEE ACCESS REQUESTS ============
  let accessRequestsList = [];

  async function loadAccessRequests() {
    const tbody = document.getElementById("accessRequestsTableBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:32px; color:var(--admin-text-dim);">Loading access requests...</td></tr>`;

    try {
      accessRequestsList = await apiFetch("/admin/access-requests");
      renderAccessRequestsTable();
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:32px; color:var(--admin-pink);">Failed to load requests: ${err.message}</td></tr>`;
    }
  }

  function renderAccessRequestsTable() {
    const tbody = document.getElementById("accessRequestsTableBody");
    if (!tbody) return;

    if (accessRequestsList.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align:center; padding:32px; color:var(--admin-text-dim);">No pending employee requests found.</td></tr>`;
      return;
    }

    tbody.innerHTML = accessRequestsList.map((req) => {
      const dateStr = new Date(req.created_at || new Date()).toLocaleDateString("en-IN", {
        day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit"
      });

      return `
        <tr data-request-id="${req.id}">
          <td style="font-family:var(--font-mono); font-size:12px;">${dateStr}</td>
          <td>
            <div style="font-weight:700; color:var(--admin-text);">${escapeHtml(req.full_name || "Employee Candidate")}</div>
            <div style="color:var(--admin-text-dim); font-size:12px;">${escapeHtml(req.email)}</div>
          </td>
          <td>
            <span style="background:rgba(255,193,7,0.15); color:#ffc107; border:1px solid rgba(255,193,7,0.3); padding:3px 8px; border-radius:4px; font-size:11px; font-weight:600; text-transform:uppercase;">
              ${req.status.toUpperCase()}
            </span>
          </td>
          <td>
            <div style="display:flex; gap:8px;">
              <button class="btn-primary" style="padding:6px 12px; font-size:11px; background:var(--admin-green); border-color:var(--admin-green);" onclick="window.FreakFitsAdmin.openApprovalModal(${req.id}, '${escapeHtml(req.email)}', '${escapeHtml(req.full_name)}')">
                Approve
              </button>
              <button class="btn-secondary" style="padding:6px 12px; font-size:11px; border-color:var(--admin-pink); color:var(--admin-pink);" onclick="window.FreakFitsAdmin.rejectAccessRequest(${req.id})">
                Reject
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  function openApprovalModal(id, email, name) {
    document.getElementById("approvalCandidateId").value = id;
    document.getElementById("approvalCandidateEmail").textContent = email;
    document.getElementById("approvalCandidateName").value = name;
    document.getElementById("approvalRole").value = "viewer";
    document.getElementById("approvalPassword").value = "";
    document.getElementById("employeeApprovalModal").style.display = "flex";
  }

  async function rejectAccessRequest(id) {
    if (!confirm("Are you sure you want to reject this employee access request?")) return;
    try {
      await apiFetch(`/admin/access-requests/${id}/reject`, { method: "POST" });
      showToast("✓ Access request rejected successfully.");
      accessRequestsList = accessRequestsList.filter(r => r.id !== id);
      renderAccessRequestsTable();
    } catch (err) {
      showToast("Failed to reject request: " + err.message);
    }
  }

  // ============ VIEW 9: COUPONS ============
  async function loadCoupons() {
    const tbody = document.getElementById("couponsTableBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;">Loading coupons...</td></tr>`;
    try {
      const data = await apiFetch("/coupons/admin/list");
      if (!Array.isArray(data)) throw new Error("Invalid format");
      if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;">No coupons found.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(c => {
        const usageText = c.usage_limit ? `${c.usage_count} / ${c.usage_limit}` : `${c.usage_count} / ∞`;
        const statusBadge = c.is_active 
          ? `<span class="status-badge" style="background:rgba(140,255,59,0.1); color:var(--admin-green);">Active</span>` 
          : `<span class="status-badge" style="background:rgba(255,62,122,0.1); color:var(--admin-pink);">Inactive</span>`;
        return `
          <tr>
            <td style="font-weight:600; color:var(--admin-green);">${escapeHtml(c.code)}</td>
            <td>${escapeHtml(c.label)}</td>
            <td>${c.discount_percent}%</td>
            <td>${usageText}</td>
            <td>${statusBadge}</td>
            <td>
              <div style="display:flex; gap:8px;">
                <button class="btn-secondary" style="padding:4px 8px; font-size:11px;" onclick="window.FreakFitsAdmin.toggleCoupon(${c.id})">Toggle</button>
                <button class="btn-secondary" style="padding:4px 8px; font-size:11px; border-color:var(--admin-pink); color:var(--admin-pink);" onclick="window.FreakFitsAdmin.deleteCoupon(${c.id})">Delete</button>
              </div>
            </td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--admin-pink);">Failed to load coupons.</td></tr>`;
    }
  }

  // ============ VIEW 10: NEWSLETTER ============
  async function loadNewsletter() {
    const tbody = document.getElementById("newsletterTableBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="2" style="text-align:center;">Loading subscribers...</td></tr>`;
    try {
      const data = await apiFetch("/admin/newsletter");
      if (!Array.isArray(data)) throw new Error("Invalid format");
      if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="2" style="text-align:center;">No subscribers yet.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.map(sub => `
        <tr>
          <td style="font-weight:600; color:var(--admin-text);">${escapeHtml(sub.email)}</td>
          <td>${new Date(sub.created_at).toLocaleString()}</td>
        </tr>
      `).join("");
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="2" style="text-align:center; color:var(--admin-pink);">Failed to load subscribers.</td></tr>`;
    }
  }

  // Init & Event Bindings
  document.addEventListener("DOMContentLoaded", () => {
    checkAuthView();

    // Close Details Modal
    const closeBtn = document.getElementById("closeOrderModalBtn");
    const modal = document.getElementById("orderDetailsModal");
    if (closeBtn && modal) {
      closeBtn.addEventListener("click", () => {
        modal.style.display = "none";
      });
      modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.style.display = "none";
      });
    }

    // Close Return Details Modal
    const closeReturnBtn = document.getElementById("closeReturnModalBtn");
        const returnModal = document.getElementById("returnDetailsModal");
    if (closeReturnBtn && returnModal) {
      closeReturnBtn.addEventListener("click", () => {
        returnModal.style.display = "none";
      });
      returnModal.addEventListener("click", (e) => {
        if (e.target === returnModal) returnModal.style.display = "none";
      });
    }

    // Login Form State Machine & Submit
    let loginStage = "email";
    let requestEmail = "";

    function resetLoginFields() {
      loginStage = "email";
      requestEmail = "";
      const emailField = document.getElementById("loginEmail");
      if (emailField) {
        emailField.disabled = false;
      }
      const passGroup = document.getElementById("loginPassGroup");
      if (passGroup) passGroup.style.display = "none";
      const nameGroup = document.getElementById("loginNameGroup");
      if (nameGroup) nameGroup.style.display = "none";
      const otpGroup = document.getElementById("loginOtpGroup");
      if (otpGroup) otpGroup.style.display = "none";
      const pendingNotice = document.getElementById("requestPendingNotice");
      if (pendingNotice) pendingNotice.style.display = "none";
      const btnText = document.getElementById("loginSubmitBtnText");
      if (btnText) btnText.textContent = "Next";
      const submitBtn = document.getElementById("loginSubmitBtn");
      if (submitBtn) {
        submitBtn.style.display = "flex";
        submitBtn.disabled = false;
      }
    }

    const loginForm = document.getElementById("loginForm");
    if (loginForm) {
      resetLoginFields();

      loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const email = document.getElementById("loginEmail").value.trim().toLowerCase();
        const pass = document.getElementById("loginPass").value.trim();
        const name = document.getElementById("loginName")?.value.trim();
        const otp = document.getElementById("loginOtp")?.value.trim();

        if (loginStage === "email") {
          if (!email) {
            showToast("Please enter an email address.");
            return;
          }
          
          if (email === "supportfreakfits@gmail.com") {
            loginStage = "password";
            document.getElementById("loginEmail").disabled = true;
            document.getElementById("loginPassGroup").style.display = "block";
            document.getElementById("loginSubmitBtnText").textContent = "Enter Control Center";
            document.getElementById("loginPass").focus();
            return;
          }

          try {
            document.getElementById("loginSubmitBtn").disabled = true;
            const res = await fetch(`${API_BASE}/admin/access-requests/request`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ email: email, name: "Pending Candidate" })
            });
            const data = await res.json();
            document.getElementById("loginSubmitBtn").disabled = false;

            if (!res.ok) {
              showToast(data.detail || "Request failed.");
              return;
            }

            if (data.approved) {
              loginStage = "password";
              document.getElementById("loginEmail").disabled = true;
              document.getElementById("loginPassGroup").style.display = "block";
              document.getElementById("loginSubmitBtnText").textContent = "Enter Control Center";
              document.getElementById("loginPass").focus();
            } else if (data.pending) {
              document.getElementById("loginEmail").disabled = true;
              document.getElementById("loginPassGroup").style.display = "none";
              document.getElementById("requestPendingNotice").style.display = "block";
              document.getElementById("loginSubmitBtn").style.display = "none";
            } else {
              requestEmail = email;
              loginStage = "otp";
              document.getElementById("loginEmail").disabled = true;
              document.getElementById("loginPassGroup").style.display = "none";
              document.getElementById("loginNameGroup").style.display = "block";
              document.getElementById("loginOtpGroup").style.display = "block";
              document.getElementById("loginSubmitBtnText").textContent = "Submit Access Request";
              showToast("✓ Verification code sent to your email!");
            }
          } catch (err) {
            document.getElementById("loginSubmitBtn").disabled = false;
            showToast("Failed to initiate request: " + err.message);
          }

        } else if (loginStage === "password") {
          try {
            document.getElementById("loginSubmitBtn").disabled = true;
            const res = await apiFetch("/admin/login", {
              method: "POST",
              body: JSON.stringify({ email, password: pass })
            });
            document.getElementById("loginSubmitBtn").disabled = false;

            localStorage.setItem(STORAGE_KEY_TOKEN, res.access_token);
            localStorage.setItem(STORAGE_KEY_ADMIN, JSON.stringify(res.admin));

            showToast(`✓ Welcome, ${res.admin.full_name}!`);
            resetLoginFields();
            checkAuthView();
          } catch (err) {
            document.getElementById("loginSubmitBtn").disabled = false;
            showToast("Login failed: " + err.message);
          }

        } else if (loginStage === "otp") {
          if (!name) {
            showToast("Please enter your full name.");
            return;
          }
          if (!otp || otp.length !== 4) {
            showToast("Please enter a valid 4-digit code.");
            return;
          }

          try {
            document.getElementById("loginSubmitBtn").disabled = true;
            const res = await fetch(`${API_BASE}/admin/access-requests/verify`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ email: requestEmail, otp_code: otp, name: name })
            });
            const data = await res.json();
            document.getElementById("loginSubmitBtn").disabled = false;

            if (!res.ok) {
              showToast(data.detail || "Verification failed.");
              return;
            }

            document.getElementById("loginNameGroup").style.display = "none";
            document.getElementById("loginOtpGroup").style.display = "none";
            document.getElementById("requestPendingNotice").style.display = "block";
            document.getElementById("loginSubmitBtn").style.display = "none";
            showToast("✓ Request submitted successfully.");
          } catch (err) {
            document.getElementById("loginSubmitBtn").disabled = false;
            showToast("Verification failed: " + err.message);
          }
        }
      });
    }

    // Logout Button
    const logoutBtn = document.getElementById("logoutBtn");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => {
        handleLogout();
        resetLoginFields();
      });
    }

    // Navigation Links
    document.querySelectorAll(".nav-link").forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        switchTab(link.dataset.tab);
      });
    });

    // Order Filter Pills
    document.querySelectorAll(".filter-pill[data-filter]").forEach((pill) => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".filter-pill[data-filter]").forEach((p) => p.classList.remove("is-active"));
        pill.classList.add("is-active");
        currentFilter = pill.dataset.filter;
        renderOrdersTable();
      });
    });

    // Order Search
    const searchInp = document.getElementById("orderSearchInput");
    if (searchInp) {
      searchInp.addEventListener("input", renderOrdersTable);
    }

    // Return Filter Pills
    document.querySelectorAll(".filter-pill[data-return-filter]").forEach((pill) => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".filter-pill[data-return-filter]").forEach((p) => p.classList.remove("is-active"));
        pill.classList.add("is-active");
        currentReturnFilter = pill.dataset.returnFilter;
        renderReturnsTable();
      });
    });

    // Return Search
    const returnSearchInp = document.getElementById("returnSearchInput");
    if (returnSearchInp) {
      returnSearchInp.addEventListener("input", renderReturnsTable);
    }

    // Review Search
    const reviewSearchInp = document.getElementById("reviewSearchInput");
    if (reviewSearchInp) {
      reviewSearchInp.addEventListener("input", renderReviewsTable);
    }

    // Image Upload Preview in Add Product
    const fileInp = document.getElementById("newProdFile");
    const previewImg = document.getElementById("newProdImgPreview");
    if (fileInp && previewImg) {
      fileInp.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (file) {
          const reader = new FileReader();
          reader.onload = (re) => {
            previewImg.src = re.target.result;
            previewImg.style.display = "block";
          };
          reader.readAsDataURL(file);
        }
      });
    }

    // Promo Toggle Pill highlights
    document.querySelectorAll(".toggle-card").forEach((card) => {
      const chk = card.querySelector("input[type='checkbox']");
      if (chk) {
        chk.addEventListener("change", () => {
          card.classList.toggle("is-active", chk.checked);
        });
      }
    });

    // Add Product Form Submit
    const addProductForm = document.getElementById("addProductForm");
    if (addProductForm) {
      addProductForm.addEventListener("submit", handleAddProduct);
    }

    // Copy Size S price to all sizes button
    const copyPricesBtn = document.getElementById("btnCopySizePrices");
    if (copyPricesBtn) {
      copyPricesBtn.addEventListener("click", () => {
        const val = document.getElementById("newPriceS")?.value || 1499;
        ["newPriceM", "newPriceL", "newPriceXL", "newPriceXXL"].forEach((id) => {
          const el = document.getElementById(id);
          if (el) el.value = val;
        });
        showToast("✓ Copied Size S price to M, L, XL, XXL");
      });
    }

    // Copy Size S Was/MRP price to all sizes button
    const copyWasPricesBtn = document.getElementById("btnCopySizeWasPrices");
    if (copyWasPricesBtn) {
      copyWasPricesBtn.addEventListener("click", () => {
        const val = document.getElementById("newWasPriceS")?.value || 1999;
        ["newWasPriceM", "newWasPriceL", "newWasPriceXL", "newWasPriceXXL"].forEach((id) => {
          const el = document.getElementById(id);
          if (el) el.value = val;
        });
        showToast("✓ Copied Size S Was price to M, L, XL, XXL");
      });
    }

    // Modal Control: Change Password
    const btnChangePass = document.getElementById("btnChangePasswordModal");
    if (btnChangePass) {
      btnChangePass.addEventListener("click", () => {
        const modal = document.getElementById("changePasswordModal");
        if (modal) modal.style.display = "flex";
      });
    }

    const closeChangePass = document.getElementById("closeChangePasswordModalBtn");
    if (closeChangePass) {
      closeChangePass.addEventListener("click", () => {
        document.getElementById("changePasswordModal").style.display = "none";
      });
    }

    const changePassForm = document.getElementById("changePasswordForm");
    if (changePassForm) {
      changePassForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const current_password = document.getElementById("changeCurrentPass").value;
        const new_password = document.getElementById("changeNewPass").value;
        const confirm_new_password = document.getElementById("changeConfirmPass").value;

        if (new_password.length < 6) {
          showToast("New password must be at least 6 characters.");
          return;
        }

        if (new_password !== confirm_new_password) {
          showToast("New passwords do not match.");
          return;
        }

        try {
          await apiFetch("/admin/change-password", {
            method: "POST",
            body: JSON.stringify({ current_password, new_password, confirm_new_password })
          });
          showToast("✓ Password updated successfully!");
          document.getElementById("changePasswordModal").style.display = "none";
          changePassForm.reset();
        } catch (err) {
          showToast("Failed to update password: " + err.message);
        }
      });
    }

    // Modal Control: Employee Approval
    const closeApprovalBtn = document.getElementById("closeApprovalModalBtn");
    if (closeApprovalBtn) {
      closeApprovalBtn.addEventListener("click", () => {
        document.getElementById("employeeApprovalModal").style.display = "none";
      });
    }

    const approvalForm = document.getElementById("employeeApprovalForm");
    if (approvalForm) {
      approvalForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const candidateId = document.getElementById("approvalCandidateId").value;
        const name = document.getElementById("approvalCandidateName").value.trim();
        const role = document.getElementById("approvalRole").value;
        const password = document.getElementById("approvalPassword").value;

        if (password.length < 6) {
          showToast("Password must be at least 6 characters.");
          return;
        }

        try {
          await apiFetch(`/admin/access-requests/${candidateId}/approve`, {
            method: "POST",
            body: JSON.stringify({ name, role, password })
          });
          showToast("✓ Employee request approved. Credentials sent via email!");
          document.getElementById("employeeApprovalModal").style.display = "none";
          approvalForm.reset();
          loadAccessRequests();
        } catch (err) {
          showToast("Approval failed: " + err.message);
        }
      });
    }

    // Check Initial Authentication Gate
    checkAuthView();

    // ============ COUPONS MANAGEMENT ============
    const btnAddNewCoupon = document.getElementById("btnAddNewCoupon");
    const couponModal = document.getElementById("couponModal");
    const closeCouponModalBtn = document.getElementById("closeCouponModalBtn");
    const couponForm = document.getElementById("couponForm");

    if (btnAddNewCoupon && couponModal) {
      btnAddNewCoupon.addEventListener("click", () => {
        couponModal.style.display = "flex";
      });
    }

    if (closeCouponModalBtn && couponModal) {
      closeCouponModalBtn.addEventListener("click", () => {
        couponModal.style.display = "none";
      });
    }

    if (couponForm) {
      couponForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const code = document.getElementById("couponCode").value.trim();
        const label = document.getElementById("couponLabel").value.trim();
        const discount_percent = parseFloat(document.getElementById("couponDiscount").value);
        const limitVal = document.getElementById("couponUsageLimit").value;
        const usage_limit = limitVal ? parseInt(limitVal, 10) : null;

        try {
          await apiFetch("/coupons/admin/create", {
            method: "POST",
            body: JSON.stringify({ code, label, discount_percent, is_active: true, usage_limit })
          });
          showToast("Coupon created successfully!");
          couponModal.style.display = "none";
          couponForm.reset();
          loadCoupons();
        } catch (err) {
          showToast("Failed to create coupon: " + err.message);
        }
      });
    }
  });

  async function toggleCoupon(couponId) {
    if (!confirm("Are you sure you want to toggle this coupon's status?")) return;
    try {
      await apiFetch(`/coupons/admin/${couponId}/toggle`, { method: "PATCH" });
      showToast("Coupon status updated!");
      loadCoupons();
    } catch (err) {
      showToast("Failed to toggle coupon: " + err.message);
    }
  }

  async function deleteCoupon(couponId) {
    if (!confirm("Are you sure you want to permanently delete this coupon? This action cannot be undone.")) return;
    try {
      await apiFetch(`/coupons/admin/${couponId}`, { method: "DELETE" });
      showToast("Coupon deleted successfully!");
      loadCoupons();
    } catch (err) {
      showToast("Failed to delete coupon: " + err.message);
    }
  }

  // Global namespace for inline callbacks
  window.FreakFitsAdmin = {
    viewOrderDetails,
    viewReturnDetails,
    switchTab,
    openApprovalModal,
    rejectAccessRequest,
    toggleCoupon: toggleCoupon,
    deleteCoupon: deleteCoupon,
    loadNewsletter: loadNewsletter
  };
})();
