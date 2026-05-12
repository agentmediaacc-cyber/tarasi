(function () {
  const drawer = document.querySelector("[data-profile-drawer]");
  const backdrop = document.querySelector("[data-profile-drawer-backdrop]");
  const openButton = document.querySelector("[data-profile-drawer-open]");
  const closeButton = document.querySelector("[data-profile-drawer-close]");

  if (!drawer || !backdrop || !openButton || !closeButton) {
    return;
  }

  function setDrawerState(isOpen) {
    drawer.classList.toggle("is-open", isOpen);
    drawer.setAttribute("aria-hidden", String(!isOpen));
    backdrop.hidden = !isOpen;
    openButton.classList.toggle("is-open", isOpen);
    openButton.setAttribute("aria-expanded", String(isOpen));
    document.body.style.overflow = isOpen ? "hidden" : "";
  }

  openButton.addEventListener("click", function () {
    setDrawerState(true);
  });

  closeButton.addEventListener("click", function () {
    setDrawerState(false);
  });

  backdrop.addEventListener("click", function () {
    setDrawerState(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      setDrawerState(false);
    }
  });

  drawer.querySelectorAll("a").forEach(function (link) {
    link.addEventListener("click", function () {
      setDrawerState(false);
    });
  });

  let touchStartX = 0;
  document.addEventListener("touchstart", function (event) {
    touchStartX = event.changedTouches[0].clientX;
  }, { passive: true });

  document.addEventListener("touchend", function (event) {
    const touchEndX = event.changedTouches[0].clientX;
    if (touchStartX < 32 && touchEndX - touchStartX > 72) {
      setDrawerState(true);
    }
    if (drawer.classList.contains("is-open") && touchStartX - touchEndX > 72) {
      setDrawerState(false);
    }
  }, { passive: true });
})();
