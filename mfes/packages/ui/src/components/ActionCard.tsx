'use client';

import { useId, type ReactNode } from 'react';
import { Badge, type Tone } from './Badge';
import { Button } from './Button';
import { ArrowRightIcon } from './icons-console';

type ActionCardProps = {
  title: string;
  description: string;
  icon: ReactNode;
  actionLabel: string;
  /**
   * A quiet state chip in the card's top row — "Standard layout", "Custom layout" — for a card whose
   * destination has something worth knowing before you open it. Informative, not a gate: an
   * unavailable card says why with `disabledReason`, which takes the same place and wins.
   */
  status?: { label: string; tone?: Tone };
} & ({ href: string; disabledReason?: never; unavailableAction?: never } | { href?: never; disabledReason: string; unavailableAction?: { href: string; label: string } });

/** A single navigation target, or an explicitly unavailable action. No nested links. */
export function ActionCard({ title, description, icon, actionLabel, status, href, disabledReason, unavailableAction }: ActionCardProps) {
  const id = useId();
  const descriptionId = `${id}-description`, statusId = `${id}-status`;
  const chip = disabledReason ? { label: disabledReason, tone: 'neutral' as const } : status;
  const content = <>
    <div className="janso-action-card__top"><span className="janso-action-card__icon" aria-hidden="true">{icon}</span>
      {chip ? <span id={statusId}><Badge tone={chip.tone ?? 'neutral'}>{chip.label}</Badge></span> : null}</div>
    <h3 id={id} className="janso-action-card__title">{title}</h3>
    <p id={descriptionId} className="janso-action-card__description">{description}</p>
    <div className={'janso-action-card__footer' + (unavailableAction ? ' janso-action-card__footer--setup' : '')}>{disabledReason
      ? <><Button type="button" variant="ghost" disabled>{actionLabel}</Button>{unavailableAction && <a className="janso-btn janso-btn--ghost" href={unavailableAction.href}>{unavailableAction.label}</a>}</>
      : <span>{actionLabel}<ArrowRightIcon /></span>}</div>
  </>;
  // The chip stays out of the link's name (the title): a name that read "Sales 2 templates" would
  // be a different link text in every state. A screen reader still gets it, as the description.
  return href ? <a href={href} className="janso-action-card" aria-labelledby={id} aria-describedby={chip ? `${descriptionId} ${statusId}` : descriptionId}>{content}</a>
    : <article className="janso-action-card" data-disabled="true" aria-labelledby={id}>{content}</article>;
}
