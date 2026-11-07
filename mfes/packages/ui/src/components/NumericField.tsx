'use client';

import { forwardRef, type ReactNode } from 'react';
import { TextField } from './TextField';
import { useDisplayConfig } from '../lib/display-config';
import { useNumericInput, type NumericInputOptions } from '../lib/numeric-input';

/**
 * A money figure and a quantity, as form fields.
 *
 * Two components over one hook: `lib/numeric-input` owns the parsing, the separators, the
 * storage scale and the focused-versus-blurred display rule, and the entry grid uses the same
 * hook for its bare cells. That split is deliberate — the mechanism is the expensive part and
 * it must behave identically in a form and in a grid, or a figure typed in one place and read
 * in the other will disagree.
 *
 * **The value is a `string`.** Every amount and quantity column is `DECIMAL(19,4)`; a `number`
 * prop here would be a float round-trip waiting to happen (CLAUDE.md §4). Callers pass and
 * receive canonical text — digits, one optional point, no separators.
 *
 * The currency sits **beside** the box, never in it. A symbol inside the input is a character
 * a caret has to be driven past, and every accounting product that puts it there is annoying
 * to type into.
 */

type SharedProps = Omit<NumericInputOptions, 'kind'> & {
  label: string;
  hint?: ReactNode;
  /** A caller's own message — a cross-field rule the field cannot know. Wins over the parse. */
  error?: string;
  optionalNote?: string;
  placeholder?: string;
  disabled?: boolean;
  required?: boolean;
  hideLabel?: boolean;
  /** Replaces the resolved currency beside the box — a per-line foreign currency, say. */
  unit?: string;
  id?: string;
  name?: string;
  /** Settled canonical value when focus leaves a storable numeric field. */
  onCommit?: (value: string) => void;
};

export type AmountFieldProps = SharedProps;
export type QuantityFieldProps = Omit<SharedProps, 'unit'> & { unit?: string };

export const AmountField = forwardRef<HTMLInputElement, AmountFieldProps>(function AmountField(
  { label, hint, error, unit, onCommit, ...rest },
  ref,
) {
  const config = useDisplayConfig();
  const numeric = useNumericInput({ ...rest, kind: 'money' });
  return (
    <TextField
      ref={ref}
      label={label}
      hint={hint}
      /* The caller's error wins: it knows things the field cannot, like that this rate is below
       * a floor. The parse problem is the fallback, not an override. */
      error={error ?? numeric.problem ?? undefined}
      optionalNote={rest.optionalNote}
      placeholder={rest.placeholder}
      disabled={rest.disabled}
      required={rest.required}
      hideLabel={rest.hideLabel}
      id={rest.id}
      name={rest.name}
      // Outside the input, so nothing has to be typed past it.
      trailing={<span className="janso-numeric__unit">{unit ?? config.currencySymbol ?? config.currency}</span>}
      {...numeric.inputProps}
      aria-invalid={numeric.invalid || undefined}
      value={numeric.text}
      onChange={(event) => numeric.onChange(event.target.value)}
      onFocus={numeric.onFocus}
      onBlur={() => { const settled = numeric.onBlur(); if (settled !== null) onCommit?.(settled); }}
    />
  );
});

export const QuantityField = forwardRef<HTMLInputElement, QuantityFieldProps>(
  function QuantityField({ label, hint, error, unit, onCommit, ...rest }, ref) {
    const numeric = useNumericInput({ ...rest, kind: 'quantity' });
    return (
      <TextField
        ref={ref}
        label={label}
        hint={hint}
        error={error ?? numeric.problem ?? undefined}
        optionalNote={rest.optionalNote}
        placeholder={rest.placeholder}
        disabled={rest.disabled}
        required={rest.required}
        hideLabel={rest.hideLabel}
        id={rest.id}
        name={rest.name}
        /* The unit of measure, when the caller knows it. Absent rather than guessed: "each" is
         * not a safe default for something sold by the kilogram. */
        trailing={unit ? <span className="janso-numeric__unit">{unit}</span> : undefined}
        {...numeric.inputProps}
        aria-invalid={numeric.invalid || undefined}
        value={numeric.text}
        onChange={(event) => numeric.onChange(event.target.value)}
        onFocus={numeric.onFocus}
        onBlur={() => { const settled = numeric.onBlur(); if (settled !== null) onCommit?.(settled); }}
      />
    );
  },
);
