import { derived, get, writable } from "svelte/store";
import { api, streamChat } from "$lib/services/api";
import { db, loadComposerPreference, saveComposerPreference } from "$lib/storage/db";
import type { AppUpdateStatus, ChatMessage, ComposerOptions, ModelOption, ProviderModels, SessionSummary, Settings, StreamEvent, ToolCall } from "$lib/types";

type ModelCatalogEntry = ProviderModels & {
  loading?: boolean;
  loaded?: boolean;
};

type ChatState = {
  sessions: SessionSummary[];
  currentSessionId: string | null;
  messages: ChatMessage[];
  toolCalls: ToolCall[];
  settings: Settings;
  status: string;
  search: string;
  draft: string;
  editIndex: number | null;
  composer: ComposerOptions;
  composerModelsByProvider: Record<string, string>;
  modelCatalog: Record<string, ModelCatalogEntry>;
  settingsOpen: boolean;
  settingsTab: "provider" | "memory" | "profile" | "app" | "capabilities";
  sidebarCollapsed: boolean;
  appUpdate: AppUpdateStatus | null;
  updateBannerDismissed: boolean;
};

const providerOptions: Array<{ id: string; label: string }> = [
  { id: "local", label: "Local fallback" },
  { id: "local_openai", label: "OpenAI-compatible" },
  { id: "codex", label: "Codex CLI" },
  { id: "gemini", label: "Gemini API" },
  { id: "openai", label: "OpenAI API" }
];

const providerLabels = Object.fromEntries(providerOptions.map((provider) => [provider.id, provider.label]));

const defaultComposer: ComposerOptions = {
  provider: "local",
  model: "",
  reasoning_effort: "auto"
};

const initialState: ChatState = {
  sessions: [],
  currentSessionId: null,
  messages: [],
  toolCalls: [],
  settings: {},
  status: "Ready",
  search: "",
  draft: "",
  editIndex: null,
  composer: defaultComposer,
  composerModelsByProvider: {},
  modelCatalog: {},
  settingsOpen: false,
  settingsTab: "provider",
  sidebarCollapsed: false,
  appUpdate: null,
  updateBannerDismissed: false
};

export const chatState = writable<ChatState>(initialState);

export const visibleSessions = derived(chatState, ($state) => {
  const query = $state.search.trim().toLowerCase();
  if (!query) return $state.sessions;
  return $state.sessions.filter((session) => session.title.toLowerCase().includes(query));
});

export const providerLabel = derived(chatState, ($state) => {
  const provider = $state.composer.provider || $state.settings.provider || "local";
  const model = $state.composer.model || modelForProvider(provider, $state.settings);
  return model ? `${providerLabels[provider] || provider} / ${model}` : providerLabels[provider] || provider;
});

export const composerModelOptions = derived(chatState, ($state) => {
  return modelOptionsForProvider($state.composer.provider, $state);
});

export async function initializeChat(): Promise<void> {
  const [sessionsData, settingsData, preference] = await Promise.all([
    api<{ sessions: SessionSummary[] }>("/api/sessions"),
    api<{ settings: Settings }>("/api/settings"),
    loadComposerPreference()
  ]);
  const settings = settingsData.settings || {};
  const provider = preference.provider || settings.provider || "local";
  const modelsByProvider = {
    ...defaultModelsByProvider(settings),
    ...(preference.models_by_provider || {})
  };
  const composer = {
    ...defaultComposer,
    provider,
    model: selectedModelForProvider(provider, settings, modelsByProvider),
    reasoning_effort: preference.reasoning_effort || "auto"
  };
  chatState.update((state) => ({
    ...state,
    sessions: sessionsData.sessions || [],
    settings,
    composer,
    composerModelsByProvider: modelsByProvider
  }));
  void ensureProviderModels(provider);
  void Promise.all(["local_openai", "codex", "gemini", "openai"].map((item) => ensureProviderModels(item)));
  void checkAppUpdate();
  await db.sessions.bulkPut((sessionsData.sessions || []).map((session) => ({ ...session, cached_at: Date.now() })));
}

export async function createSession(): Promise<void> {
  const data = await api<{ session: SessionSummary; messages: ChatMessage[]; tool_calls: ToolCall[] }>("/api/session/new", {
    method: "POST",
    body: "{}"
  });
  chatState.update((state) => ({
    ...state,
    currentSessionId: data.session.session_id,
    messages: data.messages || [],
    toolCalls: data.tool_calls || [],
    status: "Ready"
  }));
  await loadSessions();
}

