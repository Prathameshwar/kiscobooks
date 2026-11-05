import {
  ActionCard,
  ErrorState,
  Notice,
  PageHeader,
  SectionHeader,
  SettingsIcon,
} from '@janso/ui';
import { notFound } from 'next/navigation';
import { pageContext } from '../lib/page-context';
import { partyCompanyCountry } from '../lib/party-company-country';
import { companyPermission } from '../lib/company-permissions';
import {
  accountingBack,
  accountingLink,
  accountingPermission,
  accountingResource,
  accountingResources,
  accountingUUID,
} from '../lib/accounting-configuration-resources';
import { Providers } from '../providers';
import { ConsoleShell } from './ConsoleShell';
import { NoCompany } from './NoCompany';
import { AccountingNavigation } from './AccountingConfigurationCommon';
import { AccountingConfigurationDirectory } from './AccountingConfigurationDirectory';
import { AccountingConfigurationEditor } from './AccountingConfigurationEditor';
import {
  AccountingConfigurationDetail,
  AccountingConfigurationHistory,
} from './AccountingConfigurationDetail';
import { AccountingConfigurationSetup } from './AccountingConfigurationSetup';
import {
  AccountingExchangeDetail,
  AccountingExchangeDirectory,
  AccountingExchangeEditor,
} from './AccountingExchangeRates';
import {
  accountingDescription,
  accountingDescriptions,
  accountingMasters,
} from '../lib/accounting-masters';

