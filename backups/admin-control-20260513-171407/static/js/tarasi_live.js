/**
 * Tarasi Live Engine
 * Lightweight polling for real-time operational status.
 */

class TarasiLiveEngine {
  constructor(options = {}) {
    this.interval = options.interval || 25000; // 25s default
    this.endpoints = options.endpoints || [];
    this.onUpdate = options.onUpdate || (() => {});
    this.isRunning = false;
    this.timer = null;
    this.isTabActive = true;

    this.initVisibilityListener();
  }

  initVisibilityListener() {
    document.addEventListener("visibilitychange", () => {
      this.isTabActive = !document.hidden;
      if (this.isTabActive && this.isRunning) {
        this.fetchNow();
      }
    });
  }

  start() {
    if (this.isRunning) return;
    this.isRunning = true;
    this.scheduleNext();
    this.fetchNow();
  }

  stop() {
    this.isRunning = false;
    if (this.timer) clearTimeout(this.timer);
  }

  scheduleNext() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      if (this.isRunning && this.isTabActive) {
        this.fetchNow();
      } else {
        this.scheduleNext();
      }
    }, this.interval);
  }

  async fetchNow() {
    try {
      const results = await Promise.all(
        this.endpoints.map(async (url) => {
          const res = await fetch(url, { cache: "no-store" });
          if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
          return { url, data: await res.json() };
        })
      );
      this.onUpdate(results);
    } catch (error) {
      console.warn("[TarasiLive] Update failed:", error);
    } finally {
      this.scheduleNext();
    }
  }
}

// Global live instance helper
window.TarasiLive = {
  engine: null,
  notifications: [],
  init(options) {
    this.engine = new TarasiLiveEngine(options);
    this.engine.start();
    this.initNotifications();
    return this.engine;
  },
  initNotifications() {
    const trigger = document.querySelector("[data-notification-trigger]");
    const dropdown = document.querySelector("[data-notification-dropdown]");
    const clearBtn = document.querySelector("[data-clear-notifications]");

    if (trigger && dropdown) {
      trigger.addEventListener("click", (e) => {
        e.stopPropagation();
        dropdown.hidden = !dropdown.hidden;
      });

      document.addEventListener("click", () => {
        dropdown.hidden = true;
      });

      dropdown.addEventListener("click", (e) => e.stopPropagation());
    }

    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        this.notifications = [];
        this.renderNotifications();
      });
    }

    // Initial fetch or mock
    this.mockNotifications();
  },
  mockNotifications() {
    // For demo/phase implementation before full API
    this.notifications = [
      { id: 1, type: "booking", title: "Booking Confirmed", message: "Your trip T-992 is confirmed.", time: "2m ago", unread: true },
      { id: 2, type: "driver", title: "Driver Assigned", message: "Driver John is on the way.", time: "10m ago", unread: false }
    ];
    this.renderNotifications();
  },
  renderNotifications() {
    const list = document.querySelector("[data-notification-list]");
    const badge = document.querySelector("[data-unread-count]");
    if (!list) return;

    const unread = this.notifications.filter(n => n.unread).length;
    if (badge) {
      badge.textContent = unread;
      badge.hidden = unread === 0;
    }

    if (this.notifications.length === 0) {
      list.innerHTML = '<div class="empty-state">No new notifications</div>';
      return;
    }

    list.innerHTML = this.notifications.map(n => `
      <div class="notification-item ${n.unread ? 'unread' : ''}">
        <div class="notification-item-icon">${n.type === 'booking' ? '📅' : '🚗'}</div>
        <div class="notification-item-content">
          <strong>${n.title}</strong>
          <p>${n.message}</p>
          <span>${n.time}</span>
        </div>
      </div>
    `).join('');
  },
  updateStatusBadge(el, status) {
    if (!el) return;
    const normalizedStatus = status.toLowerCase().replace(/\s+/g, '-');
    el.setAttribute("data-status", normalizedStatus);
    el.textContent = status;
    
    // Pulse if active operational state
    const liveStates = ['driver-assigned', 'on-the-way', 'picked-up', 'arrived', 'moving', 'in-progress'];
    if (liveStates.includes(normalizedStatus)) {
      el.classList.add("is-live");
    } else {
      el.classList.remove("is-live");
    }
  }
};
