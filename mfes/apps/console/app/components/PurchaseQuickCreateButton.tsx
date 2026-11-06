'use client';

import type { ReactNode } from 'react';
import { IconButton, PlusIcon } from '@janso/ui';

/**
 * The small "create new" icon beside a lookup on the purchase bill. One component so the supplier field, the
 * grid rows and the mobile line editor name, size and announce it the same way: it opens a dialog, so it says so.
 */
export function PurchaseQuickCreateButton({ label, disabled, onClick, size = 'sm', ...rest }: {
  label: string; disabled?: boolean; onClick: () => void; size?: 'sm' | 'md'; className?: string; 'data-quick-create'?: string;
}) {
  return <IconButton label={label} variant="outline" size={size} icon={<PlusIcon size={size === 'sm' ? 14 : 16} />} aria-haspopup="dialog" disabled={disabled} onClick={onClick} {...rest} />;
}

/** Product authoring has company-specific steps, so the item-line action opens its existing form. */
export function PurchaseProductCreateLink({ disabled, size = 'sm', className = '', line }: {
  disabled?: boolean; size?: 'sm' | 'md'; className?: string; line: number;
}) {
  const label = `Create a new product for line ${line} (opens in a new tab)`;
  return <a href="/masters/items/new" target="_blank" rel="noopener noreferrer"
    className={['janso-btn', 'janso-btn--icon', 'janso-btn--icon-outline', 'console-product-create', size === 'sm' ? 'janso-btn--icon-sm' : '', className].filter(Boolean).join(' ')}
    aria-label={label} title={label} aria-disabled={disabled || undefined} tabIndex={disabled ? -1 : undefined}
    onClick={event => { if (disabled) event.preventDefault(); }} data-quick-create="product">
    <span className="janso-btn__icon" aria-hidden="true"><PlusIcon size={size === 'sm' ? 14 : 16} /></span>
  </a>;
}

/**
 * A lookup with its create icon in the box's own row — the label stays above, the icon sits beside the control —
 * using the layout the product masters already use for the same job. Without an action it is just the lookup.
 */
export function InlineCreate({ action, children }: { action?: ReactNode; children: ReactNode }) {
  return action ? <div className="console-reference-create console-reference-create--flush"><div className="console-reference-create__field">{children}</div>{action}</div> : <>{children}</>;
}
