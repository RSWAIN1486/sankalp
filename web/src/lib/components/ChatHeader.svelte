<script lang="ts">
  import { Settings } from "@lucide/svelte";
  import { chatState, openSettings } from "$lib/stores/chat";

  $: activeSession = $chatState.sessions.find((session) => session.session_id === $chatState.currentSessionId);
</script>

<header class="chat-header">
  <div class="title-block">
    <strong>{activeSession?.title || "New chat"}</strong>
  </div>
  <div class="header-actions">
    <button aria-label="Open settings" class:active={$chatState.settingsOpen} type="button" on:click={() => openSettings("provider")}>
      <Settings size={18} />
    </button>
  </div>
</header>
