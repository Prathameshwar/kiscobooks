import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { TextField } from '@janso/ui';
import { Providers } from '../../app/providers';
import { ConsoleShell } from '../../app/components/ConsoleShell';
import { CompanyReadiness } from '../../app/components/CompanyReadiness';
import { useEditorDraft } from '../../app/platform/useEditorDraft';
import type { Session } from '../../app/session';
import type { CompanyContext } from '../../app/lib/company-context';
import '@janso/ui/styles/tokens.css';
import '@janso/ui/styles/theme-light.css';
import '@janso/ui/styles/theme-dark.css';
import '@janso/ui/styles/theme-ledger.css';
import '@janso/ui/styles/janso-ui.css';
import '@janso/ui/styles/theme.css';
import '@janso/ui/styles/shell.css';
import '@janso/ui/styles/data.css';
import '@janso/ui/styles/overlay.css';
import '@janso/ui/styles/table.css';
import '@janso/ui/styles/setup.css';
import '../../app/globals.css';
import '../../app/console.css';
declare global { interface Window { __COMPANY_FIXTURE__: { session: Session; context: CompanyContext } } }
const { session, context } = window.__COMPANY_FIXTURE__;
function Workspace() {
  const [draft, setDraft] = useState('');
  const editor = useEditorDraft('company-foundation-browser', { name: '' });
  return <><CompanyReadiness company={session.company.id!} name={session.company.name} permissions={session.permissions} year={context.fiscalYear} fiscalNote={context.fiscalNote} />
    <TextField label="Fixture protected draft" value={editor.draft.name} onChange={event => editor.change({ name: event.target.value })} />
    <button onClick={editor.saved}>Save fixture draft</button>
    <TextField label="Fixture draft to verify context reset" value={draft} onChange={event => setDraft(event.target.value)} /></>;
}
createRoot(document.getElementById('root')!).render(<Providers session={session}><ConsoleShell session={session} context={context} activeHref="/settings"><Workspace /></ConsoleShell></Providers>);
