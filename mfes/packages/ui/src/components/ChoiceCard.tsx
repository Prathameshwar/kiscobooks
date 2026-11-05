'use client';

import { useId, type ReactNode } from 'react';

/**
 * A choice with a consequence worth reading, as a card you can click anywhere on.
 *
 * **Why not a `Checkbox` with a hint.** A checkbox's label is its title, so the description
 * beside it is not part of the hit area: the user reads two lines explaining what a setting
 * does and then has to go back and hit a 16px box. Here the whole card is the label, which is
 * both a bigger target and the obvious one.
 *
 * **Why the badges are a slot and not a boolean.** "Permanent once used" was a sentence at the
 * end of a description, in the same type as the description, on four of seven rows — the one
 * fact on the card that cannot be undone, formatted exactly like the ones that can. A caller
 * passes `Badge`s so the fact is a fact, in a shape the eye finds before it reads.
 *
 * **`depth` indents rather than nests markup.** A dependency chain three deep — stock, then
 * batches, then expiry dates — reads instantly as an indent and not at all as a sentence
 * saying "also turns on". The list stays flat for the keyboard: indentation is a visual
 * statement about data, and turning it into nested groups would make Tab behave differently
 * for a dependent choice than for a root one, which is not a difference anyone wants.
 */

type ChoiceCardProps = {
  title: ReactNode;
  description?: ReactNode;
  /** Short status chips: "Permanent", "Needs GST". */
  badges?: ReactNode;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  /** 0, 1 or 2 — how far this choice depends down a chain. */
  depth?: 0 | 1 | 2;
  /** Stated under the card when it is checked because something else needed it. */
  note?: ReactNode;
};

export function ChoiceCard({
  title,
  description,
  badges,
  checked,
  onChange,
  disabled = false,
  depth = 0,
  note,
}: ChoiceCardProps) {
  const id = useId();
  const titleId = `${id}-title`;
  const badgeId = badges ? `${id}-badges` : undefined;
  const descriptionId = description ? `${id}-description` : undefined;
  const describedBy = [badgeId, descriptionId].filter(Boolean).join(' ') || undefined;

  return (
    <div className="janso-choice" data-depth={depth} data-checked={checked || undefined}>
      <label className="janso-choice__hit" htmlFor={id}>
        {/*
          * `aria-labelledby` on the title alone, not the wrapping label's text.
          *
          * Making the whole card the label is what gives it a large target, but it also makes
          * every word inside it part of the control's accessible name: the checkbox announced
          * itself as "Expiry dates Permanent Record and report expiry against each batch" —
          * one breath, no pause, and the name is what a screen reader user hears in a list of
          * form controls. The name is the title; the badge and the description are the
          * description, which is read after it and separately.
          */}
        <input
          id={id}
          type="checkbox"
          className="janso-choice__box"
          checked={checked}
          disabled={disabled}
          aria-labelledby={titleId}
          aria-describedby={describedBy}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span className="janso-choice__text">
          <span className="janso-choice__head">
            <span className="janso-choice__title" id={titleId}>
              {title}
            </span>
            {badges ? <span id={badgeId}>{badges}</span> : null}
          </span>
          {description ? (
            <span className="janso-choice__description" id={descriptionId}>
              {description}
            </span>
          ) : null}
        </span>
      </label>
      {note ? <p className="janso-choice__note">{note}</p> : null}
    </div>
  );
}
