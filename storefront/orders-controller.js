// ==========================================================
// FreakFits — Orders Page Controller
// ==========================================================

(function () {
  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    if (typeof str !== "string") str = String(str);
    return str.replace(/[&<>'"]/g, 
      tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
  }
  document.addEventListener("DOMContentLoaded", async () => {
    const user = AuthStore.getCurrentUser();
    if (!user) {
      showToast("⚠️ Please sign in to view your orders");
      setTimeout(() => {
        window.location.href = "auth.html?redirect=orders.html";
      }, 1000);
      return;
    }

    const container = document.getElementById("ordersContainer");
    if (!container) return;

    try {
      const orders = await FreakFitsAPI.getCustomerOrdersByEmail(user.email);
      renderOrders(orders, container);
      setupReviewModal(orders);
      setupCancelButtons(orders);
    } catch (err) {
      console.error("[Orders Controller] Error fetching orders:", err);
      // Fallback: render from localStorage if backend is offline/error
      const localOrders = getLocalOrders(user.email);
      if (localOrders && localOrders.length > 0) {
        renderOrders(localOrders, container);
        setupReviewModal(localOrders);
        setupCancelButtons(localOrders);
      } else {
        container.innerHTML = `
          <div class="orders-empty">
            <svg viewBox="0 0 24 24" fill="none" class="orders-empty__icon">
              <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z" stroke="currentColor" stroke-width="2"/>
              <path d="M12 8v4M12 16h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
            <h2>Unable to load orders</h2>
            <p>${err.message || "Failed to establish database connection."}</p>
            <button onclick="window.location.reload();" class="btn btn--solid">Try Again</button>
          </div>
        `;
      }
    }
  });

  function getLocalOrders(email) {
    try {
      const allLocal = JSON.parse(localStorage.getItem("freakfits_recent_orders")) || [];
      const cleanEmail = email.toLowerCase().trim();
      return allLocal.filter(o => (o.customer_email || "").toLowerCase().trim() === cleanEmail);
    } catch (_) {
      return [];
    }
  }

  function renderOrders(orders, container) {
    if (!orders || orders.length === 0) {
      container.innerHTML = `
        <div class="orders-empty">
          <svg viewBox="0 0 80 80" fill="none" class="orders-empty__icon">
            <circle cx="40" cy="40" r="36" stroke="var(--line)" stroke-width="2" stroke-dasharray="6 4"/>
            <path d="M24 30h4l2 22h20l3-18H28" stroke="var(--text-faint)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="34" cy="56" r="2" fill="var(--text-faint)"/>
            <circle cx="46" cy="56" r="2" fill="var(--text-faint)"/>
          </svg>
          <h2>No orders found</h2>
          <p>You haven't placed any match kit orders yet.</p>
          <a href="index.html" class="btn btn--solid">Shop the Drop</a>
        </div>
      `;
      return;
    }

    container.innerHTML = orders.map(order => {
      const dateStr = new Date(order.created_at || new Date()).toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });

      const orderStatus = (order.order_status || "Pending").toLowerCase();
      let badgeClass = "status-badge--pending";
      if (orderStatus === "completed" || orderStatus === "paid" || orderStatus === "confirmed") {
        badgeClass = "status-badge--confirmed";
      } else if (orderStatus === "preparing kit" || orderStatus === "processing" || orderStatus === "preparing") {
        badgeClass = "status-badge--preparing-kit";
      } else if (orderStatus === "packing" || orderStatus === "packed") {
        badgeClass = "status-badge--packing";
      } else if (orderStatus === "shipped") {
        badgeClass = "status-badge--shipped";
      } else if (orderStatus === "delivered") {
        badgeClass = "status-badge--delivered";
      }

      const methodLabel = order.payment_method === "razorpay" ? "💳 Razorpay Online" : "🚚 Cash on Delivery";
      const paymentStatusText = order.payment_status === "PAID" ? "Paid" : (order.payment_status === "COD" ? "To Pay on Delivery" : order.payment_status);

      return `
        <article class="order-card">
          <div class="order-card__header">
            <div class="order-card__meta">
              <span class="order-card__code">${escapeHtml(order.order_code)}</span>
              <span class="order-card__date">Placed on ${dateStr}</span>
            </div>
            <span class="order-card__badge ${badgeClass}">${order.order_status || "Pending"}</span>
          </div>

          <div class="order-card__items">
            ${(order.items || []).map(item => {
              const customInfo = (item.custom_name || item.custom_number)
                ? `<div class="order-item__custom">CUSTOMIZATION: ${escapeHtml(item.custom_name || "—")} #${escapeHtml(item.custom_number || "—")}</div>`
                : "";
              return `
                <div class="order-item-row">
                  <div class="order-item__info">
                    <div class="order-item__name">
                      ${escapeHtml(item.product_name)}
                      <span class="order-item__size">${escapeHtml(item.size)}</span>
                    </div>
                    <span class="order-item__qty">Qty: ${item.quantity} · ₹${item.unit_price.toLocaleString("en-IN")} each</span>
                    ${customInfo}
                  </div>
                  <div class="order-item__pricing">
                    <span class="order-item__total">₹${(item.unit_price * item.quantity).toLocaleString("en-IN")}</span>
                  </div>
                </div>
              `;
            }).join("")}
          </div>

          <div class="order-card__footer">
            <div class="order-card__details" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; width: 100%;">
              <div class="order-detail-group">
                <label>Payment Method</label>
                <span>${methodLabel} (${paymentStatusText})</span>
              </div>
              <div class="order-detail-group">
                <label>Coupon Applied</label>
                <span>${escapeHtml(order.coupon_code || "None")}</span>
              </div>
              <div class="order-detail-group">
                <label>Shipping Fee</label>
                <span>${order.shipping_fee > 0 ? `₹${order.shipping_fee}` : "FREE"}</span>
              </div>
              ${order.shipping_address ? `
              <div class="order-detail-group" style="grid-column: 1 / -1; border-top: 1px solid var(--line); padding-top: 12px; margin-top: 4px; text-align: left;">
                <label>Delivery Address</label>
                <span style="white-space: pre-line; line-height: 1.4; color: var(--text); font-size: 0.9rem;">${escapeHtml(order.shipping_address)}</span>
              </div>
              ` : ''}
            </div>

            <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 12px;">
              <div class="order-card__grand-total">
                <span>Grand Total</span>
                <strong>₹${Math.round(order.total).toLocaleString("en-IN")}</strong>
              </div>
              
              <div class="order-card__actions" style="display: flex; gap: 8px; flex-wrap: wrap;">
                 <a href="${FreakFitsAPI.BASE_URL}/orders/${escapeHtml(order.order_code)}/invoice?token=${encodeURIComponent(FreakFitsAPI.getToken() || '')}" target="_blank" class="btn btn--ghost btn--invoice" style="padding: 10px 18px; font-size:0.85rem; border-color: var(--line); color: var(--text-dim);">Invoice 📄</a>
                <a href="contact.html?reason=shipping&order=${escapeHtml(order.order_code)}" class="btn btn--dark" style="padding: 10px 18px; border: 1px solid var(--border); background:#141712; font-size:0.85rem;">Need Help?</a>
                ${(orderStatus === "pending" || orderStatus === "confirmed") 
                  ? `<button class="btn btn--outline btn--cancel-order" style="padding: 10px 18px; font-size:0.85rem; border-color:var(--pink); color:var(--pink);" data-order-code="${escapeHtml(order.order_code)}">Cancel Order</button>` 
                  : ""}
                ${(orderStatus !== "delivered" && orderStatus !== "cancelled")
                  ? `<a href="track.html?order=${escapeHtml(order.order_code)}&phone=${encodeURIComponent(order.customer_phone || '')}" class="btn btn--solid" style="padding: 10px 18px; font-size:0.85rem;">Track Kit</a>` 
                  : (orderStatus === "delivered" ? `
                     <button class="btn btn--solid btn--rate-review" style="padding: 10px 18px; font-size:0.85rem;" data-order-code="${escapeHtml(order.order_code)}">Rate & Review</button>
                     <a href="returns.html?order=${escapeHtml(order.order_code)}" class="btn btn--outline" style="padding: 10px 18px; font-size:0.85rem; border-color:rgba(255,62,122,0.4); color:var(--pink); margin-left:8px;">Return / Exchange</a>
                    ` : '')
                }
              </div>
            </div>
          </div>
        </article>
      `;
    }).join("");
  }

  // Toast Helper
  let toastTimer = null;
  function showToast(msg) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("is-visible"), 2200);
  }

  function setupCancelButtons(ordersList) {
    const cancelBtns = document.querySelectorAll(".btn--cancel-order");
    cancelBtns.forEach(btn => {
      btn.addEventListener("click", async () => {
        if (!confirm("Are you sure you want to cancel this order? This action cannot be undone.")) return;
        
        btn.disabled = true;
        btn.textContent = "Cancelling...";
        try {
          const orderCode = btn.dataset.orderCode;
          const res = await FreakFitsAPI.cancelOrder(orderCode);
          showToast(res.message || "Order cancelled successfully");
          setTimeout(() => window.location.reload(), 1500);
        } catch (err) {
          showToast("Error: " + err.message);
          btn.disabled = false;
          btn.textContent = "Cancel Order";
        }
      });
    });
  }

  function setupReviewModal(ordersList) {
    console.log("[FreakFits Reviews] setupReviewModal initialized. Orders list:", ordersList);
    const rateBtns = document.querySelectorAll(".btn--rate-review");
    console.log("[FreakFits Reviews] Found rate buttons:", rateBtns.length);
    const modal = document.getElementById("reviewModal");
    const closeBtn = document.getElementById("closeReviewModalBtn");
    const reviewForm = document.getElementById("reviewForm");
    const fileInput = document.getElementById("reviewPhoto");
    const dropzone = document.getElementById("reviewUploadDropzone");
    const previewImg = document.getElementById("reviewPhotoPreview");
    const statusText = document.getElementById("uploadStatusText");
    const starSelector = document.getElementById("starSelector");

    if (!modal) {
      console.error("[FreakFits Reviews] reviewModal element NOT found in DOM!");
      return;
    }

    const resetStars = () => {
      const ratingValInput = document.getElementById("reviewRatingVal");
      if (ratingValInput) ratingValInput.value = 0;
      if (starSelector) {
        starSelector.querySelectorAll(".star-select-item").forEach(s => s.classList.remove("is-selected"));
      }
    };

    // Open Modal
    rateBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        console.log("[FreakFits Reviews] Rate button clicked. Code:", btn.dataset.orderCode);
        const orderCode = btn.dataset.orderCode;
        const order = ordersList.find(o => o.order_code === orderCode);
        if (!order) {
          console.error("[FreakFits Reviews] Order not found in matching list for code:", orderCode);
          return;
        }

        const modalCodeEl = document.getElementById("reviewModalOrderCode");
        if (modalCodeEl) modalCodeEl.textContent = order.order_code;
        
        // Populate select items
        const select = document.getElementById("reviewItemSelect");
        if (select) {
          select.innerHTML = order.items.map(it => 
            `<option value="${it.product_id}">${it.product_name} (${it.size})</option>`
          ).join("");
        }

        // Reset fields
        if (reviewForm) reviewForm.reset();
        if (previewImg) {
          previewImg.src = "";
          previewImg.style.display = "none";
        }
        if (statusText) {
          statusText.textContent = "Click or drag a photo here to upload your look";
        }
        resetStars();

        modal.style.display = "flex";
        console.log("[FreakFits Reviews] Modal display set to flex");
      });
    });

    // Close Modal
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        modal.style.display = "none";
      });
    }
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.style.display = "none";
    });

    // Stars rating click logic
    if (starSelector) {
      const stars = starSelector.querySelectorAll(".star-select-item");
      stars.forEach(star => {
        star.addEventListener("click", () => {
          const val = parseInt(star.dataset.val);
          document.getElementById("reviewRatingVal").value = val;
          stars.forEach(s => {
            const sVal = parseInt(s.dataset.val);
            s.classList.toggle("is-selected", sVal <= val);
          });
        });
      });
    }


    // Photo selection trigger
    if (dropzone && fileInput) {
      dropzone.addEventListener("click", () => fileInput.click());
      
      fileInput.addEventListener("change", (e) => {
        const file = e.target.files[0];
        if (file) {
          statusText.textContent = `✓ Selected: ${file.name}`;
          const reader = new FileReader();
          reader.onload = (event) => {
            previewImg.src = event.target.result;
            previewImg.style.display = "block";
          };
          reader.readAsDataURL(file);
        }
      });
    }

    // Submit review form
    if (reviewForm) {
      reviewForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const submitBtn = document.getElementById("reviewSubmitBtn");
        submitBtn.disabled = true;
        submitBtn.textContent = "Submitting...";

        const productId = document.getElementById("reviewItemSelect").value;
        const rating = parseInt(document.getElementById("reviewRatingVal").value || "0");
        const comment = document.getElementById("reviewComment").value.trim();
        const photoFile = fileInput.files[0];

        if (rating < 1) {
          showToast("⚠️ Please select a rating (1-5 stars)");
          submitBtn.disabled = false;
          submitBtn.textContent = "Submit Review";
          return;
        }

        const user = AuthStore.getCurrentUser();
        const userName = user ? (user.name || user.fullName || "FreakFits Fan") : "FreakFits Fan";

        const formData = new FormData();
        formData.append("product_id", productId);
        formData.append("rating", rating);
        formData.append("comment", comment);
        formData.append("user_name", userName);
        if (photoFile) {
          formData.append("photo", photoFile);
        }

        try {
          const apiBase = window.FREAKFITS_API_URL || "http://127.0.0.1:8000/api";
          const res = await fetch(`${apiBase}/products/reviews`, {
            method: "POST",
            body: formData
          });

          if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.detail || "Failed to submit review");
          }

          showToast("✓ Thank you! Your review was posted successfully.");
          modal.style.display = "none";
        } catch (err) {
          showToast(`❌ Error: ${err.message}`);
        } finally {
          submitBtn.disabled = false;
          submitBtn.textContent = "Submit Review";
        }
      });
    }
  }
})();
