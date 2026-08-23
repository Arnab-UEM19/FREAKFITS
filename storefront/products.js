// ==========================================================
// FreakFits — Product Catalog & Dynamic Database Sync
// Connected to FastAPI Backend (MySQL freakfits_db)
// ==========================================================

const API_BASE_URL = (typeof window !== "undefined" && window.FREAKFITS_API_URL) || "http://127.0.0.1:8000/api";

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

const PRODUCTS = [
  {
    id: 1,
    name: "Argentina Home 3-Star Kit 25/26",
    club: "Argentina FA",
    price: 1499,
    was: 1999,
    rating: 4.9,
    reviews: 312,
    color: "#8CFF3B",
    badge: "BESTSELLER",
    badgeBg: "#8CFF3B",
    category: "home",
    images: ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300483/freakfits/Argentina_Home.jpg"],
    description:
      "The official Argentina 25/26 Home Kit with three championship stars and golden crest embroidery. Engineered with advanced Dri-FIT poly-mesh technology, laser ventilation panels, and an athletic tailored match cut.",
    material: "100% Recycled Poly-Mesh Dri-FIT with golden embroidered crest",
    fit: "Athletic Tailored Match Cut — True to size",
    care: "Machine wash cold inside-out, tumble dry low or hang dry",
    sizes: ["S", "M", "L", "XL", "XXL"],
    stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
  },
  {
    id: 2,
    name: "Argentina Away Midnight Edition",
    club: "Argentina FA",
    price: 1399,
    was: 1799,
    rating: 4.8,
    reviews: 184,
    color: "#29C5F6",
    badge: "FAN FAV",
    badgeBg: "#29C5F6",
    category: "away",
    images: ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300481/freakfits/Argentina_Away.jpg"],
    description:
      "Electric midnight royal blue tones accented with metallic details. Features lightweight AeroMesh breathable zones for premium comfort on away matchdays.",
    material: "100% Performance Breathable Polyester",
    fit: "Standard Athletic Fit",
    care: "Machine wash cold, line dry recommended",
    sizes: ["S", "M", "L", "XL", "XXL"],
    stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
  },
  {
    id: 3,
    name: "Barcelona Home Blaugrana Edition",
    club: "FC Barcelona",
    price: 1599,
    was: 2099,
    rating: 4.9,
    reviews: 245,
    color: "#FF3E7A",
    badge: "ICONIC",
    badgeBg: "#FF3E7A",
    category: "home",
    images: ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300487/freakfits/Barcelona_Home.jpg"],
    description:
      "Iconic Blaugrana stripes celebrating Camp Nou heritage. Crafted from official match-grade jacquard knit with authentic heat-applied club crest and moisture-wicking weave.",
    material: "Jacquard Knit Dri-Tech Polyester",
    fit: "Slim Matchday Cut",
    care: "Machine wash cold, gentle cycle",
    sizes: ["S", "M", "L", "XL", "XXL"],
    stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
  },
  {
    id: 4,
    name: "Real Madrid Home Pure White 25/26",
    club: "Real Madrid CF",
    price: 1599,
    was: 2099,
    rating: 5.0,
    reviews: 420,
    color: "#D4A054",
    badge: "CHAMPIONS",
    badgeBg: "#D4A054",
    category: "home",
    images: ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300499/freakfits/Real_Madrid_Home.jpg"],
    description:
      "The pristine pure white Real Madrid 25/26 home shirt with refined golden accents. Tailored AEROREADY performance cut built for glory on the biggest European nights.",
    material: "Moisture-wicking AEROREADY fabric with golden shoulder accents",
    fit: "Tailored Pro Fit",
    care: "Machine wash cold inside-out",
    sizes: ["S", "M", "L", "XL", "XXL"],
    stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
  },
  {
    id: 5,
    name: "Real Madrid Fan Edition Special",
    club: "Real Madrid CF",
    price: 1799,
    was: 2299,
    rating: 4.9,
    reviews: 198,
    color: "#D4A054",
    badge: "SPECIAL DROP",
    badgeBg: "#D4A054",
    category: "fan",
    images: ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300497/freakfits/Real_Madrid_Fan_Edition.jpg"],
    description:
      "A luxury collector fan edition featuring intricate jacquard patterns, commemorative badge details, and ultra-comfortable lifestyle-to-pitch hybrid fabric.",
    material: "Premium Engineered Poly-Jacquard Hybrid",
    fit: "Relaxed Fit for terraces and streetwear",
    care: "Hand wash or gentle machine wash cold",
    sizes: ["S", "M", "L", "XL", "XXL"],
    stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
  },
  {
    id: 6,
    name: "Arsenal 24/25 Away Edition",
    club: "Arsenal FC",
    price: 1449,
    was: 1899,
    rating: 4.7,
    reviews: 165,
    color: "#8CFF3B",
    badge: "NEW DROP",
    badgeBg: "#8CFF3B",
    category: "away",
    images: ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300485/freakfits/Arsenal_24_25_Away.jpg"],
    description:
      "Bold green and black styling celebrating the Arsenal fanbase worldwide. Built with ergonomic flatlock seams and climate-control cooling panels.",
    material: "Dri-FIT Stadium fabric with embroidered Cannon emblem",
    fit: "Regular Athletic Fit",
    care: "Machine wash cold, tumble dry low",
    sizes: ["S", "M", "L", "XL", "XXL"],
    stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
  },
  {
    id: 7,
    name: "FC Bayern Munich Away Kit",
    club: "FC Bayern München",
    price: 1499,
    was: 1949,
    rating: 4.8,
    reviews: 135,
    color: "#29C5F6",
    badge: "RESTOCK",
    badgeBg: "#29C5F6",
    category: "away",
    images: ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300488/freakfits/FC_Bayern_Away.jpg"],
    description:
      "Sleek contemporary away kit inspired by Munich architecture with solar teal detailing. Built for maximum speed and agility on the pitch.",
    material: "High-grade breathable polyester with silicone crest",
    fit: "Athletic Cut",
    care: "Machine wash cold, hang dry",
    sizes: ["S", "M", "L", "XL", "XXL"],
    stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
  },
  {
    id: 8,
    name: "Germany Home DFB Classic Kit",
    club: "Germany DFB",
    price: 1499,
    was: 1999,
    rating: 4.8,
    reviews: 210,
    color: "#D4A054",
    badge: "CLASSIC",
    badgeBg: "#D4A054",
    category: "home",
    images: ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300491/freakfits/Germany_Home.jpg"],
    description:
      "A modern reinterpretation of the iconic German tournament kit featuring the national eagle crest and dynamic gradient sleeve accents.",
    material: "AEROREADY performance moisture-wicking weave",
    fit: "Standard Athletic Fit",
    care: "Machine wash cold inside-out",
    sizes: ["S", "M", "L", "XL", "XXL"],
    stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
  },
  {
    id: 9,
    name: "Manchester United Home Red Devils",
    club: "Manchester United",
    price: 1549,
    was: 2049,
    rating: 4.9,
    reviews: 320,
    color: "#FF3E7A",
    badge: "HOT",
    badgeBg: "#FF3E7A",
    category: "home",
    images: ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300496/freakfits/Manchester_United_Home.jpg"],
    description:
      "The classic Theatre of Dreams crimson red jersey with bold shoulder stripes and the iconic Red Devils woven crest. Tailored for pure passion.",
    material: "100% Recycled Polyester Match Knit",
    fit: "Regular Matchday Cut",
    care: "Machine wash cold, do not iron badge",
    sizes: ["S", "M", "L", "XL", "XXL"],
    stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
  },
  {
    id: 10,
    name: "Spain Away Euro Champions Kit",
    club: "RFEF Spain",
    price: 1399,
    was: 1799,
    rating: 4.7,
    reviews: 115,
    color: "#8CFF3B",
    badge: "CHAMPIONS",
    badgeBg: "#8CFF3B",
    category: "away",
    images: ["https://res.cloudinary.com/sjgw6cud/image/upload/f_auto,q_auto/v1787300501/freakfits/Spain_Away.jpg"],
    description:
      "Vibrant energetic yellow-volt away kit of the reigning European champions. Light, breathable, and styled with subtle national geometric textures.",
    material: "Featherlight breathable mesh fabric",
    fit: "Athletic Fit",
    care: "Machine wash cold, hang dry",
    sizes: ["S", "M", "L", "XL", "XXL"],
    stock: { S: 10, M: 10, L: 10, XL: 5, XXL: 5 }
  },
];

