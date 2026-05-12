(function () {
  const drawer = document.querySelector("[data-admin-drawer]");
  const backdrop = document.querySelector("[data-admin-drawer-backdrop]");
  const openButton = document.querySelector("[data-admin-drawer-open]");
  const closeButton = document.querySelector("[data-admin-drawer-close]");

  if (!drawer || !backdrop || !openButton || !closeButton) {
    return;
  }

  function setState(isOpen) {
    drawer.classList.toggle("is-open", isOpen);
    drawer.setAttribute("aria-hidden", String(!isOpen));
    backdrop.hidden = !isOpen;
    openButton.classList.toggle("is-open", isOpen);
    openButton.setAttribute("aria-expanded", String(isOpen));
    document.body.style.overflow = isOpen ? "hidden" : "";
  }

  openButton.addEventListener("click", function () {
    setState(true);
  });

  closeButton.addEventListener("click", function () {
    setState(false);
  });

  backdrop.addEventListener("click", function () {
    setState(false);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      setState(false);
    }
  });

  drawer.querySelectorAll("a").forEach(function (link) {
    link.addEventListener("click", function () {
      setState(false);
    });
  });
})();
