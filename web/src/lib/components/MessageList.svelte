<script lang="ts">
  import { afterUpdate } from "svelte";
  import { Brain, Copy, Pencil, RefreshCw, Trash2 } from "@lucide/svelte";
  import { chatState, deleteMessagesFrom, editMessage, regenerateFrom } from "$lib/stores/chat";
  import type { ChatMessage } from "$lib/types";

  let list: HTMLElement | undefined;
  let deleteIndex: number | null = null;

  afterUpdate(() => {
    if (list) list.scrollTop = list.scrollHeight;
  });

  async function copyMessage(message: ChatMessage) {
    await navigator.clipboard.writeText(message.content || "");
  }

  $: lastAssistantIndex = $chatState.messages.findLastIndex((message) => message.role === "assistant");

  function messageHtml(message: ChatMessage) {
    if (message.role !== "assistant") return escapeHtml(message.content || "");
    return renderMarkdown(message.content || "");
  }

  function deleteSummary(index: number) {
    const removed = $chatState.messages.slice(index);
    const userCount = removed.filter((message) => message.role === "user").length;
    const assistantCount = removed.filter((message) => message.role === "assistant").length;
    return { total: removed.length, userCount, assistantCount };
  }

  function activityMarkdown() {
    if (!$chatState.toolCalls.length) return "";
    return $chatState.toolCalls.map((call, index) => {
      const output = call.output === undefined ? "" : `\n\n\`\`\`json\n${JSON.stringify(call.output, null, 2)}\n\`\`\``;
      return `### ${index + 1}. ${call.name}\n\nStatus: **${call.status}**${output}`;
    }).join("\n\n");
  }

  async function confirmDelete() {
    if (deleteIndex === null) return;
    await deleteMessagesFrom(deleteIndex);
    deleteIndex = null;
  }

  function escapeHtml(value: string) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function renderMarkdown(markdown: string) {
    const blocks: string[] = [];
    let text = String(markdown || "");
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, _lang, code) => {
      const token = `@@CODE${blocks.length}@@`;
      blocks.push(`<pre><code>${escapeHtml(code.trim())}</code></pre>`);
      return token;
    });
    let html = escapeHtml(text);
    html = html.replace(/^### (.*)$/gm, "<h4>$1</h4>");
    html = html.replace(/^## (.*)$/gm, "<h3>$1</h3>");
    html = html.replace(/^# (.*)$/gm, "<h2>$1</h2>");
    html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
    html = html.replace(/^(?:- |\* )(.*(?:\n(?:- |\* ).*)*)/gm, (match) => {
      const items = match.split("\n").map((line) => `<li>${line.replace(/^(- |\* )/, "")}</li>`).join("");
      return `<ul>${items}</ul>`;
    });
    html = html.split(/\n{2,}/).map((part) => {
      if (/^<h[234]|^<ul>|^@@CODE/.test(part)) return part;
      return `<p>${part.replace(/\n/g, "<br>")}</p>`;
    }).join("");
    blocks.forEach((block, index) => {
      html = html.replace(`@@CODE${index}@@`, block);
    });
    return html;
  }
</script>

<section bind:this={list} class="message-list">
  {#if !$chatState.messages.length}
    <div class="welcome-panel">
      <h1>How can I help?</h1>
    </div>
  {:else}
    {#each $chatState.messages as message, index}
      <article class:assistant={message.role === "assistant"} class:user={message.role === "user"} class="message-row">
        {#if message.role === "assistant" && index === lastAssistantIndex && $chatState.toolCalls.length}
          <details class="activity-inline">
            <summary><Brain size={18} /> Activity</summary>
            <div>{@html renderMarkdown(activityMarkdown())}</div>
          </details>
        {/if}
        <div class="message-bubble">
          <div class="message-text">{@html messageHtml(message)}</div>
          {#if message.pending}
            <div class="thinking-pill">{message.status || "Thinking"}</div>
          {/if}
        </div>
        <div class="message-actions" aria-label={`${message.role} message actions`}>
          <button type="button" title="Copy" aria-label="Copy message" on:click={() => copyMessage(message)}>
            <Copy size={18} />
          </button>
          <button type="button" title="Edit" aria-label="Edit message" on:click={() => editMessage(index)}>
            <Pencil size={18} />
          </button>
          {#if message.role === "assistant"}
            <button type="button" title="Regenerate" aria-label="Regenerate from here" on:click={() => regenerateFrom(index)}>
              <RefreshCw size={18} />
            </button>
          {/if}
          <button type="button" title="Delete branch" aria-label="Delete message branch" on:click={() => (deleteIndex = index)}>
            <Trash2 size={18} />
          </button>
        </div>
      </article>
    {/each}
  {/if}
</section>

{#if deleteIndex !== null}
  {@const summary = deleteSummary(deleteIndex)}
  <div class="modal-backdrop">
    <div class="delete-modal" role="dialog" aria-modal="true" aria-label="Delete message branch">
      <h2><Trash2 size={22} /> Delete Message</h2>
      <p>
        This will delete {summary.total} message{summary.total === 1 ? "" : "s"} including:
        {summary.userCount} user message{summary.userCount === 1 ? "" : "s"} and
        {summary.assistantCount} assistant response{summary.assistantCount === 1 ? "" : "s"}.
        All messages in this branch and their responses will be removed.
      </p>
      <div>
        <button type="button" on:click={() => (deleteIndex = null)}>Cancel</button>
        <button class="danger" type="button" on:click={confirmDelete}>Delete {summary.total} Message{summary.total === 1 ? "" : "s"}</button>
      </div>
    </div>
  </div>
{/if}
