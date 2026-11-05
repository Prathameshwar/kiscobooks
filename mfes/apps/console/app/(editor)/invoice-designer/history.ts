/**
 * Undo and redo for the designer.
 *
 * Why this matters more than it looks: an editor without undo is an editor nobody
 * experiments in. A designer will not drag the logo to see how it looks if the only way
 * back is to remember where it was.
 *
 * **Coalescing is the whole design problem.** One entry per keystroke makes undo useless
 * ("TAX INVOIC", "TAX INVOI", …); one entry per session makes it useless the other way.
 * So an edit carries a *label*, and consecutive edits with the same label inside a short
 * window replace the top entry instead of pushing a new one. Typing a word is one undo;
 * typing a word, moving an element, then typing again is three.
 *
 * **Coalescing is for continuous input only.** A burst of keystrokes or a drag is one act
 * arriving as many changes, and collapsing it is what the window is for. A *discrete*
 * action — a button press, a shortcut — is already one act, and collapsing two of them
 * loses a step the designer performed: four presses of "Bring forward" must be four steps
 * back, not one that drops the element below where it started. So the caller says which
 * kind it is, rather than the window guessing from how fast the presses came.
 *
 * Pure and clock-injected, so the window is testable without waiting.
 */

export type HistoryEntry<T> = {
  readonly state: T;
  /** What produced it — `content:el-title`, `move:el-logo`, `page`. */
  readonly label: string;
  readonly at: number;
};

export type History<T> = {
  readonly past: readonly HistoryEntry<T>[];
  readonly present: HistoryEntry<T>;
  readonly future: readonly HistoryEntry<T>[];
};

/** Entries kept. Fifty is far past what anyone reaches for and costs nothing: the
 *  layouts share structure, so an entry is a handful of changed objects. */
export const HISTORY_LIMIT = 50;

/** How long two same-labelled edits still count as one action. */
export const COALESCE_MS = 700;

export function createHistory<T>(state: T, at = 0): History<T> {
  return { past: [], present: { state, label: 'initial', at }, future: [] };
}

/**
 * Record a new state.
 *
 * Redo is dropped on purpose: once you edit after undoing, the branch you undid is no
 * longer reachable, and keeping it would mean a tree rather than a stack — a far bigger
 * idea than an invoice designer needs.
 */
export function record<T>(
  history: History<T>,
  state: T,
  label: string,
  at: number,
  { coalesce = true }: { coalesce?: boolean } = {},
): History<T> {
  if (state === history.present.state) return history;

  const coalesces =
    coalesce &&
    history.present.label === label &&
    label !== 'initial' &&
    at - history.present.at <= COALESCE_MS;

  if (coalesces) {
    return { ...history, present: { state, label, at }, future: [] };
  }

  const past = [...history.past, history.present].slice(-HISTORY_LIMIT);
  return { past, present: { state, label, at }, future: [] };
}

export function canUndo<T>(history: History<T>): boolean {
  return history.past.length > 0;
}

export function canRedo<T>(history: History<T>): boolean {
  return history.future.length > 0;
}

export function undo<T>(history: History<T>): History<T> {
  const previous = history.past.at(-1);
  if (!previous) return history;
  return {
    past: history.past.slice(0, -1),
    present: previous,
    future: [history.present, ...history.future],
  };
}

export function redo<T>(history: History<T>): History<T> {
  const [next, ...rest] = history.future;
  if (!next) return history;
  return { past: [...history.past, history.present], present: next, future: rest };
}

/** What an undo would take back, for the toolbar's tooltip. */
export function undoLabel<T>(history: History<T>): string | null {
  return canUndo(history) ? history.present.label : null;
}

export function redoLabel<T>(history: History<T>): string | null {
  return history.future[0]?.label ?? null;
}
