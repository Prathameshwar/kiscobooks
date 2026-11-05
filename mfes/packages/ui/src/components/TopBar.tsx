import type { ReactNode } from 'react';

/**
 * The top bar: the collapse control on the left, then the context cluster on the right —
 * company/period chip, role, theme switcher, notifications, user menu.
 *
 * Slots rather than named props for each of those, because the cluster's membership is a
 * product decision per MFE and the shell should not need editing to add one.
 */
export function TopBar({
  left,
  right,
  children,
}: {
  left?: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="janso-topbar">
      {left ? <div className="janso-topbar__left">{left}</div> : null}
      {children ? <div className="janso-topbar__mid">{children}</div> : null}
      {right ? <div className="janso-topbar__right">{right}</div> : null}
    </header>
  );
}
