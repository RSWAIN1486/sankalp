let currentSessionId = null;
let messages = [];
let toolCalls = [];
let settings = {};

const compatiblePresets = {
  custom: { baseUrl: "http://localhost:2276/v1", model: "" },
  ollama: { baseUrl: "http://localhost:11434/v1", model: "qwen3:latest" },
  lmstudio: { baseUrl: "http://localhost:1234/v1", model: "" },
  openrouter: { baseUrl: "https://openrouter.ai/api/v1", model: "anthropic/claude-sonnet-4.6" },
  deepseek: { baseUrl: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  kimi: { baseUrl: "https://api.moonshot.ai/v1", model: "kimi-k2.5" },
  minimax: { baseUrl: "https://api.minimax.io/v1", model: "MiniMax-M2.7" },
  xai: { baseUrl: "https://api.x.ai/v1", model: "grok-4-1-fast-reasoning" },
  nvidia: { baseUrl: "https://integrate.api.nvidia.com/v1", model: "nvidia/nemotron-3-super-120b-a12b" },
  huggingface: { baseUrl: "https://router.huggingface.co/v1", model: "Qwen/Qwen3-235B-A22B-Thinking-2507" },
  alibaba: { baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen3.5-plus" },
};

const providerGuide = [
  ["Codex CLI / OpenAI Codex", "Run `codex login` once. Sankalp then uses `codex exec` in read-only ephemeral mode. Hermes sets this up as `openai-codex` through `hermes model`."],
  ["Gemini API", "Create a Gemini API key and save it here. Hermes uses `GOOGLE_API_KEY` or `GEMINI_API_KEY` for provider `gemini`."],
  ["OpenAI API", "Create an OpenAI platform key and choose a Responses-capable model."],
  ["Custom / local / OpenAI-compatible", "Use any server with `/v1/chat/completions`: Ollama, LM Studio, vLLM, llama.cpp, OpenVINO, routers, or custom proxies."],
  ["OpenRouter", "Use `OPENROUTER_API_KEY` with base URL `https://openrouter.ai/api/v1` to access many model families through one key."],
  ["Anthropic / Claude", "Hermes supports `ANTHROPIC_API_KEY` and Claude OAuth through `hermes model`. In Sankalp today, use Claude through OpenRouter or another compatible router until native Anthropic is added."],
  ["GitHub Copilot", "Hermes supports `copilot` OAuth/device-code flow and `copilot-acp` through `hermes model`. Sankalp does not yet call Copilot directly."],
  ["Nous Portal", "Hermes supports OAuth subscription setup via `hermes model`. Sankalp does not yet integrate the Nous portal."],
  ["Google Gemini OAuth", "Hermes provider `google-gemini-cli` signs in through browser PKCE via `hermes model`. Sankalp currently supports Gemini API keys."],
  ["Qwen OAuth", "Hermes provider `qwen-oauth` signs in through the Qwen portal via `hermes model`."],
  ["MiniMax OAuth", "Hermes supports MiniMax browser OAuth via `hermes model`; API-key MiniMax can use the compatible endpoint path."],
  ["DeepSeek", "Use `DEEPSEEK_API_KEY` with the DeepSeek compatible endpoint and a DeepSeek model ID."],
  ["Kimi / Moonshot", "Use `KIMI_API_KEY` or `KIMI_CN_API_KEY`; global and China endpoints are separate."],
  ["MiniMax API", "Use `MINIMAX_API_KEY` or `MINIMAX_CN_API_KEY` with the matching endpoint."],
  ["Z.AI / GLM", "Hermes uses `GLM_API_KEY` for provider `zai`; compatible endpoints can be routed through Sankalp's endpoint provider."],
  ["Alibaba DashScope", "Use `DASHSCOPE_API_KEY`; Alibaba Coding Plan uses a separate compatible endpoint but the same key family."],
  ["Hugging Face", "Use `HF_TOKEN` with `https://router.huggingface.co/v1`."],
  ["xAI", "Use `XAI_API_KEY` with `https://api.x.ai/v1`."],
  ["NVIDIA NIM", "Use `NVIDIA_API_KEY` for hosted NIM or override to a local NIM `/v1` endpoint."],
  ["Ollama Cloud", "Use `OLLAMA_API_KEY`; local Ollama usually needs no key at `http://localhost:11434/v1`."],
  ["AWS Bedrock", "Hermes uses AWS credentials and Bedrock Converse. Sankalp does not yet have a native Bedrock adapter."],
  ["AI Gateway", "Hermes uses `AI_GATEWAY_API_KEY` for provider `ai-gateway`; use a compatible endpoint if the gateway exposes `/v1`."],
  ["OpenCode Zen / Go", "Hermes uses `OPENCODE_ZEN_API_KEY` or `OPENCODE_GO_API_KEY`."],
  ["Kilo Code", "Hermes uses `KILOCODE_API_KEY`."],
  ["Xiaomi MiMo", "Hermes uses `XIAOMI_API_KEY`."],
  ["Arcee AI", "Hermes uses `ARCEEAI_API_KEY`."],
  ["GMI Cloud", "Hermes uses `GMI_API_KEY`."],
  ["Tencent TokenHub", "Hermes uses `TOKENHUB_API_KEY`."],
];

const els = {
  railButtons: document.querySelectorAll(".rail-button"),
  screens: document.querySelectorAll(".screen"),
  sessions: document.querySelector("#sessions"),
  messages: document.querySelector("#messages"),
  activity: document.querySelector("#activity"),
  memory: document.querySelector("#memory"),
  memoryTree: document.querySelector("#memoryTree"),
  folderChildren: document.querySelector("#folderChildren"),
  folderTitle: document.querySelector("#folderTitle"),
  workspaceSummary: document.querySelector("#workspaceSummary"),
  viewAllNotes: document.querySelector("#viewAllNotes"),
  notesModal: document.querySelector("#notesModal"),
  notesModalTitle: document.querySelector("#notesModalTitle"),
  notesModalSummary: document.querySelector("#notesModalSummary"),
  notesPreviewGrid: document.querySelector("#notesPreviewGrid"),
  closeNotesModal: document.querySelector("#closeNotesModal"),
  memoryStatus: document.querySelector("#memoryStatus"),
  vaultList: document.querySelector("#vaultList"),
  obsidianVaultPath: document.querySelector("#obsidianVaultPath"),
  obsidianWorkspacePath: document.querySelector("#obsidianWorkspacePath"),
  saveMemoryConfig: document.querySelector("#saveMemoryConfig"),
  traits: document.querySelector("#traits"),
  selfProfile: document.querySelector("#selfProfile"),
  saveProfile: document.querySelector("#saveProfile"),
  provider: document.querySelector("#provider"),
  providerFields: document.querySelectorAll(".provider-fields"),
  compatiblePreset: document.querySelector("#compatiblePreset"),
  providerGuide: document.querySelector("#providerGuide"),
  localOpenAIBaseUrl: document.querySelector("#localOpenAIBaseUrl"),
  localOpenAIModel: document.querySelector("#localOpenAIModel"),
  localOpenAIKey: document.querySelector("#localOpenAIKey"),
  geminiKey: document.querySelector("#geminiKey"),
  geminiModel: document.querySelector("#geminiModel"),
  geminiModelsStatus: document.querySelector("#geminiModelsStatus"),
  codexModel: document.querySelector("#codexModel"),
  codexLogin: document.querySelector("#codexLogin"),
  codexStatus: document.querySelector("#codexStatus"),
  refreshCodexModels: document.querySelector("#refreshCodexModels"),
  openaiKey: document.querySelector("#openaiKey"),
  openaiModel: document.querySelector("#openaiModel"),
  openaiModelsStatus: document.querySelector("#openaiModelsStatus"),
  saveSettings: document.querySelector("#saveSettings"),
  settingsStatus: document.querySelector("#settingsStatus"),
  relaunchApp: document.querySelector("#relaunchApp"),
  appStatus: document.querySelector("#appStatus"),
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

function renderMemoryStatus(status) {
  if (!status) return;
  const workspace = status.workspace ? `Workspace: ${status.workspace}` : "Workspace: whole vault";
  const state = status.accessible ? "Accessible" : `Access issue: ${status.error || "unknown"}`;
  els.memoryStatus.textContent = `${state}. Vault: ${status.vault}. ${workspace}.`;
}

function renderMacOSAccess(info) {
  document.querySelector("#openFullDiskAccess").style.display = info && info.is_macos ? "inline-grid" : "none";
}

function renderMemoryTree(tree) {
  if (!tree || tree.error) {
    els.memoryTree.innerHTML = `<div class="empty">${escapeHtml(tree?.error || "No tree available.")}</div>`;
    return;
  }
  const rows = [];
  function walk(items, depth) {
    (items || []).forEach((item) => {
      rows.push(`<div class="tree-row" style="--depth:${depth}">
        <strong>${item.type === "directory" ? "Folder" : "Note"}: ${escapeHtml(item.name)}</strong>
        <span>${escapeHtml(item.path)}</span>
      </div>`);
      if (item.children) walk(item.children, depth + 1);
    });
  }
  walk(tree.items, 0);
  els.memoryTree.innerHTML = rows.join("") || `<div class="empty">No folders or notes found.</div>`;
}

function renderFolderOptions(folders, selected) {
  els.obsidianWorkspacePath.innerHTML = (folders || []).map((folder) => {
    const selectedAttr = folder.path === selected ? " selected" : "";
    const label = folder.path || "Whole vault";
    return `<option value="${escapeHtml(folder.path)}"${selectedAttr}>${escapeHtml(label)}</option>`;
  }).join("");
}

function renderFolderChildren(children) {
  if (!children || children.error) {
    els.folderTitle.textContent = "Workspace";
    els.workspaceSummary.textContent = "";
    els.folderChildren.innerHTML = `<div class="empty">${escapeHtml(children?.error || "No folder loaded.")}</div>`;
    return;
  }
  const selected = children.folder || "";
  els.folderTitle.textContent = selected ? `Workspace: ${selected}` : "Workspace: whole vault";
  els.workspaceSummary.textContent = `${children.items.length} immediate item${children.items.length === 1 ? "" : "s"}`;
  els.folderChildren.innerHTML = (children.items || []).map((item) => {
    if (item.type !== "directory") return "";
    return `<div class="folder-card" data-path="${escapeHtml(item.path)}">
      <div>
        <strong>${escapeHtml(item.name)}</strong>
        <span>${escapeHtml(item.path)}</span>
      </div>
      <div class="folder-card-actions">
        <button class="icon-button" data-open-path="${escapeHtml(item.path)}" title="Open folder" aria-label="Open folder">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 7h7l2 2h9v9a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V7Z"/><path d="M3 7V6a3 3 0 0 1 3-3h4l2 2h3"/></svg>
        </button>
        <button class="icon-button" data-view-notes-path="${escapeHtml(item.path)}" title="View all notes" aria-label="View all notes">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h9l3 3v15H6V3Z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 16h6"/></svg>
        </button>
      </div>
    </div>`;
  }).join("") || `<div class="empty">No subfolders or notes in this folder.</div>`;
  els.folderChildren.querySelectorAll("button[data-open-path]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api("/api/memory/open", {
        method: "POST",
        body: JSON.stringify({ path: button.dataset.openPath }),
      });
    });
  });
  els.folderChildren.querySelectorAll("button[data-view-notes-path]").forEach((button) => {
    button.addEventListener("click", () => loadNotesPreview(button.dataset.viewNotesPath));
  });
}

