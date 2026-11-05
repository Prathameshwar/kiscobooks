'use client';

import { useContext, useId, type ReactNode, type SelectHTMLAttributes } from 'react';
import { FieldLabel } from './FieldLabel';
import { FilterBarContext } from '../lib/filter-bar';
import { AlertIcon } from './icons';
import { ChevronDownIcon } from './icons-console';

export type SelectOption = {
  value: string;
  label: string;
  /** Visible but not choosable — a currency the company has switched off, say. */
  disabled?: boolean;
};

/** A labelled run of options. Renders as `<optgroup>`, which is the only accessible form of it. */
export type SelectOptionGroup = {
  label: string;
  options: readonly SelectOption[];
};

export type SelectItem = SelectOption | SelectOptionGroup;

/** Structural, not a flag on the object: a group is the thing that has options inside it. */
function isGroup(item: SelectItem): item is SelectOptionGroup {
  return 'options' in item;
}

function flatten(items: readonly SelectItem[]): readonly SelectOption[] {
  return items.flatMap((item) => (isGroup(item) ? item.options : [item]));
}

/**
 * Everything a native `<select>` accepts is passed straight through — `required`, `name`,
 * `form`, `autoFocus`, `onBlur`. Four are taken over:
 *
 *  - `value` narrows to `string`: the control is always controlled, so there is one source of
 *    truth for what is chosen.
 *  - `onChange` reports the chosen value, not the event, so no call site reaches into
 *    `event.target`.
 *  - `children` is replaced by `options`, so a group is data rather than markup and cannot be
 *    built as nested `<div>`s by accident.
 *  - `multiple` is refused. A native multi-select is close to unusable — no visible affordance
 *    for ctrl-clicking, and a scroll box that hides its own selection — and `SearchSelect`
 *    already covers picking several things (design-system §5.5).
 */
type NativeSelectProps = Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  'className' | 'value' | 'onChange' | 'children' | 'multiple'
>;

type SelectProps = NativeSelectProps & {
  /** Rendered as a real `<label>`, tied to the control by `id` — never a floating div. */
  label: string;
  value: string;
  options: readonly SelectItem[];
  onChange: (value: string) => void;
  /** Label beside the control; defaults to inline inside FilterBar, stacked elsewhere. */
  inline?: boolean;
  /**
   * Keeps the label as the accessible name but takes it out of the layout, for a control in a
   * row of controls whose column heading already says what it is.
   */
  hideLabel?: boolean;
  /**
   * The empty choice, e.g. "All companies". Rendered first, with an empty value — and not
   * choosable when the field is `required`, which is what makes native constraint validation
   * reject "nothing picked" (§5.7).
   */
  placeholder?: string;
  hint?: ReactNode;
  error?: string;
  /** Right-aligned note beside the label, e.g. "applies to new invoices only". */
  optionalNote?: string;
  /** Right-aligned interactive element beside the label, e.g. a "Manage tax rates" link. */
  action?: ReactNode;
  /**
   * The choices have not arrived yet. The control is inoperable while this is set — there is
   * nothing to choose from — and says so rather than looking like an empty list.
   */
  loading?: boolean;
  /** Overrides the busy text, for a caller whose choices are named something specific. */
  loadingLabel?: string;
};

/**
 * A native `<select>`. A div-based listbox would owe us keyboard handling, type-ahead and a
 * mobile picker; the platform already ships all three (design-system §5.7).
 *
 * Reach for `SearchSelect` instead once the choices are entities rather than a fixed set — the
 * dividing line is roughly ten options, and is written down in §5.5.
 */
