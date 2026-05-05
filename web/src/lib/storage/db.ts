import Dexie, { type Table } from "dexie";
import type { ComposerOptions, ComposerPreference, SessionSummary } from "$lib/types";

export type DraftRecord = {
  session_id: string;
  text: string;
  updated_at: number;
};

export type UiPreference = {
  key: string;
  value: unknown;
};

export type CachedSession = SessionSummary & {
  cached_at: number;
};

class SankalpWebDb extends Dexie {
  drafts!: Table<DraftRecord, string>;
  preferences!: Table<UiPreference, string>;
  sessions!: Table<CachedSession, string>;

  constructor() {
    super("sankalp_web");
    this.version(1).stores({
      drafts: "session_id, updated_at",
      preferences: "key",
      sessions: "session_id, cached_at"
    });
  }
}

export const db = new SankalpWebDb();

export async function saveComposerPreference(value: ComposerPreference): Promise<void> {
  await db.preferences.put({ key: "composer", value });
}

export async function loadComposerPreference(): Promise<ComposerPreference> {
  const record = await db.preferences.get("composer");
  return (record?.value || {}) as ComposerPreference;
}
