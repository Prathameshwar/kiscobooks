'use client';

import type { MouseEvent } from 'react';
import { useGranted } from '../lib/permissions';
import { isSafeHref } from '../lib/url';
import { Button } from './Button';
import { Menu, type MenuItem } from './Menu';
import { ChevronDownIcon } from './icons-console';

export type SplitButtonProps = {
  label: string;
  primary: Omit<MenuItem, 'checked' | 'destructive'>;
  items: readonly MenuItem[];
  onSelect: (id: string) => void;
  onNavigate?: (event: MouseEvent<HTMLAnchorElement>) => void;
  variant?: 'primary' | 'ghost';
  disabledReason?: string;
  loading?: boolean;
  loadingLabel?: string;
};

/** A primary action beside the existing keyboard-accessible, portalled action menu. */
export function SplitButton({
  label,
  primary,
  items,
  onSelect,
  onNavigate,
  variant = 'ghost',
  disabledReason,
  loading = false,
  loadingLabel = 'Working…',
}: SplitButtonProps) {
  const granted = useGranted();
  const visible = (item: MenuItem) =>
    granted(item.permission) && (!item.href || isSafeHref(item.href));
  const showPrimary = visible(primary);
  const alternatives = items
    .filter((item) => visible(item) && (!showPrimary || item.id !== primary.id))
    .map((item) => ({
      ...item,
      disabledReason: disabledReason ?? item.disabledReason,
    }));
  const reason = disabledReason ?? primary.disabledReason;

  if (!showPrimary && alternatives.length === 0) return null;
  if (!showPrimary)
    return (
      <Menu
        label={label}
        triggerLabel={label}
        items={alternatives}
        onSelect={onSelect}
        onNavigate={onNavigate}
        disabled={loading}
      />
    );

  return (
    <span
      role="group"
      aria-label={label}
      className="janso-split-button"
      data-variant={variant}
      data-split={alternatives.length > 0 ? 'true' : undefined}
      data-state={loading ? 'busy' : reason ? 'blocked' : undefined}
    >
      {primary.href && !reason && !loading ? (
        <a
          className={'janso-btn janso-btn--' + variant}
          href={primary.href}
          onClick={onNavigate}
        >
          {primary.label}
        </a>
      ) : (
        <Button
          type="button"
          variant={variant}
          disabled={!!reason}
          title={reason}
          loading={loading}
          loadingLabel={loadingLabel}
          onClick={() => onSelect(primary.id)}
        >
          {primary.label}
        </Button>
      )}
      {alternatives.length > 0 && (
        <Menu
          label={label}
          items={alternatives}
          onSelect={onSelect}
          onNavigate={onNavigate}
          icon={<ChevronDownIcon size={16} />}
          variant="outline"
          disabled={loading}
        />
      )}
    </span>
  );
}
