(function () {
  const drawer = document.querySelector("[data-admin-drawer]");
  const backdrop = document.querySelector("[data-admin-drawer-backdrop]");
  const openButton = document.querySelector("[data-admin-drawer-open]");
  const closeButton = document.querySelector("[data-admin-drawer-close]");

  if (drawer && backdrop && openButton && closeButton) {
    function setState(isOpen) {
      drawer.classList.toggle("is-open", isOpen);
      drawer.setAttribute("aria-hidden", String(!isOpen));
      backdrop.hidden = !isOpen;
      openButton.classList.toggle("is-open", isOpen);
      openButton.setAttribute("aria-expanded", String(isOpen));
      document.body.style.overflow = isOpen ? "hidden" : "";
    }

    openButton.addEventListener("click", () => setState(true));
    closeButton.addEventListener("click", () => setState(false));
    backdrop.addEventListener("click", () => setState(false));

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setState(false);
    });

    drawer.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => setState(false));
    });
  }

  // PRICING SIMULATOR
  const simKm = document.getElementById("sim-km");
  const simMultiplier = document.getElementById("sim-multiplier");
  const simTotal = document.getElementById("sim-total");

  if (simKm && simMultiplier && simTotal) {
    function updateSim() {
      // Get values from the Configuration form if possible, or defaults
      const baseFare = parseFloat(document.querySelector('input[name="base_fare"]')?.value || 50);
      const perKm = parseFloat(document.querySelector('input[name="price_per_km"]')?.value || 12.5);
      const minFare = parseFloat(document.querySelector('input[name="min_fare"]')?.value || 80);
      
      const km = parseFloat(simKm.value || 0);
      const mult = parseFloat(simMultiplier.value || 1);
      
      let total = (baseFare + (km * perKm)) * mult;
      if (total < minFare) total = minFare;
      
      simTotal.textContent = `N$${total.toFixed(2)}`;
    }

    simKm.addEventListener("input", updateSim);
    simMultiplier.addEventListener("change", updateSim);
    
    // Also listen to changes in the config inputs to keep simulator "live"
    document.querySelectorAll('.pricing-card input').forEach(input => {
      input.addEventListener('input', updateSim);
    });
  }
})();
