import { useId, type ReactNode } from 'react';

/**
 * A named set of fields inside a form, and a row that puts two short fields side by side.
 *
 * **Why a group and not just a heading.** A step with fifteen controls in one column is a
 * list to get through; the same fifteen under four headings are four decisions to make. The
 * grouping is a `fieldset` with a `legend`, so it is a group for assistive technology too —
 * a screen reader announces "Numbers" when focus enters the decimal separator, which is the
 * context a sighted user gets from the heading above it.
 *
 * **Why a pair and not a general grid.** Every field in this design system is full width by
 * default, which is right for a name and wrong for a one-character separator — a decimal
 * separator was being given the whole width of the form. `FieldPair` is the only exception
 * offered, deliberately: two is the number of short fields that still read as one row at the
 * narrowest supported width, and it collapses to one column on a small screen. Anything that
 * wants a three-up grid should say why.
 */

type FieldGroupProps = {
  title: string;
  /** One sentence under the legend, when the group's purpose is not obvious from its name. */
  hint?: ReactNode;
  headerEnd?: ReactNode;
  children: ReactNode;
};

export function FieldGroup({ title, hint, headerEnd, children }: FieldGroupProps) {
  const titleId = useId();
  return (
    <fieldset className="janso-fieldgroup" aria-labelledby={titleId}>
      <legend className="janso-fieldgroup__legend" data-has-action={headerEnd ? '' : undefined}>
        <span className="janso-fieldgroup__heading">
          <span id={titleId}>{title}</span>
          {headerEnd}
        </span>
      </legend>
      {hint ? <p className="janso-fieldgroup__hint">{hint}</p> : null}
      <div className="janso-fieldgroup__fields">{children}</div>
    </fieldset>
  );
}

export function FieldPair({ children }: { children: ReactNode }) {
  return <div className="janso-fieldpair">{children}</div>;
}
