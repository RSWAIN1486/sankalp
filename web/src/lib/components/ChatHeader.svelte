<script lang="ts">
  import { Settings, Sparkles } from "@lucide/svelte";
  import { chatState, openSettings } from "$lib/stores/chat";

  $: activeSession = $chatState.sessions.find((session) => session.session_id === $chatState.currentSessionId);
  $: updateAvailable = Boolean($chatState.appUpdate?.update_available);
</script>

<header class="chat-header">
  <div class="title-block">
    <strong>{activeSession?.title || "New chat"}</strong>
  </div>
  <div class="header-actions">
    {#if updateAvailable}
      <button aria-label="Open app updates" class="update-icon-button" type="button" on:click={() => openSettings("app")}>
        <Sparkles size={17} />
      </button>
    {/if}
    <button aria-label="Open settings" class:active={$chatState.settingsOpen} class:update-dot={updateAvailable} type="button" on:click={() => openSettings("provider")}>
      <Settings size={18} />
    </button>
  </div>
</header>
