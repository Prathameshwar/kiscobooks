'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useDisplayConfig, useFormatters } from './display-config';
import type { DisplayConfig } from './format';

/**
 * Typing a money or quantity figure.
 *
 * **The value is a `string`, start to finish, and that is the whole point.** Every amount and
 * quantity column in this platform is `DECIMAL(19,4)` (CLAUDE.md §4). A `number` cannot hold
 * `0.1 + 0.2`, MySQL re-scales a narrower scale without erroring, and an invoice total is the
 * worst place in a product to meet either. So nothing here parses to a float except to *compare*
 * — the text the user typed is the text that is stored.
 *
 * A hook rather than a component because two chromes need the same mechanism: a labelled field
 * on a form, and a bare cell inside the entry grid. The parsing, the separators, the storage
 * scale and the display rule are the expensive part and they live here once.
 *
 * ## The display rule
 *
 * Focused, the input shows the **canonical** text — `1234.5`. Blurred, it shows the
 * **formatted** figure — `1,234.50`, or `1,23,456.78` under Indian grouping. Editing a field
 * that is inserting separators under the caret is miserable, and reading a column of ungrouped
 * digits is worse; so each state gets what it is for. The canonical value never contains a
 * separator, so what goes on the wire is never what was painted.
 */

/** The platform's fixed storage scale. Not narrowed per field: MySQL would silently re-scale. */
export const STORAGE_SCALE = 4;

export type NumericKind = 'money' | 'quantity';

export type NumericInputOptions = {
  /** The canonical value: digits, one optional `.`, no separators. `''` means not supplied. */
  value: string;
  onChange: (value: string) => void;
  kind: NumericKind;
  /** Quantities and rates are not negative; a credit note is a negative *document*. */
  allowNegative?: boolean;
  /** Rejects `0` as well as blank. A billed quantity needs this; a rate does not. */
  requirePositive?: boolean;
  /** Overrides the config precision for display only — never for what is stored. */
  precision?: number;
  /**
   * Told when the box holds text that cannot be stored, and when it stops.
   *
   * Unstorable text is kept in the box rather than discarded (see `handleBlur`), which means
   * the box and the caller's value can disagree: `2450.12345` on screen while `2450` is what
   * would be saved. A caller that gates a save must know that, or it saves a figure nobody can
   * see. Only text that settling cannot rescue counts — `1.` mid-typing is not reported, so a
   * problem list does not flash on every decimal point. Reported `null` on unmount, so a field
   * that goes away takes its problem with it.
   */
  onUnstorable?: (problem: string | null) => void;
};

export type NumericInputState = {
  /** What the input element should show right now. */
  readonly text: string;
  /** Whether what is in the box cannot be stored. Drives `aria-invalid`. */
  readonly invalid: boolean;
  /** One sentence naming the problem, or `null`. */
  readonly problem: string | null;
  readonly onChange: (next: string) => void;
  readonly onFocus: () => void;
  readonly onBlur: () => void;
  /** Drops what was typed and shows the stored value again — what `Escape` means in a cell. */
  readonly revert: () => void;
  /** Spread onto the `input` for the attributes that are always the same. */
  readonly inputProps: {
    readonly type: 'text';
    readonly inputMode: 'decimal';
    readonly autoComplete: 'off';
    readonly spellCheck: false;
  };
};

/**
 * Everything a reader might paste, reduced to canonical text.
 *
 * People paste from spreadsheets, bank statements and other systems, so the input arrives with
 * grouping separators, a currency symbol, a space, a non-breaking space, or parentheses around a
 * negative. Refusing all of that and making them retype it is the kind of strictness that gets a
 * product abandoned; silently misreading it is worse. So this normalises exactly the forms that
 * have one unambiguous reading and leaves everything else to fail visibly.
 */