function renderNotesPreview(notes) {
  if (!notes || notes.error) {
    els.notesModalTitle.textContent = "Notes";
    els.notesModalSummary.textContent = notes?.error || "";
    els.notesPreviewGrid.innerHTML = "";
    return;
  }
  const folder = notes.folder || "whole vault";
  els.notesModalTitle.textContent = `Notes: ${folder}`;
  els.notesModalSummary.textContent = `${notes.notes.length} note${notes.notes.length === 1 ? "" : "s"} found recursively`;
  els.notesPreviewGrid.innerHTML = (notes.notes || []).map((note) => {
    return `<article class="note-preview-card">
      <strong>${escapeHtml(note.name)}</strong>
      <span>${escapeHtml(note.path)}</span>
      <pre>${escapeHtml(note.preview || "")}</pre>
      <button data-open-path="${escapeHtml(note.path)}">Open in Obsidian</button>
    </article>`;
  }).join("") || `<div class="empty">No notes found.</div>`;
  els.notesPreviewGrid.querySelectorAll("button[data-open-path]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api("/api/memory/open", {
        method: "POST",
        body: JSON.stringify({ path: button.dataset.openPath }),
      });
    });
  });
}

function renderVaults(vaults) {
  els.vaultList.innerHTML = (vaults || []).map((vault) => {
    const status = vault.accessible ? "Accessible" : "Blocked by macOS permissions";
    return `<div class="vault-option">
      <div>
        <strong>${escapeHtml(vault.open ? "Open vault" : "Vault")}</strong>
        <span>${escapeHtml(vault.path)}</span>
        <span>${escapeHtml(status)}</span>
      </div>
      <button data-vault-path="${escapeHtml(vault.path)}">Use</button>
    </div>`;
  }).join("") || `<div class="empty">No Obsidian vaults discovered.</div>`;
  els.vaultList.querySelectorAll("button[data-vault-path]").forEach((button) => {
    button.addEventListener("click", () => {
      els.obsidianVaultPath.value = button.dataset.vaultPath;
    });
  });
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
  els.obsidianVaultPath.value = settings.obsidian_vault_path || "";
  els.geminiKey.placeholder = settings.has_gemini_api_key ? "Gemini key saved" : "Leave blank to keep existing key";
  els.localOpenAIKey.placeholder = settings.has_local_openai_api_key ? "Local key saved" : "Optional";
  els.openaiKey.placeholder = settings.has_openai_api_key ? "OpenAI key saved" : "Leave blank to keep existing key";
  updateProviderSummary();
  updateProviderFields();
  loadProviderModels("openai", settings.openai_model || "gpt-5.5");
  loadProviderModels("gemini", settings.gemini_model || "gemini-3-flash-preview");
  loadProviderModels("codex", settings.codex_model || "");
  loadCodexStatus();
}

