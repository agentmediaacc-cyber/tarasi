const buttons = document.querySelectorAll(".control-strip button");
const cards = document.querySelectorAll(".route-card");

buttons.forEach((btn) => {
  btn.addEventListener("click", () => {
    buttons.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    const filter = btn.dataset.filter;

    cards.forEach((card) => {
      const category = (card.dataset.category || "").toLowerCase();
      card.style.display = filter === "all" || category.includes(filter) ? "" : "none";
    });
  });
});

let tarasiMap;
let streetLayer;
let satelliteLayer;
let routeLayers = [];
let markerLayers = [];

function validCoord(lat, lng) {
  return lat !== null && lng !== null && lat !== "" && lng !== "" && !isNaN(Number(lat)) && !isNaN(Number(lng));
}

function money(value) {
  const n = Number(value || 0);
  return `N$ ${n.toFixed(2)}`;
}

function initTarasiMap() {
  const mapEl = document.getElementById("tarasiLiveMap");
  if (!mapEl || typeof L === "undefined") return;

  tarasiMap = L.map("tarasiLiveMap", {
    zoomControl: true,
    scrollWheelZoom: true
  }).setView([-22.5609, 17.0658], 6);

  streetLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap"
  }).addTo(tarasiMap);

  satelliteLayer = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {
      maxZoom: 19,
      attribution: "Tiles &copy; Esri"
    }
  );

  const routes = window.TARASI_ROUTES || [];
  const bounds = [];

  routes.forEach((route) => {
    const oLat = route.origin_lat;
    const oLng = route.origin_lng;
    const dLat = route.destination_lat;
    const dLng = route.destination_lng;
    const hLat = route.hotspot_lat;
    const hLng = route.hotspot_lng;

    if (validCoord(oLat, oLng)) {
      const pickupMarker = L.circleMarker([Number(oLat), Number(oLng)], {
        radius: 9,
        color: "#064e3b",
        fillColor: "#22c55e",
        fillOpacity: 0.95,
        weight: 3
      }).addTo(tarasiMap);

      pickupMarker.bindPopup(`
        <div class="tarasi-popup">
          <h3>${route.pickup}</h3>
          <p><b>Pickup point</b></p>
          <p>${route.name}</p>
        </div>
      `);

      markerLayers.push(pickupMarker);
      bounds.push([Number(oLat), Number(oLng)]);
    }

    if (validCoord(dLat, dLng)) {
      const dropMarker = L.circleMarker([Number(dLat), Number(dLng)], {
        radius: 9,
        color: "#064e3b",
        fillColor: "#f7d276",
        fillOpacity: 0.98,
        weight: 3
      }).addTo(tarasiMap);

      dropMarker.bindPopup(`
        <div class="tarasi-popup">
          <h3>${route.dropoff}</h3>
          <p><b>Drop-off point</b></p>
          <p>${route.name}</p>
          <p><b>${money(route.price)}</b></p>
          <a href="/book?route=${route.id || ""}">Book route</a>
        </div>
      `);

      markerLayers.push(dropMarker);
      bounds.push([Number(dLat), Number(dLng)]);
    }

    if (validCoord(oLat, oLng) && validCoord(dLat, dLng)) {
      const line = L.polyline(
        [
          [Number(oLat), Number(oLng)],
          [Number(dLat), Number(dLng)]
        ],
        {
          color: "#d6a13a",
          weight: 5,
          opacity: 0.88,
          dashArray: "10, 10"
        }
      ).addTo(tarasiMap);

      line.bindPopup(`
        <div class="tarasi-popup">
          <h3>${route.name}</h3>
          <p>${route.category || "Route"} · ${route.live_status || "Available"}</p>
          <p><b>${money(route.price)}</b></p>
          <a href="/book?route=${route.id || ""}">Book route</a>
        </div>
      `);

      routeLayers.push(line);
    }

    if (validCoord(hLat, hLng)) {
      const hotspot = L.circleMarker([Number(hLat), Number(hLng)], {
        radius: 11,
        color: "#7f1d1d",
        fillColor: "#ef4444",
        fillOpacity: 0.9,
        weight: 3
      }).addTo(tarasiMap);

      hotspot.bindPopup(`
        <div class="tarasi-popup">
          <h3>🔥 ${route.hotspot_name || "Route Hotspot"}</h3>
          <p>${route.name}</p>
          <p>Popular stop / route landmark</p>
        </div>
      `);

      markerLayers.push(hotspot);
      bounds.push([Number(hLat), Number(hLng)]);
    }
  });

  if (bounds.length) {
    tarasiMap.fitBounds(bounds, { padding: [40, 40] });
  }

  document.getElementById("satelliteMode")?.addEventListener("click", () => {
    if (tarasiMap.hasLayer(streetLayer)) tarasiMap.removeLayer(streetLayer);
    satelliteLayer.addTo(tarasiMap);
  });

  document.getElementById("streetMode")?.addEventListener("click", () => {
    if (tarasiMap.hasLayer(satelliteLayer)) tarasiMap.removeLayer(satelliteLayer);
    streetLayer.addTo(tarasiMap);
  });

  document.getElementById("fitRoutes")?.addEventListener("click", () => {
    if (bounds.length) tarasiMap.fitBounds(bounds, { padding: [40, 40] });
  });

  document.getElementById("locateMe")?.addEventListener("click", () => {
    if (!navigator.geolocation) {
      alert("Location is not supported on this device.");
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;

        const marker = L.circleMarker([lat, lng], {
          radius: 10,
          color: "#075985",
          fillColor: "#38bdf8",
          fillOpacity: 1,
          weight: 3
        }).addTo(tarasiMap);

        marker.bindPopup(`
          <div class="tarasi-popup">
            <h3>Your live location</h3>
            <p>GPS location from your device.</p>
          </div>
        `).openPopup();

        tarasiMap.setView([lat, lng], 13);
      },
      () => {
        alert("Location permission was not allowed.");
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });

  document.querySelectorAll(".focus-route").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".route-card");
      const oLat = card.dataset.originLat;
      const oLng = card.dataset.originLng;
      const dLat = card.dataset.destinationLat;
      const dLng = card.dataset.destinationLng;

      if (validCoord(oLat, oLng) && validCoord(dLat, dLng)) {
        tarasiMap.fitBounds(
          [
            [Number(oLat), Number(oLng)],
            [Number(dLat), Number(dLng)]
          ],
          { padding: [60, 60] }
        );

        document.getElementById("tarasiLiveMap").scrollIntoView({
          behavior: "smooth",
          block: "center"
        });
      } else {
        alert("This route has no coordinates yet. Add pickup/drop-off coordinates in Supabase.");
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", initTarasiMap);
