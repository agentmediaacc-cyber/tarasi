const chat = document.getElementById("chat");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("message");
const suggestions = document.getElementById("suggestions");
const quoteForm = document.getElementById("quoteForm");

function addMsg(text, who="bot"){
  const div = document.createElement("div");
  div.className = `msg ${who}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

async function sendMessage(text){
  if(!text.trim()) return;
  addMsg(text, "user");
  messageInput.value = "";

  const res = await fetch("/api/bot/message", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({message:text})
  });

  const data = await res.json();
  addMsg(data.reply || "I can help with that. Please share pickup, drop-off, date and passengers.", "bot");

  if(data.suggestions){
    suggestions.innerHTML = "";
    data.suggestions.forEach(s => {
      const btn = document.createElement("button");
      btn.textContent = s;
      btn.onclick = () => sendMessage(s);
      suggestions.appendChild(btn);
    });
  }
}

chatForm.addEventListener("submit", e => {
  e.preventDefault();
  sendMessage(messageInput.value);
});

suggestions.querySelectorAll("button").forEach(btn => {
  btn.onclick = () => sendMessage(btn.textContent);
});

quoteForm.addEventListener("submit", async e => {
  e.preventDefault();

  const form = new FormData(quoteForm);
  const payload = Object.fromEntries(form.entries());

  const res = await fetch("/api/bot/create-quote", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(payload)
  });

  const data = await res.json();

  if(!data.ok){
    addMsg(data.message || "Some details are missing.", "bot");
    return;
  }

  addMsg(`Done. Your Tarasi quotation is ready. Reference: ${data.reference}`, "bot");

  const link = document.createElement("a");
  link.href = data.pdf_url;
  link.textContent = "Download Premium Quote PDF";
  link.target = "_blank";
  link.className = "download";
  chat.appendChild(link);

  const preview = document.createElement("a");
  preview.href = data.preview_url;
  preview.textContent = "Open Trackable Quote Preview";
  preview.target = "_blank";
  preview.className = "download";
  chat.appendChild(preview);

  chat.scrollTop = chat.scrollHeight;
});
