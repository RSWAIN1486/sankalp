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
  memoryStatus: document.querySelector("#memoryStatus"),
  macosAccess: document.querySelector("#macosAccess"),
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

function renderMemoryStatus(status) {
  if (!status) return;
  const workspace = status.workspace ? `Workspace: ${status.workspace}` : "Workspace: whole vault";
  const state = status.accessible ? "Accessible" : `Access issue: ${status.error || "unknown"}`;
  els.memoryStatus.textContent = `${state}. Vault: ${status.vault}. ${workspace}.`;
}

function renderMacOSAccess(info) {
  if (!info || !info.is_macos) {
    els.macosAccess.innerHTML = "";
    return;
  }
  els.macosAccess.innerHTML = `
    <button id="installSankalpApp">${info.installed ? "Reinstall Sankalp.app" : "Install Sankalp.app"}</button>
    <button id="openFullDiskAccess">Open Full Disk Access</button>
  `;
  document.querySelector("#installSankalpApp").addEventListener("click", async () => {
    const button = document.querySelector("#installSankalpApp");
    button.textContent = "Installing...";
    const data = await api("/api/macos/install-app", { method: "POST", body: "{}" });
    button.textContent = data.macos?.ok ? "Installed in ~/Applications" : "Install failed";
    await loadMacOSStatus();
  });
  document.querySelector("#openFullDiskAccess").addEventListener("click", async () => {
    await api("/api/macos/open-full-disk-access", { method: "POST", body: "{}" });
  });
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
  els.geminiModel.value = settings.gemini_model || "gemini-2.5-flash";
  els.codexModel.value = settings.codex_model || "";
  els.openaiModel.value = settings.openai_model || "gpt-5.5";
  els.obsidianVaultPath.value = settings.obsidian_vault_path || "";
  els.obsidianWorkspacePath.value = settings.obsidian_workspace_path || "";
  els.geminiKey.placeholder = settings.has_gemini_api_key ? "Gemini key saved" : "Leave blank to keep existing key";
  els.localOpenAIKey.placeholder = settings.has_local_openai_api_key ? "Local key saved" : "Optional";
  els.openaiKey.placeholder = settings.has_openai_api_key ? "OpenAI key saved" : "Leave blank to keep existing key";
  const label = {
    local: "Local fallback",
    local_openai: `OpenAI-compatible (${els.localOpenAIModel.value || "no model"})`,
    codex: "Codex CLI",
    gemini: `Gemini API (${els.geminiModel.value})`,
    openai: `OpenAI API (${els.openaiModel.value})`,
  }[els.provider.value] || "Local fallback";
  els.providerStatus.textContent = label;
  updateProviderFields();
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
els.provider.addEventListener("change", updateProviderFields);
els.compatiblePreset.addEventListener("change", () => {
  const preset = compatiblePresets[els.compatiblePreset.value];
  if (!preset) return;
  els.localOpenAIBaseUrl.value = preset.baseUrl;
  if (preset.model) els.localOpenAIModel.value = preset.model;
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
  await Promise.all([loadMemory(), loadMemoryTree(), loadVaults()]);
  els.saveMemoryConfig.textContent = "Sync vault";
});
els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    els.form.requestSubmit();
  }
});

renderProviderGuide();

Promise.all([loadSessions(), loadMemory(), loadMemoryTree(), loadVaults(), loadMacOSStatus(), loadProfile(), loadSettings()]).then(() => {
  els.input.focus();
});
