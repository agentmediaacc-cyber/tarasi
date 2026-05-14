const live = [
  "Live route estimate ready for Windhoek pickups",
  "Airport pricing uses current Tarasi zone rules",
  "Quick quote checks map distance before pricing",
  "Windhoek suburb matching is active",
  "Premium route estimate available in seconds"
];

let i = 0;
setInterval(() => {
  const el = document.querySelector("[data-live]");
  if (el) {
    el.textContent = live[i % live.length];
    i += 1;
  }
}, 2600);

(function () {
  const form = document.querySelector("[data-home-quote-form]");
  if (!form) return;

  const pickupInput = form.querySelector("[data-home-quote-pickup]");
  const dropoffInput = form.querySelector("[data-home-quote-dropoff]");
  const passengersInput = form.querySelector("[data-home-quote-passengers]");
  const result = form.querySelector("[data-home-quote-result]");
  const priceNode = form.querySelector("[data-home-quote-price]");
  const distanceNode = form.querySelector("[data-home-quote-distance]");
  const confidenceNode = form.querySelector("[data-home-quote-confidence]");

  function money(value) {
    return `N$${Number(value || 0).toFixed(2)}`;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const pickup = pickupInput?.value?.trim() || "";
    const dropoff = dropoffInput?.value?.trim() || "";
    if (!pickup || !dropoff) {
      window.location.href = `/book/once-off?pickup=${encodeURIComponent(pickup)}&dropoff=${encodeURIComponent(dropoff)}`;
      return;
    }
    try {
      const response = await fetch("/api/quote/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pickup_text: pickup,
          dropoff_text: dropoff,
          passengers: Number(passengersInput?.value || 1),
          service_type: "town",
          vehicle_type: "sedan",
          save: false
        })
      });
      const data = await response.json();
      if (response.ok && data.final_price) {
        if (result) result.hidden = false;
        if (priceNode) priceNode.textContent = money(data.final_price);
        if (distanceNode) distanceNode.textContent = `${Number(data.distance_km || 0).toFixed(1)} km`;
        if (confidenceNode) confidenceNode.textContent = String(data.confidence || "low").toUpperCase();
      }
    } catch (_error) {
      // Keep homepage flow moving even if the estimator is temporarily unavailable.
    }
    window.location.href = `/book/once-off?pickup=${encodeURIComponent(pickup)}&dropoff=${encodeURIComponent(dropoff)}&passengers=${encodeURIComponent(passengersInput?.value || "1")}`;
  });
})();
