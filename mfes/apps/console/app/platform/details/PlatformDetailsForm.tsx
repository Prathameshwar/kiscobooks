'use client';

import { useEffect, useRef, useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, Card, CardBody, FormActions, FormLayout, Notice, PageHeader, PageNavigation, SectionHeader, TextField } from '@janso/ui';
import { PlatformError, platformCall, platformFailure, type PlatformFailure } from '../../lib/platform-api';
import { useEditorDraft } from '../useEditorDraft';
import { PlatformHistory } from '../../components/PlatformHistory';

type Details = components['schemas']['PlatformDetails'];
export function PlatformDetailsForm({ scope }: { scope: string }) {
  const editor = useEditorDraft<Details>(scope + ':platform', { name: '', public_url: '' });
  const { draft } = editor;
  const [loading, setLoading] = useState(true), [pending, setPending] = useState(false), [reload, setReload] = useState(0);
  const [error, setError] = useState<PlatformFailure | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [success, setSuccess] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const busy = useRef(false), form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(null);
    platformCall<Details>('/v1/platform/details', 'GET', undefined, undefined, controller.signal)
      .then(value => { if (!controller.signal.aborted) { editor.populate(value); setLoaded(true); setLoading(false); } })
      .catch(value => { if (!controller.signal.aborted) { setError(platformFailure(value)); setLoading(false); } });
    return () => controller.abort();
    // Editor population deliberately preserves a recovered or locally edited draft.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reload]);
  async function save() {
    if (busy.current || loading) return;
    const invalid: Record<string, string> = {};
    if (!draft.name.trim() || draft.name.length > 200 || /[\x00-\x1f]/.test(draft.name)) invalid.name = 'Enter a valid platform name with up to 200 characters.';
    try {
      const url = new URL(draft.public_url);
      if (draft.public_url.length > 2048 || !['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.search || url.hash || url.pathname !== '/' || /[\s\x00-\x1f]/.test(draft.public_url) ||
        url.port === '0' || (url.protocol === 'http:' && !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname))) throw new Error();
    } catch { invalid.public_url = 'Use an HTTPS application origin, or HTTP on localhost.'; }
    setFields(invalid); setSuccess(false); setError(null);
    if (Object.keys(invalid).length) { form.current?.elements.namedItem(Object.keys(invalid)[0]) && (form.current.elements.namedItem(Object.keys(invalid)[0]) as HTMLInputElement).focus(); return; }
    if (!form.current?.reportValidity()) return;
    busy.current = true; setPending(true);
    try { const value = await platformCall<Details>('/v1/platform/details', 'PATCH', { name: draft.name.trim(), public_url: draft.public_url });
      editor.saved(); editor.populate(value); setSuccess(true);
    } catch (value) { const failure = platformFailure(value); setError(failure); setFields(Object.fromEntries(Object.keys(failure.fields ?? {}).map(field => [field, 'Check this value and try again.']))); }
    finally { busy.current = false; setPending(false); }
  }
  const change = (field: keyof Details, value: string) => { editor.change({ [field]: value }); setFields(current => ({ ...current, [field]: '' })); setError(null); setSuccess(false); };
  // One guard for every way out of this page — the back chevron, a crumb, or Cancel.
  const leave = (event: React.MouseEvent<HTMLAnchorElement>) => {
    if (pending || (editor.touched.current && !window.confirm('Discard your unsaved changes?'))) event.preventDefault(); else editor.saved();
  };
  return <div className="janso-page">
    <PageNavigation back={{ href: '/platform', label: 'platform administration' }} onNavigate={leave}
      breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Platform details' }]} />
    <PageHeader title="Edit platform details" lede="Maintain the identity of your billing platform." />
    <PlatformError value={error} returnTo="/platform/details" onNavigate={() => { editor.preserve(); editor.touched.current = false; }} />
    {success ? <Notice tone="success">Platform details updated.</Notice> : null}
    {editor.restored ? <Notice>Your draft has been restored. Review it before saving.</Notice> : null}
    {loading ? <p role="status">Loading platform details…</p> : !loaded ? (error?.status === 403 || error?.status === 401 ? null : <Button variant="ghost" onClick={() => setReload(value => value + 1)}>Retry loading details</Button>) :
      <FormLayout aside={<><SectionHeader title="About these settings" />
        <p className="janso-fine">The public URL is installation metadata. Deployment addresses, login callbacks, and trusted origins are configured separately.</p>
        <p className="janso-fine">Your first administrator and completed setup remain protected. Saving requires a recent sign-in.</p></>}>
        <form ref={form} onSubmit={event => { event.preventDefault(); void save(); }} noValidate>
        <Card><CardBody><div className="janso-flow"><SectionHeader title="Platform identity" description="These details describe your installation." />
          <div className="janso-form-grid"><TextField label="Platform name" name="name" autoComplete="organization" required maxLength={200} disabled={pending} value={draft.name} error={fields.name} onChange={event => change('name', event.target.value)} />
            <TextField label="Public application URL" name="public_url" type="url" required maxLength={2048} disabled={pending} value={draft.public_url} error={fields.public_url} hint="For example, https://books.example.com. Use HTTP only on localhost." onChange={event => change('public_url', event.target.value)} /></div>
        </div></CardBody><FormActions cancel={{ href: '/platform', onClick: leave }}>
          <Button type="submit" loading={pending} loadingLabel="Saving…">Save changes</Button></FormActions></Card>
      </form></FormLayout>}
    {loaded ? <PlatformHistory entityType="platform_installation" revision={Number(success)} /> : null}
  </div>;
}
