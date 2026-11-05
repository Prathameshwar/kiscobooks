import type { ReactNode } from 'react';

/**
 * The inspector's anatomy: a group, a labelled row, and the empty state.
 *
 * Deliberately only the skeleton. The typed controls that fill these rows — segmented
 * choices, millimetre steppers, colour fields — are the next phase, and shipping the
 * anatomy first means those controls drop into a shape that already reads correctly with
 * forty rows on screen.
 *
 * A row is a grid, not a flex pair, so every label column in the panel lines up without
 * each row agreeing on a width.
 */

export function InspectorGroup({
  title,
  children,
  hint,
}: {
  title: string;
  children: ReactNode;
  /** One sentence under the group, for a rule that is not obvious from the controls. */
  hint?: ReactNode;
}) {
  return (
    <section className="janso-editor__group">
      <h2 className="janso-editor__group-label">{title}</h2>
      {children}
      {hint ? <p className="janso-editor__row-hint">{hint}</p> : null}
    </section>
  );
}

export function InspectorRow({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <>
      <div className="janso-editor__row">
        <span className="janso-editor__row-label">{label}</span>
        <span className="janso-editor__row-value">{children}</span>
      </div>
      {hint ? <p className="janso-editor__row-hint">{hint}</p> : null}
    </>
  );
}

/**
 * The panel with nothing selected.
 *
 * It states how to get something selected rather than apologising for being empty: an
 * editor's empty inspector is the moment a new user needs the keyboard model, and
 * "nothing selected" on its own teaches nobody anything.
 */
export function InspectorEmpty({ children }: { children: ReactNode }) {
  return <p className="janso-editor__empty">{children}</p>;
}

/** A key, rendered as one. Used in hints that name a shortcut. */
export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="janso-editor__kbd">{children}</kbd>;
}
