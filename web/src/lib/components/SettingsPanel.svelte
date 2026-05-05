<script lang="ts">
  import { onMount } from "svelte";
  import { Folder, KeyRound, RotateCw, ShieldCheck, User, X } from "@lucide/svelte";
  import { api } from "$lib/services/api";
  import { chatState, closeSettings, refreshSettings, setSettingsTab } from "$lib/stores/chat";
  import type { Settings } from "$lib/types";

  type Tab = "provider" | "memory" | "profile" | "app";
  type Trait = { id: string; title: string; confidence: string; text: string; evidence?: string };
  type Profile = { self_profile?: string; traits?: Trait[] };
  type FolderOption = { path: string };
  type MemoryChild = { name: string; path: string; type: "directory" | "file" };
  type FolderChildren = { folder?: string; items: MemoryChild[]; error?: string };
  type NotePreview = { name: string; path: string; preview?: string };
  type NotesPreview = { folder?: string; notes: NotePreview[]; error?: string };
  type Vault = { path: string; open?: boolean; accessible?: boolean };
  type MemoryStatus = { accessible?: boolean; error?: string; vault?: string; workspace?: string };

  let settings: Settings = {};
  let profile: Profile = {};
  let folders: FolderOption[] = [];
  let children: FolderChildren = { items: [] };
  let notesPreview: NotesPreview | null = null;
  let notesOpen = false;
  let vaults: Vault[] = [];
  let memoryStatus: MemoryStatus = {};
  let status = "";
  let providerTest = "";
  let codexStatus = "";
  let appStatus = "";
  let macosAvailable = false;
  let localOpenAIKey = "";
  let geminiKey = "";
  let openaiKey = "";

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "provider", label: "Provider" },
    { id: "memory", label: "Memory" },
    { id: "profile", label: "Profile" },
    { id: "app", label: "App" }
  ];

  $: provider = settings.provider || "local";

  onMount(async () => {
    await loadAll();
  });

  async function loadAll() {
    status = "Loading...";
    const [settingsData, profileData, foldersData, vaultData, macosData, codexData] = await Promise.all([
      api<{ settings: Settings }>("/api/settings"),
      api<{ profile: Profile }>("/api/profile"),
      api<{ folders: FolderOption[]; status: MemoryStatus }>("/api/memory/folders"),
      api<{ vaults: Vault[] }>("/api/obsidian/vaults"),
      api<{ macos: { is_macos?: boolean } }>("/api/macos/status"),
      api<{ codex: { logged_in?: boolean; login_running?: boolean } }>("/api/codex/status")
    ]);
    settings = settingsData.settings || {};
    profile = profileData.profile || {};
    folders = foldersData.folders || [];
    memoryStatus = foldersData.status || {};
    vaults = vaultData.vaults || [];
    macosAvailable = Boolean(macosData.macos?.is_macos);
    codexStatus = codexData.codex?.logged_in
      ? "Codex is logged in."
      : codexData.codex?.login_running
        ? "Codex login is running."
        : "Codex is not logged in.";
    refreshSettings(settings);
    await loadFolderChildren(settings.obsidian_workspace_path || "");
    status = "";
  }

  async function saveProvider() {
    status = "Saving provider...";
    const data = await api<{ settings: Settings }>("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        ...settings,
        local_openai_api_key: localOpenAIKey,
        gemini_api_key: geminiKey,
        openai_api_key: openaiKey
      })
    });
    settings = data.settings || {};
    localOpenAIKey = "";
    geminiKey = "";
    openaiKey = "";
    refreshSettings(settings);
    status = "Saved";
  }

  async function testProvider() {
    providerTest = "Testing...";
    const data = await api<{ test: { ok?: boolean; text?: string; model?: string; error?: string } }>("/api/provider/test", {
      method: "POST",
      body: JSON.stringify(settings)
    });
    const model = data.test?.model ? ` (${data.test.model})` : "";
    providerTest = data.test?.ok ? `Working${model}: ${data.test.text || "response received"}` : data.test?.error || "Provider test failed.";
  }

  async function startCodexLogin() {
    codexStatus = "Starting Codex login...";
    await api("/api/codex/login", { method: "POST", body: "{}" });
    const data = await api<{ codex: { logged_in?: boolean; login_running?: boolean } }>("/api/codex/status");
    codexStatus = data.codex?.logged_in ? "Codex is logged in." : "Codex login is running.";
  }

  async function saveMemory() {
    status = "Syncing memory...";
    const data = await api<{ settings: Settings; memory_status: MemoryStatus }>("/api/settings", {
      method: "POST",
      body: JSON.stringify({
        obsidian_vault_path: settings.obsidian_vault_path || "",
        obsidian_workspace_path: settings.obsidian_workspace_path || ""
      })
    });
    settings = data.settings || {};
    memoryStatus = data.memory_status || {};
    refreshSettings(settings);
    const foldersData = await api<{ folders: FolderOption[]; status: MemoryStatus }>("/api/memory/folders");
    folders = foldersData.folders || [];
    memoryStatus = foldersData.status || memoryStatus;
    await loadFolderChildren(settings.obsidian_workspace_path || "");
    status = "Synced";
  }

  async function loadFolderChildren(folder: string) {
    const data = await api<{ children: FolderChildren; status: MemoryStatus }>(
      `/api/memory/children?folder=${encodeURIComponent(folder || "")}`
    );
    children = data.children || { items: [] };
    memoryStatus = data.status || memoryStatus;
    notesPreview = null;
  }

  async function viewNotes(folder?: string) {
    const target = folder ?? settings.obsidian_workspace_path ?? "";
    const data = await api<{ notes: NotesPreview; status?: MemoryStatus }>(
      `/api/memory/notes?folder=${encodeURIComponent(target || "")}`
    );
    notesPreview = data.notes || { notes: [] };
    notesOpen = true;
  }

  async function openMemoryPath(path: string) {
    await api("/api/memory/open", {
      method: "POST",
      body: JSON.stringify({ path })
    });
  }

  async function saveProfile() {
    status = "Saving profile...";
    const data = await api<{ profile: Profile }>("/api/profile", {
      method: "POST",
      body: JSON.stringify({ self_profile: profile.self_profile || "" })
    });
    profile = data.profile || {};
    status = "Saved";
  }

  async function deleteTrait(traitId: string) {
    const data = await api<{ profile: Profile }>("/api/profile/trait/delete", {
      method: "POST",
      body: JSON.stringify({ trait_id: traitId })
    });
    profile = data.profile || {};
  }

  async function relaunchApp() {
    appStatus = "Relaunching...";
    await api("/api/app/relaunch", { method: "POST", body: "{}" });
    appStatus = "Relaunch requested";
  }

  async function openFullDiskAccess() {
    await api("/api/macos/open-full-disk-access", { method: "POST", body: "{}" });
  }
