<script lang="ts">
  import ChatHeader from "$lib/components/ChatHeader.svelte";
  import Composer from "$lib/components/Composer.svelte";
  import MessageList from "$lib/components/MessageList.svelte";
  import SettingsPanel from "$lib/components/SettingsPanel.svelte";
  import Sidebar from "$lib/components/Sidebar.svelte";
  import { chatState } from "$lib/stores/chat";
</script>

<main class="app-shell {$chatState.sidebarCollapsed ? 'sidebar-collapsed' : ''}">
  <Sidebar />
  <section class="chat-workspace">
    <ChatHeader />
    <MessageList />
    <Composer />
  </section>
  {#if $chatState.settingsOpen}
    <SettingsPanel />
  {/if}
</main>
