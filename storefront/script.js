// ==========================================================
// FreakFits — Homepage Interactivity
// Uses shared products.js and cart-store.js
// ==========================================================

function renderProducts() {
  const grid = document.getElementById("productGrid");
  if (!grid) return;

  if (PRODUCTS.length === 0) {
    grid.innerHTML = Array.from({length: 6}).map(() => `
      <article class="skeleton-card skeleton">
        <div class="img"></div>
        <div class="title"></div>
        <div class="subtitle"></div>
        <div class="price"></div>
        <div class="btn"></div>
      </article>
    `).join("");
    return;
  }

  const e = window.escapeHtml || (s => s);
  
  // Only show the top 12 latest/trending products on the homepage
  const trendingProducts = PRODUCTS.slice(0, 12);

  grid.innerHTML = trendingProducts.map((p, i) => `
    <article class="product-card" style="--card-accent:${e(p.color)}">
      <a href="product.html?id=${e(p.id)}" class="product-card__link">
        <div class="product-card__media">
          ${p.badge ? `<span class="product-card__badge" style="--badge-bg:${e(p.badgeBg || p.color)}">${e(p.badge)}</span>` : ""}
          <button class="product-card__wish" aria-label="Save ${e(p.name)}" data-wish="${e(p.id)}">
            <svg viewBox="0 0 24 24" fill="none"><path d="M12 20s-7-4.4-9.5-9C.7 7.3 3 3.5 6.8 3.5c2 0 3.6 1 5.2 3 1.6-2 3.2-3 5.2-3 3.8 0 6.1 3.8 4.3 7.5C19 15.6 12 20 12 20z" fill="currentColor"/></svg>
          </button>
          <img src="${e(p.images[0])}" alt="${e(p.name)}" class="product-card__img" loading="lazy">
        </div>
      </a>
      <div class="product-card__body">
        <span class="product-card__club">${e(p.club)}</span>
        <a href="product.html?id=${e(p.id)}" class="product-card__name">${e(p.name)}</a>
        <span class="product-card__stars">${starString(p.rating)} <span>(${p.reviews})</span></span>
        <div class="product-card__price">
          <span class="now">₹${getSizePrice(p).toLocaleString("en-IN")}</span>
          <span class="was">₹${getSizeWasPrice(p).toLocaleString("en-IN")}</span>
        </div>
        <button class="product-card__add" data-add="${e(p.id)}">Add to Cart</button>
      </div>
    </article>
  `).join("");

  grid.querySelectorAll("[data-add]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const prod = getProductById(btn.dataset.add);
      await CartStore.addItem({
        id: prod.id,
        name: prod.name,
        club: prod.club,
        price: prod.price,
        was: prod.was,
        color: prod.color,
        image: prod.images[0],
        category: prod.category,
      });
      showToast(`Added — ${prod.name}`);
    });
  });

  grid.querySelectorAll("[data-wish]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      const currentUser = typeof AuthStore !== "undefined" ? AuthStore.getCurrentUser() : null;
      if (!currentUser) {
        showToast("⚠️ Please log in to save items to your wishlist.");
        return;
      }

      const productId = parseInt(btn.dataset.wish);
      const isActive = btn.classList.contains("is-active");
      
      try {
        if (isActive) {
          await FreakFitsAPI.removeFromWishlist(productId);
          btn.classList.remove("is-active");
          showToast("Removed from your list");
        } else {
          await FreakFitsAPI.addToWishlist(productId);
          btn.classList.add("is-active");
          showToast("Saved to your list");
        }
      } catch (err) {
        showToast("Failed to update wishlist.");
      }
    });
  });

  // Sync wishlist state if logged in
  if (typeof AuthStore !== "undefined" && AuthStore.getCurrentUser()) {
    FreakFitsAPI.getWishlist().then(items => {
      items.forEach(item => {
        const btn = document.querySelector(`[data-wish="${item.product_id}"]`);
        if (btn) btn.classList.add("is-active");
      });
    }).catch(console.error);
  }
}

// ---------- Toast ----------
let toastTimer = null;
function showToast(msg) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2200);
}

// ---------- Mobile nav ----------
function initNav() {
  const burger = document.getElementById("burgerBtn");
  const nav = document.getElementById("mainNav");
  if (!burger || !nav) return;
  burger.addEventListener("click", () => {
    nav.classList.toggle("is-open");
    burger.classList.toggle("is-active");
  });
  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      nav.classList.remove("is-open");
      burger.classList.remove("is-active");
    });
  });
}


// ---------- Jersey Carousel ----------
function initJerseyCarousel() {
  const carousel = document.getElementById("jerseyCarousel");
  if (!carousel) return;

  const jerseys = carousel.querySelectorAll(".hero-jersey");
  const dots = carousel.querySelectorAll(".jersey-dot");
  const totalJerseys = jerseys.length;
  let currentIndex = 0;
  let intervalId = null;

  function goTo(index) {
    if (index === currentIndex) return;
    const prevIndex = currentIndex;

    // Apply exit-right class to outgoing jersey
    const prevJersey = jerseys[prevIndex];
    prevJersey.classList.remove("hero-jersey--active");
    prevJersey.classList.add("hero-jersey--exit-right");
    dots[prevIndex].classList.remove("is-active");

    setTimeout(() => {
      prevJersey.classList.remove("hero-jersey--exit-right");
    }, 700);

    // Set new index
    currentIndex = index;

    // Activate incoming jersey
    const nextJersey = jerseys[currentIndex];
    nextJersey.classList.remove("hero-jersey--exit-right");
    nextJersey.classList.add("hero-jersey--active");
    dots[currentIndex].classList.add("is-active");
  }

  function next() {
    goTo((currentIndex + 1) % totalJerseys);
  }

  function startAutoPlay() {
    stopAutoPlay();
    intervalId = setInterval(next, 5000);
  }

  function stopAutoPlay() {
    if (intervalId) {
      clearInterval(intervalId);
      intervalId = null;
    }
  }

  // Dot click handlers
  dots.forEach((dot) => {
    dot.addEventListener("click", () => {
      goTo(parseInt(dot.dataset.dot));
      startAutoPlay(); // Reset timer on manual navigation
    });
  });

  // Pause on hover, resume on leave
  carousel.addEventListener("mouseenter", stopAutoPlay);
  carousel.addEventListener("mouseleave", startAutoPlay);

  // Start auto-rotation
  startAutoPlay();
}



document.addEventListener("DOMContentLoaded", () => {
  renderProducts();
  initNav();
  initJerseyCarousel();
});

window.addEventListener("freakfits:products-synced", () => {
  renderProducts();
});
