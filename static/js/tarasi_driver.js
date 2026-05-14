/* TARASI DRIVER APP LOGIC */
(function() {
    const DriverApp = {
        init: function() {
            this.setupLocationTracking();
            this.setupEmergency();
            console.log("Tarasi Driver App Initialized");
        },

        setupLocationTracking: function() {
            if ("geolocation" in navigator) {
                // Background tracking every 30 seconds if page is open
                setInterval(() => {
                    navigator.geolocation.getCurrentPosition((pos) => {
                        const data = {
                            lat: pos.coords.latitude,
                            lng: pos.coords.longitude,
                            speed: pos.coords.speed ? Math.round(pos.coords.speed * 3.6) : 0
                        };
                        
                        // Only sync if online
                        const statusPill = document.querySelector(".driver-status-pill");
                        if (statusPill && statusPill.classList.contains("is-online")) {
                            fetch("/driver/location/update", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify(data)
                            });
                        }
                    }, null, { enableHighAccuracy: true });
                }, 30000);
            }
        },

        setupEmergency: function() {
            const sosBtn = document.querySelector(".emergency-btn");
            if (sosBtn) {
                sosBtn.addEventListener("click", (e) => {
                    e.preventDefault();
                    if (confirm("EMERGENCY: Do you want to alert Tarasi Control and send your current location?")) {
                        alert("Emergency signal sent. Help is on the way.");
                        // In real app, this would POST to a specialized emergency endpoint
                    }
                });
            }
        },

        speak: function(text) {
            if ('speechSynthesis' in window) {
                const msg = new SpeechSynthesisUtterance(text);
                msg.rate = 0.95;
                window.speechSynthesis.speak(msg);
            }
        }
    };

    window.DriverApp = DriverApp;
    document.addEventListener("DOMContentLoaded", () => DriverApp.init());
})();
