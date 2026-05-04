let currentSessionId = null;
let messages = [];
let toolCalls = [];
let settings = {};

const els = {
  railButtons: document.querySelectorAll(".rail-button"),
  sidePanels: document.querySelectorAll(".side-panel"),
  sessions: document.querySelector("#sessions"),
  messages: document.querySelector("#messages"),
  activity: document.querySelector("#activity"),
  memory: document.querySelector("#memory"),
  traits: document.querySelector("#traits"),
  selfProfile: document.querySelector("#selfProfile"),
  saveProfile: document.querySelector("#saveProfile"),
  provider: document.querySelector("#provider"),
  localOpenAIBaseUrl: document.querySelector("#localOpenAIBaseUrl"),
  localOpenAIModel: document.querySelector("#localOpenAIModel"),
  localOpenAIKey: document.querySelector("#localOpenAIKey"),
  geminiKey: document.querySelector("#geminiKey"),
  geminiModel: document.querySelector("#geminiModel"),
  codexModel: document.querySelector("#codexModel"),
  openaiKey: document.querySelector("#openaiKey"),
  openaiModel: document.querySelector("#openaiModel"),
  saveSettings: document.querySelector("#saveSettings"),
  settingsStatus: document.querySelector("#settingsStatus"),
  providerStatus: document.querySelector("#providerStatus"),
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

function renderProfile(profile) {
  els.selfProfile.value = profile.self_profile || "";
  els.traits.innerHTML = (profile.traits || []).map((trait) => {
    return `<div class="trait">
      <strong>${escapeHtml(trait.title)}</strong>
      <span>${escapeHtml(trait.confidence)} confidence</span>
      <p>${escapeHtml(trait.text)}</p>
      <pre>${escapeHtml(trait.evidence || "")}</pre>
      <button data-trait-id="${escapeHtml(trait.id)}">Delete trait</button>
    </div>`;
  }).join("") || `<div class="empty">No inferred traits yet.</div>`;
  els.traits.querySelectorAll("button[data-trait-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      const data = await api("/api/profile/trait/delete", {
        method: "POST",
        body: JSON.stringify({ trait_id: button.dataset.traitId }),
      });
      renderProfile(data.profile);
      await loadMemory();
    });
  });
}

function renderSettings(nextSettings) {
  settings = nextSettings || {};
  els.provider.value = settings.provider || "local";
  els.localOpenAIBaseUrl.value = settings.local_openai_base_url || "http://localhost:2276/v1";
  els.localOpenAIModel.value = settings.local_openai_model || "";
  els.geminiModel.value = settings.gemini_model || "gemini-2.5-flash";
  els.codexModel.value = settings.codex_model || "";
  els.openaiModel.value = settings.openai_model || "gpt-5.5";
  els.geminiKey.placeholder = settings.has_gemini_api_key ? "Gemini key saved" : "Leave blank to keep existing key";
  els.localOpenAIKey.placeholder = settings.has_local_openai_api_key ? "Local key saved" : "Optional";
  els.openaiKey.placeholder = settings.has_openai_api_key ? "OpenAI key saved" : "Leave blank to keep existing key";
  const label = {
    local: "Local fallback",
    local_openai: `OpenAI-compatible local (${els.localOpenAIModel.value || "no model"})`,
    codex: "Codex CLI",
    gemini: `Gemini API (${els.geminiModel.value})`,
    openai: `OpenAI API (${els.openaiModel.value})`,
  }[els.provider.value] || "Local fallback";
  els.providerStatus.textContent = label;
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

async function loadProfile() {
  const data = await api("/api/profile");
  renderProfile(data.profile);
}

async function loadSettings() {
  const data = await api("/api/settings");
  renderSettings(data.settings);
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
    await loadProfile();
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
els.railButtons.forEach((button) => {
  button.addEventListener("click", () => {
    els.railButtons.forEach((item) => item.classList.toggle("active", item === button));
    els.sidePanels.forEach((panel) => panel.classList.toggle("active", panel.id === `panel${button.dataset.panel[0].toUpperCase()}${button.dataset.panel.slice(1)}`));
  });
});
els.saveProfile.addEventListener("click", async () => {
  els.saveProfile.textContent = "Saving...";
  const data = await api("/api/profile", {
    method: "POST",
    body: JSON.stringify({ self_profile: els.selfProfile.value }),
  });
  renderProfile(data.profile);
  await loadMemory();
  els.saveProfile.textContent = "Save profile";
});
els.saveSettings.addEventListener("click", async () => {
  els.settingsStatus.textContent = "Saving...";
  const data = await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({
      provider: els.provider.value,
      local_openai_base_url: els.localOpenAIBaseUrl.value,
      local_openai_model: els.localOpenAIModel.value,
      local_openai_api_key: els.localOpenAIKey.value,
      gemini_api_key: els.geminiKey.value,
      gemini_model: els.geminiModel.value,
      codex_model: els.codexModel.value,
      openai_api_key: els.openaiKey.value,
      openai_model: els.openaiModel.value,
    }),
  });
  els.geminiKey.value = "";
  els.localOpenAIKey.value = "";
  els.openaiKey.value = "";
  renderSettings(data.settings);
  els.settingsStatus.textContent = "Saved";
});
els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    els.form.requestSubmit();
  }
});

Promise.all([loadSessions(), loadMemory(), loadProfile(), loadSettings()]).then(() => {
  els.input.focus();
});
