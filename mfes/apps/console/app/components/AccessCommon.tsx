'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, ConfirmDialog, ErrorState, Notice, PageNavigation, asErrorStatus } from '@janso/ui';
import { type AccessContext } from '../lib/access-directory';
import type { RequestFailure } from '../lib/service-call';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { goTo } from '../lib/navigate';
import { organisationLinks } from '../lib/organisation-navigation';
import { administrationBackLabel, administrationDirectoryReturn, administrationLink, administrationPages, type AdministrationResource } from '../lib/administration-navigation';

export function AccessNavigation({ context, back, backLabel, resource, mode = 'directory', id, title, onLeave }: {
  context: AccessContext; back?: string; backLabel?: string; resource?: AdministrationResource;
  mode?: 'directory' | 'detail' | 'edit' | 'new' | 'clone'; id?: string; title?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
}) {
  const links = organisationLinks(context), page = resource ? administrationPages[resource] : undefined;
  const accessPage = resource && ['roles', 'assignments', 'permissions'].includes(resource);
  const destination = back ?? (resource === 'my-access' || !links.length ? '/' : '/organisation');
  const directory = resource ? administrationDirectoryReturn(resource, destination) : '';
  const breadcrumbs = page ? [{ label: 'Business overview', href: '/' }, ...(links.length && resource !== 'my-access' ? [{ label: 'Administration', href: '/organisation' }] : []),
    ...(accessPage && links.some(link => link.href === '/roles') ? [{ label: 'Roles & access', href: '/organisation/access' }] : []),
    ...(mode !== 'directory' ? [{ label: page.label, href: directory }] : []),
    ...(id && ['edit', 'clone'].includes(mode) ? [{ label: title ?? page.singular + ' details', href: administrationLink(page.href + '/' + id, directory) }] : []),
    { label: mode === 'directory' ? page.label : mode === 'detail' ? title ?? page.singular + ' details' : (mode === 'new' ? 'New ' : mode === 'clone' ? 'Clone ' : 'Edit ') + page.singular }] : [];
  return <><PageNavigation back={back || resource ? { href: destination, label: resource ? administrationBackLabel(destination) : backLabel ?? 'directory' } : undefined} breadcrumbs={breadcrumbs} onNavigate={onLeave} /><nav className="janso-page-navigation" aria-label="Access administration">
    {links.length > 0 && <a className="janso-link" href="/organisation" onClick={onLeave}>Organisation</a>}
    {links.map(link => <a key={link.href} className="janso-link" href={link.href} aria-current={page?.href === link.href ? 'page' : undefined} onClick={onLeave}>{link.label}</a>)}
    <a className="janso-link" href="/my-access" aria-current={resource === 'my-access' ? 'page' : undefined} onClick={onLeave}>My access</a>
  </nav></>;
}
export function AccessFailure({ failure, refresh, uncertain = false }: { failure: RequestFailure | null; refresh?: () => void; uncertain?: boolean }) {
  if (!failure) return null;
  if (uncertain) return <Notice tone="danger"><p>The result of this change could not be confirmed. Your values are retained. Review the latest record or directory before trying again.</p>{refresh && <Button type="button" variant="ghost" onClick={refresh}>Reload and review</Button>}</Notice>;
  if (failure.status === 409 || failure.status === 422) return <Notice tone="danger">{failure.message}{failure.status === 409 ? ' Reload and review the latest record before saving again.' : ''}</Notice>;
  return <ErrorState status={asErrorStatus(failure.status)} detail={failure.message} action={refresh && ![401, 403].includes(failure.status) ? <Button type="button" onClick={refresh}>Retry loading</Button> : undefined} />;
}
export function useAccessDraft(dirty: boolean, pending: boolean) {
  const [leaving, setLeaving] = useState<string | null>(null);
  const discarded = useRef(false);
  useUnsavedChanges(() => !discarded.current && (dirty || pending));
  function leave(event: React.MouseEvent<HTMLAnchorElement>) {
    if (dirty || pending) { event.preventDefault(); if (!pending) setLeaving(event.currentTarget.href); }
  }
  const confirmation = <ConfirmDialog open={!!leaving} title="Discard unsaved changes?" confirmLabel="Discard and leave" onCancel={() => setLeaving(null)} onConfirm={() => { if (leaving) { discarded.current = true; goTo(leaving); } }}>Your changes have not been saved.</ConfirmDialog>;
  return { leave, confirmation };
}
export function AccessFocusErrors({ fields }: { fields: Record<string, string> }) {
  const previous = useRef<string[]>([]);
  useEffect(() => {
    const keys = Object.keys(fields), added = keys.some(key => !previous.current.includes(key));
    previous.current = keys;
    if (added) document.querySelector<HTMLInputElement>('main [aria-invalid="true"], .janso-page [aria-invalid="true"]')?.focus();
  }, [fields]);
  return null;
}
