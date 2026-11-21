const messagesEl = document.getElementById("messages");
const form = document.getElementById("chatForm");
const input = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const resetBtn = document.getElementById("resetBtn");
const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
const csrfHeaders = {"X-CSRF-Token": csrfToken};

function addMessage(role, content) {
  const row = document.createElement("div");
  row.className = `message ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "TOI" : "CK";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  const sender = document.createElement("span");
  sender.className = "sender";
  sender.textContent = role === "user" ? "TOI" : "CHUMAN-KINK";
  const p = document.createElement("p");
  p.textContent = content;
  bubble.append(sender, p);
  row.append(avatar, bubble);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();
    const dot = document.getElementById("statusDot");
    const label = document.getElementById("statusText");
    dot.classList.toggle("online", data.core === "online");
    label.textContent = data.ai_connected ? "IA connectée" : "Noyau actif · mode démo";
  } catch {
    document.getElementById("statusText").textContent = "Serveur indisponible";
  }
}

async function loadHistory() {
  let before = null;
  const allMessages = [];
  while (true) {
    const query = before ? `?before=${before}&limit=100` : "?limit=100";
    const res = await fetch(`/api/history${query}`);
    if (res.status === 401) { window.location.href = "/login"; return; }
    if (!res.ok) throw new Error("Impossible de charger l'historique");
    const page = await res.json();
    if (!Array.isArray(page.messages)) throw new Error("Format d'historique invalide");
    allMessages.unshift(...page.messages);
    if (!page.has_more || !page.next_before) break;
    before = page.next_before;
  }
  if (allMessages.length === 0) return;
  messagesEl.innerHTML = "";
  allMessages.forEach(item => addMessage(item.role, item.content));
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  addMessage("user", message);
  input.value = "";
  sendBtn.disabled = true;
  sendBtn.textContent = "…";
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json", ...csrfHeaders},
      body: JSON.stringify({message})
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Erreur");
    addMessage("assistant", data.reply);
  } catch (err) {
    addMessage("assistant", "Je n'ai pas pu joindre le serveur. Réessaie dans un instant.");
  } finally {
    sendBtn.disabled = false;
    sendBtn.textContent = "Envoyer";
    input.focus();
  }
});

resetBtn.addEventListener("click", async () => {
  if (!confirm("Effacer tout l'historique de cette conversation ?")) return;
  const res = await fetch("/api/reset", {method: "POST", headers: csrfHeaders});
  if (res.ok) {
    messagesEl.innerHTML = "";
    addMessage("assistant", "Historique effacé. Nous pouvons recommencer.");
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 120) + "px";
});

document.getElementById("logoutForm")?.addEventListener("submit", (event) => {
  event.preventDefault();
  fetch("/logout", {method: "POST", headers: csrfHeaders}).finally(() => { window.location.href = "/login"; });
});

loadStatus();
loadHistory().catch(() => {});
