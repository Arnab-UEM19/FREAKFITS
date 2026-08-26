// ==========================================================
// FreakFits — Product Catalog & Dynamic Database Sync
// Connected to FastAPI Backend (MySQL freakfits_db)
// ==========================================================

const API_BASE_URL = (typeof window !== "undefined" && window.FREAKFITS_API_URL) || "https://freakfits-api.onrender.com/api";

const JERSEY_PATH =
  "M14 3 L6 9 L2 17 L8 22 L12 19 L12 45 Q22 48 32 45 L32 19 L36 22 L42 17 L38 9 L30 3 Q26 7 22 7 Q18 7 14 3Z";

// Dynamic size price helpers that resolve against individual product size prices
function getSizePrice(productOrSize, size) {
  if (typeof productOrSize === "object" && productOrSize !== null) {
    if (size && productOrSize.size_prices && productOrSize.size_prices[size] !== undefined) {
      return parseFloat(productOrSize.size_prices[size]);
    }
    if (productOrSize.size_prices && productOrSize.size_prices["S"] !== undefined) {
      return parseFloat(productOrSize.size_prices["S"]);
    }
    return productOrSize.price || 1499;
  }
  if (typeof productOrSize === "number") {
    const p = getProductById(productOrSize);
    if (p && size && p.size_prices && p.size_prices[size] !== undefined) {
      return parseFloat(p.size_prices[size]);
    }
    return p ? p.price : 1499;
  }
  return 1499;
}

function getSizeWasPrice(productOrSize, size) {
  if (typeof productOrSize === "object" && productOrSize !== null) {
    if (size && productOrSize.size_was_prices && productOrSize.size_was_prices[size] !== undefined) {
      return parseFloat(productOrSize.size_was_prices[size]);
    }
    if (productOrSize.size_was_prices && productOrSize.size_was_prices["S"] !== undefined) {
      return parseFloat(productOrSize.size_was_prices["S"]);
    }
    const currPrice = getSizePrice(productOrSize, size);
    if (productOrSize.was_price && productOrSize.was_price > currPrice) {
      return parseFloat(productOrSize.was_price);
    }
    return productOrSize.was || (currPrice + 400);
  }
  if (typeof productOrSize === "number") {
    const p = getProductById(productOrSize);
    if (p && size && p.size_was_prices && p.size_was_prices[size] !== undefined) {
      return parseFloat(p.size_was_prices[size]);
    }
    const currPrice = getSizePrice(p || productOrSize, size);
    return p ? (p.was || p.was_price || (currPrice + 400)) : (currPrice + 400);
  }
  return 1999;
}

const PRODUCTS = [];

function starString(rating) {
  let html = "";
  for(let i=0; i<5; i++) {
    html += i < Math.floor(rating) ? "★" : "☆";
  }
  return html;
}

function getProductById(id) {
  return PRODUCTS.find((p) => p.id === parseInt(id));
}

// ============ LIVE BACKEND SYNCHRONIZER ============
async function syncProductsFromBackend() {
  try {
    const res = await fetch(`${API_BASE_URL}/products?limit=1000`);
    if (!res.ok) return;
    const data = await res.json();
    const items = data.items || data; // Handle both paginated and unpaginated responses
    if (Array.isArray(items) && items.length > 0) {
      items.forEach((apiProd) => {
        const existing = PRODUCTS.find((p) => p.id === apiProd.id);
        const mapped = {
          id: apiProd.id,
          name: apiProd.name,
          club: apiProd.club,
          price: apiProd.price,
          was: apiProd.was_price || (apiProd.price + 400),
          rating: apiProd.rating || 4.8,
          reviews: apiProd.reviews || 120,
          color: apiProd.color || "#8CFF3B",
          badge: apiProd.badge || null,
          badgeBg: apiProd.badge_bg || apiProd.color || "#8CFF3B",
          category: apiProd.category || "home",
          images: Array.isArray(apiProd.images) && apiProd.images.length > 0
            ? apiProd.images
            : (existing ? existing.images : ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300483/freakfits/Argentina_Home.jpg"]),
          description: apiProd.description || (existing ? existing.description : `${apiProd.name} official match jersey.`),
          material: apiProd.material || (existing ? existing.material : "100% Recycled Poly-Mesh Dri-FIT"),
          fit: apiProd.fit || (existing ? existing.fit : "Athletic Tailored Match Cut"),
          care: apiProd.care || (existing ? existing.care : "Machine wash cold inside-out"),
          sizes: ["S", "M", "L", "XL", "XXL"],
          stock: apiProd.stock || { S: 10, M: 10, L: 10, XL: 5, XXL: 5 },
          size_prices: apiProd.size_prices || {
            S: apiProd.price, M: apiProd.price, L: apiProd.price, XL: apiProd.price, XXL: apiProd.price
          },
          size_was_prices: apiProd.size_was_prices || {
            S: apiProd.was_price || (apiProd.price + 400),
            M: apiProd.was_price || (apiProd.price + 400),
            L: apiProd.was_price || (apiProd.price + 400),
            XL: apiProd.was_price || (apiProd.price + 400),
            XXL: apiProd.was_price || (apiProd.price + 400)
          }
        };

        if (existing) {
          Object.assign(existing, mapped);
        } else {
          PRODUCTS.push(mapped);
        }
      });

      // Sort PRODUCTS: "NEW DROP" items first, then others by ID descending (newest first)
      PRODUCTS.sort((a, b) => {
        const aNew = a.badge === "NEW DROP";
        const bNew = b.badge === "NEW DROP";
        if (aNew && !bNew) return -1;
        if (!aNew && bNew) return 1;
        return b.id - a.id;
      });

      // Dispatch event to re-render storefront components with live MySQL prices
      window.dispatchEvent(new CustomEvent("freakfits:products-synced", { detail: PRODUCTS }));
    }
  } catch (err) {
    console.debug("[FreakFits] Backend sync offline, using local catalog data:", err.message);
  }
}

// Auto-run sync on page load
if (typeof window !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => syncProductsFromBackend());
  } else {
    syncProductsFromBackend();
  }
}

function getProductsByCategory(cat) {
  if (cat === "clearance") return PRODUCTS.filter(p => p.was_price || (p.was && p.was > p.price));
  return PRODUCTS.filter(p => p.category.toLowerCase() === cat.toLowerCase());
}

function getProductsBySearch(query) {
  const q = query.toLowerCase();
  return PRODUCTS.filter(p => 
    p.name.toLowerCase().includes(q) || 
    p.club.toLowerCase().includes(q) || 
    p.category.toLowerCase().includes(q)
  );
}
