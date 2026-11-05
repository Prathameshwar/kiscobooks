'use client';

import {
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from 'react';

/**
 * The inspector's controls.
 *
 * One family, one file, because they share the editor's row anatomy and density: 26px
 * tall, label to the left, tabular numerals. The product's form controls are 40px with a
 * floating label — right on a page where someone fills in eight fields, wrong in a panel
 * that holds forty of them.
 *
 * Three rules all of them follow:
 *
 *   **One tab stop per control.** A segmented choice is a radiogroup with arrow-key
 *   movement, not four tab stops; a swatch list is a group of pressable swatches reached
 *   from one. Forty controls must not mean two hundred tab stops.
 *
 *   **The keyboard does what the pointer does.** A measurement steps with the arrows
 *   (shift for a coarse step), which is how a designer actually nudges a value.
 *
 *   **No colour literal lives here.** A swatch's colour is document data the caller
 *   passes in; everything else is a token. A control that knew a hex value would be a
 *   theme decision hiding in a component.
 */

/* ---------------------------------------------------------------- measurement */

type MeasureFieldProps = {
  label: string;
  value: number;
  onChange: (value: number) => void;
  /** Millimetres for geometry, points for type. The unit is shown, never guessed. */
  unit?: 'mm' | 'pt' | '%' | '×';
  min?: number;
  max?: number;
  /** Arrow-key step. `shift` multiplies it by ten, which is the coarse nudge. */
  step?: number;
  /** Shown instead of a value when the property is not set on this element. */
  placeholder?: string;
  disabled?: boolean;
};

/**
 * A number with a unit.
 *
 * Deliberately not `<input type="number">`: its spinners are 16px of unusable target, it
 * accepts `e` notation, and its arrow-key step cannot be made coarse with `shift`. This
 * is a text input with the numeric keyboard hint, arrow stepping, and a value that is only
 * reported when it parses — so a half-typed "1." does not momentarily set the width to 1.
 */
export function MeasureField({
  label,
  value,
  onChange,
  unit = 'mm',
  min = 0,
  max = 2000,
  step = 1,
  placeholder,
  disabled = false,
}: MeasureFieldProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? (Number.isFinite(value) ? String(round(value)) : '');
  const invalid = draft !== null && !parses(draft);

  function commit(raw: string, { revertIfInvalid }: { revertIfInvalid: boolean }) {
    const parsed = Number.parseFloat(raw.replace(',', '.'));
    if (!Number.isFinite(parsed)) {
      // On blur, revert: an invalid field must not be left behind. On Enter, keep the
      // text and the invalid marker, so the designer can fix what they typed.
      if (revertIfInvalid) setDraft(null);
      return;
    }
    onChange(clamp(parsed, min, max));
    setDraft(null);
  }

  function nudge(by: number) {
    onChange(clamp(round((Number.isFinite(value) ? value : 0) + by), min, max));
    setDraft(null);
  }

  function onKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    const coarse = event.shiftKey ? 10 : 1;
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      nudge(step * coarse);
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      nudge(-step * coarse);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      commit(event.currentTarget.value, { revertIfInvalid: false });
    } else if (event.key === 'Escape') {
      setDraft(null);
    }
  }

  return (
    <span className="janso-editor__control">
      <input
        className="janso-editor__input janso-editor__input--measure"
        type="text"
        inputMode="decimal"
        aria-label={label}
        aria-invalid={invalid || undefined}
        value={shown}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(event: ChangeEvent<HTMLInputElement>) => setDraft(event.target.value)}
        onBlur={(event) => commit(event.target.value, { revertIfInvalid: true })}
        onKeyDown={onKeyDown}
      />
      <span className="janso-editor__unit" aria-hidden="true">
        {unit}
      </span>
    </span>
  );
}

