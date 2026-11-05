'use client';

import { InspectorGroup, InspectorRow, formatMm } from '@janso/ui';
import {
  ALIGN_LABELS,
  type AlignEdge,
  MIN_DISTRIBUTE,
  type MmRect,
  ZORDER_LABELS,
  type ZOrder,
} from './layout-arrange';

/**
 * What a designer does once more than one thing is selected: line these up, space these
 * evenly, put this behind that, copy it, remove it.
 *
 * **Buttons, not drag.** Every operation here is an exact geometric statement — "these six
 * share a left edge" — and a pointer is the wrong instrument for stating it exactly. The
 * canvas has the pointer gestures; this panel has the ones that are easier to press than
 * to perform.
 *
 * **It appears for one element too.** With a single selection, aligning is against the
 * element's own zone, which is the common case on a document: push the total to the right
 * edge of the totals block. A panel that only appeared at two selections would hide the
 * useful half.
 *
 * Every button states what it does in its accessible name; the visible text is short
 * because the panel is 280mm of screen, not of paper.
 */

export type ArrangeHandlers = {
  onAlign: (edge: AlignEdge) => void;
  onDistribute: (axis: 'x' | 'y') => void;
  onReorder: (order: ZOrder) => void;
  onDuplicate: () => void;
  onDelete: () => void;
};

type ArrangePanelProps = {
  /** How many elements are selected. Zones are not arranged, so they do not count. */
  count: number;
  /** The box around the selection, in page millimetres. */
  bounds: MmRect | null;
  /** Where the lone selection sits in its zone's stack, when there is exactly one. */
  depth: { at: number; of: number } | null;
  handlers: ArrangeHandlers;
  readOnly?: boolean;
};

const ALIGN_ROWS: readonly { edge: AlignEdge; short: string }[] = [
  { edge: 'left', short: 'Left' },
  { edge: 'centreX', short: 'Centre' },
  { edge: 'right', short: 'Right' },
  { edge: 'top', short: 'Top' },
  { edge: 'middleY', short: 'Middle' },
  { edge: 'bottom', short: 'Bottom' },
];

const STACK_ROWS: readonly { order: ZOrder; short: string }[] = [
  { order: 'front', short: 'Front' },
  { order: 'forward', short: 'Forward' },
  { order: 'backward', short: 'Backward' },
  { order: 'back', short: 'Back' },
];

export function ArrangePanel({
  count,
  bounds,
  depth,
  handlers,
  readOnly = false,
}: ArrangePanelProps) {
  if (count === 0) return null;
  const many = count > 1;

  return (
    <InspectorGroup
      title="Arrange"
      hint={
        many
          ? `${count} elements selected · alignment is against the box around them`
          : 'One element · alignment is against its zone'
      }
    >
      {bounds ? (
        <InspectorRow label="Selection">
          <span data-testid="arrange-bounds">
            {formatMm(bounds.xMm)}, {formatMm(bounds.yMm)} mm · {formatMm(bounds.widthMm)} ×{' '}
            {formatMm(bounds.heightMm)} mm
          </span>
        </InspectorRow>
      ) : null}

      <InspectorRow label="Align">
        <span className="janso-editor__arrange">
          {ALIGN_ROWS.map(({ edge, short }) => (
            <button
              key={edge}
              type="button"
              className="janso-editor__button"
              aria-label={ALIGN_LABELS[edge]}
              disabled={readOnly}
              onClick={() => handlers.onAlign(edge)}
            >
              {short}
            </button>
          ))}
        </span>
      </InspectorRow>

      <InspectorRow
        label="Distribute"
        hint={
          count < MIN_DISTRIBUTE
            ? `Needs ${MIN_DISTRIBUTE} — a first, a last, and something between them`
            : 'Equal gaps, with the outermost two left where they are'
        }
      >
        <span className="janso-editor__arrange janso-editor__arrange--pair">
          <button
            type="button"
            className="janso-editor__button"
            aria-label="Distribute across"
            disabled={readOnly || count < MIN_DISTRIBUTE}
            onClick={() => handlers.onDistribute('x')}
          >
            Across
          </button>
          <button
            type="button"
            className="janso-editor__button"
            aria-label="Distribute down"
            disabled={readOnly || count < MIN_DISTRIBUTE}
            onClick={() => handlers.onDistribute('y')}
          >
            Down
          </button>
        </span>
      </InspectorRow>

      <InspectorRow
        label="Stack"
        hint={
          depth
            ? `${depth.at} of ${depth.of} in this zone — higher is painted later`
            : 'Within each zone: a zone is laid out in sequence and an element cannot leave it'
        }
      >
        <span className="janso-editor__arrange janso-editor__arrange--pair">
          {STACK_ROWS.map(({ order, short }) => (
            <button
              key={order}
              type="button"
              className="janso-editor__button"
              aria-label={ZORDER_LABELS[order]}
              disabled={readOnly}
              onClick={() => handlers.onReorder(order)}
            >
              {short}
            </button>
          ))}
        </span>
      </InspectorRow>

      <InspectorRow label="Copy">
        <span className="janso-editor__arrange janso-editor__arrange--pair">
          <button
            type="button"
            className="janso-editor__button"
            aria-label={many ? `Duplicate ${count} elements` : 'Duplicate element'}
            disabled={readOnly}
            onClick={handlers.onDuplicate}
          >
            Duplicate
          </button>
          <button
            type="button"
            className="janso-editor__button janso-editor__button--danger"
            aria-label={many ? `Delete ${count} elements` : 'Delete element'}
            disabled={readOnly}
            onClick={handlers.onDelete}
          >
            Delete
          </button>
        </span>
      </InspectorRow>
    </InspectorGroup>
  );
}
