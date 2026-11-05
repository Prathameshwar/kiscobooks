'use client';

import { useId, type InputHTMLAttributes, type ReactNode } from 'react';
import { CheckIcon } from './icons';

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> & {
  children: ReactNode;
  /**
   * The third state: *some* of what this box stands for is selected — a page where four of fifty
   * rows are ticked.
   *
   * It lives here rather than at the call site because HTML has no `indeterminate` attribute: it is
   * a DOM property only, so it has to be set through a ref, and every select-all box in the
   * application would otherwise carry its own copy of that. Browsers expose the property as
   * `aria-checked="mixed"` on their own, so nothing is stated twice.
   */
  indeterminate?: boolean;
  /**
   * What ticking this box actually does, under the label.
   *
   * Rendered **outside** the `<label>` and attached with `aria-describedby`, which is the whole
   * point: inside it, a forty-word explanation becomes part of the control's accessible *name*
   * and a screen reader reads the lot before saying "checkbox". A settings screen whose
   * consequences are permanent needs somewhere to say so beside the control, and a caller that
   * invents its own paragraph there loses both the association and the alignment.
   */
  hint?: ReactNode;
};

export function Checkbox({ children, indeterminate = false, hint, id, ...input }: CheckboxProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  const hintId = `${inputId}-hint`;

  const control = (
    <label className="janso-check" htmlFor={inputId}>
      <input
        type="checkbox"
        id={inputId}
        aria-describedby={hint ? hintId : undefined}
        // A fresh callback each render, deliberately: React re-runs it, which is what keeps the
        // property in step with the prop after the parent re-renders with a different selection.
        ref={(element) => {
          if (element) element.indeterminate = indeterminate;
        }}
        {...input}
      />
      <span className="janso-check__box" aria-hidden="true">
        <CheckIcon size={12} />
      </span>
      <span>{children}</span>
    </label>
  );

  if (!hint) return control;
  return (
    <span className="janso-check-field">
      {control}
      <span className="janso-check__hint" id={hintId}>
        {hint}
      </span>
    </span>
  );
}