function updateProviderSummary() {
  const label = {
    local: "Local fallback",
    local_openai: `OpenAI-compatible (${els.localOpenAIModel.value || "no model"})`,
    codex: "Codex CLI",
    gemini: `Gemini API (${els.geminiModel.value})`,
    openai: `OpenAI API (${els.openaiModel.value})`,
  }[els.provider.value] || "Local fallback";
  els.providerStatus.textContent = label;
}

function updateProviderFields() {
  els.providerFields.forEach((block) => {
    block.classList.toggle("active", block.dataset.providerFields === els.provider.value);
  });
}

function renderProviderGuide() {
  els.providerGuide.innerHTML = providerGuide.map(([name, detail]) => {
    return `<div class="guide-card"><strong>${escapeHtml(name)}</strong><span>${escapeHtml(detail)}</span></div>`;
  }).join("");
}

function setModelOptions(select, models, selected) {
  const selectedValue = selected || (models[0] && models[0].id) || "";
  const normalized = [...(models || [])];
  if (selectedValue && !normalized.some((model) => model.id === selectedValue)) {
    normalized.unshift({ id: selectedValue, label: selectedValue });
  }
  select.innerHTML = normalized.map((model) => {
    const attr = model.id === selectedValue ? " selected" : "";
    return `<option value="${escapeHtml(model.id)}"${attr}>${escapeHtml(model.label || model.id)}</option>`;
  }).join("");
}