function starString(rating) {
  const full = Math.round(rating);
  return "★".repeat(full) + "☆".repeat(5 - full);
}

function jerseySVG(color) {
  return `<svg viewBox="0 0 44 48"><path d="${JERSEY_PATH}" fill="${color}" stroke="#0A0C08" stroke-width="1.4" stroke-linejoin="round"/></svg>`;
}

function getProductsByCategory(cat) {
  if (!cat || cat === "all") return PRODUCTS;
  if (cat === "fan") {
    return PRODUCTS.filter((p) => p.category === "fan" || (p.name && p.name.toLowerCase().includes("fan")));
  }
  if (cat === "sale" || cat === "clearance") {
    return PRODUCTS.filter((p) => p.was && p.was > p.price);
  }
  return PRODUCTS.filter((p) => p.category === cat);
}

function getProductsBySearch(q) {
  const term = (q || "").toLowerCase().trim();
  if (!term) return [];
  return PRODUCTS.filter((p) => 
    p.name.toLowerCase().includes(term) ||
    p.club.toLowerCase().includes(term) ||
    (p.description && p.description.toLowerCase().includes(term)) ||
    (p.category && p.category.toLowerCase().includes(term))
  );
}

function getProductById(id) {
  return PRODUCTS.find((p) => p.id === parseInt(id));
}

// ============ LIVE BACKEND SYNCHRONIZER ============
async function syncProductsFromBackend() {
  try {
    const res = await fetch(`${API_BASE_URL}/products`);
    if (!res.ok) return;
    const data = await res.json();
    if (Array.isArray(data) && data.length > 0) {
      data.forEach((apiProd) => {
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