export function canonicalise(raw: string, config: DisplayConfig, _allowNegative: boolean): string {
  let text = raw.trim();
  if (!text) return '';

  // `(1,234.00)` is accounting's negative. Recognised before anything else strips the brackets.
  let negative = false;
  if (/^\(.*\)$/.test(text)) {
    negative = true;
    text = text.slice(1, -1);
  }

  text = text
    // The symbol and the code, either side.
    .replace(config.currencySymbol ?? '', '')
    .replace(new RegExp(config.currency, 'gi'), '')
    // Ordinary, non-breaking and narrow no-break spaces all appear as group separators.
    .replace(/[\s  ]/g, '');

  if (text.startsWith('-')) {
    negative = true;
    text = text.slice(1);
  } else if (text.startsWith('+')) {
    text = text.slice(1);
  }

  /*
   * The decimal separator is config, so the group separator may be `.`. Splitting on the
   * configured decimal first and only then clearing groups is what stops `1.234,56` under a
   * German-style config being read as one thousand two hundred and thirty-four.
   */
  const decimal = config.decimalSeparator || '.';
  const parts = text.split(decimal);
  const integer = (parts[0] ?? '').split(config.groupSeparator || ',').join('');
  /*
   * Rejoined with points, **not** concatenated. Concatenating read `12..5` as `12.5` and
   * `1.2.3` as `1.23` — a silent reinterpretation of something genuinely ambiguous, which is
   * the one thing this function is not allowed to do. Keeping the extra separators leaves the
   * text unstorable, so it fails where the reader can see it.
   */
  const fraction = parts.length > 1 ? parts.slice(1).join('.') : null;

  /*
   * The sign is kept even where a negative is not allowed. Dropping it read a pasted `-50`
   * discount as a 50 discount — the opposite of what was written, and silently. Kept, the text
   * is unstorable and says so (`storable` refuses a sign where none is allowed). The flag is
   * still taken so callers keep one signature; it no longer changes what is read.
   */
  const sign = negative ? '-' : '';
  if (fraction === null) return sign + integer;
  return sign + integer + '.' + fraction;
}

/**
 * Canonical text as the company writes it, for a box being edited: the point swapped for the
 * configured decimal separator, and nothing else — no grouping under the caret.
 *
 * The focused box used to show the canonical `12.5` while every keystroke was re-read with the
 * company's separators. Under a `,` decimal and `.` grouping that made the point a group
 * separator, so typing `6` after `12,5` stored **1256**. What the box shows has to be what it
 * reads.
 */
export function localise(canonical: string, config: DisplayConfig): string {
  const decimal = config.decimalSeparator || '.';
  return decimal === '.' ? canonical : canonical.replace('.', decimal);
}

/** Whether canonical text is something the platform can store. `''` is "not supplied". */
export function storable(canonical: string, options: { allowNegative: boolean }): boolean {
  if (canonical === '') return true;
  const pattern = options.allowNegative
    ? new RegExp(`^-?\\d{1,15}(\\.\\d{1,${STORAGE_SCALE}})?$`)
    : new RegExp(`^\\d{1,15}(\\.\\d{1,${STORAGE_SCALE}})?$`);
  return pattern.test(canonical);
}

/** Tidies what is legal but awkward to keep: `1.` → `1`, `.5` → `0.5`, `007` → `7`. */
export function settle(canonical: string): string {
  if (canonical === '' || canonical === '-') return '';
  let text = canonical.endsWith('.') ? canonical.slice(0, -1) : canonical;
  const negative = text.startsWith('-');
  if (negative) text = text.slice(1);
  if (text.startsWith('.')) text = '0' + text;
  // A leading zero run, but never the lone zero before a point or on its own.
  text = text.replace(/^0+(?=\d)/, '');
  return (negative ? '-' : '') + text;
}

