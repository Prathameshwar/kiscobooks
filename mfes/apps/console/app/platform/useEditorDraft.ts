'use client';

import { useEffect, useRef, useState } from 'react';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';

/** Per-tab handoff for explicit reauthentication. Never stores tokens, passwords or invitations. */
export function useEditorDraft<T extends Record<string, string>>(scope: string, initial: T) {
  const [draft, setDraft] = useState(initial);
  const [restored, setRestored] = useState(false);
  const key = useRef('');
  const touched = useRef(false);
  const hydrated = useRef('');
  const storageKey = 'janso-platform-draft:' + scope;
  const clear = () => { try { sessionStorage.removeItem(storageKey); } catch { /* Storage is optional. */ } };
  useEffect(() => {
    if (hydrated.current === storageKey) return;
    if (hydrated.current) { setDraft(initial); touched.current = false; setRestored(false); }
    hydrated.current = storageKey;
    key.current = crypto.randomUUID();
    try {
      const value = JSON.parse(sessionStorage.getItem(storageKey) ?? 'null');
      clear();
      if (value && typeof value.at === 'number' && Date.now() - value.at >= 0 && Date.now() - value.at < 30 * 60 * 1000 &&
        typeof value.key === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(value.key) && value.draft &&
        Object.keys(value.draft).length === Object.keys(initial).length && Object.keys(initial).every(field => typeof value.draft[field] === 'string' && value.draft[field].length <= 2048)) {
        setDraft(value.draft); key.current = value.key; touched.current = true; setRestored(true);
      }
    } catch { clear(); }
    // Scope identifies a fixed editor; initial values are populated separately by its read endpoint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);
  const change = (patch: Partial<T>) => { touched.current = true; key.current = crypto.randomUUID(); setDraft(current => ({ ...current, ...patch })); };
  const populate = (value: T) => { if (!touched.current) setDraft(value); };
  const preserve = () => { try { sessionStorage.setItem(storageKey, JSON.stringify({ at: Date.now(), key: key.current, draft })); } catch { /* The form remains usable without draft recovery. */ } };
  const saved = () => { touched.current = false; clear(); };
  useUnsavedChanges(() => touched.current);
  return { draft, change, populate, preserve, saved, clear, restored, key, touched };
}
