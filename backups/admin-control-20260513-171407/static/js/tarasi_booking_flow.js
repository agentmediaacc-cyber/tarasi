(function () {
  const form = document.querySelector("[data-booking-flow]");
  if (!form) return;

  const estimateBtn = form.querySelector("[data-estimate-price]");
  const createBtn = form.querySelector("[data-create-booking]");
  const pricingCard = form.querySelector("[data-pricing-card]");
  const confirmationCard = form.querySelector("[data-booking-confirmation]");
  const quoteNumberInput = form.querySelector("[data-created-quote-number]");
  const finalPriceInput = form.querySelector("[data-created-final-price]");
  const trackLink = form.querySelector("[data-track-booking-link]");
  const invoiceLink = form.querySelector("[data-booking-invoice-link]");
  const proofButton = form.querySelector("[data-submit-payment-proof]");
  const invoiceButton = form.querySelector("[data-create-booking-invoice]");
  const proofText = form.querySelector("[data-payment-proof-text]");
  const luggageLegacy = form.querySelector("#luggage");

  let lastEstimate = null;
  let lastBooking = null;

  function money(value) {
    return `N$${Number(value || 0).toFixed(2)}`;
  }

  function setText(selector, value) {
    const node = form.querySelector(selector);
    if (node) node.textContent = value;
  }

  function getPayload() {
    const pickup = form.querySelector("[data-pricing-pickup]")?.value?.trim() || "";
    const dropoff = form.querySelector("[data-pricing-dropoff]")?.value?.trim() || "";
    const vehicleType = form.querySelector("[data-pricing-vehicle]")?.value || "sedan";
    const passengers = Number(form.querySelector("[data-pricing-passengers]")?.value || 1);
    const luggageCount = Number(form.querySelector("[data-pricing-luggage]")?.value || 0);
    const serviceType = form.querySelector("[data-pricing-service-type]")?.value || "town";
    const travelTime = form.querySelector("[data-pricing-time]")?.value || "";
    if (luggageLegacy) {
      luggageLegacy.value = `${luggageCount} bag${luggageCount === 1 ? "" : "s"}`;
    }
    return {
      pickup,
      dropoff,
      vehicle_type: vehicleType,
      passengers,
      luggage_count: luggageCount,
      service_type: serviceType,
      travel_time: travelTime
    };
  }

  function validateRoute(payload) {
    if (!payload.pickup || !payload.dropoff) {
      window.alert("Please enter both pickup and drop-off before estimating.");
      return false;
    }
    return true;
  }

  function renderEstimate(data) {
    lastEstimate = data;
    pricingCard.classList.remove("is-hidden");
    createBtn.disabled = false;
    quoteNumberInput.value = data.quote_number || "";
    finalPriceInput.value = data.final_price || "";

    setText("[data-pricing-confidence]", data.confidence || "estimate");
    setText("[data-summary-pickup]", data.pickup || "-");
    setText("[data-summary-dropoff]", data.dropoff || "-");
    setText("[data-summary-vehicle]", String(data.vehicle_type || "").toUpperCase());
    setText("[data-summary-distance]", `${data.distance_km} km`);
    setText("[data-summary-duration]", `${data.duration_minutes} min`);
    setText("[data-summary-zone]", `${data.pickup_zone || "-"} to ${data.dropoff_zone || "-"}`);
    setText("[data-summary-price]", money(data.final_price));

    const breakdown = data.price_breakdown || {};
    setText("[data-breakdown-base]", money(breakdown.base_fare));
    setText("[data-breakdown-distance]", money(breakdown.distance_fee));
    setText("[data-breakdown-zone]", money(breakdown.zone_fee));
    setText("[data-breakdown-waiting]", money(breakdown.waiting_fee));
    setText("[data-breakdown-luggage]", money(breakdown.luggage_fee));
    setText("[data-breakdown-service]", money((breakdown.night_fee || 0) + (breakdown.service_fee || 0)));

    const notes = Array.isArray(data.notes) ? data.notes.join(" ") : (data.notes || "Pricing notes not available.");
    setText("[data-pricing-notes]", notes);

    const suggestions = form.querySelector("[data-pricing-suggestions]");
    if (suggestions) {
      suggestions.innerHTML = "";
      (data.suggestions || []).forEach((item) => {
        const chip = document.createElement("span");
        chip.className = "tarasi-note-chip";
        chip.textContent = item;
        suggestions.appendChild(chip);
      });
    }
  }

  async function estimatePrice() {
    const payload = getPayload();
    if (!validateRoute(payload)) return;
    estimateBtn.disabled = true;
    estimateBtn.textContent = "Estimating…";
    try {
      const res = await fetch("/api/pricing/estimate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) {
        window.alert(data.error || "Estimate failed.");
        return;
      }
      renderEstimate(data);
      pricingCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (_error) {
      window.alert("Pricing estimate is not responding right now.");
    } finally {
      estimateBtn.disabled = false;
      estimateBtn.textContent = "Estimate Price";
    }
  }

  async function createBookingFromEstimate() {
    if (!lastEstimate?.quote_number) {
      window.alert("Estimate the trip first before creating the booking.");
      return;
    }
    createBtn.disabled = true;
    createBtn.textContent = "Creating booking…";
    try {
      const bookingPayload = {
        quote_number: lastEstimate.quote_number,
        client_name: form.querySelector("#full_name")?.value?.trim() || "Guest customer",
        client_phone: form.querySelector("#phone")?.value?.trim() || "",
        pickup: form.querySelector("[data-pricing-pickup]")?.value?.trim() || "",
        dropoff: form.querySelector("[data-pricing-dropoff]")?.value?.trim() || "",
        travel_date: form.querySelector("[data-pricing-date]")?.value || "",
        travel_time: form.querySelector("[data-pricing-time]")?.value || "",
        vehicle_type: form.querySelector("[data-pricing-vehicle]")?.value || "sedan",
        passengers: Number(form.querySelector("[data-pricing-passengers]")?.value || 1),
        luggage_count: Number(form.querySelector("[data-pricing-luggage]")?.value || 0),
        final_price: lastEstimate.final_price
      };
      const res = await fetch("/api/bookings/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(bookingPayload)
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        window.alert(data.error || "Booking could not be created.");
        return;
      }
      const booking = data.booking || {};
      lastBooking = booking;
      confirmationCard.classList.remove("is-hidden");
      setText("[data-booking-number]", booking.booking_number || "Booking created");
      setText("[data-booking-price]", `Final price: ${money(booking.final_price)}`);
      setText("[data-booking-status]", `Status: ${booking.status || "pending"}`);
      setText("[data-booking-payment]", `Payment status: ${booking.payment_status || "unpaid"}`);
      if (trackLink && booking.booking_number) {
        trackLink.href = `/track/${booking.booking_number}`;
      }
      localStorage.setItem("tarasi_last_booking_number", booking.booking_number || "");
      confirmationCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (_error) {
      window.alert("Booking creation is not responding right now.");
    } finally {
      createBtn.disabled = false;
      createBtn.textContent = "Create Booking";
    }
  }

  async function submitPaymentProof() {
    if (!lastBooking?.booking_number) {
      window.alert("Create the booking first.");
      return;
    }
    const payload = {
      proof_text: proofText?.value?.trim() || "Customer marked payment as submitted."
    };
    try {
      const res = await fetch(`/api/bookings/${lastBooking.booking_number}/payment-proof`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        window.alert(data.error || "Payment proof could not be saved.");
        return;
      }
      setText("[data-booking-payment]", "Payment status: pending_verification");
    } catch (_error) {
      window.alert("Payment proof endpoint is not responding right now.");
    }
  }

  async function createInvoice() {
    if (!lastBooking?.booking_number) {
      window.alert("Create the booking first.");
      return;
    }
    try {
      const res = await fetch(`/api/bookings/${lastBooking.booking_number}/invoice`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        window.alert(data.error || "Invoice could not be created.");
        return;
      }
      if (invoiceLink) {
        invoiceLink.href = data.invoice_url || "#";
        invoiceLink.classList.remove("is-hidden");
        invoiceLink.textContent = `Open invoice ${data.invoice_number}`;
      }
    } catch (_error) {
      window.alert("Invoice endpoint is not responding right now.");
    }
  }

  estimateBtn?.addEventListener("click", estimatePrice);
  createBtn?.addEventListener("click", createBookingFromEstimate);
  proofButton?.addEventListener("click", submitPaymentProof);
  invoiceButton?.addEventListener("click", createInvoice);
})();
