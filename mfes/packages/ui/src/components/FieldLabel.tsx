import type { ReactNode } from 'react';

/**
 * A field's label, and the mark that says whether it has to be filled in.
 *
 * **Why this exists as a component.** `required` was already being passed to every field in
 * the console and reaching only the native element: constraint validation worked, screen
 * readers announced it, and a sighted user discovered it by submitting and failing. On the
 * company wizard that meant four of six fields on the first step were required with nothing
 * on screen saying so. One label component means no author has to remember the mark, and the
 * mark cannot drift between a `TextField` and a `Select`.
 *
 * **The mark sits outside the `<label>`, deliberately.** Inside it — even `aria-hidden` — it
 * becomes part of the label's text content, and `getByLabelText('Legal name')` stops matching:
 * 426 such queries across 169 test files in the console app. `getByRole` honours `aria-hidden`
 * and would have been fine; `getByLabelText` reads raw text and would not. A sibling is correct
 * for both, and correct for the accessible name, which stays exactly the label.
 *
 * **Why an asterisk and not "Optional" on the others.** GOV.UK marks optional fields, on the
 * grounds that an unexplained asterisk is a convention people have to be taught. The argument
 * holds for a public form filled in once; this is an operator console whose forms are mostly
 * required, where marking the exceptions means marking almost everything. The asterisk is also
 * not load-bearing: `required` is on the control, so assistive technology is told properly and
 * the browser refuses the submit. This is the visual echo of a fact already stated.
 */

type FieldLabelProps = {
  htmlFor: string;
  children: ReactNode;
  /** Draws the required mark. Pass the same value the control gets. */
  required?: boolean;
  /** Clips the label out of the paint, keeping it as the accessible name. */
  hidden?: boolean;
};

export function FieldLabel({ htmlFor, children, required = false, hidden = false }: FieldLabelProps) {
  const label = (
    <label className={hidden ? 'janso-label janso-visually-hidden' : 'janso-label'} htmlFor={htmlFor}>
      {children}
    </label>
  );

  // No wrapper when there is no mark: an extra span around every label in the console buys
  // nothing and changes the CSS a dozen rules rely on.
  if (!required || hidden) return label;

  return (
    <span className="janso-label-group">
      {label}
      <span className="janso-required" aria-hidden="true" title="Required">
        *
      </span>
    </span>
  );
}
