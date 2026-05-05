<script lang="ts">
  import { onMount } from "svelte";
  import AppShell from "$lib/components/AppShell.svelte";
  import { initializeChat } from "$lib/stores/chat";

  let loading = true;
  let error = "";

  onMount(async () => {
    try {
      await initializeChat();
    } catch (err) {
      error = err instanceof Error ? err.message : "Could not load Sankalp.";
    } finally {
      loading = false;
    }
  });
</script>

{#if loading}
  <main class="boot-screen">
    <div>
      <strong>Sankalp</strong>
      <span>Loading workspace...</span>
    </div>
  </main>
{:else if error}
  <main class="boot-screen error">
    <div>
      <strong>Sankalp could not start</strong>
      <span>{error}</span>
    </div>
  </main>
{:else}
  <AppShell />
{/if}
