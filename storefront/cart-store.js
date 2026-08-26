// ==========================================================
// FreakFits — Shared Cart Store (Backend Synced)
// ==========================================================

const CartStore = (function () {
  const STORAGE_KEY = "freakfits_cart";
  const COUPON_KEY = "freakfits_coupon";
  const VALID_COUPONS = {
    FREAK5P: { discount: 0.05, label: "5% OFF — FREAK5P" },
  };

  let localCartCache = [];

  function _isLoggedIn() {
    return typeof FreakFitsAPI !== "undefined" && FreakFitsAPI.getToken() !== null;
  }

  function _readLocal() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY)) || [];
    } catch {
      return [];
    }
  }

  function _writeLocal(cart) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
    _broadcastCount(cart);
  }

  function _broadcastCount(cart) {
    const count = cart.reduce((sum, item) => sum + item.qty, 0);
    document.querySelectorAll("[data-cart-count]").forEach((el) => {
      el.textContent = count;
    });
    const legacy = document.getElementById("cartCount");
    if (legacy) legacy.textContent = count;
  }

  async function getCart() {
    if (_isLoggedIn()) {
      try {
        const backendItems = await FreakFitsAPI.getCart();
        const mapped = backendItems.map(item => ({
          id: item.product_id,
          size: item.size,
          qty: item.quantity,
          customName: item.custom_name || "",
          customNumber: item.custom_number || "",
          cart_item_id: item.id
        }));
        
        const fullCart = mapped.map(item => {
          const p = typeof getProductById === 'function' ? getProductById(item.id) : null;
          if (p) {
            return {
              ...item,
              name: p.name,
              club: p.club,
              price: typeof getSizePrice === 'function' ? getSizePrice(p, item.size) : p.price,
              was: p.size_was_prices ? p.size_was_prices[item.size] : p.was,
              color: p.color,
              image: Array.isArray(p.images) ? p.images[0] : p.images,
              category: p.category
            };
          }
          return item;
        });
        localCartCache = fullCart;
        _broadcastCount(localCartCache);
        return localCartCache;
      } catch (err) {
        console.error("Failed to fetch cart from backend", err);
        return localCartCache;
      }
    } else {
      const cart = _readLocal();
      localCartCache = cart;
      _broadcastCount(cart);
      return cart;
    }
  }

  async function addItem(product) {
    if (_isLoggedIn()) {
      try {
        await FreakFitsAPI.addCartItem(
          product.id,
          product.size || "M",
          product.qty || 1,
          product.customName || null,
          product.customNumber || null
        );
        return await getCart();
      } catch (err) {
        console.error("Failed to add item to backend cart", err);
        return localCartCache;
      }
    } else {
      const cart = _readLocal();
      const existing = cart.find((item) => item.id === product.id && item.size === product.size);
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
      _writeLocal(cart);
      localCartCache = cart;
      return cart;
    }
  }

  async function removeItem(id, size) {
    if (_isLoggedIn()) {
      const item = localCartCache.find(i => i.id === id && i.size === size);
      if (item && item.cart_item_id) {
        try {
          await FreakFitsAPI.removeCartItem(item.cart_item_id);
          return await getCart();
        } catch (err) {
          console.error("Failed to remove item", err);
        }
      }
      return localCartCache;
    } else {
      let cart = _readLocal();
      cart = cart.filter((item) => !(item.id === id && item.size === size));
      _writeLocal(cart);
      localCartCache = cart;
      return cart;
    }
  }

  async function updateQty(id, size, qty) {
    if (_isLoggedIn()) {
      const item = localCartCache.find(i => i.id === id && i.size === size);
      if (item && item.cart_item_id) {
        try {
          await FreakFitsAPI.updateCartItem(item.cart_item_id, Math.max(1, qty), undefined, undefined);
          return await getCart();
        } catch (err) {
          console.error("Failed to update qty", err);
        }
      }
      return localCartCache;
    } else {
      const cart = _readLocal();
      const item = cart.find((i) => i.id === id && i.size === size);
      if (item) {
        item.qty = Math.max(1, qty);
      }
      _writeLocal(cart);
      localCartCache = cart;
      return cart;
    }
  }

  async function updateCustomization(id, size, customName, customNumber) {
    if (_isLoggedIn()) {
      const item = localCartCache.find(i => i.id === id && i.size === size);
      if (item && item.cart_item_id) {
        try {
          await FreakFitsAPI.updateCartItem(item.cart_item_id, undefined, customName, customNumber);
          return await getCart();
        } catch (err) {
          console.error("Failed to update customization", err);
        }
      }
      return localCartCache;
    } else {
      const cart = _readLocal();
      const item = cart.find((i) => i.id === id && i.size === size);
      if (item) {
        item.customName = customName || "";
        item.customNumber = customNumber || "";
      }
      _writeLocal(cart);
      localCartCache = cart;
      return cart;
    }
  }

  async function clearCart() {
    if (_isLoggedIn()) {
      try {
        await FreakFitsAPI.clearCart();
        localCartCache = [];
        _broadcastCount([]);
        return [];
      } catch (err) {
        console.error("Failed to clear backend cart", err);
      }
    } else {
      _writeLocal([]);
      localCartCache = [];
      return [];
    }
  }

  async function syncLocalToBackend() {
    if (!_isLoggedIn()) return;
    const local = _readLocal();
    if (local.length === 0) return;
    
    for (let item of local) {
      try {
        await FreakFitsAPI.addCartItem(
          item.id,
          item.size,
          item.qty,
          item.customName || null,
          item.customNumber || null
        );
      } catch (err) {
        console.error("Failed to sync item to backend", err);
      }
    }
    localStorage.removeItem(STORAGE_KEY);
    await getCart();
  }

  function getSubtotal() {
    return localCartCache.reduce((sum, item) => sum + item.price * item.qty, 0);
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
      count: localCartCache.reduce((sum, item) => sum + item.qty, 0)
    };
  }

  function getGrandTotal() {
    return getTotal().total;
  }

  async function init() {
    await getCart();
  }

  return {
    init,
    getCart,
    addItem,
    removeItem,
    updateQty,
    updateCustomization,
    clearCart,
    syncLocalToBackend,
    getSubtotal,
    getTotal,
    getGrandTotal,
    applyCoupon,
    removeCoupon,
    getAppliedCoupon,
    VALID_COUPONS,
  };
})();

if (typeof window !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    // Only init if products are synced or if they don't use products (but we rely on products.js for details)
  });
  window.addEventListener("freakfits:products-synced", () => {
    CartStore.init();
  });
}
