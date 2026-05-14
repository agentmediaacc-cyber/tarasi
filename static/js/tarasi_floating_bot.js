(function () {
  const bubble = document.getElementById("tarasiBotBubble");
  const panel = document.getElementById("tarasiBotPanel");
  const closeBtn = document.getElementById("tarasiBotClose");
  const messages = document.getElementById("tarasiBotMessages");
  const form = document.getElementById("tarasiBotForm");
  const input = document.getElementById("tarasiBotInput");
  const suggestions = document.getElementById("tarasiBotSuggestions");
  const status = document.getElementById("tarasiBotStatus");
  const feedback = document.getElementById("tarasiBotFeedback");
  const typing = document.getElementById("tarasiBotTyping");
  const modeBadge = document.getElementById("tarasiBotModeBadge");

  if (!bubble || !panel || !messages || !form || !input || !suggestions) return;

  let lastConversationId = localStorage.getItem("tarasi_bot_conversation_id") || "";
  let lastQuote = null;
  let lastBookingNumber = localStorage.getItem("tarasi_last_booking_number") || "";
  let activeChatNumber = localStorage.getItem("tarasi_active_chat_number") || "";
  let supportPollingInterval = null;

  function showTyping(show = true) {
    if (typing) typing.hidden = !show;
    messages.scrollTop = messages.scrollHeight;
  }

  function addMsg(text, who = "bot", meta = {}) {
    if (!text) return;
    const div = document.createElement("div");
    div.className = `tarasi-msg ${who}`;
    if (who === "system") div.className = "tarasi-msg system-msg";
    div.textContent = text;
    if (meta.msgId) div.setAttribute("data-msg-id", meta.msgId);
    if (meta.ticketNumber) {
      const badge = document.createElement("div");
      badge.className = "tarasi-msg-ticket";
      badge.textContent = `Ticket: ${meta.ticketNumber}`;
      div.appendChild(badge);
    }
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
    
    // Feedback logic: Only show if bot replies and it's not a step in a flow
    if (who === "bot" && feedback && !meta.isStep) {
        feedback.hidden = false;
        feedback.querySelector("span").textContent = meta.feedbackText || "Was this reply helpful?";
    }
  }

  function renderAddressResult(result, type = "pickup") {
    const card = document.createElement("div");
    card.className = "tarasi-address-result";
    card.innerHTML = `
      <strong>${result.display_name}</strong>
      <span>OpenStreetMap Result</span>
    `;
    card.addEventListener("click", () => {
      sendMessage(`Yes correct ${type}: ${result.display_name}`);
    });
    messages.appendChild(card);
    messages.scrollTop = messages.scrollHeight;
  }

  function renderQuoteCard(quote) {
    if (!quote) return;
    lastQuote = quote;
    const card = document.createElement("div");
    card.className = "tarasi-estimate-card";
    card.innerHTML = `
      <div class="tarasi-estimate-head">
        <strong>Quotation Preview</strong>
        <span>${quote.quote_number || "Draft"}</span>
      </div>
      <div class="tarasi-estimate-grid">
        <div><span>Pickup</span><strong>${quote.pickup_text || "-"}</strong></div>
        <div><span>Drop-off</span><strong>${quote.dropoff_text || "-"}</strong></div>
        <div><span>Distance</span><strong>${quote.distance_km} km</strong></div>
        <div><span>Price</span><strong>N$${Number(quote.final_price || 0).toFixed(2)}</strong></div>
      </div>
    `;
    
    if (quote.quote_number) {
        const downloadBtn = document.createElement("a");
        downloadBtn.className = "tarasi-quote-download";
        downloadBtn.textContent = "⬇️ Download Quote PDF";
        downloadBtn.href = "#";
        downloadBtn.addEventListener("click", async (e) => {
            e.preventDefault();
            const res = await fetch("/api/bot/create-quote-pdf", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ quote_number: quote.quote_number })
            });
            const data = await res.json();
            if (data.ok) window.open(data.file_url, "_blank");
        });
        card.appendChild(downloadBtn);
    }
    
    messages.appendChild(card);
    messages.scrollTop = messages.scrollHeight;
  }

  function setSuggestions(chips) {
    suggestions.innerHTML = "";
    chips.forEach((chip) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = chip;
      btn.addEventListener("click", () => sendMessage(chip));
      suggestions.appendChild(btn);
    });
  }

  async function sendMessage(text) {
    if (!text.trim()) return;
    addMsg(text, "user");
    input.value = "";
    showTyping(true);

    if (activeChatNumber) {
        // Send to live support
        await fetch(`/api/support/chat/${activeChatNumber}/message`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text })
        });
        showTyping(false);
        return;
    }

    try {
      const res = await fetch("/api/bot/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text })
      });
      const data = await res.json();
      showTyping(false);
      
      if (data.handoff) {
          startSupportPolling(data.chat_number);
      }
      
      addMsg(data.reply, "bot", {
          ticketNumber: data.ticket_number,
          isStep: data.stage && data.stage !== "greeting",
          feedbackText: data.stage === "quote_ready" ? "Did this solve what you needed?" : null
      });

      if (data.quote) {
          renderQuoteCard(data.quote);
      }
      
      if (data.suggestions) {
          setSuggestions(data.suggestions);
      }
    } catch (e) {
      showTyping(false);
      addMsg("Sorry, I'm having trouble connecting. Please try again or talk to support.", "bot");
    }
  }

  function startSupportPolling(chatNumber) {
    if (supportPollingInterval) clearInterval(supportPollingInterval);
    activeChatNumber = chatNumber;
    modeBadge.textContent = "Live Support";
    modeBadge.style.background = "#4caf50";
    status.textContent = "Connected to Tarasi Support";
    
    supportPollingInterval = setInterval(async () => {
      const res = await fetch(`/api/support/chat/${chatNumber}`);
      const data = await res.json();
      if (data.ok) {
        const displayedIds = Array.from(messages.querySelectorAll("[data-msg-id]")).map(el => el.dataset.msgId);
        data.messages.forEach(m => {
          if (!displayedIds.includes(String(m.id))) {
             if (m.sender_type === "admin" || m.sender_type === "system") {
                addMsg(m.message, m.sender_type === "admin" ? "bot" : "system", { msgId: m.id });
             } else if (m.sender_type === "user" && !Array.from(messages.querySelectorAll(".user")).some(el => el.textContent === m.message)) {
                // If user message is in DB but not on screen (e.g. refresh), add it
                addMsg(m.message, "user", { msgId: m.id });
             }
          }
        });
        if (data.chat.status === "closed") {
            addMsg("Support chat closed. Returning to bot.", "system");
            stopSupportPolling();
        }
      }
    }, 4000);
  }

  function stopSupportPolling() {
    clearInterval(supportPollingInterval);
    activeChatNumber = "";
    modeBadge.textContent = "Bot";
    modeBadge.style.background = "#c89a2b";
    status.textContent = "AI + Human Support";
  }

  async function submitReview(helpful) {
    if (helpful) {
        addMsg("Thanks! Glad I could help.", "bot");
        feedback.hidden = true;
    } else {
        sendMessage("Talk to support");
    }
  }

  bubble.addEventListener("click", () => panel.classList.add("open"));
  closeBtn.addEventListener("click", () => panel.classList.remove("open"));
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(input.value);
  });
  
  if (feedback) {
    feedback.querySelectorAll("[data-review]").forEach(btn => {
        btn.addEventListener("click", () => submitReview(btn.dataset.review === "up"));
    });
  }

  // Initial Greeting
  sendMessage("hi");

})();
