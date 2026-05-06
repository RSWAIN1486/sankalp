<script lang="ts">
  import { onDestroy } from "svelte";
  import { Database, Download, MessageSquarePlus, MoreHorizontal, PanelRight, Pencil, Search, Sparkles, Trash2 } from "@lucide/svelte";
  import { api } from "$lib/services/api";
  import {
    chatState,
    createSession,
    deleteSession,
    openSession,
    openSettings,
    renameSession,
    setSearch,
    toggleSidebar,
    visibleSessions
  } from "$lib/stores/chat";
  import type { ChatMessage, SessionSummary, ToolCall } from "$lib/types";

  let searchOpen = false;
  let menuSessionId: string | null = null;
  let menuTop = 0;
  let menuLeft = 0;

  $: activeMenuSession = menuSessionId ? $visibleSessions.find((session) => session.session_id === menuSessionId) ?? null : null;

  function closeMenu() {
    menuSessionId = null;
  }

  function toggleMenu(sessionId: string, trigger: HTMLButtonElement) {
    if (menuSessionId === sessionId) {
      closeMenu();
      return;
    }
    const rect = trigger.getBoundingClientRect();
    const menuWidth = 210;
    const viewportPadding = 10;
    menuTop = rect.bottom + 6;
    menuLeft = Math.max(viewportPadding, Math.min(rect.right - menuWidth, window.innerWidth - menuWidth - viewportPadding));
    menuSessionId = sessionId;
  }

  function handleGlobalPointerDown(event: PointerEvent) {
    if (!menuSessionId) return;
    const target = event.target as Element | null;
    if (!target) return;
    if (target.closest(".session-menu") || target.closest(".session-menu-button")) return;
    closeMenu();
  }

  function handleGlobalEscape(event: KeyboardEvent) {
    if (event.key === "Escape") closeMenu();
  }

  function handleViewportChange() {
    if (menuSessionId) closeMenu();
  }

  if (typeof window !== "undefined") {
    window.addEventListener("pointerdown", handleGlobalPointerDown);
    window.addEventListener("keydown", handleGlobalEscape);
    window.addEventListener("resize", handleViewportChange);
    window.addEventListener("scroll", handleViewportChange, true);
  }

  onDestroy(() => {
    if (typeof window === "undefined") return;
    window.removeEventListener("pointerdown", handleGlobalPointerDown);
    window.removeEventListener("keydown", handleGlobalEscape);
    window.removeEventListener("resize", handleViewportChange);
    window.removeEventListener("scroll", handleViewportChange, true);
  });

  async function rename(session: SessionSummary) {
    closeMenu();
    const title = window.prompt("Rename conversation", session.title);
    if (!title) return;
    await renameSession(session.session_id, title);
  }

  async function remove(session: SessionSummary) {
    closeMenu();
    if (!window.confirm(`Delete "${session.title}"?`)) return;
    await deleteSession(session.session_id);
  }

  async function exportSession(session: SessionSummary) {
    closeMenu();
    const data = await api<{ session: SessionSummary; messages: ChatMessage[]; tool_calls: ToolCall[] }>(
      `/api/session?id=${encodeURIComponent(session.session_id)}`
    );
    const fallbackMessages = $chatState.currentSessionId === session.session_id ? $chatState.messages : [];
    const messages = data.messages?.length ? data.messages : fallbackMessages;
    const lines = [
      `# ${data.session.title}`,
      "",
      `Session: ${data.session.session_id}`,
      "",
      ...messages.map((message) => `## ${message.role}\n\n${message.content || ""}\n`)
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${safeName(data.session.title || "sankalp-chat")}.md`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function safeName(value: string) {
    return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 70) || "sankalp-chat";
  }
</script>

<aside class:collapsed={$chatState.sidebarCollapsed} class="sidebar">
  <div class="brand-row">
    <strong>Sankalp</strong>
    <button class="sidebar-collapse" type="button" title="Collapse sidebar" aria-label="Collapse sidebar" on:click={toggleSidebar}>
      <PanelRight size={18} />
    </button>
  </div>

  {#if !$chatState.sidebarCollapsed}
    <nav class="side-nav" aria-label="Sankalp navigation">
      <button type="button" on:click={createSession}>
        <MessageSquarePlus size={18} />
        <span>New chat</span>
      </button>

      <button type="button" on:click={() => (searchOpen = !searchOpen)}>
        <Search size={18} />
        <span>Search</span>
      </button>

      <button type="button" on:click={() => openSettings("memory")}>
        <Database size={18} />
        <span>Memory</span>
      </button>

      <button type="button" on:click={() => openSettings("capabilities")}>
        <Sparkles size={18} />
        <span>Capabilities</span>
      </button>
    </nav>

    {#if searchOpen}
      <label class="search-box">
        <Search size={16} />
        <input
          aria-label="Search conversations"
          placeholder="Search conversations"
          value={$chatState.search}
          on:input={(event) => setSearch(event.currentTarget.value)}
        />
      </label>
    {/if}

    <div class="sidebar-section-title">Conversations</div>
    <div class="session-list">
      {#each $visibleSessions as session}
        <div class:active={session.session_id === $chatState.currentSessionId} class="session-item">
          <button class="session-open" type="button" on:click={() => openSession(session.session_id)}>
            <span>{session.title}</span>
            <small>{session.message_count} messages</small>
          </button>
          <button
            class="session-menu-button"
            type="button"
            title="Conversation menu"
            aria-label={`Conversation menu for ${session.title}`}
            on:click={(event) => toggleMenu(session.session_id, event.currentTarget as HTMLButtonElement)}
          >
            <MoreHorizontal size={18} />
          </button>
        </div>
      {:else}
        <div class="empty-state">No conversations found.</div>
      {/each}
    </div>

    {#if activeMenuSession}
      <div class="session-menu floating" style={`--menu-top:${menuTop}px; --menu-left:${menuLeft}px;`}>
        <button type="button" on:click={() => rename(activeMenuSession)}><Pencil size={18} /> Edit</button>
        <button type="button" on:click={() => exportSession(activeMenuSession)}><Download size={18} /> Export</button>
        <button class="danger" type="button" on:click={() => remove(activeMenuSession)}><Trash2 size={18} /> Delete</button>
      </div>
    {/if}
  {/if}
</aside>
