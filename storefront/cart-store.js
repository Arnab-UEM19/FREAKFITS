// ==========================================================
// FreakFits — Shared Cart Store (localStorage-based)
// ==========================================================

const CartStore = (function () {
  const STORAGE_KEY = "freakfits_cart";
  const COUPON_KEY = "freakfits_coupon";
  const VALID_COUPONS = {
    FREAK5P: { discount: 0.05, label: "5% OFF — FREAK5P" },
  };

  function _read() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
    } catch {
      return [];
    }
  }

  function _write(cart) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
    _broadcastCount();
  }

  function _broadcastCount() {
    const count = getCount();
    document.querySelectorAll("[data-cart-count]").forEach((el) => {
      el.textContent = count;
    });
    // Also update legacy #cartCount
    const legacy = document.getElementById("cartCount");
    if (legacy) legacy.textContent = count;
  }

  function getCart() {
    return _read();
  }

  function getCount() {
    return _read().reduce((sum, item) => sum + item.qty, 0);
  }

  function addItem(product) {
    const cart = _read();
    // product: { id, name, club, price, was, color, size, qty, image, category, customName, customNumber }
    const existing = cart.find(
      (item) => item.id === product.id && item.size === product.size
    );
    if (existing) {
      existing.qty += product.qty || 1;
    } else {
      cart.push({
        id: product.id,
        name: product.name,
        club: product.club || "",
        price: product.price,
        was: product.was || null,
        color: product.color || "#8CFF3B",
        size: product.size || "M",
        qty: product.qty || 1,
        image: product.image || null,
        category: product.category || "home",
        customName: product.customName || "",
        customNumber: product.customNumber || "",
      });
    }
    _write(cart);
    return cart;
  }

  function removeItem(id, size) {
    let cart = _read();
    cart = cart.filter((item) => !(item.id === id && item.size === size));
    _write(cart);
    return cart;
  }

  function updateQty(id, size, qty) {
    const cart = _read();
    const item = cart.find((i) => i.id === id && i.size === size);
    if (item) {
      item.qty = Math.max(1, qty);
    }
    _write(cart);
    return cart;
  }

  function updateCustomization(id, size, customName, customNumber) {
    const cart = _read();
    const item = cart.find((i) => i.id === id && i.size === size);
    if (item) {
      item.customName = customName || "";
      item.customNumber = customNumber || "";
    }
    _write(cart);
    return cart;
  }

  function getSubtotal() {
    return _read().reduce((sum, item) => sum + item.price * item.qty, 0);
  }

  function applyCoupon(couponData) {
    if (couponData && couponData.valid) {
      const couponObj = {
        code: couponData.code,
        discount: couponData.discount_percent / 100.0,
        label: couponData.label
      };
      localStorage.setItem(COUPON_KEY, JSON.stringify(couponObj));
      return { valid: true, ...couponObj };
    }
    localStorage.removeItem(COUPON_KEY);
    return { valid: false, label: "Invalid coupon code" };
  }

  function removeCoupon() {
    localStorage.removeItem(COUPON_KEY);
  }

  function getAppliedCoupon() {
    const raw = localStorage.getItem(COUPON_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && parsed.code) {
        return parsed;
      }
    } catch (e) {
      // Legacy format (plain string) or invalid JSON. Fallback to hardcoded list if it matches.
      if (typeof raw === "string" && raw.trim()) {
        const code = raw.trim().toUpperCase();
        if (VALID_COUPONS[code]) {
          return { code, ...VALID_COUPONS[code] };
        }
      }
    }
    return null;
  }

  function getTotal() {
    const subtotal = getSubtotal();
    const coupon = getAppliedCoupon();
    const discountAmount = coupon ? subtotal * coupon.discount : 0;
    const discountedSubtotal = Math.max(0, subtotal - discountAmount);
    const shipping = subtotal === 0 ? 0 : (discountedSubtotal >= 500 ? 0 : 99);
    return {
      subtotal,
      discountAmount,
      coupon,
      shipping,
      total: subtotal === 0 ? 0 : (discountedSubtotal + shipping),
    };
  }

  function clearCart() {
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(COUPON_KEY);
    _broadcastCount();
  }

  // Init badge count on load
  function init() {
    document.addEventListener("DOMContentLoaded", _broadcastCount);
  }

  function getGrandTotal() {
    return getTotal().total;
  }

  function getDiscountAmount() {
    return getTotal().discountAmount;
  }

  function getShippingFee() {
    return getTotal().shipping;
  }

  return {
    getCart,
    getCount,
    addItem,
    removeItem,
    updateQty,
    updateCustomization,
    getSubtotal,
    getGrandTotal,
    getDiscountAmount,
    getShippingFee,
    applyCoupon,
    removeCoupon,
    getAppliedCoupon,
    getTotal,
    clearCart,
    init,
  };
})();

CartStore.init();
