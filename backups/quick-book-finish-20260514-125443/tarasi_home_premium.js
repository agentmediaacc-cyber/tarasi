window.TarasiRealQuickBook = (() => {
  let lastQuote = null;

  const $ = id => document.getElementById(id);
  const val = id => ($(id)?.value || "").trim();

  function setText(id, text){ const el=$(id); if(el) el.textContent=text; }

  async function confirmPlace(text, targetId){
    if(!text){ setText(targetId, "Waiting..."); return null; }
    try{
      const r = await fetch("/api/map/search", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({query:text})
      });
      const j = await r.json();
      const place = j.result || j.place || (j.results && j.results[0]) || j;
      if(place && (place.display_name || place.name)){
        setText(targetId, "✓ Map confirmed: " + (place.display_name || place.name).slice(0,80));
        return place;
      }
      setText(targetId, "⚠ Not confirmed on map. Price will use nearest zone.");
      return null;
    }catch(e){
      setText(targetId, "⚠ Map check failed. Price will use nearest zone.");
      return null;
    }
  }

  function payload(save=false){
    return {
      pickup_text: val("rqbPickup"),
      dropoff_text: val("rqbDropoff"),
      service_type: val("rqbService") || "once_off",
      vehicle_type: val("rqbVehicle") || "sedan",
      pickup_date: val("rqbDate"),
      pickup_time: val("rqbTime"),
      passengers: Number(val("rqbPeople") || 1),
      luggage_count: Number(val("rqbLuggage") || 0),
      notes: val("rqbNote"),
      save
    };
  }

  async function estimate(save=false){
    const p = payload(save);
    if(!p.pickup_text) return alert("Type pickup street or place.");
    if(!p.dropoff_text) return alert("Type drop-off street or place.");

    document.body.classList.add("rqb-loading");

    await confirmPlace(p.pickup_text, "rqbPickupConfirm");
    await confirmPlace(p.dropoff_text, "rqbDropoffConfirm");

    try{
      const r = await fetch("/api/quote/estimate", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify(p)
      });
      const j = await r.json();
      if(!r.ok || j.ok === false) throw new Error(j.message || "Quote failed");

      lastQuote = j.quote || j;
      show(lastQuote);
      return lastQuote;
    }catch(e){
      alert(e.message || "Could not calculate quote.");
      return null;
    }finally{
      document.body.classList.remove("rqb-loading");
    }
  }

  function show(q){
    $("rqbResult")?.classList.add("show");
    const price = Number(q.final_price || q.amount || q.price || 0);
    setText("rqbPrice", `N$${price.toFixed(2)}`);
    setText("rqbKm", `${Number(q.distance_km || 0).toFixed(2)} km`);
    setText("rqbEta", `${Number(q.duration_minutes || 0)} min`);
    setText("rqbConfidence", q.price_confidence || q.confidence || "medium");
    setText("rqbZones", `Zones: ${q.pickup_zone || "nearest zone"} → ${q.dropoff_zone || "nearest zone"}`);
    setText("rqbQuoteNo", q.quote_number ? `Professional quote proof: ${q.quote_number}` : "Proceed to booking to save quote proof.");
  }

  async function book(){
    const q = lastQuote || await estimate(true);
    if(!q) return;
    const p = payload(true);
    const params = new URLSearchParams({
      pickup: p.pickup_text, dropoff: p.dropoff_text,
      service_type: p.service_type, vehicle_type: p.vehicle_type,
      pickup_date: p.pickup_date, pickup_time: p.pickup_time,
      passengers: String(p.passengers), luggage_count: String(p.luggage_count),
      notes: p.notes, quote_number: q.quote_number || "",
      estimated_price: String(q.final_price || q.amount || "")
    });
    location.href = `/book/once-off?${params.toString()}`;
  }

  document.addEventListener("DOMContentLoaded", () => {
    if($("rqbDate") && !$("rqbDate").value) $("rqbDate").value = new Date().toISOString().slice(0,10);
  });

  return {estimate, book};
})();