export async function loadSessions(): Promise<void> {
  const data = await api<{ sessions: SessionSummary[] }>("/api/sessions");
  chatState.update((state) => ({ ...state, sessions: data.sessions || [] }));
  await db.sessions.bulkPut((data.sessions || []).map((session) => ({ ...session, cached_at: Date.now() })));
}

export async function openSession(sessionId: string): Promise<void> {
  const data = await api<{ session: SessionSummary; messages: ChatMessage[]; tool_calls: ToolCall[] }>(
    `/api/session?id=${encodeURIComponent(sessionId)}`
  );
  chatState.update((state) => ({
    ...state,
    currentSessionId: data.session.session_id,
    messages: data.messages || [],
    toolCalls: data.tool_calls || [],
    status: "Ready"
  }));
}

export async function sendMessage(text: string, editIndex: number | null = null): Promise<void> {
  const trimmed = text.trim();
  if (!trimmed) return;
  const snapshot = get(chatState);
  const pendingAssistant: ChatMessage = { role: "assistant", content: "", pending: true, status: "Thinking" };

  chatState.update((state) => ({
    ...state,
    messages: [
      ...(editIndex === null ? state.messages : state.messages.slice(0, editIndex)),
      { role: "user", content: trimmed },
      pendingAssistant
    ],
    draft: "",
    editIndex: null,
    status: "Thinking"
  }));

  try {
    await streamChat(
      {
        session_id: snapshot.currentSessionId,
        message: trimmed,
        attachments: [],
        options: snapshot.composer,
        edit_index: editIndex
      },
      handleStreamEvent
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Request failed";
    replacePending({ role: "assistant", content: `Request failed: ${message}` });
  } finally {
    chatState.update((state) => ({ ...state, status: "Ready" }));
  }
}

export async function updateComposer(next: Partial<ComposerOptions>): Promise<void> {
  let composer: ComposerOptions = defaultComposer;
  let modelsByProvider: Record<string, string> = {};
  chatState.update((state) => {
    const providerChanged = typeof next.provider === "string" && next.provider !== state.composer.provider;
    const provider = next.provider || state.composer.provider || state.settings.provider || "local";
    modelsByProvider = { ...state.composerModelsByProvider };

    if (typeof next.model === "string") {
      modelsByProvider[provider] = next.model;
    }

    const model = providerChanged
      ? selectedModelForProvider(provider, state.settings, modelsByProvider, state.modelCatalog)
      : typeof next.model === "string"
        ? next.model
        : state.composer.model;

    if (providerChanged) {
      modelsByProvider[provider] = model;
    }

    composer = { ...state.composer, ...next, provider, model };
    return { ...state, composer, composerModelsByProvider: modelsByProvider };
  });
  await saveComposerPreference({ ...composer, models_by_provider: modelsByProvider });
  if (next.provider) void ensureProviderModels(next.provider);
}

export function setSearch(search: string): void {
  chatState.update((state) => ({ ...state, search }));
}

export function setDraft(draft: string): void {
  chatState.update((state) => ({ ...state, draft }));
}

export function editMessage(index: number): void {
  const state = get(chatState);
  const message = state.messages[index];
  if (!message) return;
  chatState.update((current) => ({ ...current, draft: message.content || "", editIndex: index }));
}

export async function deleteMessagesFrom(index: number): Promise<void> {
  const state = get(chatState);
  if (!state.currentSessionId) {
    chatState.update((current) => ({ ...current, messages: current.messages.slice(0, index) }));
    return;
  }
  const data = await api<{ session: SessionSummary; messages: ChatMessage[]; tool_calls: ToolCall[] }>("/api/session/truncate", {
    method: "POST",
    body: JSON.stringify({ session_id: state.currentSessionId, index })
  });
  chatState.update((current) => ({
    ...current,
    messages: data.messages || [],
    toolCalls: data.tool_calls || [],
    currentSessionId: data.session.session_id
  }));
  await loadSessions();
}

export async function regenerateFrom(index: number): Promise<void> {
  const state = get(chatState);
  const userIndex = state.messages[index]?.role === "user"
    ? index
    : state.messages.slice(0, index).findLastIndex((message) => message.role === "user");
  const userMessage = state.messages[userIndex];
  if (!userMessage) return;
  await sendMessage(userMessage.content || "", userIndex);
}

export async function renameSession(sessionId: string, title: string): Promise<void> {
  await api("/api/session/rename", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, title })
  });
  await loadSessions();
}

export async function deleteSession(sessionId: string): Promise<void> {
  await api("/api/session/delete", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId })
  });
  chatState.update((state) => {
    if (state.currentSessionId !== sessionId) return state;
    return { ...state, currentSessionId: null, messages: [], toolCalls: [], draft: "", editIndex: null };
  });
  await loadSessions();
}

