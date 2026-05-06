export type Role = "user" | "assistant" | "system" | "tool";

export type ChatMessage = {
  role: Role;
  content: string;
  pending?: boolean;
  status?: string;
  tools?: string;
  reasoning?: string;
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

export type ComposerPreference = Partial<ComposerOptions> & {
  models_by_provider?: Record<string, string>;
};

export type StreamDiagnostics = {
  enabled: boolean;
  active_provider: string;
  started_at: number | null;
  last_event_at: number | null;
  events: Record<string, number>;
  chars: {
    delta: number;
    reasoning: number;
  };
};

export type ModelOption = {
  id: string;
  label?: string;
};

export type ProviderModels = {
  provider: string;
  models: ModelOption[];
  source?: string;
  error?: string | null;
};

export type AppUpdateManifest = {
  version?: string;
  channel?: string;
  title?: string;
  notes?: string[];
  minimum_supported_version?: string;
};

export type AppUpdateStatus = {
  ok?: boolean;
  current_version?: string;
  current_commit?: string;
  latest_version?: string;
  latest?: AppUpdateManifest;
  update_available?: boolean;
  checked_at?: number;
  manifest_url?: string;
  error?: string;
  message?: string;
};

export type StreamEvent =
  | { event: "status"; data: { label?: string; detail?: string } }
  | { event: "session"; data: { session: SessionSummary; tool_calls?: ToolCall[] } }
  | { event: "reasoning"; data: { text?: string } }
  | { event: "delta"; data: { text?: string } }
  | { event: "done"; data: { session: SessionSummary; messages: ChatMessage[]; tool_calls?: ToolCall[] } }
  | { event: "error"; data: { error?: string } };

export type CapabilitySkill = {
  id: string;
  name: string;
  description: string;
  path: string;
  entrypoint: string;
  category?: string;
  version?: string;
  commands?: string[];
  triggers?: string[];
  requires?: Record<string, unknown>;
};

export type CapabilityTool = {
  name: string;
  description: string;
};

export type CapabilityCommand = {
  command: string;
  description: string;
};

export type Capabilities = {
  skills: CapabilitySkill[];
  tools: CapabilityTool[];
  commands: CapabilityCommand[];
};
