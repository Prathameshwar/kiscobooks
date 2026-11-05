'use client';

import { useState } from 'react';
import { EditorSelect, EditorTextField, InspectorGroup, InspectorRow, MeasureField, Toggle } from '@janso/ui';
import { COLUMN_LABELS, type CanvasElement, type ColumnKey } from './layout-model';
import { columnBudget } from './layout-edit';

/**
 * The item table's columns — the single most-used customisation in any invoice designer.
 *
 * Three decisions worth knowing:
 *
 * **Hide and remove are both offered**, because they are different intentions. Hiding
 * keeps a column's width and heading for the next time; removing forgets them. A designer
 * suppressing HSN for a non-GST customer wants the first, one dropping MRP from a design
 * wants the second.
 *
 * **Reordering is buttons, not drag.** Order is the printed order, and a list of ten rows
 * in a 280px panel is the place where drag-and-drop is worst — small targets, scrolling,
 * and nothing for a keyboard. The same move is one key press here, and the canvas has
 * drag handles on the table itself for the people who think in pointers.
 *
 * **The budget is always visible.** A column set that overflows its table is the layout
 * error that looks right on screen and comes out of the printer with a column missing, so
 * the millimetres spent and the millimetres left are stated above the list, not discovered.
 */

export type ColumnDesignerHandlers = {
  onColumn: (elementId: string, key: ColumnKey, patch: { widthMm?: number; show?: boolean; label?: string }) => void;
  onAddColumn: (elementId: string, key: ColumnKey) => void;
  onRemoveColumn: (elementId: string, key: ColumnKey) => void;
  onMoveColumn: (elementId: string, key: ColumnKey, direction: 'left' | 'right') => void;
  onDistribute: (elementId: string) => void;
};

type ColumnDesignerProps = {
  element: CanvasElement;
  available: readonly ColumnKey[];
  handlers: ColumnDesignerHandlers;
  readOnly?: boolean;
};

export function ColumnDesigner({
  element,
  available,
  handlers,
  readOnly = false,
}: ColumnDesignerProps) {
  const columns = element.columns ?? [];
  const { usedMm, totalMm } = columnBudget(element);
  const leftMm = Math.round((totalMm - usedMm) * 10) / 10;
  const [adding, setAdding] = useState<ColumnKey | ''>('');
  const [renaming, setRenaming] = useState<ColumnKey | null>(null);

  return (
    <InspectorGroup
      title="Columns"
      hint={
        leftMm === 0
          ? `${usedMm} of ${totalMm} mm used — the table is exactly full`
          : leftMm > 0
            ? `${usedMm} of ${totalMm} mm used · ${leftMm} mm free`
            : `${usedMm} of ${totalMm} mm used · ${Math.abs(leftMm)} mm over the table`
      }
    >
      {/* A progressbar rather than a sentence alone: "190 of 190" is a number, and whether
       * the table is full is a shape. */}
      <div className="janso-editor__row">
        <span className="janso-editor__row-label">Budget</span>
        <span className="janso-editor__row-value">
          <span
            className="janso-editor__budget"
            role="progressbar"
            aria-label="Column width used"
            aria-valuemin={0}
            aria-valuemax={totalMm}
            aria-valuenow={usedMm}
            aria-valuetext={`${usedMm} of ${totalMm} millimetres`}
            data-over={leftMm < 0 || undefined}
          >
            <span
              className="janso-editor__budget-fill"
              style={{ width: `${Math.min(100, (usedMm / totalMm) * 100)}%` }}
            />
          </span>
        </span>
      </div>

      <ol className="janso-editor__columns">
        {columns.map((column, index) => {
          const name = column.label ?? COLUMN_LABELS[column.key];
          return (
            <li key={column.key} className="janso-editor__column">
              <span className="janso-editor__column-head">
                <span className="janso-editor__column-name">{name}</span>
                <span className="janso-editor__column-actions">
                  <button
                    type="button"
                    className="janso-editor__icon"
                    aria-label={`Move ${name} left`}
                    disabled={readOnly || index === 0}
                    onClick={() => handlers.onMoveColumn(element.id, column.key, 'left')}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className="janso-editor__icon"
                    aria-label={`Move ${name} right`}
                    disabled={readOnly || index === columns.length - 1}
                    onClick={() => handlers.onMoveColumn(element.id, column.key, 'right')}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className="janso-editor__icon"
                    aria-label={`Rename ${name}`}
                    aria-pressed={renaming === column.key}
                    disabled={readOnly}
                    onClick={() =>
                      setRenaming((current) => (current === column.key ? null : column.key))
                    }
                  >
                    ✎
                  </button>
                  <button
                    type="button"
                    className="janso-editor__icon"
                    aria-label={`Remove ${name}`}
                    disabled={readOnly || columns.length <= 1}
                    onClick={() => handlers.onRemoveColumn(element.id, column.key)}
                  >
                    ✕
                  </button>
                </span>
              </span>

              <span className="janso-editor__column-controls">
                <Toggle
                  label={`Show ${name}`}
                  checked={column.show}
                  disabled={readOnly}
                  onChange={(show) => handlers.onColumn(element.id, column.key, { show })}
                />
                <MeasureField
                  label={`${name} width`}
                  value={column.widthMm}
                  min={1}
                  max={element.widthMm}
                  disabled={readOnly || !column.show}
                  onChange={(widthMm) => handlers.onColumn(element.id, column.key, { widthMm })}
                />
              </span>

              {renaming === column.key ? (
                <span className="janso-editor__column-rename">
                  <EditorTextField
                    label={`${COLUMN_LABELS[column.key]} heading`}
                    value={column.label ?? ''}
                    maxLength={40}
                    placeholder={COLUMN_LABELS[column.key]}
                    disabled={readOnly}
                    onChange={(label) =>
                      handlers.onColumn(element.id, column.key, { label: label || undefined })
                    }
                  />
                </span>
              ) : null}
            </li>
          );
        })}
      </ol>

      {available.length > 0 ? (
        <InspectorRow
          label="Add"
          hint="A column with no room arrives hidden, so nothing else changes width."
        >
          <span className="janso-editor__control">
            <EditorSelect
              label="Column to add"
              value={adding}
              options={[
                { value: '' as const, label: 'Choose…' },
                ...available.map((key) => ({ value: key, label: COLUMN_LABELS[key] })),
              ]}
              disabled={readOnly}
              onChange={(key) => setAdding(key as ColumnKey | '')}
            />
            <button
              type="button"
              className="janso-editor__button"
              disabled={readOnly || adding === ''}
              onClick={() => {
                if (adding === '') return;
                handlers.onAddColumn(element.id, adding);
                setAdding('');
              }}
            >
              Add
            </button>
          </span>
        </InspectorRow>
      ) : null}

      <InspectorRow label="Fit" hint="Scales the shown columns proportionally to fill the table.">
        <button
          type="button"
          className="janso-editor__button"
          disabled={readOnly}
          onClick={() => handlers.onDistribute(element.id)}
        >
          Fit to table width
        </button>
      </InspectorRow>
    </InspectorGroup>
  );
}
