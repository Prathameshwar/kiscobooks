import type { ReactNode } from 'react';

type ToolbarProps = {
  /** Labels, counts, the "what am I looking at" side. */
  left?: ReactNode;
  /** Controls: range select, refresh, overflow, filters. */
  right?: ReactNode;
};

/**
 * The row of controls above a data region. The trailing side is pushed by `margin-left:auto`
 * rather than `space-between`, so a toolbar with only a `right` slot still sits right.
 */
export function Toolbar({ left, right }: ToolbarProps) {
  return (
    <div className="janso-toolbar">
      {left ? <div className="janso-toolbar__side">{left}</div> : null}
      {right ? <div className="janso-toolbar__side janso-toolbar__side--end">{right}</div> : null}
    </div>
  );
}
