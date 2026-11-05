import type { ReactNode } from 'react';

/**
 * One step, when a bare label is not enough.
 *
 * `complete: false` is the case a label cannot express: a step the user has *visited* and left
 * with something required still missing. Without it a wizard either locks the user in place or
 * lets them reach the end and fail at submission, having been told all along that every step
 * behind them was done.
 */
export type StepperStep = { label: string; complete?: boolean; note?: string };

/**
 * Sequential navigation: steps up to the furthest one reached may be revisited; the rest stay
 * locked. `reached` defaults to `current`, which is the plain forward-only wizard — pass it
 * explicitly when the user may jump back and must be able to return.
 */
export function Stepper({ steps, current, reached = current, onStep, orientation = 'vertical', allowFuture = false }: {
  steps: readonly (string | StepperStep)[]; current: number; reached?: number; onStep?: (step: number) => void;
  /** Horizontal page progress; vertical remains the setup-sidebar default. */
  orientation?: 'vertical' | 'horizontal';
  /** Allow freely choosing a step while preserving honest upcoming/completed states. */
  allowFuture?: boolean;
}) {
  return <nav className={'janso-stepper' + (orientation === 'horizontal' ? ' janso-stepper--horizontal' : '')} aria-label="Setup progress">
    <ol>{steps.map((step, index) => {
      const { label, complete, note } = typeof step === 'string' ? { label: step, complete: undefined, note: undefined } : step;
      const state = index === current ? 'current'
        : index > reached ? 'upcoming'
        : complete === false ? 'incomplete' : 'complete';
      const marker: ReactNode = state === 'complete' ? '✓' : state === 'incomplete' ? '!' : index + 1;
      return <li key={label} data-state={state}>
        <button type="button" aria-current={index === current ? 'step' : undefined}
          disabled={!onStep || (!allowFuture && index > reached)} onClick={() => onStep?.(index)}>
          <span className="janso-stepper__marker" aria-hidden="true">{marker}</span>
          <span className="janso-stepper__text">
            <span>{label}</span>
            {note ? <span className="janso-stepper__note">{note}</span> : null}
          </span>
          <span className="janso-visually-hidden">{state === 'complete' ? ', completed'
            : state === 'incomplete' ? ', incomplete'
            : state === 'current' ? ', current step' : ', upcoming'}</span>
        </button>
      </li>;
    })}</ol>
  </nav>;
}
