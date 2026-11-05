'use client';

import { type DisplayConfig, formatDate, formatDateTime, formatMoney, formatQuantity } from '@janso/ui';

/**
 * What these settings will actually print.
 *
 * **Why the preview belongs beside the controls, not on a review page.** Nobody picks a
 * decimal separator or `half_even` from first principles — they pick it by recognising the
 * result. The wizard already computed exactly this to show on its review step, which is one
 * step too late: by then the choice has been made and the only way to change it is to go back.
 * The same numbers, rendered where the controls are, turn six abstract settings into one
 * recognisable line of output.
 *
 * **Negative and zero are shown on purpose.** `negative_format` is the setting people get
 * wrong, and parentheses against a minus sign is invisible until you see a negative number.
 * Zero catches a separator typo that a positive number hides.
 *
 * It renders from the *draft*, so it moves as the form moves — and it is read-only output, so
 * it is a `figure` rather than a region anyone has to tab into.
 */

type FormatPreviewProps = {
  /** The resolved display config built from the draft. */
  display: DisplayConfig;
  /** The date the samples use; the wizard passes its own "today" so tests are stable. */
  today: string;
};

/** A sample that exercises grouping at both Indian and Western breakpoints. */
const AMOUNT = '1234567.891';
const NEGATIVE = '-98765.4';
const QUANTITY = '1234.5678';

export function FormatPreview({ display, today }: FormatPreviewProps) {
  const rows: readonly { label: string; value: string }[] = [
    { label: 'A date', value: formatDate(today, display) },
    { label: 'A date and time', value: formatDateTime(`${today}T14:30:00Z`, display) },
    { label: 'An amount', value: formatMoney(AMOUNT, display) },
    { label: 'A negative amount', value: formatMoney(NEGATIVE, display) },
    { label: 'Zero', value: formatMoney('0', display) },
    { label: 'A quantity', value: formatQuantity(QUANTITY, display) },
  ];

  return (
    <figure className="janso-preview" data-testid="format-preview">
      <figcaption className="janso-preview__caption">On your documents</figcaption>
      <dl className="janso-preview__grid">
        {rows.map((row) => (
          <div className="janso-preview__row" key={row.label}>
            <dt className="janso-preview__key">{row.label}</dt>
            <dd className="janso-preview__value">{row.value}</dd>
          </div>
        ))}
      </dl>
    </figure>
  );
}
