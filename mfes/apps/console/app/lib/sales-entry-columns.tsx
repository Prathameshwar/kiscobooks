import { Badge, SearchSelect, type EntryColumn, type SearchSelectLoader } from '@janso/ui';
import {
  COLUMN_LABELS,
  DERIVED_COLUMNS,
  isAvailable,
  type LineColumn,
  type SalesEntryPolicy,
} from './sales-entry-policy';
import { isAccountLine, type DraftLine, type DraftProblem, type SalesDraft } from './sales-entry-draft';
import * as D from './fixed-decimal';
import type { InvoicePreview } from './sales-entry-preview';

/**
 * What choosing a master supplies to a line: its price, unit, classification and resolved tax.
 *
 * A *resolution*, not a default the form invents. The rate arrives with its source so it is
 * provenance-tracked, and the tax rate arrives as a fact rather than an input — the line has no
 * box for it anywhere. `null` means the master supplied nothing, which leaves the line alone.
 */
export type SubjectResolver = (
  id: string,
  priceLevel?: string,
) => Partial<DraftLine> | null | Promise<Partial<DraftLine> | null>;

/** What a resolved subject merges into a line: its fields, and its rate marked as the list's. */
export function resolvedPatch(resolved: Partial<DraftLine> | null): Partial<DraftLine> {
  return {
    ...(resolved ?? {}),
    ...(resolved?.rate ? { resolvedRate: resolved.rate, rateSource: 'PRICE_LEVEL' as const, rateReason: '' } : {}),
  };
}

/**
 * The sales line grid's columns.
 *
 * `EntryGrid` owns the keyboard, the cell types and the row chrome; this owns which columns a
 * sales bill has, what each one means, and which of them a reader may touch. Keeping the two
 * apart is the mechanism-versus-policy line the platform draws everywhere else: a purchase bill
 * or a credit note will reuse the grid with its own column list.
 *
 * Three rules from the platform contracts show up directly here:
 *
 *  - **`taxable_value`, `tax_rate`, `tax_amount` and `amount` are `derived`.** Tax is resolved,
 *    not entered, and a display preference cannot disable it. They render as read-only text, so
 *    there is no box to wonder about.
 *  - **`actual` and `billed` are two columns**, because 10+1 is actual 11 and billed 10 and a
 *    single quantity column cannot express it.
 *  - **The discount cell is an input onto a component**, not a second amount. What the rail
 *    shows is derived from the component the service builds out of this.
 */

export type ColumnContext = {
  readonly draft: SalesDraft;
  readonly policy: SalesEntryPolicy;
  readonly problems: readonly DraftProblem[];
  readonly loadSubjects: SearchSelectLoader;
  /** Applies a whole patch — the lookup sets several fields from one choice. */
  readonly onPatchLine: (key: string, patch: Partial<DraftLine>) => void;
  /** A resolution arriving after the choice; see the draft's `resolveLine`. */
  readonly onResolveLine?: (key: string, subjectId: string, patch: Partial<DraftLine>) => void;
  readonly resolveSubject?: SubjectResolver;
  /** The provisional preview, for the derived columns. */
  readonly preview?: InvoicePreview;
  /**
   * The company's figure formatter. A derived cell shows `1,23,456.78` under Indian grouping,
   * not the canonical `123456.78` — the same rule every other figure on the page follows, and
   * one this file cannot apply itself because it is not a component and has no hook.
   */
  readonly formatFigure?: (value: string) => string;
  /** The company's currency symbol, beside an amount discount — `₹10` against `10 %`. */
  readonly currencySymbol?: string;
};

/**
 * The first problem for each field of each line, by `lineKey|field`.
 *
 * An index rather than a `find` per cell: the grid asks every cell of every row on every
 * keystroke, and on a 200-line bill with a problem per line a linear scan per cell is tens of
 * thousands of comparisons to answer a question a map answers in one.
 */
function indexProblems(problems: readonly DraftProblem[]): Map<string, string> {
  const index = new Map<string, string>();
  for (const problem of problems) {
    if (!problem.lineKey) continue;
    const key = `${problem.lineKey}|${problem.field}`;
    if (!index.has(key)) index.set(key, problem.message);
  }
  return index;
}