export function Select({
  label,
  value,
  options,
  onChange,
  inline,
  hideLabel = false,
  placeholder,
  hint,
  error,
  optionalNote,
  action,
  loading = false,
  loadingLabel = 'Loading…',
  id,
  disabled = false,
  required = false,
  name,
  ...select
}: SelectProps) {
  const inFilterBar = useContext(FilterBarContext);
  const inlineLayout = inline ?? inFilterBar;
  const autoId = useId();
  const selectId = id ?? autoId;
  const hintId = `${selectId}-hint`;
  const errorId = `${selectId}-error`;
  const busyId = `${selectId}-busy`;

  /*
   * Exactly the ids that render, and nothing else: a dangling idref is dropped silently by
   * assistive technology, so a joined list of "every id we might use" quietly loses the one
   * description that was actually on screen. The busy line stacks *with* error or hint rather
   * than replacing it — reloading the choices does not make a validation error untrue.
   */
  const describedBy =
    [loading ? busyId : null, error ? errorId : hint ? hintId : null].filter(Boolean).join(' ') ||
    undefined;

  /*
   * Whether anything in the list actually carries `value`.
   *
   * React sets `value` on the element, and a value matching no option leaves `selectedIndex`
   * at -1 — a control rendering blank, with no way for the reader to tell that from "nothing
   * chosen yet". So an unmatched value always gets the empty row, whether or not the caller
   * asked for a placeholder: saying "nothing is selected" is true, and blank says nothing.
   */
  const matched = flatten(options).some((option) => option.value === value);
  const emptyLabel = placeholder ?? 'Select…';
  const showEmpty = loading || placeholder !== undefined || !matched;

  /* Busy is not the same as withheld. `disabled` drops a control from form submission, which is
   * what a caller means by `disabled` and never what they mean by `loading` — so while the
   * choices are in flight the value is mirrored into a hidden input and a submit still carries
   * what was already chosen. A genuinely disabled field submits nothing, as it should. */
  const inoperable = disabled || loading;
  const mirrorValue = loading && !disabled && name !== undefined && value !== '';

  /** One slot beside the label — an action wins over the note, as on every other field. */
  const beside =
    action ?? (optionalNote ? <span className="janso-optional">{optionalNote}</span> : null);

  /* `hideLabel` needs no class of its own: `janso-visually-hidden` is out of flow, so the label
   * costs no layout either stacked or inline. */
  const classes = ['janso-field', 'janso-select', inlineLayout ? 'janso-select--inline' : '']
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={classes}
      data-invalid={error ? 'true' : undefined}
      data-disabled={inoperable ? 'true' : undefined}
    >
      {/*
        `hideLabel` clips the *label*, never the row: `janso-visually-hidden` hides without
        removing, so hiding the row left a button passed as `action` focusable and invisible — a tab
        stop a sighted keyboard user cannot see (WCAG 2.4.7). With nothing beside the label there is
        no row to render at all.
      */}
      {hideLabel && !beside ? (
        <FieldLabel htmlFor={selectId} hidden>
          {label}
        </FieldLabel>
      ) : (
        <div className="janso-field__row">
          <FieldLabel htmlFor={selectId} required={required} hidden={hideLabel}>
            {label}
          </FieldLabel>
          {beside}
        </div>
      )}

      <div className="janso-select__wrap">
        <select
          id={selectId}
          name={name}
          className="janso-input janso-select__control"
          value={matched ? value : ''}
          disabled={inoperable}
          required={required}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          aria-busy={loading || undefined}
          onChange={(event) => onChange(event.target.value)}
          {...select}
        >
          {showEmpty ? (
            <option value="" disabled={required || loading}>
              {loading ? loadingLabel : emptyLabel}
            </option>
          ) : null}
          {options.map((item) =>
            isGroup(item) ? (
              <optgroup key={item.label} label={item.label}>
                {item.options.map((option) => (
                  <option key={option.value} value={option.value} disabled={option.disabled}>
                    {option.label}
                  </option>
                ))}
              </optgroup>
            ) : (
              <option key={item.value} value={item.value} disabled={item.disabled}>
                {item.label}
              </option>
            ),
          )}
        </select>

        {/* Decorative: the caret repeats what the control's shape already says, and
            `pointer-events: none` in CSS keeps the whole box clickable. */}
        <span className="janso-select__caret" aria-hidden="true">
          {loading ? <span className="janso-spinner" /> : <ChevronDownIcon size={14} />}
        </span>
      </div>

      {/* Named, not just spun. A spinner is invisible to a screen reader, and `aria-busy` alone
          announces nothing — so the state has a sentence, and the control points at it. */}
      {loading ? (
        <p className="janso-hint" id={busyId} role="status">
          {loadingLabel}
        </p>
      ) : null}

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

      {mirrorValue ? <input type="hidden" name={name} value={value} /> : null}
    </div>
  );
}
