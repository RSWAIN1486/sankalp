export type Role = "user" | "assistant" | "system" | "tool";

export type ChatMessage = {
  role: Role;
  content: string;
  pending?: boolean;
  status?: string;
  tools?: string;
};

export type SessionSummary = {
  session_id: string;
  title: string;
  message_count: number;
  updated_at?: string;
};

export type ToolCall = {
  name: string;
  status: string;
  input?: unknown;
  output?: unknown;
  started_at?: string;
  finished_at?: string;
};

export type Settings = {
  provider?: string;
  local_openai_base_url?: string;
  local_openai_model?: string;
  local_openai_api_key?: string;
  has_local_openai_api_key?: boolean;
  gemini_model?: string;
  gemini_api_key?: string;
  has_gemini_api_key?: boolean;
  codex_model?: string;
  openai_model?: string;
  openai_api_key?: string;
  has_openai_api_key?: boolean;
  obsidian_vault_path?: string;
  obsidian_workspace_path?: string;
};

export type ComposerOptions = {
  provider: string;
  model: string;
  reasoning_effort: string;
};

export type StreamEvent =
  | { event: "status"; data: { label?: string; detail?: string } }
  | { event: "session"; data: { session: SessionSummary; tool_calls?: ToolCall[] } }
  | { event: "delta"; data: { text?: string } }
  | { event: "done"; data: { session: SessionSummary; messages: ChatMessage[]; tool_calls?: ToolCall[] } }
  | { event: "error"; data: { error?: string } };
