import type { MouseEvent, ReactNode } from 'react';
import { Card, CardBody, CardFooter } from './Card';
import { Button } from './Button';
import { isSafeHref } from '../lib/url';

export type FormLayoutProps = {
  /** The `<form>` and its card. */
  children: ReactNode;
  /**
   * Standing context for the form — what the change affects, what stays protected. Wrapped in
   * its own card beside the form, and dropped below it on a narrow viewport.
   */
  aside?: ReactNode;
};

/**
 * The shape of a create/edit page: one form card, optionally one context card beside it.
 *
 * Four pages had hand-copied this grid and had started to drift apart — one of them full width,
 * one with no context card, each with its own idea of where the actions go. It is a mechanism,
 * so it lives here (CLAUDE.md §3) and a new editor inherits the shape instead of inventing one.
 */
export function FormLayout({ children, aside }: FormLayoutProps) {
  if (!aside) return <div className="janso-form-layout">{children}</div>;
  return (
    <div className="janso-grid janso-grid--split janso-grid--start">
      {children}
      <Card>
        <CardBody>
          <div className="janso-flow">{aside}</div>
        </CardBody>
      </Card>
    </div>
  );
}

export type FormActionsProps = {
  /**
   * A route destination uses a link, preserving normal browser navigation; onClick
   * lets the editor confirm discarding a draft. Inline editors use onCancel to
   * close in place, with a button that can be disabled while a save is pending.
   */
  cancel?:
    | { href: string; label?: string; onClick?: (event: MouseEvent<HTMLAnchorElement>) => void }
    | { onCancel: () => void; label?: string; disabled?: boolean };
  /** The submit button, and any sibling action, right-aligned. */
  children?: ReactNode;
};

/** The footer of a form card: cancel on the left, the committing action on the right. */
export function FormActions({ cancel, children }: FormActionsProps) {
  return (
    <CardFooter>
      {cancel && 'onCancel' in cancel ? (
        <Button type="button" variant="ghost" onClick={cancel.onCancel} disabled={cancel.disabled}>
          {cancel.label ?? 'Cancel'}
        </Button>
      ) : cancel && isSafeHref(cancel.href) ? (
        <a className="janso-link" href={cancel.href} onClick={cancel.onClick}>
          {cancel.label ?? 'Cancel'}
        </a>
      ) : null}
      <div className="janso-form-actions">{children}</div>
    </CardFooter>
  );
}