export async function AccountingConfigurationPage({
  segments = [],
  query = {},
}: {
  segments?: string[];
  query?: Record<string, string | string[] | undefined>;
} = {}) {
  const overview = segments.length === 0,
    setup = segments.length === 1 && segments[0] === 'setup',
    supplier = segments[0] === 'suppliers',
    exchange = segments[0] === 'exchange-rates',
    config = accountingResource(supplier ? 'parties' : segments[0]);
  const creating = segments.length === 2 && segments[1] === 'new',
    id = segments[1]?.toLowerCase(),
    detail = segments.length === 2 && accountingUUID.test(id ?? ''),
    editing =
      segments.length === 3 &&
      segments[2] === 'edit' &&
      accountingUUID.test(id ?? ''),
    history =
      segments.length === 3 &&
      segments[2] === 'history' &&
      accountingUUID.test(id ?? '');
  if (
    !overview &&
    !setup &&
    (exchange
      ? !(segments.length === 1 || detail || creating)
      : !config ||
        !(
          segments.length === 1 ||
          detail ||
          (!config.workflow && history) ||
          (!config.readonly && (creating || (!config.workflow && editing)))
        ))
  )
    notFound();
  const { session, context } = await pageContext(),
    company = session.company.id;
  const available: string[] = company
    ? accountingResources
        .filter((candidate) =>
          companyPermission(
            session,
            accountingPermission(candidate, 'read'),
            company,
          ),
        )
        .map((candidate) => candidate.resource)
    : [];
  if (company && companyPermission(session, 'accounting.finance.read', company))
    available.push('exchange-rates');
  const manageable = company
    ? accountingResources
        .filter(
          (candidate) =>
            !candidate.readonly &&
            available.includes(candidate.resource) &&
            companyPermission(
              session,
              accountingPermission(candidate, 'manage'),
              company,
            ) &&
            (candidate.resource !== 'posting-mappings' ||
              companyPermission(
                session,
                'accounting.mapping.publish',
                company,
              )),
        )
        .map((candidate) => candidate.resource)
    : [];
  const canRead = overview
    ? available.length > 0
    : setup
      ? !!company &&
        companyPermission(session, 'accounting.setup.read', company)
      : exchange
        ? available.includes('exchange-rates')
        : !!company && !!config && available.includes(config.resource);
  const canManage =
    !!company &&
    (setup
      ? companyPermission(session, 'accounting.setup.manage', company)
      : exchange
        ? companyPermission(session, 'accounting.finance.manage', company)
        : !!config && manageable.includes(config.resource));
  const canHistory =
      !!company &&
      companyPermission(session, 'accounting.history.read', company),
    returnTo = typeof query.returnTo === 'string' ? query.returnTo : undefined;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query))
    if (typeof value === 'string') params.set(key, value);
  const prefills: Record<string, string> = {};
  for (const key of [
    'party_id',
    'account_id',
    'group_id',
    'payment_term_id',
    'section_id',
    'commercial_type_id',
    'role',
    'kind',
  ])
    if (typeof query[key] === 'string') prefills[key] = query[key] as string;
  const overviewHere = accountingLink(
    '/accounting',
    accountingBack(returnTo, '/settings'),
  );
  const fromOverview = (path: string) =>
    returnTo ? accountingLink(path, overviewHere) : path;
  const primary: readonly string[] = accountingMasters;
  const companyCountry = company && creating && config?.resource === 'parties' &&
    canRead && canManage && companyPermission(session, 'company.read', company)
    ? await partyCompanyCountry(company) : undefined;
  return (
    <Providers session={session}>
      <ConsoleShell
        session={session}
        context={context}
        activeHref={
          overview || setup
            ? '/accounting'
            : '/accounting/' +
              (exchange
                ? 'exchange-rates'
                : supplier
                  ? 'suppliers'
                  : config!.resource)
        }
      >
        {!company ? (
          <NoCompany
            action="configure"
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : !canRead ||
          ((creating || editing) && !canManage) ||
          (history && !canHistory) ? (
          <ErrorState
            status={403}
            detail="The requested Accounting read/action permission is required for this company."
          />
        ) : overview ? (
          <div className="janso-page">
            <AccountingNavigation
              title="Accounting configuration"
              back={accountingBack(returnTo, '/settings')}
            />
            <PageHeader
              title="Accounting configuration"
              lede="Set up your chart, ledger identities, parties and financial policies for the current company."
            />
            <Notice>
              Start with the chart and account groups, then configure accounts
              and parties. Dated rates and policies retain their evidence and
              financial history.
            </Notice>
            <div className="janso-action-card-grid">
              {accountingResources
                .filter(
                  (candidate) =>
                    primary.includes(candidate.resource) &&
                    available.includes(candidate.resource),
                )
                .map((candidate) => (
                  <ActionCard
                    key={candidate.resource}
                    title={
                      candidate.resource === 'accounts'
                        ? 'Ledger accounts'
                        : candidate.title
                    }
                    description={accountingDescription(candidate)}
                    icon={<SettingsIcon />}
                    actionLabel="Open configuration"
                    href={fromOverview('/accounting/' + candidate.resource)}
                  />
                ))}
              {available.includes('exchange-rates') && (
                <ActionCard
                  title="Exchange rates"
                  description={accountingDescriptions['exchange-rates']}
                  icon={<SettingsIcon />}
                  actionLabel="Open quotes"
                  href={fromOverview('/accounting/exchange-rates')}
                />
              )}
              {available.includes('parties') && (
                <ActionCard
                  title="Suppliers"
                  description="Manage suppliers using their shared party identities and active supplier roles."
                  icon={<SettingsIcon />}
                  actionLabel="Open suppliers"
                  href={fromOverview('/accounting/suppliers')}
                />
              )}
              {available.includes('accounting-setup') && (
                <ActionCard
                  title="Company Accounting setup"
                  description="Initialize native books and review chart installation or upgrades."
                  icon={<SettingsIcon />}
                  actionLabel="Configure books"
                  href={fromOverview('/accounting/setup')}
                />
              )}
            </div>
            <SectionHeader
              title="Supporting configuration"
              description="Open permitted profiles, defaults, evidence and installed chart records."
            />
            <div className="janso-action-card-grid">
              {accountingResources
                .filter(
                  (candidate) =>
                    !primary.includes(candidate.resource) &&
                    candidate.resource !== 'accounting-setup' &&
                    available.includes(candidate.resource),
                )
                .map((candidate) => (
                  <ActionCard
                    key={candidate.resource}
                    title={candidate.title}
                    description={accountingDescription(candidate)}
                    icon={<SettingsIcon />}
                    actionLabel="Open configuration"
                    href={fromOverview('/accounting/' + candidate.resource)}
                  />
                ))}
            </div>
          </div>
        ) : setup ? (
          <AccountingConfigurationSetup
            key={company}
            company={company}
            canManage={canManage}
            returnTo={returnTo}
          />
        ) : exchange ? (
          creating ? (
            <AccountingExchangeEditor
              key={company}
              company={company}
              returnTo={returnTo}
            />
          ) : detail ? (
            <AccountingExchangeDetail
              key={company + ':' + id}
              company={company}
              id={id!}
              userId={session.user.id}
              canManage={canManage}
              returnTo={returnTo}
            />
          ) : (
            <AccountingExchangeDirectory
              key={company}
              company={company}
              canManage={canManage}
              initialQuery={params.toString()}
            />
          )
        ) : creating || editing ? (
          <AccountingConfigurationEditor
            key={company + ':' + segments.join('/')}
            company={company}
            companyCountry={companyCountry}
            config={config!}
            id={editing ? id : undefined}
            supplier={supplier}
            availableResources={available}
            manageableResources={manageable}
            canCreateCompanyBank={
              companyPermission(session, 'company.read', company) &&
              companyPermission(session, 'company.update', company)
            }
            returnTo={returnTo}
            prefills={prefills}
          />
        ) : history ? (
          <AccountingConfigurationHistory
            key={company + ':' + id}
            company={company}
            config={config!}
            id={id!}
            returnTo={returnTo}
          />
        ) : detail ? (
          <AccountingConfigurationDetail
            key={company + ':' + id}
            company={company}
            config={config!}
            id={id!}
            canManage={canManage}
            canHistory={canHistory}
            availableResources={available}
            manageableResources={manageable}
            returnTo={returnTo}
            supplierSetup={query.setup === 'SUPPLIER'}
            canOpening={companyPermission(session, 'accounting.finance.read', company)}
          />
        ) : (
          <AccountingConfigurationDirectory
            key={company + ':' + segments[0]}
            company={company}
            config={config!}
            canManage={canManage}
            supplier={supplier}
            canOpening={companyPermission(session, 'accounting.finance.read', company)}
            initialQuery={params.toString()}
            canHistory={canHistory}
            canSetup={available.includes('accounting-setup')}
            canImport={companyPermission(
              session,
              'accounting.import.manage',
              company,
            )}
            availableResources={available}
            manageableResources={manageable}
            canReadCompanyConfiguration={companyPermission(
              session,
              'company.read',
              company,
            )}
            canManagePartyPricing={
              companyPermission(session, 'customer_pricing.read', company) &&
              companyPermission(session, 'customer_pricing.manage', company)
            }
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
