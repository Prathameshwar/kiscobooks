'use client';

import { useState } from 'react';
import { EditorSelect, InspectorGroup, InspectorRow } from '@janso/ui';
import { TOTALS_LABELS, type CanvasElement, type TotalsRow } from './layout-model';

/**
 * The rows a totals block prints, in the order it prints them.
 *
 * Order matters here in a way it does not elsewhere: a grand total above its own tax rows
 * reads as a mistake, and "amount in words" belongs last because it restates what is above
 * it. So the list is ordered and movable rather than a set of checkboxes.
 *
 * A totals block may legitimately end up empty — a delivery challan carries goods and no
 * money — so unlike the column designer there is no floor.
 */

export type TotalsBuilderHandlers = {
  onAddTotalsRow: (elementId: string, row: TotalsRow) => void;
  onRemoveTotalsRow: (elementId: string, row: TotalsRow) => void;
  onMoveTotalsRow: (elementId: string, row: TotalsRow, direction: 'up' | 'down') => void;
};

type TotalsBuilderProps = {
  element: CanvasElement;
  available: readonly TotalsRow[];
  handlers: TotalsBuilderHandlers;
  readOnly?: boolean;
};

export function TotalsBuilder({
  element,
  available,
  handlers,
  readOnly = false,
}: TotalsBuilderProps) {
  const rows = element.totalsRows ?? [];
  const [adding, setAdding] = useState<TotalsRow | ''>('');

  return (
    <InspectorGroup
      title="Totals rows"
      hint={
        rows.length === 0
          ? 'Nothing prints in this block — right for a document that carries no money.'
          : 'Printed top to bottom in this order.'
      }
    >
      <ol className="janso-editor__columns">
        {rows.map((row, index) => (
          <li key={row} className="janso-editor__column">
            <span className="janso-editor__column-head">
              <span className="janso-editor__column-name">{TOTALS_LABELS[row]}</span>
              <span className="janso-editor__column-actions">
                <button
                  type="button"
                  className="janso-editor__icon"
                  aria-label={`Move ${TOTALS_LABELS[row]} up`}
                  disabled={readOnly || index === 0}
                  onClick={() => handlers.onMoveTotalsRow(element.id, row, 'up')}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className="janso-editor__icon"
                  aria-label={`Move ${TOTALS_LABELS[row]} down`}
                  disabled={readOnly || index === rows.length - 1}
                  onClick={() => handlers.onMoveTotalsRow(element.id, row, 'down')}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className="janso-editor__icon"
                  aria-label={`Remove ${TOTALS_LABELS[row]}`}
                  disabled={readOnly}
                  onClick={() => handlers.onRemoveTotalsRow(element.id, row)}
                >
                  ✕
                </button>
              </span>
            </span>
          </li>
        ))}
      </ol>

      {available.length > 0 ? (
        <InspectorRow label="Add">
          <span className="janso-editor__control">
            <EditorSelect
              label="Totals row to add"
              value={adding}
              options={[
                { value: '' as const, label: 'Choose…' },
                ...available.map((row) => ({ value: row, label: TOTALS_LABELS[row] })),
              ]}
              disabled={readOnly}
              onChange={(row) => setAdding(row as TotalsRow | '')}
            />
            <button
              type="button"
              className="janso-editor__button"
              disabled={readOnly || adding === ''}
              onClick={() => {
                if (adding === '') return;
                handlers.onAddTotalsRow(element.id, adding);
                setAdding('');
              }}
            >
              Add
            </button>
          </span>
        </InspectorRow>
      ) : null}
    </InspectorGroup>
  );
}