</script>

<aside class="settings-drawer">
  <header>
    <div>
      <strong>Settings</strong>
      <span>{status || "Sankalp controls"}</span>
    </div>
    <button aria-label="Close settings" type="button" on:click={closeSettings}>
      <X size={18} />
    </button>
  </header>

  <nav class="settings-tabs" aria-label="Settings sections">
    {#each tabs as tab}
      <button class:active={$chatState.settingsTab === tab.id} type="button" on:click={() => setSettingsTab(tab.id)}>{tab.label}</button>
    {/each}
  </nav>

  {#if $chatState.settingsTab === "provider"}
    <section class="settings-section">
      <h2><KeyRound size={16} /> Provider</h2>
      <label>Provider
        <select bind:value={settings.provider}>
          <option value="local">Local fallback</option>
          <option value="local_openai">OpenAI-compatible endpoint</option>
          <option value="codex">Codex CLI</option>
          <option value="gemini">Gemini API</option>
          <option value="openai">OpenAI API</option>
        </select>
      </label>

      {#if provider === "local_openai"}
        <label>Base URL <input bind:value={settings.local_openai_base_url} placeholder="http://localhost:2276/v1" /></label>
        <label>Model <input bind:value={settings.local_openai_model} placeholder="model name" /></label>
        <label>API key <input bind:value={localOpenAIKey} placeholder={settings.has_local_openai_api_key ? "Local key saved" : "Optional"} type="password" /></label>
      {:else if provider === "codex"}
        <label>Codex model <input bind:value={settings.codex_model} placeholder="gpt-5.5" /></label>
        <div class="settings-inline">
          <button type="button" on:click={startCodexLogin}>Login</button>
          <span>{codexStatus}</span>
        </div>
      {:else if provider === "gemini"}
        <label>Gemini model <input bind:value={settings.gemini_model} placeholder="gemini-3-flash-preview" /></label>
        <label>Gemini API key <input bind:value={geminiKey} placeholder={settings.has_gemini_api_key ? "Gemini key saved" : "Leave blank to keep existing key"} type="password" /></label>
      {:else if provider === "openai"}
        <label>OpenAI model <input bind:value={settings.openai_model} placeholder="gpt-5.5" /></label>
        <label>OpenAI API key <input bind:value={openaiKey} placeholder={settings.has_openai_api_key ? "OpenAI key saved" : "Leave blank to keep existing key"} type="password" /></label>
      {:else}
        <p>Local fallback does not call an external model.</p>
      {/if}

      <div class="settings-actions">
        <button type="button" on:click={saveProvider}>Save</button>
        <button type="button" on:click={testProvider}>Test hello</button>
      </div>
      {#if providerTest}<p>{providerTest}</p>{/if}
    </section>
  {:else if $chatState.settingsTab === "memory"}
    <section class="settings-section">
      <h2><ShieldCheck size={16} /> Memory</h2>
      <label>Vault path <input bind:value={settings.obsidian_vault_path} placeholder="/Users/you/Documents/Obsidian Vault" /></label>
      <label>Workspace subfolder
        <select
          bind:value={settings.obsidian_workspace_path}
          on:change={() => loadFolderChildren(settings.obsidian_workspace_path || "")}
        >
          {#each folders as folder}
            <option value={folder.path}>{folder.path || "Whole vault"}</option>
          {/each}
        </select>
      </label>
      <p>{memoryStatus.accessible ? "Accessible" : memoryStatus.error || "Memory status not checked."}</p>
      <div class="settings-actions">
        <button type="button" on:click={saveMemory}>Sync vault</button>
        <button type="button" on:click={() => viewNotes(settings.obsidian_workspace_path || "")}>View all notes</button>
        {#if macosAvailable}<button type="button" on:click={openFullDiskAccess}>Full Disk Access</button>{/if}
      </div>
      <div class="memory-browser">
        {#if children.error}
          <p>{children.error}</p>
        {:else}
          {#each children.items || [] as item}
            <article>
              <div>
                <strong>{item.name}</strong>
                <span>{item.path}</span>
              </div>
              <div class="memory-actions">
                <button type="button" on:click={() => openMemoryPath(item.path)}>
                  <Folder size={15} /> Open
                </button>
                {#if item.type === "directory"}
                  <button type="button" on:click={() => viewNotes(item.path)}>Notes</button>
                {/if}
              </div>
            </article>
          {:else}
            <p>No subfolders or notes in this workspace.</p>
          {/each}
        {/if}
      </div>
      {#if notesOpen && notesPreview}
        <div class="notes-preview">
          <div class="notes-preview-header">
            <strong>Notes: {notesPreview.folder || "whole vault"}</strong>
            <button type="button" on:click={() => (notesOpen = false)}>Close</button>
          </div>
          {#if notesPreview.error}
            <p>{notesPreview.error}</p>
          {:else}
            {#each notesPreview.notes || [] as note}
              <article>
                <strong>{note.name}</strong>
                <span>{note.path}</span>
                <pre>{note.preview || ""}</pre>
                <button type="button" on:click={() => openMemoryPath(note.path)}>Open in Obsidian</button>
              </article>
            {:else}
              <p>No notes found.</p>
            {/each}
          {/if}
        </div>
      {/if}
      <div class="vault-list">
        {#each vaults as vault}
          <button type="button" on:click={() => (settings.obsidian_vault_path = vault.path)}>
            <span>{vault.open ? "Open vault" : "Vault"}</span>
            <small>{vault.path}</small>
          </button>
        {/each}
      </div>
    </section>
  {:else if $chatState.settingsTab === "profile"}
    <section class="settings-section">
      <h2><User size={16} /> Profile</h2>
      <label>Your profile
        <textarea bind:value={profile.self_profile} rows="9"></textarea>
      </label>
      <div class="settings-actions"><button type="button" on:click={saveProfile}>Save profile</button></div>
      <div class="trait-list">
        {#each profile.traits || [] as trait}
          <article>
            <strong>{trait.title}</strong>
            <span>{trait.confidence} confidence</span>
            <p>{trait.text}</p>
            <button type="button" on:click={() => deleteTrait(trait.id)}>Delete</button>
          </article>
        {:else}
          <p>No inferred traits yet.</p>
        {/each}
      </div>
    </section>
  {:else}
    <section class="settings-section">
      <h2><RotateCw size={16} /> App</h2>
      <p>Reinstall the app wrapper from this repo and restart the backend with the latest code.</p>
      <div class="settings-actions"><button type="button" on:click={relaunchApp}>Relaunch with latest code</button></div>
      {#if appStatus}<p>{appStatus}</p>{/if}
    </section>
  {/if}
</aside>