export function toggleSidebar(): void {
  chatState.update((state) => ({ ...state, sidebarCollapsed: !state.sidebarCollapsed }));
}

export function toggleSettings(): void {
  chatState.update((state) => ({ ...state, settingsOpen: !state.settingsOpen }));
}

export function openSettings(tab: "provider" | "memory" | "profile" | "app" | "capabilities" = "provider"): void {
  chatState.update((state) => ({ ...state, settingsOpen: true, settingsTab: tab }));
}

export function setSettingsTab(tab: "provider" | "memory" | "profile" | "app" | "capabilities"): void {
  chatState.update((state) => ({ ...state, settingsTab: tab }));
}

export function closeSettings(): void {
  chatState.update((state) => ({ ...state, settingsOpen: false }));
}

export function dismissUpdateBanner(): void {
  const version = get(chatState).appUpdate?.latest_version || "";
  if (version) localStorage.setItem("sankalp-update-dismissed-version", version);
  chatState.update((state) => ({ ...state, updateBannerDismissed: true }));
}

export async function checkAppUpdate(force = false): Promise<void> {
  const lastChecked = Number(localStorage.getItem("sankalp-update-last-checked") || "0");
  const oneDay = 24 * 60 * 60 * 1000;
  if (!force && Date.now() - lastChecked < oneDay) {
    const cached = localStorage.getItem("sankalp-update-status");
    if (cached) {
      try {
        const update = JSON.parse(cached) as AppUpdateStatus | null;
        const dismissedVersion = localStorage.getItem("sankalp-update-dismissed-version") || "";
        chatState.update((state) => ({
          ...state,
          appUpdate: update,
          updateBannerDismissed: Boolean(update?.update_available && update.latest_version && dismissedVersion === update.latest_version)
        }));
      } catch {
        localStorage.removeItem("sankalp-update-status");
      }
    }
    return;
  }

  try {
    const data = await api<{ update: AppUpdateStatus }>("/api/app/update");
    localStorage.setItem("sankalp-update-last-checked", String(Date.now()));
    localStorage.setItem("sankalp-update-status", JSON.stringify(data.update || null));
    const dismissedVersion = localStorage.getItem("sankalp-update-dismissed-version") || "";
    const latestVersion = data.update?.latest_version || "";
    chatState.update((state) => ({
      ...state,
      appUpdate: data.update || null,
      updateBannerDismissed: Boolean(data.update?.update_available && latestVersion && dismissedVersion === latestVersion)
    }));
  } catch {
    if (force) {
      chatState.update((state) => ({
        ...state,
        appUpdate: { ok: false, error: "Could not check for updates." }
      }));
    }
  }
}

export async function startAppUpdate(): Promise<void> {
  const data = await api<{ update: AppUpdateStatus }>("/api/app/update", { method: "POST", body: "{}" });
  chatState.update((state) => ({ ...state, appUpdate: data.update || state.appUpdate }));
  if (data.update?.ok) {
    void waitForBackendAndRefresh();
  }
}

async function waitForBackendAndRefresh(): Promise<void> {
  const start = Date.now();
  const timeoutMs = 8 * 60 * 1000;
  const initialDelayMs = 2000;
  const retryDelayMs = 1500;
  let sawBackendRestart = false;

  await delay(initialDelayMs);
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(`/api/health?t=${Date.now()}`, {
        cache: "no-store",
        headers: { "cache-control": "no-store" }
      });
      if (response.ok && sawBackendRestart) {
        window.location.reload();
        return;
      }
    } catch {
      sawBackendRestart = true;
    }
    await delay(retryDelayMs);
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function refreshSettings(settings: Settings): void {
  chatState.update((state) => {
    const defaults = defaultModelsByProvider(settings);
    const modelsByProvider = { ...defaults, ...state.composerModelsByProvider };
    const provider = state.composer.provider || settings.provider || "local";
    const model = state.composer.model || selectedModelForProvider(provider, settings, modelsByProvider, state.modelCatalog);
    return {
      ...state,
      settings,
      composerModelsByProvider: modelsByProvider,
      composer: { ...state.composer, provider, model }
    };
  });
}