const UNITS = [
  { value: '', label: '—' },
  { value: 'nos', label: 'nos' },
  { value: 'kg', label: 'kg' },
  { value: 'g', label: 'g' },
  { value: 'ltr', label: 'ltr' },
  { value: 'box', label: 'box' },
  { value: 'bag', label: 'bag' },
];

/** What a rate's provenance is called, when it is worth saying. */
const RATE_SOURCE: Record<DraftLine['rateSource'], { label: string; tone: 'neutral' | 'warn' }> = {
  PRICE_LEVEL: { label: 'List', tone: 'neutral' },
  QUANTITY_TIER: { label: 'Tier', tone: 'neutral' },
  LAST_SOLD: { label: 'Last', tone: 'neutral' },
  MANUAL: { label: 'Override', tone: 'warn' },
};

export function salesColumns(
  columns: readonly LineColumn[],
  context: ColumnContext,
): EntryColumn<DraftLine>[] {
  const { draft, policy, problems, loadSubjects, onPatchLine, resolveSubject, preview } = context;
  const problemIndex = indexProblems(problems);
  const problemFor = (line: DraftLine, field: string) =>
    problemIndex.get(`${line.key}|${field}`);
  const previewLines = new Map(preview?.lines.map((entry) => [entry.key, entry]) ?? []);
  const previewLine = (line: DraftLine) => previewLines.get(line.key);
  const figure = (value: string | null) =>
    value === null || value === '' ? '' : (context.formatFigure?.(value) ?? value);
  const accounts = draft.mode === 'ACCOUNTS';
  const mixed = draft.mode === 'MIXED';
  const currency = context.currencySymbol ?? '₹';
  /** An account line has no quantity: its quantity cells are not boxes to fill. */
  const unmeasured = (line: DraftLine) => isAccountLine(draft, line);

  const build = (column: LineColumn): EntryColumn<DraftLine> => {
    // A mixed bill's lookup finds either, and its heading says so.
    const label = mixed && column === 'item' ? 'Item or account' : COLUMN_LABELS[column];
    const derived = DERIVED_COLUMNS.has(column);

    switch (column) {
      case 'item':
      case 'account':
        return {
          key: 'subjectId',
          label,
          kind: 'custom',
          width: '16rem',
          // What the line is stays in view while the grid scrolls across to its figures.
          pin: 'start',
          required: true,
          value: (line) => line.subjectId ?? '',
          problem: (line) => problemFor(line, 'subjectId'),
          /*
           * A lookup, not a text box. `SearchSelect` already portals its list and pages
           * remotely, which is what this needs inside a scroll container — and choosing an item
           * sets several fields at once, so it patches rather than writing one cell.
           */
          render: (line, cell) => (
            <span
              className="janso-entry-cell__lookup"
              data-entry-row={cell.cellProps['data-entry-row']}
              data-entry-col={cell.cellProps['data-entry-col']}
              ref={cell.registerRef}
            >
              <SearchSelect
                /* The cell's own name — "Item, line 4" — on the combobox, where a screen reader
                 * reads it. On the wrapper it named nothing, and every row was just "Item". */
                label={cell.cellProps['aria-label']}
                hideLabel
                /* No clear button in a cell: it was a second tab stop between the item and the
                 * next column, and choosing another item or removing the line covers it. */
                clearable={false}
                scopeKey={draft.mode}
                value={line.subjectId}
                selected={
                  line.subjectId ? { id: line.subjectId, label: line.subjectLabel } : null
                }
                loadOptions={loadSubjects}
                disabled={cell.disabled}
                placeholder={accounts ? 'Find an account' : mixed ? 'Find an item or account' : 'Find an item'}
                /* Opened by typing, not by arriving: Tab and Enter land here dozens of times a
                 * minute, and an empty "type two characters" panel each time covered the row
                 * above. */
                openOnFocus={false}
                error={problemFor(line, 'subjectId')}
                onChange={(id, option) => {
                  const answer = id ? resolveSubject?.(id, draft.priceLevel) : null;
                  // A master that answers later — a service call — fills the line when it does.
                  const pending = answer instanceof Promise ? answer : null;
                  const resolved = pending ? null : (answer as Partial<DraftLine> | null | undefined) ?? null;
                  if (pending && id) {
                    void pending.then((late) => {
                      if (late) context.onResolveLine?.(line.key, id, resolvedPatch(late));
                    });
                  }
                  const kind = id ? (resolved?.subjectKind ?? (accounts ? 'ACCOUNT' : 'ITEM')) : null;
                  onPatchLine(line.key, {
                    /*
                     * An account has no quantity. Re-choosing an account over an item on a mixed
                     * bill kept the item's 11 and 10, and the row went on showing "1 free".
                     */
                    ...(kind === 'ACCOUNT'
                      ? { actualQuantity: '', billedQuantity: '', unit: '', quantityReason: '' }
                      : {}),
                    subjectId: id,
                    subjectLabel: option?.label ?? '',
                    // The resolver knows which source the id came from; on a mixed bill only it
                    // can say. Otherwise the mode's own source decides.
                    subjectKind: kind,
                    subjectNature: null,
                    freePurpose: '',
                    /*
                     * What the *previous* subject supplied goes with it: its list price, its
                     * classification, its tax rate, its unit. Merging over them would leave a
                     * second item carrying the first one's HSN and a "List" badge for a price
                     * it never had. A rate the reader typed themselves is theirs and stays.
                     */
                    resolvedRate: '',
                    rateSource: 'MANUAL' as const,
                    rateReason: '',
                    taxRate: '',
                    hsnSac: '',
                    unit: '',
                    stockIntent: 'EXECUTE' as const,
                    ...(line.rateSource !== 'MANUAL' ? { rate: '' } : {}),
                    // The chosen master supplies what it knows. An absent price leaves a typed
                    // rate alone rather than zeroing it — a blank rate is not a price of nil.
                    // A resolved price is marked as the *list* price, so typing over it later
                    // is visibly an override, and returning to it quiets the badge again.
                    ...resolvedPatch(resolved),
                  });
                }}
              />
            </span>
          ),
        };

      case 'description':
        return {
          key: 'description',
          label,
          kind: 'text',
          width: '14rem',
          placeholder: 'As it prints',
          value: (line) => line.description,
        };

      case 'hsn_sac':
        return {
          key: 'hsnSac',
          label,
          kind: 'text',
          width: '7rem',
          value: (line) => line.hsnSac,
          problem: (line) => problemFor(line, 'hsnSac'),
        };

      case 'actual_quantity':
        return {
          key: 'actualQuantity',
          label,
          kind: 'quantity',
          align: 'end',
          width: '6.5rem',
          requirePositive: true,
          /* What physically moves. Free units are part of this and not of `billed`. */
          value: (line) => (unmeasured(line) ? '' : line.actualQuantity),
          readOnly: unmeasured,
          placeholder: mixed ? '—' : undefined,
          unit: (line) => line.unit || undefined,
          problem: (line) => problemFor(line, 'actualQuantity'),
        };

      case 'billed_quantity':
        return {
          key: 'billedQuantity',
          label,
          kind: 'quantity',
          align: 'end',
          width: '6.5rem',
          required: true,
          requirePositive: true,
          /* The consideration basis. 10 paid units of a 10+1 deal, not 11. */
          value: (line) => (unmeasured(line) ? '' : line.billedQuantity),
          readOnly: unmeasured,
          placeholder: mixed ? '—' : undefined,
          unit: (line) => line.unit || undefined,
          problem: (line) => problemFor(line, 'billedQuantity'),
        };

      case 'unit':
        return {
          key: 'unit',
          label,
          kind: 'select',
          width: '5.5rem',
          value: (line) => (unmeasured(line) ? '' : line.unit),
          readOnly: unmeasured,
          options: () => UNITS,
        };

      case 'rate':
        return {
          key: 'rate',
          label,
          kind: 'amount',
          align: 'end',
          width: '8rem',
          required: true,
          /* Four places, because a unit rate routinely carries more than a total shows. */
          precision: 4,
          value: (line) => line.rate,
          /*
           * Where the rate came from, beside it. Quiet for a list, tier or last-sold price; a
           * warning badge for an override, because a price typed over the list is the one a
           * reviewer looks for — and it is only an override once a price was resolved.
           */
          adornment: (line) => {
            const source = rateProvenance(line);
            if (!source) return null;
            return source.tone === 'warn' ? (
              <span className="janso-entry__provenance">
                <Badge tone="warn">{source.label}</Badge>
              </span>
            ) : (
              <span className="janso-entry__provenance">{source.label}</span>
            );
          },
          renderKey: (line) => `${line.rateSource}|${line.resolvedRate}`,
          problem: (line) =>
            problemFor(line, 'rate') ?? problemFor(line, 'rateReason'),
        };

      case 'discount':
        return {
          key: 'discountInput',
          label,
          kind: 'amount',
          align: 'end',
          width: '7rem',
          placeholder: isAvailable(policy.components.lineDiscount) ? '0' : undefined,
          readOnly: () => !isAvailable(policy.components.lineDiscount),
          /*
           * One input, one authority. The calculation contract forbids accepting a percentage
           * and an amount as two authorities for the same benefit, so the kind is a choice on
           * the line (set in the drawer) and this cell is whichever one it is.
           */
          value: (line) => line.discountInput,
          // Seen, not only named: `10` percent and `10` rupees are different discounts.
          showUnit: true,
          unit: (line) => (line.discountKind === 'PERCENT' ? '%' : currency),
          /*
           * Typing the unit switches the kind without leaving the row: `10%` is a percentage and
           * `₹10` an amount. The figure stays — the reader typed it to go with the unit.
           */
          unitKeys: ['%', currency],
          onUnitKey: (line, key) =>
            onPatchLine(line.key, { discountKind: key === '%' ? 'PERCENT' : 'AMOUNT' }),
          problem: (line) => problemFor(line, 'discountInput'),
        };

      default:
        return {
          key: column,
          label,
          kind: 'derived',
          align: 'end',
          width: column === 'tax_rate' ? '5.5rem' : '8rem',
          // What the line comes to stays in view, however far across the reader has scrolled.
          ...(column === 'amount' ? { pin: 'end' as const } : {}),
          /*
           * From the provisional preview, and an em dash wherever the preview does not know —
           * an unresolved tax rate is unknown, not zero. The rail labels the whole set as
           * provisional; these are the same figures, line by line.
           */
          value: (line) => {
            const figures = previewLine(line);
            if (!figures) return '';
            if (column === 'taxable_value') return figure(figures.taxableValue);
            // A rate as it is spoken — `5%`, `12.5%` — not at the storage scale's `5.00%`.
            if (column === 'tax_rate') return figures.taxRate === null ? '' : `${plain(D.parse(figures.taxRate) ?? D.ZERO)}%`;
            if (column === 'tax_amount') return figure(figures.tax);
            return figure(figures.amount);
          },
        };
    }
  };

  return columns.map(build);
}

