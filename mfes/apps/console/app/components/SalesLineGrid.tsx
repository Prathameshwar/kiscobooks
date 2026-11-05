'use client';

import { useMemo, useState } from 'react';
import { EntryGrid, useDisplayConfig, useFormatters, type EntryRowState, type SearchSelectLoader } from '@janso/ui';
import { columnsFor, type SalesEntryPolicy } from '../lib/sales-entry-policy';
import { freeQuantity, isRewardLine, salesColumns, spokenPlaces, type SubjectResolver } from '../lib/sales-entry-columns';
import type { InvoicePreview } from '../lib/sales-entry-preview';
import type { DraftAction, DraftLine, DraftProblem, SalesDraft } from '../lib/sales-entry-draft';
import { isAccountLine, isBlank } from '../lib/sales-entry-draft';
import { SalesLineDrawer } from './SalesLineDrawer';

/**
 * The sales bill's lines.
 *
 * `EntryGrid` owns the keyboard and the row chrome, `sales-entry-columns` owns which columns a
 * sales bill has, and this joins them to the draft: it maps a cell change onto the reducer, maps
 * a line's problems onto a row state and a note, and opens the drawer for the long tail.
 *
 * Nothing here calculates. Every figure the service owns is a `derived` column, read from the
 * provisional preview and an em dash wherever the preview does not know.
 */

export function SalesLineGrid({
  draft,
  policy,
  problems,
  dispatch,
  loadSubjects,
  canEdit,
  resolveSubject,
  preview,
  openLine: controlledOpen,
  onOpenLine,
  onCellUnstorable,
}: {
  draft: SalesDraft;
  policy: SalesEntryPolicy;
  problems: readonly DraftProblem[];
  dispatch: (action: DraftAction) => void;
  loadSubjects: SearchSelectLoader;
  canEdit: boolean;
  resolveSubject?: SubjectResolver;
  preview?: InvoicePreview;
  /**
   * Which line's detail is open, when the page decides — a problem link to a missing reason
   * opens it. Left out, the grid keeps the choice itself.
   */
  openLine?: string | null;
  onOpenLine?: (key: string | null) => void;
  /** A cell holding text that cannot be stored; see `EntryGrid.onCellUnstorable`. */
  onCellUnstorable?: (lineKey: string, field: string, problem: string | null) => void;
}) {
  const [ownOpen, setOwnOpen] = useState<string | null>(null);
  const openLine = controlledOpen !== undefined ? controlledOpen : ownOpen;
  const setOpenLine = onOpenLine ?? setOwnOpen;
  const { money, quantity } = useFormatters();
  const { currencySymbol, currency } = useDisplayConfig();
  /** A quantity in a sentence: the company's separators, only the places it has. */
  const say = (value: string) => quantity(value, { precision: spokenPlaces(value) });

  const columns = useMemo(
    () =>
      salesColumns(columnsFor(draft.mode, policy), {
        draft,
        policy,
        problems,
        loadSubjects,
        onPatchLine: (key, patch) => dispatch({ type: 'line', key, patch }),
        onResolveLine: (key, subjectId, patch) => dispatch({ type: 'resolveLine', key, subjectId, patch }),
        ...(resolveSubject ? { resolveSubject } : {}),
        ...(preview ? { preview } : {}),
        formatFigure: (value) => money(value, { display: 'none' }),
        currencySymbol: currencySymbol ?? currency,
      }),
    [currency, currencySymbol, dispatch, draft, loadSubjects, money, policy, preview, problems, resolveSubject],
  );

  /** The worst thing wrong with a line, since a row has one edge marker and one note. */
  const lineProblems = useMemo(() => {
    const byLine = new Map<string, DraftProblem[]>();
    for (const problem of problems) {
      if (!problem.lineKey) continue;
      const existing = byLine.get(problem.lineKey);
      if (existing) existing.push(problem);
      else byLine.set(problem.lineKey, [problem]);
    }
    return byLine;
  }, [problems]);

  const rowState = (line: DraftLine): EntryRowState | undefined => {
    const entries = lineProblems.get(line.key) ?? [];
    if (entries.some((problem) => problem.severity === 'error')) return 'invalid';
    if (entries.length > 0) return 'warn';
    /*
     * A reward line is marked as *deliberate*, not as wrong. Free units are a recorded term,
     * and a row that looks like an error every time someone gives away a sample trains people
     * to ignore the marker that matters.
     */
    return !isAccountLine(draft, line) && isRewardLine(line) ? 'reward' : undefined;
  };

  const rowNote = (line: DraftLine) => {
    const entries = lineProblems.get(line.key) ?? [];
    const first = entries.find((problem) => problem.severity === 'error') ?? entries[0];
    if (first) {
      return { message: first.message, tone: first.severity === 'error' ? ('error' as const) : ('warning' as const) };
    }
    if (!isAccountLine(draft, line) && isRewardLine(line) && line.quantityReason) {
      // Says what the line *is*, once it is explained — so the band reads as a statement
      // rather than as an unresolved complaint. The arithmetic comes first, in words, because
      // "11 leave the store, 10 are charged" is the part people get wrong.
      return {
        message: `${say(line.billedQuantity)} charged + ${say(freeQuantity(line))} free — ${line.quantityReason}`,
        tone: 'warning' as const,
      };
    }
    return undefined;
  };

  const open = draft.lines.find((line) => line.key === openLine);
  const openOrdinal = draft.lines.findIndex((line) => line.key === openLine) + 1;

  return (
    <>
      <EntryGrid<DraftLine>
        label={draft.mode === 'ACCOUNTS' ? 'Account lines' : 'Item lines'}
        rows={draft.lines}
        columns={columns}
        rowKey={(line) => line.key}
        disabled={!canEdit}
        readOnlyNote="You can read this bill but not change it."
        onCellChange={(key, column, value) =>
          dispatch({ type: 'line', key, patch: { [column]: value } as Partial<DraftLine> })
        }
        onAddRow={() => dispatch({ type: 'addLine' })}
        onInsertRow={(after) => dispatch({ type: 'insertLine', after })}
        onRemoveRow={(key) => dispatch({ type: 'removeLine', key })}
        onDuplicateRow={(key) => dispatch({ type: 'duplicateLine', key })}
        onMoveRow={(key, by) => dispatch({ type: 'moveLine', key, by })}
        rowState={rowState}
        rowNote={rowNote}
        isRowBlank={isBlank}
        {...(onCellUnstorable ? { onCellUnstorable } : {})}
        onExpandRow={setOpenLine}
        expandLabel="Line detail"
      />

      {open ? (
        <SalesLineDrawer
          line={open}
          ordinal={openOrdinal}
          draft={draft}
          policy={policy}
          problems={problems}
          onPatch={(patch) => {
            if (canEdit) dispatch({ type: 'line', key: open.key, patch });
          }}
          onClose={() => setOpenLine(null)}
          canEdit={canEdit}
        />
      ) : null}
    </>
  );
}

/** How many lines have been entered, for the page's own summary. */
export function enteredLineCount(draft: SalesDraft): number {
  return draft.lines.filter((line) => !isBlank(line)).length;
}
