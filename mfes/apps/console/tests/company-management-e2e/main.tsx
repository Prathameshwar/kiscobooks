import React from 'react';
import { createRoot } from 'react-dom/client';
import { ThemeProvider, ThemeSwitcher, DisplayConfigProvider, PermissionProvider } from '@janso/ui';
import { CompanyDirectory } from '../../app/components/CompanyDirectory';
import { CompanyProfile } from '../../app/components/CompanyProfile';
import { CompanyFinancialYears } from '../../app/components/CompanyFinancialYears';
import { companyId, yearId } from './api';
import type { Session } from '../../app/session';
import '@janso/ui/styles/tokens.css';
import '@janso/ui/styles/theme-light.css';
import '@janso/ui/styles/theme-dark.css';
import '@janso/ui/styles/theme-ledger.css';
import '@janso/ui/styles/janso-ui.css';
import '@janso/ui/styles/theme.css';
import '@janso/ui/styles/data.css';
import '@janso/ui/styles/table.css';
import '@janso/ui/styles/overlay.css';
import '@janso/ui/styles/setup.css';
import '../../app/console.css';

const permissions = ['company.read', 'company.update', 'company.create', 'period.read', 'period.manage', 'period.close', 'period.reopen', 'period.lock', 'accounting.finance.read', 'accounting.finance.initialize'];
const session = { grants: [{ scope_type: 'tenant', scope_id: null, valid_from: '2020-01-01', valid_to: null, permissions }] } as Session;
createRoot(document.getElementById('root')!).render(<ThemeProvider initial="light"><PermissionProvider permissions={permissions}><DisplayConfigProvider>
  <div className="janso-page"><ThemeSwitcher />
    {window.location.pathname.includes('/years') ? <CompanyFinancialYears session={session} companyId={companyId} companyName="Acme Manufacturing"
      mode={window.location.pathname.endsWith('/new') ? 'new' : 'list'} yearId={window.location.pathname.endsWith('/' + yearId) ? yearId : undefined} />
      : window.location.pathname === '/companies/manage' ? <CompanyDirectory session={session} /> : <CompanyProfile companyId={companyId} canEdit editing={window.location.pathname.endsWith('/edit')} />}
  </div>
</DisplayConfigProvider></PermissionProvider></ThemeProvider>);
