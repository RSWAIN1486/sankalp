<script lang="ts">
  import { Box, Plus, SendHorizontal } from "@lucide/svelte";
  import { chatState, composerModelOptions, ensureProviderModels, sendMessage, setDraft, updateComposer } from "$lib/stores/chat";

  let sending = false;
  let commandIndex = 0;
  let slashQuery = "";
  let slashVisible = false;
  let slashMatches: Array<{ command: string; description: string }> = [];

  const slashCommands = [
    { command: "/remember ", description: "Save a fact into memory inbox" },
    { command: "/fetch ", description: "Fetch a URL and read text" },
    { command: "/read ", description: "Read a local file path" },
    { command: "/append ", description: "Append text: /append path :: text" },
    { command: "/sh ", description: "Run terminal command (if enabled)" }
  ];

  $: void ensureProviderModels($chatState.composer.provider);
  $: slashQuery = $chatState.draft.startsWith("/") ? $chatState.draft.slice(1).toLowerCase() : "";
  $: slashVisible = $chatState.draft.startsWith("/");
  $: slashMatches = slashVisible
    ? slashCommands.filter((item) => item.command.slice(1).toLowerCase().startsWith(slashQuery))
    : [];
  $: if (commandIndex >= slashMatches.length) commandIndex = 0;

  async function submit() {
    if (sending || !$chatState.draft.trim()) return;
    const value = $chatState.draft;
    const editIndex = $chatState.editIndex;
    sending = true;
    try {
      await sendMessage(value, editIndex);
    } finally {
      sending = false;
    }
  }

  function applyCommand(command: string) {
    setDraft(command);
  }
</script>

<form class="composer-panel" on:submit|preventDefault={submit}>
  <textarea
    value={$chatState.draft}
    placeholder="Type a message..."
    rows="3"
    on:input={(event) => setDraft(event.currentTarget.value)}
    on:keydown={(event) => {
      if (slashMatches.length > 0 && event.key === "ArrowDown") {
        event.preventDefault();
        commandIndex = (commandIndex + 1) % slashMatches.length;
        return;
      }
      if (slashMatches.length > 0 && event.key === "ArrowUp") {
        event.preventDefault();
        commandIndex = (commandIndex - 1 + slashMatches.length) % slashMatches.length;
        return;
      }
      if (slashMatches.length > 0 && (event.key === "Tab" || (event.key === "Enter" && !event.metaKey && !event.ctrlKey))) {
        event.preventDefault();
        applyCommand(slashMatches[commandIndex].command);
        return;
      }
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit();
    }}
  ></textarea>
  {#if slashMatches.length > 0}
    <div class="slash-menu" role="listbox" aria-label="Slash command suggestions">
      {#each slashMatches as item, idx}
        <button
          class:active={idx === commandIndex}
          type="button"
          on:click={() => applyCommand(item.command)}
        >
          <code>{item.command}</code>
          <span>{item.description}</span>
        </button>
      {/each}
    </div>
  {/if}
  <div class="composer-toolbar">
    <div class="composer-left">
      <button aria-label="Attach files" class="icon-button" type="button">
        <Plus size={18} />
      </button>
    </div>
    <div class="composer-right">
      <select
        aria-label="Provider"
        value={$chatState.composer.provider}
        on:change={(event) => updateComposer({ provider: event.currentTarget.value })}
      >
        <option value="local">Local fallback</option>
        <option value="local_openai">OpenAI-compatible</option>
        <option value="codex">Codex CLI</option>
        <option value="gemini">Gemini API</option>
        <option value="openai">OpenAI API</option>
      </select>
      <select
        aria-label="Model"
        value={$chatState.composer.model}
        disabled={$composerModelOptions.length === 0}
        on:change={(event) => updateComposer({ model: event.currentTarget.value })}
      >
        {#each $composerModelOptions as model}
          <option value={model.id}>{model.label || model.id || "No model"}</option>
        {:else}
          <option value="">No models loaded</option>
        {/each}
      </select>
      <select
        aria-label="Reasoning effort"
        value={$chatState.composer.reasoning_effort}
        on:change={(event) => updateComposer({ reasoning_effort: event.currentTarget.value })}
      >
        <option value="auto">auto</option>
        <option value="none">none</option>
        <option value="low">low</option>
        <option value="medium">medium</option>
        <option value="high">high</option>
        <option value="xhigh">xhigh</option>
      </select>
    </div>
    <button class="send-button" disabled={sending || !$chatState.draft.trim()} title={$chatState.editIndex === null ? "Send" : "Send edited message"} type="submit">
      <Box size={16} />
      <SendHorizontal size={18} />
    </button>
  </div>
</form>