export async function ensureProviderModels(provider: string, force = false): Promise<void> {
  if (!["local_openai", "codex", "gemini", "openai"].includes(provider)) return;
  const current = get(chatState).modelCatalog[provider];
  if (current?.loading || (current?.loaded && !force)) return;
  chatState.update((state) => ({
    ...state,
    modelCatalog: {
      ...state.modelCatalog,
      [provider]: {
        provider,
        models: current?.models || [],
        source: current?.source,
        error: current?.error,
        loading: true,
        loaded: false
      }
    }
  }));
  try {
    const data = await api<{ models: ProviderModels }>(`/api/models?provider=${encodeURIComponent(provider)}`);
    const payload = normalizeProviderModels(provider, data.models);
    chatState.update((state) => {
      const catalog = {
        ...state.modelCatalog,
        [provider]: { ...payload, loading: false, loaded: true }
      };
      if (state.composer.provider !== provider) return { ...state, modelCatalog: catalog };
      const selected = selectedModelForProvider(provider, state.settings, state.composerModelsByProvider, catalog);
      return {
        ...state,
        modelCatalog: catalog,
        composer: { ...state.composer, model: selected },
        composerModelsByProvider: { ...state.composerModelsByProvider, [provider]: selected }
      };
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not load models";
    chatState.update((state) => ({
      ...state,
      modelCatalog: {
        ...state.modelCatalog,
        [provider]: { provider, models: [], source: "error", error: message, loading: false, loaded: true }
      }
    }));
  }
}

function handleStreamEvent(item: StreamEvent): void {
  if (item.event === "status") {
    chatState.update((state) => ({
      ...state,
      status: item.data.detail || item.data.label || "Thinking",
      messages: state.messages.map((message, index) =>
        index === state.messages.length - 1 && message.pending
          ? { ...message, status: item.data.detail || item.data.label || "Thinking" }
          : message
      )
    }));
  }
  if (item.event === "session") {
    chatState.update((state) => ({
      ...state,
      currentSessionId: item.data.session.session_id,
      toolCalls: item.data.tool_calls || []
    }));
  }
  if (item.event === "delta") {
    chatState.update((state) => ({
      ...state,
      messages: state.messages.map((message, index) =>
        index === state.messages.length - 1 && message.pending
          ? { ...message, content: message.content + (item.data.text || "") }
          : message
      )
    }));
  }
  if (item.event === "done") {
    chatState.update((state) => ({
      ...state,
      currentSessionId: item.data.session.session_id,
      messages: item.data.messages || state.messages,
      toolCalls: item.data.tool_calls || [],
      status: "Ready"
    }));
    void loadSessions();
  }
  if (item.event === "error") {
    replacePending({ role: "assistant", content: item.data.error || "Request failed." });
  }
}

function replacePending(replacement: ChatMessage): void {
  chatState.update((state) => ({
    ...state,
    messages: state.messages.map((message, index) =>
      index === state.messages.length - 1 && message.pending ? replacement : message
    )
  }));
}

function modelForProvider(provider: string | undefined, settings: Settings): string {
  if (provider === "local_openai") return settings.local_openai_model || "";
  if (provider === "codex") return settings.codex_model || "";
  if (provider === "gemini") return settings.gemini_model || "";
  if (provider === "openai") return settings.openai_model || "";
  return "";
}

function defaultModelsByProvider(settings: Settings): Record<string, string> {
  return {
    local: "",
    local_openai: settings.local_openai_model || "",
    codex: settings.codex_model || "",
    gemini: settings.gemini_model || "",
    openai: settings.openai_model || ""
  };
}

function selectedModelForProvider(
  provider: string,
  settings: Settings,
  modelsByProvider: Record<string, string>,
  catalog: Record<string, ModelCatalogEntry> = {}
): string {
  if (provider === "local") return "";
  const saved = modelsByProvider[provider] || "";
  const configured = modelForProvider(provider, settings);
  const available = catalog[provider]?.models || [];
  if (saved && (!available.length || available.some((model) => model.id === saved))) return saved;
  if (configured && (!available.length || available.some((model) => model.id === configured))) return configured;
  return available[0]?.id || saved || configured || "";
}

function modelOptionsForProvider(provider: string, state: ChatState): ModelOption[] {
  if (provider === "local") return [{ id: "", label: "No model" }];
  const selected = state.composer.model || selectedModelForProvider(provider, state.settings, state.composerModelsByProvider, state.modelCatalog);
  const models = [...(state.modelCatalog[provider]?.models || [])];
  if (provider === "local_openai" && !models.length && selected) {
    models.push({ id: selected, label: selected });
  }
  if (selected && !models.some((model) => model.id === selected)) {
    models.unshift({ id: selected, label: selected });
  }
  return models;
}

function normalizeProviderModels(provider: string, payload?: ProviderModels): ProviderModels {
  const models = (payload?.models || [])
    .filter((model) => model && model.id)
    .map((model) => ({ id: model.id, label: model.label || model.id }));
  return {
    provider: payload?.provider || provider,
    models,
    source: payload?.source || "unknown",
    error: payload?.error || null
  };
}
