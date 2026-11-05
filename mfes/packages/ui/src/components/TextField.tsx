'use client';

import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';
import { FieldLabel } from './FieldLabel';
import { AlertIcon } from './icons';

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'className'> & {
  label: string;
  /** Right-aligned note beside the label, e.g. "used to sign in". */
  optionalNote?: string;
  /** Right-aligned interactive element beside the label, e.g. a "Forgot?" link. */
  action?: ReactNode;
  hint?: ReactNode;
  error?: string;
  /** A small icon inside the input's leading edge (decorative; the label names the field). */
  leading?: ReactNode;
  /** Rendered inside the input wrap (e.g. a password show/hide toggle). */
  trailing?: ReactNode;
  /**
   * Clips the label out of the paint but keeps it as the input's accessible name — for a field
   * whose icon and placeholder already say what it is (a search box in a filter bar). Same
   * contract as `Select`'s: it clips the *label*, never the row, so an `action` stays visible.
   */
  hideLabel?: boolean;
};

/**
 * The ref is forwarded to the `input`, not to the wrapper: a field inside a popup has to take
 * focus when the popup opens (`ContextSwitcher`'s filter), and focusing the `div` would move the
 * caret nowhere. Everything else about the component is reachable without it.
 */
export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField(
  {
    label,
    optionalNote,
    action,
    hint,
    error,
    leading,
    trailing,
    hideLabel = false,
    id,
    ...input
  },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const hintId = `${inputId}-hint`;
  const errorId = `${inputId}-error`;
  const describedBy = [error ? errorId : null, hint ? hintId : null].filter(Boolean).join(' ') || undefined;
  const side = action ?? (optionalNote ? <span className="janso-optional">{optionalNote}</span> : null);

  return (
    <div className="janso-field">
      {hideLabel ? <FieldLabel htmlFor={inputId} hidden>{label}</FieldLabel> : null}
      {!hideLabel || side ? (
        <div className="janso-field__row">
          {hideLabel ? null : (
            <FieldLabel htmlFor={inputId} required={input.required}>
              {label}
            </FieldLabel>
          )}
          {side}
        </div>
      ) : null}
      <div className="janso-input-wrap">
        {leading ? (
          <span className="janso-input__lead" aria-hidden="true">
            {leading}
          </span>
        ) : null}
        <input
          ref={ref}
          id={inputId}
          className={[
            'janso-input',
            leading ? 'janso-input--leading' : '',
            trailing ? 'janso-input--trailing' : '',
          ]
            .filter(Boolean)
            .join(' ')}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...input}
        />
        {trailing}
      </div>
      {error ? (
        <p className="janso-error" id={errorId} role="alert">
          <AlertIcon size={14} />
          {error}
        </p>
      ) : hint ? (
        <p className="janso-hint" id={hintId}>
          {hint}
        </p>
      ) : null}
    </div>
  );
});
