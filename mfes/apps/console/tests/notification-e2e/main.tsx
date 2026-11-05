import React from 'react';
import { createRoot } from 'react-dom/client';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider, PermissionProvider, ThemeProvider } from '@janso/ui';
import { NotificationAdmin } from '../../app/components/NotificationAdmin';
import { NotificationEntryCard } from '../../app/components/NotificationEntryCard';
import '@janso/ui/styles/tokens.css';
import '@janso/ui/styles/theme-light.css';
import '@janso/ui/styles/theme-dark.css';
import '@janso/ui/styles/theme-ledger.css';
import '@janso/ui/styles/janso-ui.css';
import '@janso/ui/styles/theme.css';
import '@janso/ui/styles/shell.css';
import '@janso/ui/styles/data.css';
import '@janso/ui/styles/search-select.css';
import '@janso/ui/styles/overlay.css';
import '@janso/ui/styles/table.css';
import '@janso/ui/styles/setup.css';
import '../../app/globals.css';
import '../../app/console.css';

declare global { interface Window { __NOTIFICATION_FIXTURE__: { companyId: string; profile: string } } }
const owner = location.pathname.startsWith('/platform') ? 'platform' : 'tenant';
const prefix = owner === 'platform' ? 'platform.notification_' : 'notification.';
const read = ['provider', 'template', 'route', 'recipient', 'request', 'delivery'].map(family => prefix + family + '.read');
const permissions = window.__NOTIFICATION_FIXTURE__.profile === 'reader' ? read : [...read, ...['provider', 'template', 'route', 'consent', 'suppression'].map(family => prefix + family + '.manage'), prefix + 'delivery.retry'];
const root = owner === 'platform' ? '/platform/notifications' : '/settings/notifications';
const route = location.pathname.startsWith(root) ? location.pathname.slice(root.length).split('/').filter(Boolean) : [];
const query = Object.fromEntries(new URLSearchParams(location.search));
const home = location.pathname === '/platform' || location.pathname === '/settings';
createRoot(document.getElementById('root')!).render(<ThemeProvider initial="light"><DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><PermissionProvider permissions={permissions}><main className="janso-root janso-page">
  {home ? <NotificationEntryCard owner={owner} permissions={permissions} /> : <NotificationAdmin owner={owner} permissions={permissions} route={route} query={query} companyId={owner === 'tenant' ? window.__NOTIFICATION_FIXTURE__.companyId : undefined} />}
</main></PermissionProvider></DisplayConfigProvider></ThemeProvider>);