function parses(raw: string): boolean {
  return raw.trim() !== '' && Number.isFinite(Number.parseFloat(raw.replace(',', '.')));
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** One decimal: the layout stores display geometry, and 0.1mm is finer than any printer. */
function round(value: number): number {
  return Math.round(value * 10) / 10;
}

/* ---------------------------------------------------------------- segmented */

export type SegmentedOption<T extends string> = {
  value: T;
  /** Short enough for four of them in a 280px panel. */
  label: string;
  /** Read instead of the label when the label is a glyph. */
  title?: string;
};

type SegmentedControlProps<T extends string> = {
  label: string;
  value: T | null;
  options: readonly SegmentedOption<T>[];
  onChange: (value: T) => void;
  disabled?: boolean;
  /**
   * Print the label above the options, at form scale. The inspector row already carries a
   * visible label, so the designer leaves this off; a form has no row label, and a set of
   * options with no question beside it ("A percentage | An amount") is a guess.
   */
  showLabel?: boolean;
};

/**
 * A choice between three or four things, as a radiogroup.
 *
 * One tab stop; the arrows move *and* commit, which is the radiogroup convention and the
 * reason this is not four buttons.
 */
export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled = false,
  showLabel = false,
}: SegmentedControlProps<T>) {
  const labelId = useId();
  const groupRef = useRef<HTMLDivElement | null>(null);
  /**
   * The option an arrow key asked for, focused once it is actually the value. A caller may
   * refuse or defer the change — the sales bill asks before switching mode — and focusing at
   * the keystroke left focus on an option that was never selected.
   */
  const focusWhenSelected = useRef<T | null>(null);
  useEffect(() => {
    const wanted = focusWhenSelected.current;
    focusWhenSelected.current = null;
    if (wanted === null || wanted !== value) return;
    const index = options.findIndex((option) => option.value === value);
    groupRef.current?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[index]?.focus();
  }, [options, value]);
  function onKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown';
    const backward = event.key === 'ArrowLeft' || event.key === 'ArrowUp';
    if (!forward && !backward) return;
    event.preventDefault();
    const index = options.findIndex((option) => option.value === value);
    const next = forward
      ? (index + 1) % options.length
      : (index - 1 + options.length) % options.length;
    const target = next < 0 ? 0 : next;
    const option = options[target];
    if (!option) return;
    /*
     * Focus moves with the selection, as a radiogroup's does — once the selection has moved.
     * Left on the previous button (unchecked, out of the tab order) a screen reader announced
     * the wrong option and Space re-selected it.
     */
    focusWhenSelected.current = option.value;
    onChange(option.value);
  }

  const group = (
    <div
      ref={groupRef}
      className="janso-editor__segmented"
      role="radiogroup"
      {...(showLabel ? { 'aria-labelledby': labelId } : { 'aria-label': label })}
      aria-disabled={disabled || undefined}
      onKeyDown={onKeyDown}
    >
      {options.map((option) => {
        const checked = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            className="janso-editor__segment"
            role="radio"
            aria-checked={checked}
            aria-label={option.title}
            // Roving tabindex: the group is one stop, the arrows move within it.
            tabIndex={checked || (value === null && option === options[0]) ? 0 : -1}
            disabled={disabled}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
  if (!showLabel) return group;
  return (
    <div className="janso-segmented-field">
      <span className="janso-label" id={labelId}>
        {label}
      </span>
      {group}
    </div>
  );
}

/* ---------------------------------------------------------------- colour */

type ColourFieldProps = {
  label: string;
  value: string | null;
  onChange: (value: string) => void;
  /**
   * Document colours the caller offers as one click. They are document data, not theme
   * tokens — which is exactly why they arrive as a prop rather than living in here.
   */
  swatches?: readonly string[];
  /**
   * What the native picker shows while the property is unset. Also document data: a
   * default ink is a decision about the page, and a hex literal in this file would be a
   * colour decision smuggled into the design system (`tests/tokens.test.ts` enforces it).
   */
  fallback: string;
  disabled?: boolean;
};

const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

/**
 * A document colour, as the schema defines one: `#rgb` or `#rrggbb` and nothing else.
 *
 * The native picker is the swatch, so the control is the preview. The hex input is beside
 * it because a brand colour arrives as a hex string from a brand guideline, and retyping
 * it into a colour wheel is absurd. A value that does not match the schema's pattern is
 * refused rather than normalised: a CSS colour function or a named colour would fail
 * validation at the service, far from where it was typed.
 *
 * (The example of a rejected value is described rather than written out, because the token
 * test reads this file for colour syntax and a doc comment is not an exception.)
 */
export function ColourField({
  label,
  value,
  onChange,
  swatches = [],
  fallback,
  disabled = false,
}: ColourFieldProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const shown = draft ?? value ?? '';
  const invalid = draft !== null && draft !== '' && !HEX.test(draft);
  const pickerId = useId();

  function commit(raw: string, { revertIfInvalid }: { revertIfInvalid: boolean }) {
    if (HEX.test(raw)) {
      onChange(raw);
      setDraft(null);
      return;
    }
    // Same rule as a measurement: Enter keeps the invalid text to be corrected, blur
    // reverts to the colour that is actually on the element.
    if (revertIfInvalid) setDraft(null);
  }

  return (
    <>
      <span className="janso-editor__control">
        <input
          id={pickerId}
          className="janso-editor__swatch"
          type="color"
          aria-label={`${label} picker`}
          value={HEX.test(value ?? '') ? (value as string) : fallback}
          disabled={disabled}
          onChange={(event) => onChange(event.target.value)}
        />
        <input
          className="janso-editor__input"
          type="text"
          aria-label={label}
          aria-invalid={invalid || undefined}
          value={shown}
          placeholder="#rrggbb"
          spellCheck={false}
          disabled={disabled}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={(event) => commit(event.target.value, { revertIfInvalid: true })}
          onKeyDown={(event) => {
            if (event.key === 'Enter') commit(event.currentTarget.value, { revertIfInvalid: false });
            if (event.key === 'Escape') setDraft(null);
          }}
        />
      </span>
      {swatches.length > 0 ? (
        <span className="janso-editor__swatches" role="group" aria-label={`${label} presets`}>
          {swatches.map((swatch) => (
            <button
              key={swatch}
              type="button"
              className="janso-editor__swatch janso-editor__swatch--small"
              style={{ background: swatch }}
              aria-label={swatch}
              aria-pressed={value?.toLowerCase() === swatch.toLowerCase()}
              disabled={disabled}
              onClick={() => onChange(swatch)}
            />
          ))}
        </span>
      ) : null}
    </>
  );
}

/* ---------------------------------------------------------------- toggle */

type ToggleProps = {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
};

/** A switch. The inspector row already carries the label, so this is the control alone. */
export function Toggle({ label, checked, onChange, disabled = false }: ToggleProps) {
  return (
    <button
      type="button"
      className="janso-editor__toggle"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    />
  );
}

/* ---------------------------------------------------------------- select & text */

type EditorSelectProps<T extends string> = {
  label: string;
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
  disabled?: boolean;
};

/** A native select at editor height: right when there are more options than fit a segment. */
export function EditorSelect<T extends string>({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: EditorSelectProps<T>) {
  return (
    <select
      className="janso-editor__select"
      aria-label={label}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value as T)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

type TextFieldProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  /** A paragraph of static text gets a textarea; a title gets one line. */
  multiline?: boolean;
  maxLength?: number;
  placeholder?: string;
  disabled?: boolean;
};

/**
 * Text a designer types, committed as they type.
 *
 * Live rather than on blur, because the point of this editor is that the page changes
 * under your hands — and the layout is in memory, so there is nothing to debounce for.
 */
export function EditorTextField({
  label,
  value,
  onChange,
  multiline = false,
  maxLength = 2000,
  placeholder,
  disabled = false,
}: TextFieldProps) {
  const common = {
    'aria-label': label,
    value,
    maxLength,
    placeholder,
    disabled,
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      onChange(event.target.value),
  };
  return multiline ? (
    <textarea className="janso-editor__textarea" rows={3} {...common} />
  ) : (
    <input className="janso-editor__input" type="text" {...common} />
  );
}

/** A row whose control spans both columns — a textarea, a swatch list. */
export function InspectorStack({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="janso-editor__row janso-editor__row--stack">
      <span className="janso-editor__row-label">{label}</span>
      <span className="janso-editor__row-value">{children}</span>
    </div>
  );
}
