<script lang="ts">
  import { Box, Plus, SendHorizontal } from "@lucide/svelte";
  import { chatState, sendMessage, setDraft, updateComposer } from "$lib/stores/chat";

  let sending = false;

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
</script>

<form class="composer-panel" on:submit|preventDefault={submit}>
  <textarea
    value={$chatState.draft}
    placeholder="Type a message..."
    rows="3"
    on:input={(event) => setDraft(event.currentTarget.value)}
    on:keydown={(event) => {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit();
    }}
  ></textarea>
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
      <input
        aria-label="Model"
        placeholder="Model"
        value={$chatState.composer.model}
        on:input={(event) => updateComposer({ model: event.currentTarget.value })}
      />
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
