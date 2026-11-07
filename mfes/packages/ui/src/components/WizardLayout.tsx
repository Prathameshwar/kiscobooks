'use client';

import { useEffect, useRef, type FormEvent, type ReactNode } from 'react';
import { Card, CardBody } from './Card';
import { Stepper, type StepperStep } from './Stepper';

/**
 * The gap grid a wizard step's fields sit in. Exported so a caller never has to know the class
 * name, and so a step that is not a list of fields — a review table, a list of feature toggles —
 * still gets the same rhythm as one that is.
 */
export function FieldGrid({ children, disabled }: { children: ReactNode; disabled?: boolean }) {
  /*
   * A `<fieldset>` once `disabled` is supplied, because that is how a form takes every control
   * out of play for the length of a request without touching each one. Omitted, it stays a
   * `div`: an empty `<fieldset>` is still announced as a group.
   */
  if (disabled === undefined) return <div className="janso-setup__fields">{children}</div>;
  return <fieldset className="janso-setup__fields" disabled={disabled}>{children}</fieldset>;
}

/**
 * A label/value summary. The `div` wrapper per row is `display: contents`, so the pairs stay in
 * the definition list's own grid rather than forming a row box of their own.
 */
/**
 * The summary before a wizard commits, with a way back to each thing in it.
 *
 * **Why each row gets its own Edit.** The stepper can already be clicked back to any
 * completed step, but nothing on a review page says so — and even knowing it, a reader who
 * spots a wrong legal name has to work out which of six steps it came from. `onEdit` moves
 * that from a memory exercise to a button beside the mistake. Omitting `onEdit` keeps the
 * plain list, so a read-only summary stays read-only.
 *
 * The button's accessible name carries the field, because "Edit" eleven times in a row is
 * eleven identical names in a screen reader's list of controls.
 */
export function ReviewList({
  items,
  onEdit,
  stacked = false,
}: {
  items: readonly { label: string; value: ReactNode; step?: number }[];
  onEdit?: (step: number) => void;
  /** Put labels above values in narrow side panels, independent of viewport width. */
  stacked?: boolean;
}) {
  return (
    <dl className={'janso-setup__review' + (stacked ? ' janso-setup__review--stacked' : '')}>
      {items.map((item) => (
        <div key={item.label}>
          <dt>{item.label}</dt>
          {/*
            * The value is wrapped only when there is an action to make room for. A
            * read-only summary keeps the `dd` holding its text directly, because callers
            * query it that way — `getByText('Company B', { selector: 'dd' })` stops
            * matching the moment the text moves into a child.
            */}
          {onEdit && item.step !== undefined ? (
            <dd>
              <span className="janso-setup__review-value">{item.value}</span>
              <button
                type="button"
                className="janso-setup__review-edit"
                aria-label={`Edit ${item.label.toLowerCase()}`}
                onClick={() => onEdit(item.step as number)}
              >
                Edit
              </button>
            </dd>
          ) : (
            <dd>{item.value}</dd>
          )}
        </div>
      ))}
    </dl>
  );
}

/**
 * The full-page layout every multi-step setup flow shares: masthead, stepper rail, one card of
 * fields, and a persistent action bar (design-system §4.4).
 *
 * It owns the `form`, so Enter submits the step the user is looking at and the caller's buttons
 * are plain `type="submit"` / `type="button"` rather than click handlers that duplicate the
 * keyboard path. `noValidate` leaves per-field validation to the wizard's caller. It also owns
 * where focus goes when the step changes: the heading, which announces the new step.
 *
 * `apps/auth`'s first-run `/setup` page predates this and still composes the same classes by
 * hand; it should migrate here rather than a second copy of this layout being grown beside it.
 */
export function WizardLayout({
  brand,
  headerEnd,
  steps,
  current,
  reached,
  onStep,
  title,
  subtitle,
  progress,
  notice,
  actions,
  onSubmit,
  children,
}: {
  brand: ReactNode;
  headerEnd?: ReactNode;
  steps: readonly (string | StepperStep)[];
  current: number;
  reached?: number;
  onStep?: (step: number) => void;
  title: string;
  subtitle?: ReactNode;
  /** "Step 3 of 6" — the overline above the title. */
  progress?: string;
  /** Errors and warnings, above the card so they are never scrolled past inside it. */
  notice?: ReactNode;
  /** The action bar's contents: Back on the left, the step's primary action on the right. */
  actions: ReactNode;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  children: ReactNode;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const previous = useRef({ current, title });

  /*
   * On step or activity-title changes only. Focusing the heading on first render would scroll the page to the top
   * and take focus from wherever the browser restored it, which is a worse first impression than
   * no announcement at all — and on arrival there is nothing yet to announce.
   */
  useEffect(() => {
    if (previous.current.current === current && previous.current.title === title) return;
    previous.current = { current, title };
    heading.current?.focus();
    heading.current?.closest('main')?.querySelector<HTMLElement>('.janso-preparation-progress')?.scrollIntoView?.({ block: 'nearest' });
  }, [current, title]);

  return (
    <form className="janso-setup janso-setup--wizard" onSubmit={onSubmit} noValidate>
      <div className="janso-setup__scroll">
        <header className="janso-setup__header">
          {brand}
          {headerEnd}
        </header>
        <div className="janso-setup__layout">
          <Stepper steps={steps} current={current} reached={reached} onStep={onStep} />
          <main className="janso-setup__content">
            <div>
              {progress ? <p className="janso-setup__progress">{progress}</p> : null}
              <h1 ref={heading} tabIndex={-1} className="janso-setup__title">
                {title}
              </h1>
              {subtitle ? <p className="janso-setup__subtitle">{subtitle}</p> : null}
            </div>
            {notice}
            <Card>
              <CardBody>
                <FieldGrid>{children}</FieldGrid>
              </CardBody>
            </Card>
          </main>
        </div>
      </div>
      <footer className="janso-setup__footer">
        <div className="janso-setup__actions">{actions}</div>
      </footer>
    </form>
  );
}
