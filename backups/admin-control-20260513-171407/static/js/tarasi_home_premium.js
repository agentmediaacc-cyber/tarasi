const live = [
  "🚐 Executive SUV heading to Hosea Kutako Airport",
  "✈️ Airport pickup confirmed for 4 passengers",
  "🏜️ Sossusvlei desert transfer request received",
  "🌊 Swakopmund coastal route active today",
  "🎒 School transport schedule ready"
];
let i = 0;
setInterval(() => {
  const el = document.querySelector("[data-live]");
  if (el) {
    el.textContent = live[i % live.length];
    i++;
  }
}, 2600);