/** The provenance chip beside a rate, shown only when it says something. */
export function rateProvenance(line: DraftLine): { label: string; tone: 'neutral' | 'warn' } | null {
  if (!line.rate) return null;
  // Nothing resolved a price, so "Override" would be claiming a departure from a figure that
  // never existed — the distinction the draft reducer's tests forced.
  if (line.rateSource === 'MANUAL' && line.resolvedRate === '') return null;
  return RATE_SOURCE[line.rateSource];
}

/** Actual less billed, exactly, or `null` when either is not a quantity. */
function quantityGap(line: DraftLine): D.Fixed | null {
  const actual = D.parse(line.actualQuantity.trim());
  const billed = D.parse(line.billedQuantity.trim());
  return actual === null || billed === null ? null : actual - billed;
}

/** A quantity as a reader writes it: `0.1`, not `0.1000` and never `0.10000000000000009`. */
function plain(value: D.Fixed): string {
  const text = D.format(value, D.SCALE);
  return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text;
}

/**
 * The places a quantity needs when said in a sentence: `10`, `0.5`, never `10.0000`. Passed as
 * the formatter's precision, so the company's separators and grouping still apply.
 */
export function spokenPlaces(value: string): number {
  const fraction = value.trim().split('.')[1] ?? '';
  return fraction.replace(/0+$/, '').length;
}

/** Whether this line is carrying free units: actual above billed. */
export function isRewardLine(line: DraftLine): boolean {
  const gap = quantityGap(line);
  return gap !== null && gap > D.ZERO;
}

/** The free quantity. Derived — never a third editable quantity. */
export function freeQuantity(line: DraftLine): string {
  const gap = quantityGap(line);
  return gap !== null && gap > D.ZERO ? plain(gap) : '';
}

/** How many fewer leave than are charged for — a short supply. */
export function shortQuantity(line: DraftLine): string {
  const gap = quantityGap(line);
  return gap !== null && gap < D.ZERO ? plain(-gap) : '';
}
