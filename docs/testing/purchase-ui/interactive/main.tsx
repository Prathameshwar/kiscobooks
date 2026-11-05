import React from 'react';
import { createRoot } from 'react-dom/client';
import { DisplayConfigProvider, ThemeProvider, type SearchSelectLoader } from '@janso/ui';
import { PurchaseWorkspace } from '../../../../mfes/apps/console/app/components/PurchaseWorkspace';
import { PurchaseWorkflowWorkspace } from '../../../../mfes/apps/console/app/components/PurchaseWorkflowWorkspace';
import { PurchaseEntryConnected } from '../../../../mfes/apps/console/app/components/PurchaseEntryConnected';
import { reviewFixture } from './review-fixtures';
import '../../../../mfes/packages/ui/src/styles/fonts.css';
import '../../../../mfes/packages/ui/src/styles/tokens.css';
import '../../../../mfes/packages/ui/src/styles/theme-light.css';
import '../../../../mfes/packages/ui/src/styles/theme-dark.css';
import '../../../../mfes/packages/ui/src/styles/theme-ledger.css';
import '../../../../mfes/packages/ui/src/styles/janso-ui.css';
import '../../../../mfes/packages/ui/src/styles/controls.css';
import '../../../../mfes/packages/ui/src/styles/theme.css';
import '../../../../mfes/packages/ui/src/styles/shell.css';
import '../../../../mfes/packages/ui/src/styles/data.css';
import '../../../../mfes/packages/ui/src/styles/search-select.css';
import '../../../../mfes/packages/ui/src/styles/file-upload.css';
import '../../../../mfes/packages/ui/src/styles/overlay.css';
import '../../../../mfes/packages/ui/src/styles/entry.css';
import '../../../../mfes/apps/console/app/globals.css';
import '../../../../mfes/apps/console/app/console.css';

// Isolated actual-component review. Not mounted by Next and never bypasses app authentication.
const params = new URLSearchParams(location.search);
const theme = params.get('theme') === 'dark' ? 'dark' : params.get('theme') === 'ledger' ? 'ledger' : 'light';
const { draft, policy, display } = reviewFixture(params);
const supplierLookup: SearchSelectLoader | undefined = params.has('slowlookup') ? async ({ q, signal }) => {
  await new Promise<void>((resolve, reject) => {
    const timer = setTimeout(resolve, q === 'Pa' ? 1800 : 700);
    signal.addEventListener('abort', () => { clearTimeout(timer); reject(new DOMException('Cancelled', 'AbortError')); }, { once: true });
  });
  if (q === 'error') throw Error('Synthetic lookup unavailable');
  return { items: policy.suppliers.filter(supplier => supplier.label.toLocaleLowerCase().includes(q.toLocaleLowerCase())), nextCursor: null };
} : undefined;
if (params.has('locale')) document.documentElement.lang = 'de-DE';
createRoot(document.getElementById('root')!).render(<ThemeProvider initial={theme}><DisplayConfigProvider config={{ ...display, currency: 'INR', currencySymbol: '₹' }}>
  <main className="janso-page">{params.has('connected') ? <PurchaseEntryConnected company="10000000-0000-7000-8000-000000000001" actor="10000000-0000-7000-8000-000000000012" year="10000000-0000-7000-8000-000000000013" currency="INR" canCreate permissions={['vouchers.read', 'vouchers.create', 'vouchers.edit', 'vouchers.submit']} /> : params.has('workflow') ? <PurchaseWorkflowWorkspace context={{ company: 'review-company', year: '2026-27' }} today="2026-10-31"
    permissions={{ create: true, edit: !params.has('readonly'), submit: !params.has('readonly') }} initialExample={params.get('workflow') || 'NEW'} policy={policy}
    initialDraft={params.has('blank') ? undefined : draft} supplierLookup={supplierLookup} />
    : <PurchaseWorkspace today="2026-10-31" canCreate policy={policy} initialDraft={params.has('blank') ? undefined : draft} supplierLookup={supplierLookup} />}</main>
</DisplayConfigProvider></ThemeProvider>);
