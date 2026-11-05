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

/**
 * A lookup with its create icon in the box's own row — the label stays above, the icon sits beside the control —
 * using the layout the product masters already use for the same job. Without an action it is just the lookup.
 */
export function InlineCreate({ action, children }: { action?: ReactNode; children: ReactNode }) {
  return action ? <div className="console-reference-create console-reference-create--flush"><div className="console-reference-create__field">{children}</div>{action}</div> : <>{children}</>;
}
