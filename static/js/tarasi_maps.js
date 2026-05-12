const mapRootSelector = "[data-map-root]";
const routeThumbnailSelector = "[data-route-thumbnail]";
const bookingHelperSelector = "[data-booking-helper]";
const prefersReducedMotionMaps = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function parseJsonAttribute(node, attributeName, fallback = null) {
  const value = node.getAttribute(attributeName);
  if (!value) return fallback;
  try {
    return JSON.parse(value);
  } catch (_error) {
    return fallback;
  }
}

function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (window.__tarasiLeafletPromise) return window.__tarasiLeafletPromise;

  window.__tarasiLeafletPromise = new Promise((resolve, reject) => {
    if (!document.querySelector('link[data-leaflet-style]')) {
      const style = document.createElement("link");
      style.rel = "stylesheet";
      style.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      style.crossOrigin = "";
      style.setAttribute("data-leaflet-style", "true");
      document.head.appendChild(style);
    }

    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.defer = true;
    script.crossOrigin = "";
    script.onload = () => resolve(window.L);
    script.onerror = () => reject(new Error("Leaflet failed to load."));
    document.body.appendChild(script);
  });

  return window.__tarasiLeafletPromise;
}

function renderMapEmptyState(node, message) {
  node.innerHTML = `<div class="map-empty-state">${message}</div>`;
}

function allMapPoints(config) {
  const points = [];
  if (Array.isArray(config.route_points)) {
    config.route_points.forEach((point) => {
      if (Array.isArray(point) && point.length === 2) points.push(point);
    });
  }
  ["pickup_marker", "dropoff_marker", "driver_marker"].forEach((key) => {
    const marker = config[key];
    if (marker && marker.lat !== undefined && marker.lng !== undefined) {
      points.push([marker.lat, marker.lng]);
    }
  });
  if (Array.isArray(config.routes)) {
    config.routes.forEach((route) => {
      const preview = route.map_preview || {};
      (preview.route_points || []).forEach((point) => points.push(point));
    });
  }
  return points;
}

