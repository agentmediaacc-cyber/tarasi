const drawer = document.querySelector("[data-mobile-drawer]");
const drawerOpen = document.querySelector("[data-menu-open]");
const drawerClose = document.querySelector("[data-menu-close]");
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function setDrawer(open) {
  if (!drawer) return;
  drawer.classList.toggle("open", open);
  document.body.classList.toggle("menu-open", open);
  drawer.setAttribute("aria-hidden", open ? "false" : "true");
  if (drawerOpen) drawerOpen.setAttribute("aria-expanded", open ? "true" : "false");
}

if (drawerOpen) drawerOpen.addEventListener("click", () => setDrawer(true));
if (drawerClose) drawerClose.addEventListener("click", () => setDrawer(false));

if (drawer) {
  drawer.addEventListener("click", (event) => {
    if (event.target === drawer) setDrawer(false);
  });
  drawer.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => setDrawer(false));
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    setDrawer(false);
  }
});

function initHeroRotator() {
  if (prefersReducedMotion) return;
  const words = Array.from(document.querySelectorAll(".hero-rotator span"));
  if (words.length < 2) return;
  let activeIndex = 0;
  window.setInterval(() => {
    words[activeIndex].classList.remove("is-active");
    activeIndex = (activeIndex + 1) % words.length;
    words[activeIndex].classList.add("is-active");
  }, 2200);
}

function initDestinationSlideshow() {
  const root = document.querySelector("[data-destination-slideshow]");
  if (!root) return;
  const slides = Array.from(root.querySelectorAll("[data-destination-slide]"));
  const dots = Array.from(root.querySelectorAll("[data-slide-dot]"));
  const prev = root.querySelector("[data-slide-prev]");
  const next = root.querySelector("[data-slide-next]");
  if (slides.length < 2 || root.hasAttribute("data-static")) return;

  let activeIndex = slides.findIndex((slide) => slide.classList.contains("is-active"));
  if (activeIndex < 0) activeIndex = 0;
  let intervalId = null;
  let startX = 0;

  function setSlide(index) {
    activeIndex = (index + slides.length) % slides.length;
    slides.forEach((slide, slideIndex) => {
      const isActive = slideIndex === activeIndex;
      slide.classList.toggle("is-active", isActive);
      slide.setAttribute("aria-hidden", isActive ? "false" : "true");
    });
    dots.forEach((dot, dotIndex) => {
      const isActive = dotIndex === activeIndex;
      dot.classList.toggle("is-active", isActive);
      dot.setAttribute("aria-selected", isActive ? "true" : "false");
    });
  }

  function restartAutoSlide() {
    if (prefersReducedMotion) return;
    if (intervalId) window.clearInterval(intervalId);
    intervalId = window.setInterval(() => setSlide(activeIndex + 1), 4200);
  }

  if (prev) prev.addEventListener("click", () => { setSlide(activeIndex - 1); restartAutoSlide(); });
  if (next) next.addEventListener("click", () => { setSlide(activeIndex + 1); restartAutoSlide(); });
  dots.forEach((dot, index) => {
    dot.addEventListener("click", () => {
      setSlide(index);
      restartAutoSlide();
    });
  });

  root.addEventListener("touchstart", (event) => {
    startX = event.changedTouches[0].clientX;
  }, { passive: true });

  root.addEventListener("touchend", (event) => {
    const delta = event.changedTouches[0].clientX - startX;
    if (Math.abs(delta) < 40) return;
    if (delta < 0) {
      setSlide(activeIndex + 1);
    } else {
      setSlide(activeIndex - 1);
    }
    restartAutoSlide();
  }, { passive: true });

  if (!prefersReducedMotion) {
    root.addEventListener("pointermove", (event) => {
      const rect = root.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width - 0.5) * 10;
      const y = ((event.clientY - rect.top) / rect.height - 0.5) * 10;
      slides.forEach((slide, index) => {
        if (index === activeIndex) {
          slide.style.setProperty("--parallax-x", `${x}px`);
          slide.style.setProperty("--parallax-y", `${y}px`);
        }
      });
    });
    root.addEventListener("pointerleave", () => {
      slides.forEach((slide) => {
        slide.style.setProperty("--parallax-x", "0px");
        slide.style.setProperty("--parallax-y", "0px");
      });
    });
  }

  restartAutoSlide();
}

function initRevealObserver() {
  if (prefersReducedMotion || !("IntersectionObserver" in window)) return;
  const targets = document.querySelectorAll(".card, .panel, .route-preview-card, .service-card-live, .fleet-preview-card, .tour-live-card");
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  targets.forEach((target) => {
    target.classList.add("reveal-ready");
    observer.observe(target);
  });
}

