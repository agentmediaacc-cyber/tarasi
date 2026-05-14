window.TarasiQuickBook = (() => {
  const state = { pickup:null, dropoff:null, quote:null };
  const $ = id => document.getElementById(id);
  const val = id => ($(id)?.value || "").trim();
  const set = (id, txt) => { const el=$(id); if(el) el.textContent = txt; };

  async function post(url, payload){
    const res = await fetch(url, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
    let data = {};
    try { data = await res.json(); } catch(e) {}
    if(!res.ok) throw new Error(data.message || "Request failed");
    return data;
  }

  function normalizeResults(data){
    const raw = data.results || data.places || data.items || data.result || data.place || data;
    const arr = Array.isArray(raw) ? raw : raw ? [raw] : [];
    return arr.filter(x => x && (x.display_name || x.name || x.address_text)).slice(0,6);
  }

  function renderResults(kind, items){
    const box = $(kind === "pickup" ? "qbPickupResults" : "qbDropoffResults");
    if(!box) return;
    if(!items.length){ box.classList.remove("show"); box.innerHTML=""; return; }
    box.innerHTML = items.map((x,i) => {
      const name = x.display_name || x.name || x.address_text || "Unknown place";
      const area = x.suburb_area || x.suburb || x.city || "Namibia";
      return `<div class="tarasi-qb-option" data-kind="${kind}" data-index="${i}"><b>${escapeHtml(name)}</b><span>${escapeHtml(area)}</span></div>`;
    }).join("");
    box._items = items;
    box.classList.add("show");
  }

  function escapeHtml(v){ return String(v||"").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m])); }

  async function search(kind){
    const inputId = kind === "pickup" ? "qbPickup" : "qbDropoff";
    const statusId = kind === "pickup" ? "qbPickupStatus" : "qbDropoffStatus";
    const q = val(inputId);
    if(q.length < 3){ set(statusId, "Type at least 3 letters."); return; }
    set(statusId, "Searching map...");
    try{
      const data = await post("/api/map/search", {query:q, q});
      const items = normalizeResults(data);
      renderResults(kind, items);
      set(statusId, items.length ? "Choose the correct map result." : "No exact map result. Try adding suburb/city.");
    }catch(e){
      set(statusId, "Map search failed. Try suburb + street.");
    }
  }

  function choose(kind, place){
    const inputId = kind === "pickup" ? "qbPickup" : "qbDropoff";
    const statusId = kind === "pickup" ? "qbPickupStatus" : "qbDropoffStatus";
    const boxId = kind === "pickup" ? "qbPickupResults" : "qbDropoffResults";
    const name = place.display_name || place.name || place.address_text || val(inputId);
    const lat = Number(place.lat || place.latitude || 0);
    const lng = Number(place.lng || place.lon || place.longitude || 0);
    state[kind] = { text:name, lat, lng, raw:place };
    $(inputId).value = name;
    $(boxId)?.classList.remove("show");
    set(statusId, `✓ Confirmed: ${name.slice(0,90)}`);
  }

  async function useCurrentLocation(){
    if(!navigator.geolocation) return alert("Your browser does not support location.");
    set("qbPickupStatus", "Allow location permission...");
    navigator.geolocation.getCurrentPosition(async pos => {
      const lat = pos.coords.latitude, lng = pos.coords.longitude;
      set("qbPickupStatus", "Finding your current street...");
      try{
        const data = await post("/api/map/reverse", {lat, lng});
        const place = data.result || data.place;
        if(place){ choose("pickup", {...place, lat: place.lat || lat, lng: place.lng || lng}); }
        else { set("qbPickupStatus", "Could not confirm current street. Type pickup manually."); }
      }catch(e){ set("qbPickupStatus", "Current location failed. Type pickup manually."); }
    }, () => set("qbPickupStatus", "Location permission denied. Type pickup manually."), {enableHighAccuracy:true, timeout:10000});
  }

  function payload(save=false){
    return {
      pickup_text: state.pickup?.text || val("qbPickup"),
      dropoff_text: state.dropoff?.text || val("qbDropoff"),
      pickup_lat: state.pickup?.lat,
      pickup_lng: state.pickup?.lng,
      dropoff_lat: state.dropoff?.lat,
      dropoff_lng: state.dropoff?.lng,
      service_type: val("qbService") || "once_off",
      vehicle_type: val("qbVehicle") || "sedan",
      pickup_date: val("qbDate"),
      pickup_time: val("qbTime"),
      passengers: Number(val("qbPeople") || 1),
      luggage_count: Number(val("qbLuggage") || 0),
      notes: val("qbNote"),
      save
    };
  }

  async function estimate(save=false){
    if(!state.pickup) return alert("Please search and confirm pickup street first.");
    if(!state.dropoff) return alert("Please search and confirm drop-off street first.");
    const root = $("tarasiQuickBook"); root?.classList.add("tarasi-qb-loading");
    try{
      const data = await post("/api/quote/estimate", payload(save));
      const quote = data.quote || data;
      state.quote = quote;
      showQuote(quote);
      saveRecent();
      return quote;
    }catch(e){ alert(e.message || "Could not calculate quotation."); return null; }
    finally{ root?.classList.remove("tarasi-qb-loading"); }
  }

  function showQuote(q){
    $("qbResult")?.classList.add("show");
    const price = Number(q.final_price || q.amount || q.price || 0);
    set("qbPrice", `N$${price.toFixed(2)}`);
    set("qbKm", `${Number(q.distance_km || 0).toFixed(2)} km`);
    set("qbEta", `${Number(q.duration_minutes || 0)} min`);
    set("qbVehicleOut", val("qbVehicle") || q.vehicle_type || "sedan");
    set("qbConfidence", q.price_confidence || q.confidence || "medium");
    set("qbConfirmed", `Pickup: ${state.pickup?.text || q.pickup_text} → Drop-off: ${state.dropoff?.text || q.dropoff_text}`);
    set("qbQuoteNo", q.quote_number ? `Quotation proof: ${q.quote_number}` : "Proceed to booking to save quotation proof.");
  }

  async function proceed(){
    const q = state.quote?.quote_number ? state.quote : await estimate(true);
    if(!q) return;
    const p = payload(true);
    const params = new URLSearchParams({
      pickup:p.pickup_text, dropoff:p.dropoff_text,
      pickup_lat:String(p.pickup_lat||""), pickup_lng:String(p.pickup_lng||""),
      dropoff_lat:String(p.dropoff_lat||""), dropoff_lng:String(p.dropoff_lng||""),
      quote_number:q.quote_number || "", estimated_price:String(q.final_price || q.amount || ""),
      service_type:p.service_type, vehicle_type:p.vehicle_type,
      pickup_date:p.pickup_date, pickup_time:p.pickup_time,
      passengers:String(p.passengers), luggage_count:String(p.luggage_count), notes:p.notes
    });
    location.href = `/book/once-off?${params.toString()}`;
  }

  function saveRecent(){
    if(!state.pickup || !state.dropoff) return;
    const item = {pickup:state.pickup, dropoff:state.dropoff, at:Date.now()};
    const list = JSON.parse(localStorage.getItem("tarasi_recent_routes") || "[]").filter(x => x.pickup?.text !== item.pickup.text || x.dropoff?.text !== item.dropoff.text);
    list.unshift(item);
    localStorage.setItem("tarasi_recent_routes", JSON.stringify(list.slice(0,5)));
    renderRecent();
  }

  function renderRecent(){
    const box = $("qbRecentRoutes"); if(!box) return;
    const list = JSON.parse(localStorage.getItem("tarasi_recent_routes") || "[]");
    box.innerHTML = list.map((r,i)=>`<button type="button" class="tarasi-qb-chip" data-recent="${i}">${escapeHtml((r.pickup?.text||"Pickup").split(",")[0])} → ${escapeHtml((r.dropoff?.text||"Drop-off").split(",")[0])}</button>`).join("");
    box.querySelectorAll("[data-recent]").forEach(btn => btn.onclick = () => {
      const r = list[Number(btn.dataset.recent)];
      if(r){ state.pickup=r.pickup; state.dropoff=r.dropoff; $("qbPickup").value=r.pickup.text; $("qbDropoff").value=r.dropoff.text; set("qbPickupStatus","✓ Recent pickup selected"); set("qbDropoffStatus","✓ Recent drop-off selected"); }
    });
  }

  let timers = {};
  document.addEventListener("input", e => {
    if(e.target?.id === "qbPickup" || e.target?.id === "qbDropoff"){
      const kind = e.target.id === "qbPickup" ? "pickup" : "dropoff";
      state[kind] = null;
      clearTimeout(timers[kind]);
      timers[kind] = setTimeout(()=>search(kind), 450);
    }
  });

  document.addEventListener("click", e => {
    const opt = e.target.closest(".tarasi-qb-option");
    if(opt){
      const kind = opt.dataset.kind;
      const box = $(kind === "pickup" ? "qbPickupResults" : "qbDropoffResults");
      const item = box?._items?.[Number(opt.dataset.index)];
      if(item) choose(kind, item);
    }else{
      $("qbPickupResults")?.classList.remove("show");
      $("qbDropoffResults")?.classList.remove("show");
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    if($("qbDate") && !$("qbDate").value) $("qbDate").value = new Date().toISOString().slice(0,10);
    renderRecent();
  });

  return {search, choose, useCurrentLocation, estimate, proceed};
})();
