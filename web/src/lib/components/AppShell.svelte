<script lang="ts">
  import ChatHeader from "$lib/components/ChatHeader.svelte";
  import Composer from "$lib/components/Composer.svelte";
  import MessageList from "$lib/components/MessageList.svelte";
  import SettingsPanel from "$lib/components/SettingsPanel.svelte";
  import Sidebar from "$lib/components/Sidebar.svelte";
  import { chatState, closeSettings, dismissUpdateBanner, openSettings } from "$lib/stores/chat";

  $: showUpdateBanner = Boolean($chatState.appUpdate?.update_available && !$chatState.updateBannerDismissed);
</script>

<main class="app-shell {$chatState.sidebarCollapsed ? 'sidebar-collapsed' : ''}">
  <Sidebar />
  <section class="chat-workspace">
    <ChatHeader />
    {#if showUpdateBanner}
      <div class="update-banner">
        <button type="button" on:click={() => openSettings("app")}>
          <strong>{$chatState.appUpdate?.latest?.title || "Sankalp update available"}</strong>
          <span>{$chatState.appUpdate?.current_version} -> {$chatState.appUpdate?.latest_version}</span>
        </button>
        <button aria-label="Dismiss update notification" type="button" on:click={dismissUpdateBanner}>Dismiss</button>
      </div>
    {/if}
    <MessageList />
    <Composer />
  </section>
  {#if $chatState.settingsOpen}
    <button class="settings-backdrop" type="button" aria-label="Close settings" on:click={closeSettings}></button>
    <div class="settings-container">
      <SettingsPanel />
    </div>
  {/if}
</main>
