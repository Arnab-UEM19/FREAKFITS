// ==========================================================
// FreakFits - Frontend API Client Connector (FastAPI Backend)
// ==========================================================

window.escapeHtml = function(unsafe) {
  if (typeof unsafe !== 'string') return unsafe;
  return unsafe
       .replace(/&/g, "&amp;")
       .replace(/</g, "&lt;")
       .replace(/>/g, "&gt;")
       .replace(/"/g, "&quot;")
       .replace(/'/g, "&#039;");
};

const FreakFitsAPI = (function () {
  const BASE_URL = window.FREAKFITS_API_URL || "http://127.0.0.1:8000/api";
  const TOKEN_KEY = "freakfits_jwt_token";
  
  let consecutiveFailures = 0;
  let offlineBanner = null;

  function showOfflineBanner() {
    if (offlineBanner || typeof document === 'undefined') return;
    offlineBanner = document.createElement("div");
    offlineBanner.className = "offline-banner";
    offlineBanner.innerHTML = "We're having trouble connecting to our servers. Please check your internet connection and try again.";
    document.body.appendChild(offlineBanner);
  }

  function hideOfflineBanner() {
    if (offlineBanner && typeof document !== 'undefined') {
      offlineBanner.remove();
      offlineBanner = null;
    }
  }

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token) {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  }

  async function _fetch(endpoint, options) {
    options = options || {};
    var url = BASE_URL + endpoint;
    var method = (options.method || "GET").toUpperCase();
    if (method === "GET") {
      var sep = url.indexOf("?") === -1 ? "?" : "&";
      url = url + sep + "_t=" + Date.now();
    }
    var headers = Object.assign({}, options.headers || {});
    if (!(options.body instanceof FormData)) {
      headers = Object.assign({ "Content-Type": "application/json" }, headers);
    }

    var token = getToken();
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = "Bearer " + token;
    }

    var controller = new AbortController();
    var timeoutId = setTimeout(function() { controller.abort(); }, 10000);

    // Add credentials: "include" to send cookies
    var fetchOptions = Object.assign({ credentials: "include" }, options, { headers: headers, signal: controller.signal });

    try {
      var response = await fetch(url, fetchOptions);
      clearTimeout(timeoutId);
      
      consecutiveFailures = 0;
      hideOfflineBanner();
      
      var data = await response.json().catch(function() { return {}; });
      if (response.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem("freakfits_user");
        if (typeof AuthStore !== "undefined" && AuthStore.logout) {
          AuthStore.logout();
        }
        window.location.reload();
      }
      if (!response.ok) {
        throw new Error(data.detail || data.message || ("HTTP " + response.status));
      }
      return data;
    } catch (err) {
      clearTimeout(timeoutId);
      
      if (err.name === 'TypeError' || err.name === 'AbortError') {
        consecutiveFailures++;
        if (consecutiveFailures >= 2) {
          showOfflineBanner();
        }
      }
      
      console.warn("[FreakFits API] Request to " + endpoint + " failed:", err.message);
      throw err;
    }
  }

  // ============ AUTH ENDPOINTS ============
  async function sendOtp(email) {
    return _fetch("/auth/send-otp", { method: "POST", body: JSON.stringify({ email: email }) });
  }

  async function verifyOtp(email, otp_code) {
    return _fetch("/auth/verify-otp", { method: "POST", body: JSON.stringify({ email: email, otp_code: otp_code }) });
  }

  async function register(params) {
    var res = await _fetch("/auth/register", {
      method: "POST",
      body: JSON.stringify({ full_name: params.name, mobile_number: params.mobile, email: params.email, password: params.password }),
    });
    if (res.access_token) setToken(res.access_token);
    return res;
  }

  async function login(email, password) {
    var res = await _fetch("/auth/login", { method: "POST", body: JSON.stringify({ email: email, password: password }) });
    if (res.access_token) setToken(res.access_token);
    return res;
  }

  async function updateProfile(data) {
    return _fetch("/auth/me", {
      method: "PUT",
      body: JSON.stringify(data),
    });
  }

  async function changePassword(currentPassword, newPassword) {
    return _fetch("/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  }

  async function getMe() { return _fetch("/auth/me"); }
  async function logout() { 
    try { await _fetch("/auth/logout", { method: "POST" }); } catch(e) {}
    setToken(null); 
  }

  // ============ PRODUCT ENDPOINTS ============
  async function getProducts(params) {
    params = params || {};
    var p = new URLSearchParams();
    if (params.category) p.append("category", params.category);
    if (params.sort) p.append("sort", params.sort);
    if (params.q) p.append("q", params.q);
    return _fetch("/products?" + p.toString());
  }
  async function getProduct(id) { return _fetch("/products/" + id); }

  // ============ CART ENDPOINTS ============
  async function getCart() {
    return _fetch("/cart/");
  }

  async function addCartItem(productId, size, quantity, customName, customNumber) {
    return _fetch("/cart/", {
      method: "POST",
      body: JSON.stringify({
        product_id: productId,
        size: size,
        quantity: quantity,
        custom_name: customName || null,
        custom_number: customNumber || null
      })
    });
  }

  async function updateCartItem(itemId, quantity, customName, customNumber) {
    return _fetch("/cart/" + itemId, {
      method: "PUT",
      body: JSON.stringify({
        quantity: quantity,
        custom_name: customName !== undefined ? customName : null,
        custom_number: customNumber !== undefined ? customNumber : null
      })
    });
  }

  async function removeCartItem(itemId) {
    return _fetch("/cart/" + itemId, { method: "DELETE" });
  }

  async function clearCart() {
    return _fetch("/cart/", { method: "DELETE" });
  }

  // ============ ORDER ENDPOINTS ============
  async function getMyOrders() { return _fetch("/orders/my-orders"); }
  async function getCustomerOrdersByEmail(email) {
    return _fetch("/customer/orders/" + encodeURIComponent(email.toLowerCase().trim()));
  }
  async function trackOrder(orderCode, phone) {
    return _fetch("/orders/track?order_code=" + encodeURIComponent(orderCode.trim()) + "&phone=" + encodeURIComponent(phone.trim()));
  }
  async function cancelOrder(orderCode) {
    return _fetch("/orders/" + encodeURIComponent(orderCode.trim()) + "/cancel", { method: "POST" });
  }

  // ============ RAZORPAY PAYMENT ENDPOINTS ============
  /** Step 1: Create Razorpay order. Returns { razorpay_order_id, amount, currency, freakfits_order_code, key_id } */
  async function createPayment(payload) {
    return _fetch("/payments/create", { method: "POST", body: JSON.stringify(payload) });
  }
  /** Step 2: Verify Razorpay signature. Returns { success, order_code, payment_id, message } */
  async function verifyPayment(payload) {
    return _fetch("/payments/verify", { method: "POST", body: JSON.stringify(payload) });
  }

  // ============ COUPON ENDPOINTS ============
  async function validateCoupon(code) {
    return _fetch("/coupons/validate", { method: "POST", body: JSON.stringify({ code: code }) });
  }
  async function checkHealth() { return _fetch("/health"); }

  // ============ RETURN ENDPOINTS ============
  async function submitReturnRequest(formData) {
    return _fetch("/returns", { method: "POST", body: formData });
  }

  // ============ CONTACT ENDPOINTS ============
  async function submitContactMessage(payload) {
    return _fetch("/contact", { method: "POST", body: JSON.stringify(payload) });
  }

  // ============ FORGOT/RESET PASSWORD ENDPOINTS ============
  async function forgotPassword(email) {
    return _fetch("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email: email }) });
  }
  async function resetPassword(email, password, confirm_password) {
    return _fetch("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ email: email, password: password, confirm_password: confirm_password })
    });
  }

  // ============ ADDRESS ENDPOINTS ============
  async function getAddresses() {
    return _fetch("/auth/addresses");
  }

  async function createAddress(addressData) {
    return _fetch("/auth/addresses", { method: "POST", body: JSON.stringify(addressData) });
  }

  async function updateAddress(id, addressData) {
    return _fetch("/auth/addresses/" + id, { method: "PUT", body: JSON.stringify(addressData) });
  }

  async function deleteAddress(id) {
    return _fetch("/auth/addresses/" + id, { method: "DELETE" });
  }

  // ============ WISHLIST ============
  async function getWishlist() {
    return _fetch("/auth/wishlist", { method: "GET" });
  }

  async function addToWishlist(productId) {
    return _fetch("/auth/wishlist", { method: "POST", body: JSON.stringify({ product_id: productId }) });
  }

  async function removeFromWishlist(productId) {
    return _fetch("/auth/wishlist/" + productId, { method: "DELETE" });
  }

  // ============ NEWSLETTER ============
  async function subscribeNewsletter(email) {
    return _fetch("/newsletter/subscribe", {
      method: "POST",
      body: JSON.stringify({ email: email })
    });
  }

  return {
    BASE_URL: BASE_URL,
    getToken: getToken, setToken: setToken,
    sendOtp: sendOtp, verifyOtp: verifyOtp, register: register, login: login, getMe: getMe, logout: logout,
    updateProfile: updateProfile, changePassword: changePassword,
    forgotPassword: forgotPassword, resetPassword: resetPassword,
    getProducts: getProducts, getProduct: getProduct,
    getMyOrders: getMyOrders, getCustomerOrdersByEmail: getCustomerOrdersByEmail, trackOrder: trackOrder, cancelOrder: cancelOrder,
    createPayment: createPayment, verifyPayment: verifyPayment,
    validateCoupon: validateCoupon, checkHealth: checkHealth,
    submitReturnRequest: submitReturnRequest,
    submitContactMessage: submitContactMessage,
    getAddresses: getAddresses,
    createAddress: createAddress,
    updateAddress: updateAddress,
    deleteAddress: deleteAddress,
    getWishlist: getWishlist,
    addToWishlist: addToWishlist,
    removeFromWishlist: removeFromWishlist,
    subscribeNewsletter: subscribeNewsletter,
    getCart: getCart,
    addCartItem: addCartItem,
    updateCartItem: updateCartItem,
    removeCartItem: removeCartItem,
    clearCart: clearCart
  };
})();