function addRipple(event, target) {
  if (prefersReducedMotion) return;
  const ripple = document.createElement("span");
  ripple.className = "tap-ripple";
  const rect = target.getBoundingClientRect();
  ripple.style.left = `${event.clientX - rect.left}px`;
  ripple.style.top = `${event.clientY - rect.top}px`;
  target.appendChild(ripple);
  window.setTimeout(() => ripple.remove(), 500);
}

function initRipples() {
  document.addEventListener("pointerdown", (event) => {
    const target = event.target.closest(".btn, .service-card-live, .route-preview-card, .tour-live-card, .fleet-preview-card, .live-route-row");
    if (!target) return;
    addRipple(event, target);
  });
}

function ensureBookingOverlay() {
  let overlay = document.querySelector("[data-booking-overlay]");
  if (overlay) return overlay;
  overlay = document.createElement("div");
  overlay.className = "booking-launch-overlay booking-loader";
  overlay.hidden = true;
  overlay.setAttribute("aria-hidden", "true");
  overlay.setAttribute("data-booking-overlay", "");
  overlay.innerHTML = `
    <div class="booking-launch-loader" role="status" aria-live="polite">
      <div class="loader-road">
        <div class="loader-car">▸</div>
      </div>
      <strong>Preparing your Tarasi booking…</strong>
    </div>
  `;
  document.body.appendChild(overlay);
  return overlay;
}

function resetBookingOverlay() {
  const overlay = document.querySelector("[data-booking-overlay]");
  if (!overlay) return;
  overlay.classList.remove("is-active");
  overlay.hidden = true;
  overlay.setAttribute("aria-hidden", "true");
  document.body.classList.remove("booking-transition-active");
}

function shouldAnimateBookingLink(link) {
  const href = link.getAttribute("href") || "";
  return link.classList.contains("booking-launch-link") || /^\/book(\/|$)/.test(href);
}

function initBookingLaunchLoader() {
  resetBookingOverlay();
  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link || !shouldAnimateBookingLink(link) || prefersReducedMotion) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (link.target && link.target !== "_self") return;
    const href = link.getAttribute("href");
    if (!href || href.startsWith("#") || href.startsWith("http")) return;
    event.preventDefault();
    const overlay = ensureBookingOverlay();
    overlay.hidden = false;
    overlay.classList.add("is-active");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("booking-transition-active");
    window.setTimeout(() => {
      window.location.href = href;
    }, 420);
  });

  window.addEventListener("pageshow", () => {
    resetBookingOverlay();
  });
}

function initPrefetchLinks() {
  const prefetched = new Set();
  function prefetch(href) {
    if (!href || prefetched.has(href) || href.startsWith("http") || href.startsWith("#")) return;
    prefetched.add(href);
    fetch(href, { method: "GET", credentials: "same-origin" }).catch(() => {});
  }

  document.querySelectorAll("a[href]").forEach((link) => {
    const href = link.getAttribute("href") || "";
    if (!/^\/(book|tours|tour|routes|fleet)/.test(href)) return;
    link.addEventListener("mouseenter", () => prefetch(href), { passive: true, once: true });
    link.addEventListener("touchstart", () => prefetch(href), { passive: true, once: true });
    link.addEventListener("focus", () => prefetch(href), { passive: true, once: true });
  });
}

function initRevealObserver() {
  const options = {
    threshold: 0.1,
    rootMargin: "0px 0px -50px 0px"
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      }
    });
  }, options);

  document.querySelectorAll(".section, .card, .panel, .service-card-live, .category-glow-card").forEach((el) => {
    el.classList.add("reveal-on-scroll");
    observer.observe(el);
  });
}

function initImageHints() {
  document.querySelectorAll("img").forEach((image, index) => {
    if (!image.hasAttribute("loading")) {
      image.setAttribute("loading", index < 2 ? "eager" : "lazy");
    }
    if (!image.hasAttribute("decoding")) {
      image.setAttribute("decoding", "async");
    }
  });
}

const oauthBridge = document.querySelector("[data-oauth-bridge]");
if (oauthBridge) {
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const accessToken = hash.get("access_token");
  const refreshToken = hash.get("refresh_token");
  const provider = hash.get("provider_token") ? "oauth" : "oauth";
  const output = document.querySelector("[data-oauth-message]");
  if (accessToken) {
    fetch("/auth/callback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        access_token: accessToken,
        refresh_token: refreshToken,
        provider
      })
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.ok && data.redirect) {
          window.location.href = data.redirect;
          return;
        }
        if (output) output.textContent = data.message || "OAuth login could not be completed.";
      })
      .catch(() => {
        if (output) output.textContent = "OAuth callback failed. Please try again.";
      });
  }
}

initHeroRotator();
initDestinationSlideshow();
initRevealObserver();
initRipples();
initBookingLaunchLoader();
initImageHints();
initPrefetchLinks();
