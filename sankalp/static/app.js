let currentSessionId = null;
let messages = [];
let toolCalls = [];

const els = {
  sessions: document.querySelector("#sessions"),
  messages: document.querySelector("#messages"),
  activity: document.querySelector("#activity"),
  memory: document.querySelector("#memory"),
  form: document.querySelector("#composer"),
  input: document.querySelector("#messageInput"),
  status: document.querySelector("#status"),
  title: document.querySelector("#sessionTitle"),
  newSession: document.querySelector("#newSession"),
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options,
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function renderMessages() {
  els.messages.innerHTML = messages.map((message) => {
    return `<article class="message ${message.role}">${escapeHtml(message.content)}</article>`;
  }).join("");
  els.messages.scrollTop = els.messages.scrollHeight;
}

function renderTools() {
  if (!toolCalls.length) {
    els.activity.className = "activity empty";
    els.activity.textContent = "No tool calls yet.";
    return;
  }
  els.activity.className = "activity";
  els.activity.innerHTML = toolCalls.slice().reverse().map((call) => {
    const output = JSON.stringify(call.output, null, 2);
    return `<div class="tool ${escapeHtml(call.status)}">
      <strong>${escapeHtml(call.name)}</strong>
      <span>${escapeHtml(call.status)}</span>
      <pre>${escapeHtml(output)}</pre>
    </div>`;
  }).join("");
}

function renderMemory(items) {
  els.memory.innerHTML = (items || []).map((note) => {
    return `<div class="note">
      <strong>${escapeHtml(note.path)}</strong>
      <pre>${escapeHtml(note.preview)}</pre>
    </div>`;
  }).join("") || `<div class="empty">No memory notes yet.</div>`;
}

async function loadSessions() {
  const data = await api("/api/sessions");
  els.sessions.innerHTML = data.sessions.map((session) => {
    const active = session.session_id === currentSessionId ? " active" : "";
    return `<button class="session${active}" data-id="${session.session_id}">
      ${escapeHtml(session.title)}
      <small>${session.message_count} messages</small>
    </button>`;
  }).join("");
  els.sessions.querySelectorAll(".session").forEach((button) => {
    button.addEventListener("click", async () => {
      currentSessionId = button.dataset.id;
      const data = await api(`/api/session?id=${encodeURIComponent(currentSessionId)}`);
      messages = data.messages || [];
      toolCalls = data.tool_calls || [];
      els.title.textContent = data.session.title;
      renderMessages();
      renderTools();
      loadSessions();
    });
  });
}

async function loadMemory() {
  const data = await api("/api/memory");
  renderMemory(data.memory);
}

async function newSession() {
  const data = await api("/api/session/new", { method: "POST", body: "{}" });
  currentSessionId = data.session.session_id;
  messages = [];
  toolCalls = [];
  els.title.textContent = data.session.title;
  renderMessages();
  renderTools();
  await loadSessions();
}

async function sendMessage(event) {
  event.preventDefault();
  const text = els.input.value.trim();
  if (!text) return;
  els.input.value = "";
  messages.push({ role: "user", content: text });
  renderMessages();
  els.status.textContent = "Thinking";
  try {
    const data = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({ session_id: currentSessionId, message: text }),
    });
    currentSessionId = data.session.session_id;
    messages = data.messages;
    toolCalls = data.tool_calls || [];
    els.title.textContent = data.session.title;
    renderMessages();
    renderTools();
    renderMemory(data.memory);
    await loadSessions();
  } catch (error) {
    messages.push({ role: "assistant", content: `Request failed: ${error.message}` });
    renderMessages();
  } finally {
    els.status.textContent = "Ready";
    els.input.focus();
  }
}

els.form.addEventListener("submit", sendMessage);
els.newSession.addEventListener("click", newSession);
els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    els.form.requestSubmit();
  }
});

Promise.all([loadSessions(), loadMemory()]).then(() => {
  els.input.focus();
});