function buildMarkerIcon(type) {
  return window.L.divIcon({
    className: "",
    html: `<span class="tarasi-marker ${type}"></span>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

function addMarker(layer, marker, type, popupText) {
  if (!marker || marker.lat === undefined || marker.lng === undefined) return null;
  const item = window.L.marker([marker.lat, marker.lng], { icon: buildMarkerIcon(type) }).addTo(layer);
  if (popupText) item.bindPopup(popupText);
  return item;
}

function initLeafletMap(node, config) {
  if (!config) {
    renderMapEmptyState(node, "Map data is not available for this page.");
    return;
  }

  const points = allMapPoints(config);
  if (!points.length) {
    renderMapEmptyState(node, "Route coordinates are not available yet.");
    return;
  }

  const map = window.L.map(node, {
    zoomControl: true,
    scrollWheelZoom: false,
    dragging: true,
    attributionControl: false,
  });

  window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    minZoom: 4,
  }).addTo(map);

  node._leafletMarkers = {};

  if (Array.isArray(config.routes) && config.routes.length) {
    config.routes.forEach((route) => {
      const preview = route.map_preview || {};
      if (Array.isArray(preview.route_points) && preview.route_points.length >= 2) {
        window.L.polyline(preview.route_points, {
          color: "#0c6b70",
          weight: 4,
          opacity: 0.72,
        }).addTo(map);
      }
      addMarker(map, preview.pickup_marker, "pickup", route.pickup);
      addMarker(map, preview.dropoff_marker, "dropoff", route.dropoff);
    });
  } else {
    if (Array.isArray(config.route_points) && config.route_points.length >= 2) {
      window.L.polyline(config.route_points, {
        color: "#0c6b70",
        weight: 4,
        opacity: 0.82,
      }).addTo(map);
    }
    addMarker(map, config.pickup_marker, "pickup", config.pickup_marker?.label);
    addMarker(map, config.dropoff_marker, "dropoff", config.dropoff_marker?.label);
    const driver = addMarker(map, config.driver_marker, "driver", config.driver_marker?.label);
    if (driver) node._leafletMarkers.driver = driver;
  }

  const bounds = window.L.latLngBounds(points);
  if (bounds.isValid() && points.length > 1) {
    map.fitBounds(bounds, { padding: [26, 26] });
  } else {
    const center = config.center || { lat: -22.5609, lng: 17.0658 };
    map.setView([center.lat, center.lng], 7);
  }

  if (!prefersReducedMotionMaps) {
    window.setTimeout(() => map.invalidateSize(), 120);
  }
  node._leafletMap = map;
}

// Global TarasiMap API
window.TarasiMap = {
  updateDriverMarker(lat, lng) {
    const mapNode = document.querySelector(mapRootSelector);
    if (!mapNode || !mapNode._leafletMap || !mapNode._leafletMarkers?.driver) return;
    
    const driver = mapNode._leafletMarkers.driver;
    const currentPos = driver.getLatLng();
    
    // Only update if change is significant (> 0.0001)
    if (Math.abs(currentPos.lat - lat) < 0.0001 && Math.abs(currentPos.lng - lng) < 0.0001) return;
    
    if (prefersReducedMotionMaps) {
      driver.setLatLng([lat, lng]);
    } else {
      // Leaflet doesn't have native smooth transition, but we can animate it
      this.animateMarker(driver, currentPos, { lat, lng });
    }
  },
  animateMarker(marker, from, to, duration = 2000) {
    const start = performance.now();
    const animate = (time) => {
      let progress = (time - start) / duration;
      if (progress > 1) progress = 1;
      
      const currentLat = from.lat + (to.lat - from.lat) * progress;
      const currentLng = from.lng + (to.lng - from.lng) * progress;
      
      marker.setLatLng([currentLat, currentLng]);
      
      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };
    requestAnimationFrame(animate);
  }
};

function renderRouteThumbnail(node, config) {
  if (!config || !Array.isArray(config.route_points) || config.route_points.length < 2) {
    node.innerHTML = '<div class="route-thumbnail-empty">Preview available once route coordinates are set.</div>';
    return;
  }
  const [start, end] = config.route_points;
  const x1 = 24;
  const y1 = 82;
  const x2 = 232;
  const y2 = 36;
  node.innerHTML = `
    <svg viewBox="0 0 256 120" role="presentation" aria-hidden="true" preserveAspectRatio="none">
      <defs>
        <linearGradient id="routeLineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#0c6b70"></stop>
          <stop offset="100%" stop-color="#d3a83d"></stop>
        </linearGradient>
      </defs>
      <rect width="256" height="120" rx="18" fill="rgba(255,255,255,0.28)"></rect>
      <path d="M ${x1} ${y1} C 94 28, 164 104, ${x2} ${y2}" fill="none" stroke="url(#routeLineGradient)" stroke-width="6" stroke-linecap="round"></path>
      <circle cx="${x1}" cy="${y1}" r="9" fill="#0c6b70"></circle>
      <circle cx="${x2}" cy="${y2}" r="9" fill="#d3a83d"></circle>
      <text x="24" y="108" fill="#223142" font-size="10">${config.pickup_marker?.label || start.join(", ")}</text>
      <text x="156" y="18" fill="#223142" font-size="10">${config.dropoff_marker?.label || end.join(", ")}</text>
    </svg>
  `;
}

function updateMapNode(node, config) {
  if (!node) return;
  if (node._leafletMap) {
    node._leafletMap.remove();
    node._leafletMap = null;
    node.innerHTML = "";
  }
  loadLeaflet()
    .then(() => initLeafletMap(node, config))
    .catch(() => renderMapEmptyState(node, "Map preview could not be loaded right now."));
}

function normalizeKey(value) {
  return String(value || "").trim().toLowerCase();
}

function buildAdHocPreview(pickup, dropoff, towns) {
  const pickupTown = towns.find((town) => normalizeKey(town.label) === normalizeKey(pickup));
  const dropoffTown = towns.find((town) => normalizeKey(town.label) === normalizeKey(dropoff));
  if (!pickupTown || !dropoffTown) return null;
  return {
    center: {
      lat: Number(((pickupTown.lat + dropoffTown.lat) / 2).toFixed(4)),
      lng: Number(((pickupTown.lng + dropoffTown.lng) / 2).toFixed(4)),
      label: `${pickupTown.label} to ${dropoffTown.label}`,
    },
    pickup_marker: { label: pickupTown.label, lat: pickupTown.lat, lng: pickupTown.lng },
    dropoff_marker: { label: dropoffTown.label, lat: dropoffTown.lat, lng: dropoffTown.lng },
    route_points: [[pickupTown.lat, pickupTown.lng], [dropoffTown.lat, dropoffTown.lng]],
  };
}

function initBookingHelper() {
  const root = document.querySelector(bookingHelperSelector);
  const form = document.querySelector("form.field-grid");
  if (!root || !form) return;

  const pickupInput = form.querySelector("#pickup_location");
  const dropoffInput = form.querySelector("#dropoff_location");
  if (!pickupInput || !dropoffInput) return;

  const routes = parseJsonAttribute(root, "data-routes", []);
  const towns = parseJsonAttribute(root, "data-towns", []);
  const previewCopy = root.querySelector("[data-booking-preview-copy]");
  const previewRoute = root.querySelector("[data-preview-route]");
  const previewMeta = root.querySelector("[data-preview-meta]");
  const mapNode = root.querySelector("[data-booking-map]");

  function activeRouteMatch() {
    return routes.find((route) => (
      normalizeKey(route.pickup) === normalizeKey(pickupInput.value)
      && normalizeKey(route.dropoff) === normalizeKey(dropoffInput.value)
    ));
  }

  function updateSuggestionSelection() {
    document.querySelectorAll("[data-route-suggestion]").forEach((button) => {
      const isSelected = normalizeKey(button.dataset.pickup) === normalizeKey(pickupInput.value)
        && normalizeKey(button.dataset.dropoff) === normalizeKey(dropoffInput.value);
      button.classList.toggle("is-selected", isSelected);
    });
  }

  function renderCurrentPreview() {
    const matchedRoute = activeRouteMatch();
    const preview = matchedRoute?.map_preview || buildAdHocPreview(pickupInput.value, dropoffInput.value, towns);
    if (matchedRoute) {
      previewRoute.textContent = matchedRoute.route;
      previewMeta.textContent = [matchedRoute.distance_label, matchedRoute.duration_label, matchedRoute.price_label].filter(Boolean).join(" • ");
    } else if (preview) {
      previewRoute.textContent = `${pickupInput.value || "Pickup"} -> ${dropoffInput.value || "Drop-off"}`;
      previewMeta.textContent = "Preview only. Pricing and duration confirm after route validation.";
    } else {
      previewRoute.textContent = "Route preview will appear here.";
      previewMeta.textContent = "Popular Namibia routes update the map instantly when both locations are known.";
      renderMapEmptyState(mapNode, "Select pickup and drop-off points to preview the route.");
      updateSuggestionSelection();
      return;
    }
    updateMapNode(mapNode, preview);
    updateSuggestionSelection();
  }

  document.querySelectorAll("[data-route-suggestion]").forEach((button) => {
    button.addEventListener("click", () => {
      pickupInput.value = button.dataset.pickup || "";
      dropoffInput.value = button.dataset.dropoff || "";
      renderCurrentPreview();
    });
  });

  root.querySelectorAll("[data-fill-route]").forEach((button) => {
    button.addEventListener("click", () => {
      const [pickup, dropoff] = String(button.getAttribute("data-fill-route") || "").split("|");
      pickupInput.value = pickup || "";
      dropoffInput.value = dropoff || "";
      renderCurrentPreview();
    });
  });

  root.querySelectorAll("[data-fill-pickup]").forEach((button) => {
    button.addEventListener("click", () => {
      pickupInput.value = button.getAttribute("data-fill-pickup") || "";
      renderCurrentPreview();
    });
  });

  root.querySelectorAll("[data-fill-town]").forEach((button) => {
    button.addEventListener("click", () => {
      const label = button.getAttribute("data-fill-town") || "";
      if (!pickupInput.value) {
        pickupInput.value = label;
      } else {
        dropoffInput.value = label;
      }
      renderCurrentPreview();
    });
  });

  ["change", "blur", "input"].forEach((eventName) => {
    pickupInput.addEventListener(eventName, renderCurrentPreview);
    dropoffInput.addEventListener(eventName, renderCurrentPreview);
  });

  renderCurrentPreview();
}

document.querySelectorAll(routeThumbnailSelector).forEach((node) => {
  renderRouteThumbnail(node, parseJsonAttribute(node, "data-route-thumbnail", null));
});

if (document.querySelector(mapRootSelector)) {
  document.querySelectorAll(mapRootSelector).forEach((node) => {
    const config = parseJsonAttribute(node, "data-map-config", null);
    updateMapNode(node, config);
  });
}

initBookingHelper();

function initDriverLocationShare() {
  const button = document.querySelector("[data-share-driver-location]");
  const feedback = document.querySelector("[data-driver-location-feedback]");
  if (!button || !feedback) return;

  button.addEventListener("click", () => {
    if (!navigator.geolocation) {
      feedback.textContent = "Geolocation is not available on this device.";
      return;
    }
    button.disabled = true;
    feedback.textContent = "Requesting current location…";
    navigator.geolocation.getCurrentPosition(
      (position) => {
        fetch("/api/driver/location", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({
            driver_id: button.getAttribute("data-driver-id"),
            lat: position.coords.latitude,
            lng: position.coords.longitude,
          }),
        })
          .then((response) => response.json().then((payload) => ({ ok: response.ok, payload })))
          .then(({ ok, payload }) => {
            if (!ok || !payload.ok) {
              feedback.textContent = payload.error || "Location could not be shared.";
              return;
            }
            feedback.textContent = `Location shared at ${payload.location.last_location_at}.`;
          })
          .catch(() => {
            feedback.textContent = "Location could not be shared right now.";
          })
          .finally(() => {
            button.disabled = false;
          });
      },
      (error) => {
        feedback.textContent = error.message || "Location permission was denied.";
        button.disabled = false;
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 },
    );
  });
}

function initTripShare() {
  document.querySelectorAll("[data-share-trip]").forEach((button) => {
    button.addEventListener("click", async () => {
      const reference = button.getAttribute("data-share-trip") || "trip";
      const url = `${window.location.origin}/track/${reference}`;
      const payload = {
        title: `Tarasi trip ${reference}`,
        text: `Track my Tarasi trip: ${reference}`,
        url,
      };
      if (navigator.share) {
        try {
          await navigator.share(payload);
          return;
        } catch (_error) {
          return;
        }
      }
      try {
        await navigator.clipboard.writeText(url);
        button.textContent = "Trip link copied";
        window.setTimeout(() => { button.textContent = "Share trip"; }, 1800);
      } catch (_error) {
        window.location.href = url;
      }
    });
  });
}

initDriverLocationShare();
initTripShare();
