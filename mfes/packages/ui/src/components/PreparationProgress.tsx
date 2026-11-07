'use client';

import { useEffect, useRef, type ReactNode } from 'react';

/** Activity with verified stage labels, without inventing a percentage or completion time. */
export function PreparationProgress({ label, title, detail, active = true, steps = [], action, autoScroll = false, variant = 'compact', complete = false }: {
  label: string;
  title: string;
  detail: string;
  active?: boolean;
  steps?: readonly { label: string; state: 'current' | 'done' | 'waiting' }[];
  action?: ReactNode;
  autoScroll?: boolean;
  variant?: 'compact' | 'panel';
  complete?: boolean;
}) {
  const section = useRef<HTMLElement>(null);
  useEffect(() => { if (autoScroll) section.current?.scrollIntoView?.({ block: 'nearest' }); }, [autoScroll]);
  return <section ref={section} className="janso-preparation-progress" role="region" aria-label={label} data-active={active} data-action={!!action} data-variant={variant} data-complete={complete}>
    <div role="status" aria-atomic="true"><strong>{title}</strong><span>{detail}</span></div>
    <div className="janso-preparation-meter" role={active && variant === 'compact' ? 'progressbar' : undefined} aria-label={active && variant === 'compact' ? title : undefined} aria-valuetext={active && variant === 'compact' ? detail : undefined}>
      {active && <span className="janso-preparation-meter__track" role={variant === 'panel' ? 'progressbar' : undefined} aria-hidden={variant === 'compact' ? true : undefined} aria-label={variant === 'panel' ? title : undefined} aria-valuetext={variant === 'panel' ? detail : undefined}><span /></span>}
      {steps.length > 0 && <ol>{steps.map(step => <li key={step.label} data-state={step.state} aria-current={step.state === 'current' ? 'step' : undefined}>{step.label}</li>)}</ol>}
    </div>
    {action && <div className="janso-preparation-progress__action">{action}</div>}
  </section>;
}
