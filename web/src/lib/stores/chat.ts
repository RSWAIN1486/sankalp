import { derived, get, writable } from "svelte/store";
import { api, streamChat } from "$lib/services/api";
import { db, loadComposerPreference, saveComposerPreference } from "$lib/storage/db";
import type { ChatMessage, ComposerOptions, SessionSummary, Settings, StreamEvent, ToolCall } from "$lib/types";

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
  settingsOpen: boolean;
  settingsTab: "provider" | "memory" | "profile" | "app";
  sidebarCollapsed: boolean;
};

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
  settingsOpen: false,
  settingsTab: "provider",
  sidebarCollapsed: false
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
  const labels: Record<string, string> = {
    local: "Local fallback",
    local_openai: "OpenAI-compatible",
    codex: "Codex CLI",
    gemini: "Gemini API",
    openai: "OpenAI API"
  };
  return model ? `${labels[provider] || provider} / ${model}` : labels[provider] || provider;
});

export async function initializeChat(): Promise<void> {
  const [sessionsData, settingsData, preference] = await Promise.all([
    api<{ sessions: SessionSummary[] }>("/api/sessions"),
    api<{ settings: Settings }>("/api/settings"),
    loadComposerPreference()
  ]);
  const settings = settingsData.settings || {};
  const composer = {
    ...defaultComposer,
    provider: preference.provider || settings.provider || "local",
    model: preference.model || modelForProvider(preference.provider || settings.provider || "local", settings),
    reasoning_effort: preference.reasoning_effort || "auto"
  };
  chatState.update((state) => ({
    ...state,
    sessions: sessionsData.sessions || [],
    settings,
    composer
  }));
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
  chatState.update((state) => {
    composer = { ...state.composer, ...next };
    return { ...state, composer };
  });
  await saveComposerPreference(composer);
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

export function openSettings(tab: "provider" | "memory" | "profile" | "app" = "provider"): void {
  chatState.update((state) => ({ ...state, settingsOpen: true, settingsTab: tab }));
}

export function setSettingsTab(tab: "provider" | "memory" | "profile" | "app"): void {
  chatState.update((state) => ({ ...state, settingsTab: tab }));
}

export function closeSettings(): void {
  chatState.update((state) => ({ ...state, settingsOpen: false }));
}

export function refreshSettings(settings: Settings): void {
  chatState.update((state) => ({ ...state, settings }));
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