async function loadProviderModels(provider, selected) {
  const data = await api(`/api/models?provider=${encodeURIComponent(provider)}`);
  const payload = data.models || {};
  if (provider === "openai") {
    setModelOptions(els.openaiModel, payload.models || [], selected);
    els.openaiModelsStatus.textContent = `Models: ${payload.source || "unknown"}${payload.error ? ` (${payload.error})` : ""}`;
    updateProviderSummary();
  }
  if (provider === "gemini") {
    setModelOptions(els.geminiModel, payload.models || [], selected);
    els.geminiModelsStatus.textContent = `Models: ${payload.source || "unknown"}${payload.error ? ` (${payload.error})` : ""}`;
    updateProviderSummary();
  }
  if (provider === "codex") {
    setModelOptions(els.codexModel, payload.models || [], selected);
    updateProviderSummary();
  }
}

async function loadCodexStatus() {
  const data = await api("/api/codex/status");
  const status = data.codex || {};
  els.codexStatus.textContent = status.logged_in ? "Codex is logged in." : status.login_running ? "Codex login is running." : "Codex is not logged in.";
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
  renderMemoryStatus(data.status);
}

async function loadMemoryTree() {
  const data = await api("/api/memory/tree");
  renderMemoryTree(data.tree);
  renderMemoryStatus(data.status);
}

async function loadMemoryFolders() {
  const data = await api("/api/memory/folders");
  renderFolderOptions(data.folders, settings.obsidian_workspace_path || "");
  renderMemoryStatus(data.status);
}