export function useNumericInput(options: NumericInputOptions): NumericInputState {
  const {
    value,
    onChange,
    kind,
    allowNegative = false,
    requirePositive = false,
    precision,
    onUnstorable,
  } = options;
  const config = useDisplayConfig();
  const formatters = useFormatters();
  const [focused, setFocused] = useState(false);
  /**
   * What was typed, kept only while it is *not* canonical.
   *
   * Mid-typing states exist that are not yet storable — `1.`, `-`, `1.23456` — and a controlled
   * input that threw them away would delete the character as it was typed. The draft holds them,
   * the parent holds the canonical value, and the draft is dropped the moment the two agree.
   */
  const [draft, setDraft] = useState<string | null>(null);

  const problem = useMemo(() => {
    const canonical = draft !== null ? canonicalise(draft, config, allowNegative) : value;
    if (!storable(canonical, { allowNegative })) {
      if (!allowNegative && canonical.startsWith('-')) return 'Enter a figure without a minus sign.';
      return (canonical.split('.')[1]?.length ?? 0) > STORAGE_SCALE
        ? `Up to ${STORAGE_SCALE} decimal places.`
        : 'Enter a number.';
    }
    if (requirePositive && value !== '' && Number(value) <= 0) {
      return 'Enter a quantity greater than zero.';
    }
    return null;
  }, [allowNegative, config, draft, requirePositive, value]);

  const text = useMemo(() => {
    if (draft !== null) return draft;
    if (value === '') return value;
    if (focused) return localise(value, config);
    // Blurred and storable: show the figure the way the company reads figures.
    return kind === 'money'
      ? formatters.money(value, {
          display: 'none',
          ...(precision !== undefined ? { precision } : {}),
        })
      : formatters.quantity(value, precision !== undefined ? { precision } : undefined);
  }, [config, draft, focused, formatters, kind, precision, value]);

  const handleChange = useCallback(
    (next: string) => {
      const canonical = canonicalise(next, config, allowNegative);
      // The draft survives only while the text cannot be stored, so an unfinished `1.` keeps
      // its point and a finished `1.5` stops being special.
      setDraft(storable(canonical, { allowNegative }) ? null : next);
      if (storable(canonical, { allowNegative })) onChange(canonical);
    },
    [allowNegative, config, onChange],
  );

  const unstorable =
    draft !== null && !storable(settle(canonicalise(draft, config, allowNegative)), { allowNegative });
  const report = useRef(onUnstorable);
  report.current = onUnstorable;
  /* Transitions only: a 200-line grid mounting 2,400 cells must not make 2,400 "all fine" calls. */
  const reported = useRef<string | null>(null);
  useEffect(() => {
    const next = unstorable ? problem : null;
    if (next === reported.current) return;
    reported.current = next;
    report.current?.(next);
  }, [problem, unstorable]);
  useEffect(
    () => () => {
      if (reported.current !== null) report.current?.(null);
    },
    [],
  );

  const handleBlur = useCallback(() => {
    setFocused(false);
    /*
     * Settled *before* the check, not after. `.5` and `1.` are legal things to type and neither
     * is storable as written, so testing the raw canonical text first rejected exactly the
     * input this step exists to tidy — the blur test caught it.
     */
    // Only typed text is re-read with the company's separators. The stored value is canonical
    // already, and re-reading it under a `.` group separator turned `12.56` into 1256 on blur.
    const tidy = settle(draft !== null ? canonicalise(draft, config, allowNegative) : value);
    if (storable(tidy, { allowNegative })) {
      setDraft(null);
      if (tidy !== value) onChange(tidy);
      return;
    }
    // Unstorable text is **kept**, not reverted. `MeasureField` reverts because its value is a
    // number with a usable previous state; here the text is the value, and silently discarding
    // what someone typed into a money field is how a wrong figure gets committed unnoticed.
  }, [allowNegative, config, draft, onChange, value]);

  return {
    text,
    invalid: problem !== null,
    problem,
    onChange: handleChange,
    onFocus: useCallback(() => setFocused(true), []),
    onBlur: handleBlur,
    revert: useCallback(() => setDraft(null), []),
    inputProps: { type: 'text', inputMode: 'decimal', autoComplete: 'off', spellCheck: false },
  };
}