async function loadFolderChildren(folder) {
  const data = await api(`/api/memory/children?folder=${encodeURIComponent(folder || "")}`);
  renderFolderChildren(data.children);
  renderMemoryStatus(data.status);
}

async function loadNotesPreview(folder) {
  const target = folder ?? els.obsidianWorkspacePath.value;
  const data = await api(`/api/memory/notes?folder=${encodeURIComponent(target || "")}`);
  renderNotesPreview(data.notes);
  els.notesModal.classList.add("active");
  els.notesModal.setAttribute("aria-hidden", "false");
}

async function loadVaults() {
  const data = await api("/api/obsidian/vaults");
  renderVaults(data.vaults);
}

async function loadMacOSStatus() {
  const data = await api("/api/macos/status");
  renderMacOSAccess(data.macos);
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
    if (data.memory_status) renderMemoryStatus(data.memory_status);
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
    els.screens.forEach((screen) => screen.classList.toggle("active", screen.id === `screen${button.dataset.panel[0].toUpperCase()}${button.dataset.panel.slice(1)}`));
  });
});
els.provider.addEventListener("change", () => {
  updateProviderFields();
  updateProviderSummary();
});
els.geminiModel.addEventListener("change", updateProviderSummary);
els.codexModel.addEventListener("change", updateProviderSummary);
els.openaiModel.addEventListener("change", updateProviderSummary);
els.compatiblePreset.addEventListener("change", () => {
  const preset = compatiblePresets[els.compatiblePreset.value];
  if (!preset) return;
  els.localOpenAIBaseUrl.value = preset.baseUrl;
  if (preset.model) els.localOpenAIModel.value = preset.model;
  updateProviderSummary();
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
els.codexLogin.addEventListener("click", async () => {
  els.codexStatus.textContent = "Starting Codex login...";
  const data = await api("/api/codex/login", { method: "POST", body: "{}" });
  if (data.codex && data.codex.ok === false) {
    els.codexStatus.textContent = data.codex.error || "Could not start Codex login.";
    return;
  }
  await loadCodexStatus();
});
els.refreshCodexModels.addEventListener("click", async () => {
  await loadCodexStatus();
  await loadProviderModels("codex", els.codexModel.value);
});
els.relaunchApp.addEventListener("click", async () => {
  els.appStatus.textContent = "Relaunching...";
  els.relaunchApp.disabled = true;
  await api("/api/app/relaunch", { method: "POST", body: "{}" });
  setTimeout(() => {
    window.location.reload();
  }, 2500);
});
els.saveMemoryConfig.addEventListener("click", async () => {
  els.saveMemoryConfig.textContent = "Syncing...";
  const data = await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({
      obsidian_vault_path: els.obsidianVaultPath.value,
      obsidian_workspace_path: els.obsidianWorkspacePath.value,
    }),
  });
  renderSettings(data.settings);
  if (data.memory_status) renderMemoryStatus(data.memory_status);
  await Promise.all([loadMemory(), loadMemoryFolders(), loadFolderChildren(els.obsidianWorkspacePath.value), loadVaults()]);
  els.saveMemoryConfig.textContent = "Sync vault";
});
els.obsidianWorkspacePath.addEventListener("change", () => {
  loadFolderChildren(els.obsidianWorkspacePath.value);
});
els.viewAllNotes.addEventListener("click", () => loadNotesPreview(els.obsidianWorkspacePath.value));
els.closeNotesModal.addEventListener("click", () => {
  els.notesModal.classList.remove("active");
  els.notesModal.setAttribute("aria-hidden", "true");
});
document.querySelector("#openFullDiskAccess").addEventListener("click", async () => {
  await api("/api/macos/open-full-disk-access", { method: "POST", body: "{}" });
});
els.notesModal.addEventListener("click", (event) => {
  if (event.target === els.notesModal) {
    els.notesModal.classList.remove("active");
    els.notesModal.setAttribute("aria-hidden", "true");
  }
});
els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    els.form.requestSubmit();
  }
});

renderProviderGuide();

Promise.all([loadSessions(), loadSettings()]).then(async () => {
  await Promise.all([loadMemory(), loadMemoryFolders(), loadFolderChildren(settings.obsidian_workspace_path || ""), loadVaults(), loadMacOSStatus(), loadProfile()]);
  els.input.focus();
});
