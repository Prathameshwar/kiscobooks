'use client';
import { SubjectHistory } from './SubjectHistory';
import { MasterOpeningSummary } from './MasterOpeningSummary';
import { ACCOUNTING_AUDIT_ENTITIES_BY_RESOURCE } from '../lib/master-audit-entities';
import { useRef, useState } from 'react';
import {
  ActionCard,
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  DataTable,
  Menu,
  Notice,
  PageHeader,
  ReviewList,
  SettingsIcon,
  SectionHeader,
  SplitButton,
  TextField,
  useFormatters,
  type Column,
  type MenuItem,
} from '@janso/ui';
import {
  accountingDescription,
  accountingRelations,
  accountingRelationshipSections,
} from '../lib/accounting-masters';
import { validMasterDate } from '../lib/catalog-masters';
import { accountRelatedActions } from '../lib/account-related-actions';
import type { components } from '@janso/api-client/accounting';
import {
  accountingBase,
  assertAccountingRecord,
  useAccountingCommand,
  useAccountingRecord,
} from '../lib/accounting-configuration';
import {
  accountingBack,
  accountingLabel,
  accountingLink,
  accountingResources,
  accountingRoot,
  type AccountingRecord,
  type AccountingResourceConfig,
} from '../lib/accounting-configuration-resources';
import { useServiceList } from '../lib/service-resource';
import { accountingRequest } from '../lib/accounting-configuration';
import { useAccessDraft } from './AccessCommon';
import {
  AccountingFailure,
  AccountingSections,
  AccountingLoading,
  AccountingNavigation,
  AccountingPager,
} from './AccountingConfigurationCommon';

export function AccountingConfigurationDetail({
  company,
  config,
  id,
  canManage,
  canHistory,
  availableResources,
  manageableResources = [],
  returnTo,
  supplierSetup = false,
  canOpening = false,
}: {
  company: string;
  config: AccountingResourceConfig;
  id: string;
  canManage: boolean;
  canHistory: boolean;
  availableResources: readonly string[];
  manageableResources?: readonly string[];
  returnTo?: string;
  supplierSetup?: boolean;
  canOpening?: boolean;
}) {
  const read = useAccountingRecord(company, config, id, false),
    command = useAccountingCommand(),
    format = useFormatters();
  const relatedRegion = useRef<HTMLElement>(null);
  const [action, setAction] = useState<
      'activate' | 'deactivate' | 'close' | null
    >(null),
    [reviewing, setReviewing] = useState(false),
    [message, setMessage] = useState(''),
    [endDate, setEndDate] = useState(''),
    [endError, setEndError] = useState('');
  const guard = useAccessDraft(reviewing || command.uncertain, command.pending),
    back = accountingBack(returnTo, accountingRoot + '/' + config.resource),
    here = accountingLink(
      accountingRoot +
        '/' +
        config.resource +
        '/' +
        id +
        (supplierSetup ? '?setup=SUPPLIER' : ''),
      back,
    );
  const row = read.record,
    verified = !!row && !!read.metadata && !read.loading && !read.failure,
    permittedManage = canManage && !!read.metadata?.can_manage,
    retired = row?.status === 'INACTIVE',
    active = row?.status === 'ACTIVE',
    blocked = command.pending || command.uncertain,
    status = active
      ? 'Active'
      : retired
        ? 'Retired'
        : row?.status === 'DRAFT'
          ? 'Draft'
          : 'Not readable';
  const items: MenuItem[] = [
    ...(permittedManage && !config.readonly && !config.workflow && !retired
      ? [
          {
            id: 'edit',
            label: 'Edit',
            href: accountingLink(here.split('?')[0] + '/edit', here),
            disabledReason: blocked
              ? 'Resolve the unconfirmed change first'
              : undefined,
          },
        ]
      : []),
    ...(permittedManage &&
    config.workflow === 'charge' &&
    row?.valid_from &&
    read.metadata?.fields.some(
      (field) =>
        field.key === 'valid_to' &&
        field.readable &&
        field.writable &&
        field.visible &&
        !field.conditional_access,
    )
      ? [
          {
            id: 'close',
            label: 'Close policy',
            disabledReason: blocked
              ? 'Resolve the unconfirmed change first'
              : undefined,
          },
        ]
      : []),
    ...(permittedManage && row?.status === 'DRAFT'
      ? [
          {
            id: 'activate',
            label: 'Activate',
            disabledReason: blocked
              ? 'Resolve the unconfirmed change first'
              : undefined,
          },
        ]
      : []),
    ...(permittedManage && active && !row?.system_key
      ? [
          {
            id: 'deactivate',
            label: 'Retire',
            destructive: true,
            disabledReason: blocked
              ? 'Resolve the unconfirmed change first'
              : undefined,
          },
        ]
      : []),
    ...(canHistory && !config.workflow
      ? [
          {
            id: 'history',
            label: 'View history',
            href: accountingLink(here.split('?')[0] + '/history', here),
            disabledReason: blocked
              ? 'Resolve the unconfirmed change first'
              : undefined,
          },
        ]
      : []),
  ];
  async function apply() {
    if (!row || !action || !permittedManage || command.pending) return;
    if (command.blocked && !command.uncertain) {
      command.clear();
      setReviewing(false);
      setAction(null);
      read.refresh();
      return;
    }
    if (
      action === 'close' &&
      (!validMasterDate(endDate) ||
        endDate < String(row.valid_from) ||
        (row.valid_to && endDate >= String(row.valid_to)))
    ) {
      setEndError(
        'Choose an end date on or after the start date and earlier than the existing end date.',
      );
      return;
    }
    const saved = await command.execute<AccountingRecord>(
      {
        path: accountingBase(company, config) + '/' + id + '/' + action,
        method: 'POST',
        body: {
          expected_version: row.row_version,
          ...(action === 'close' ? { valid_to: endDate } : {}),
        },
      },
      (value) => {
        assertAccountingRecord(value, company, id);
        if (
          value.row_version <= row.row_version ||
          (action === 'close'
            ? value.valid_to !== endDate
            : value.status !== (action === 'activate' ? 'ACTIVE' : 'INACTIVE'))
        )
          throw {
            status: 502,
            message: 'The lifecycle result could not be verified.',
          };
      },
    );
    if (saved) {
      read.setRecord(saved);
      setReviewing(false);
      setAction(null);
      setMessage(
        action === 'close'
          ? 'Policy end date saved successfully.'
          : action === 'activate'
            ? 'Record activated successfully.'
            : 'Record retired. Its history and references are retained.',
      );
    }
  }
  const owner =
    config.resource === 'parties'
      ? 'party_id'
      : config.resource === 'accounts'
        ? 'account_id'
        : config.resource === 'account-groups'
          ? 'group_id'
          : config.resource === 'payment-terms'
            ? 'payment_term_id'
            : undefined;
  const related = accountingResources
    .filter(
      (candidate) =>
        candidate.owner === owner &&
        owner &&
        availableResources.includes(candidate.resource),
    )
    .map((candidate) => ({ config: candidate, filter: owner! }));
  for (const link of accountingRelations(config.resource)) {
    const candidate = accountingResources.find(
      (value) => value.resource === link.resource,
    );
    if (candidate && availableResources.includes(candidate.resource))
      related.push({ config: candidate, filter: link.filter });
  }
  const relatedActions =
    verified && config.resource === 'accounts'
      ? accountRelatedActions(
          row!,
          read.metadata!.fields,
          here,
          availableResources,
          manageableResources,
        )
      : verified && config.resource === 'parties'
        ? related.map(({ config: child, filter }) => ({
            id: 'manage-' + child.resource,
            label: 'Manage ' + child.title.toLowerCase(),
            href: accountingLink(
              '/accounting/' +
                child.resource +
                '?' +
                new URLSearchParams({ [filter]: id }),
              here,
            ),
          }))
        : [];
  const edit = items.find((item) => item.id === 'edit');
  const requiredProfile =
    verified &&
    config.resource === 'accounts' &&
    row!.status === 'DRAFT' &&
    read.metadata!.fields.some(
      (field) =>
        field.key === 'kind' &&
        field.readable &&
        field.visible &&
        !field.conditional_access,
    )
      ? row!.kind === 'BANK'
        ? 'bank'
        : row!.kind === 'TAX'
          ? 'tax'
          : undefined
      : undefined;
  const profileArea = requiredProfile
    ? relatedActions.find(
        (item) => item.id === 'manage-account-' + requiredProfile + '-profiles',
      )
    : undefined;
  const primary = edit
    ? {
        ...edit,
        label: config.resource === 'parties' ? 'Edit party' : 'Edit account',
      }
    : related.length
      ? { id: 'related', label: 'Related configuration' }
      : (items.find((item) => item.id === 'history') ?? relatedActions[0]);
  function selectAction(value: string) {
    if (blocked || reviewing) return;
    if (value === 'related') {
      relatedRegion.current?.scrollIntoView?.({
        block: 'start',
        behavior: 'smooth',
      });
      relatedRegion.current?.focus({ preventScroll: true });
    } else if (
      value === 'activate' ||
      value === 'deactivate' ||
      value === 'close'
    ) {
      if (!items.some((item) => item.id === value && !item.disabledReason))
        return;
      command.clear();
      setAction(value);
      setEndDate('');
      setEndError('');
      setReviewing(true);
    }
  }
  return (
    <div className="janso-page">
      <AccountingNavigation
        title={config.singular + ' configuration'}
        back={back}
        onLeave={guard.leave}
        resource={config.resource}
        availableResources={availableResources}
        id={id}
        mode="detail"
      />
      <PageHeader
        title={row ? accountingLabel(row) : config.singular + ' configuration'}
        lede={accountingDescription(config)}
        actions={
          verified &&
          (items.length ||
            relatedActions.length ||
            ['accounts', 'parties'].includes(config.resource)) ? (
            <div className="janso-form-actions">
              {canOpening && ['accounts', 'parties'].includes(config.resource) && <a className="janso-link" href={'/accounting/opening?' + new URLSearchParams({ [config.resource === 'parties' ? 'party_id' : 'account_id']: id })} onClick={guard.leave}>Opening balances</a>}
              {['accounts', 'parties'].includes(config.resource) && primary && (
                <SplitButton
                  label={
                    config.resource === 'parties'
                      ? 'Party actions'
                      : 'Account actions'
                  }
                  variant="primary"
                  primary={primary}
                  items={[...relatedActions, ...items]}
                  onSelect={selectAction}
                  onNavigate={guard.leave}
                  disabledReason={
                    blocked
                      ? 'Resolve the unconfirmed change first'
                      : reviewing
                        ? 'Finish or cancel the current action first'
                        : undefined
                  }
                  loading={command.pending}
                />
              )}
              {['accounts', 'parties'].includes(config.resource) && (
                <Button
                  type="button"
                  variant="ghost"
                  disabled
                  title={
                    config.resource === 'parties'
                      ? 'Merging duplicate parties will be available in a future update.'
                      : 'Merging duplicate accounts will be available in a future update.'
                  }
                >
                  {config.resource === 'parties'
                    ? 'Merge parties'
                    : 'Merge accounts'}
                </Button>
              )}
              {items.length > 0 && (
                <Menu
                  label="Record actions"
                  items={items}
                  onSelect={selectAction}
                  onNavigate={guard.leave}
                />
              )}
            </div>
          ) : undefined
        }
      />
      <AccountingFailure
        failure={read.failure}
        retry={read.refresh}
        onLeave={guard.leave}
      />
      {read.loading ? (
        <AccountingLoading />
      ) : (
        row &&
        read.metadata && (
          <>
            {message && <Notice tone="success">{message}</Notice>}
            {read.metadata.unavailable_reason && (
              <Notice tone="warning">
                {read.metadata.unavailable_reason}{' '}
                <a
                  className="janso-link"
                  href={accountingLink(
                    '/companies/' + company + '/configuration',
                    here,
                  )}
                >
                  Open Company Config
                </a>
              </Notice>
            )}
            {read.metadata.notices?.map((note) => (
              <Notice key={note}>{note}</Notice>
            ))}
            {retired && (
              <Notice>
                Retired identities retain their history and cannot be
                reactivated. Create a new record when needed.
              </Notice>
            )}
            {['accounts', 'parties'].includes(config.resource) &&
              row.status === 'DRAFT' && (
                <Notice>
                  {config.resource === 'parties'
                    ? 'Draft party. Review and activate this identity before completing its customer or supplier roles.'
                    : 'Draft account. Review its group, currency and posting controls before activation.'}
                </Notice>
              )}
            {supplierSetup && (
              <Notice>
                Party saved. To finish supplier setup, activate this party, then{' '}
                {active &&
                availableResources.includes('party-roles') &&
                manageableResources.includes('party-roles') ? (
                  <a
                    className="janso-link"
                    href={accountingLink(
                      '/accounting/party-roles/new?' +
                        new URLSearchParams({ party_id: id, role: 'SUPPLIER' }),
                      here,
                    )}
                    onClick={guard.leave}
                  >
                    add its supplier role
                  </a>
                ) : (
                  <span>
                    add its supplier role with the required party management
                    access
                  </span>
                )}{' '}
                and activate that role. It will then appear in Suppliers.
              </Notice>
            )}
            {requiredProfile && (
              <Notice>
                {requiredProfile === 'bank'
                  ? 'Bank accounts require a profile linked to an available company bank before activation.'
                  : 'Tax accounts require a profile with the applicable duty, scheme, component and purpose before activation.'}{' '}
                {profileArea?.href && !blocked && !reviewing ? (
                  <a
                    className="janso-link"
                    href={profileArea.href}
                    onClick={guard.leave}
                  >
                    Review {requiredProfile} profile
                  </a>
                ) : !profileArea ? (
                  <span>
                    Ask an administrator with {requiredProfile} profile access
                    to complete this setup.
                  </span>
                ) : null}
              </Notice>
            )}
            {config.resource === 'party-commercial-types' &&
              canManage &&
              !retired &&
              availableResources.includes(
                'party-commercial-type-memberships',
              ) && (
                <Notice>
                  Assign this classification through a dated membership.{' '}
                  <a
                    className="janso-link"
                    href={accountingLink(
                      '/accounting/party-commercial-type-memberships/new?' +
                        new URLSearchParams({ commercial_type_id: id }),
                      here,
                    )}
                    onClick={guard.leave}
                  >
                    Assign to a party
                  </a>
                </Notice>
              )}
            <Card>
              <CardHeader title="Record details" />
              <CardBody>
                <ReviewList
                  items={[
                    ...(read.metadata.lifecycle === 'status'
                      ? [
                          {
                            label: 'Status',
                            value: (
                              <Badge tone={active ? 'success' : 'neutral'}>
                                {status}
                              </Badge>
                            ),
                          },
                        ]
                      : []),
                    ...(!['accounts', 'parties'].includes(config.resource)
                      ? [{ label: 'Version', value: String(row.row_version) }]
                      : []),
                    ...(row.created_at
                      ? [
                          {
                            label: 'Created',
                            value: format.dateTime(String(row.created_at)),
                          },
                        ]
                      : []),
                    ...(row.account_number_last4
                      ? [
                          {
                            label: 'Account number',
                            value: '•••• ' + row.account_number_last4,
                          },
                        ]
                      : []),
                  ]}
                />
              </CardBody>
            </Card>
            <AccountingSections
              readView={
                config.resource === 'accounts' || config.resource === 'parties'
              }
              company={company}
              resource={config.resource}
              fields={read.metadata.fields.filter(
                (field) => !field.control.write_only,
              )}
              values={row}
              disabled
              onChange={() => {}}
              returnTo={here}
              onLeave={guard.leave}
            />
            {related.length > 0 && (
              <section
                className="janso-flow"
                ref={relatedRegion}
                tabIndex={-1}
                aria-label={
                  config.resource === 'accounts'
                    ? 'Related account configuration'
                    : 'Related configuration'
                }
              >
                <SectionHeader
                  title="Related configuration"
                  description="Open each area to manage the records and dated defaults for this identity."
                />
                {accountingRelationshipSections(config.resource, related).map(
                  (group) => (
                    <section
                      key={group.title}
                      className="janso-flow"
                      aria-label={group.title}
                    >
                      <SectionHeader title={group.title} />
                      <div className="janso-action-card-grid">
                        {group.items.map(({ config: candidate, filter }) => (
                          <ActionCard
                            key={candidate.resource + filter}
                            title={
                              candidate.resource === config.resource
                                ? 'Child groups'
                                : candidate.title
                            }
                            description={
                              'Review and configure ' +
                              candidate.title.toLowerCase() +
                              '.'
                            }
                            icon={<SettingsIcon />}
                            actionLabel="Open configuration"
                            {...(blocked || reviewing
                              ? {
                                  disabledReason:
                                    'Finish or recover the current action first',
                                }
                              : {
                                  href: accountingLink(
                                    '/accounting/' +
                                      candidate.resource +
                                      '?' +
                                      new URLSearchParams({ [filter]: id }),
                                    here,
                                  ),
                                })}
                          />
                        ))}
                      </div>
                    </section>
                  ),
                )}
              </section>
            )}
            {config.resource === 'parties' &&
              availableResources.includes('accounts') && (
                <a
                  className="janso-link"
                  href={accountingLink(
                    '/accounting/accounts?' +
                      new URLSearchParams({ party_id: id }),
                    here,
                  )}
                  onClick={guard.leave}
                >
                  View this party's accounts
                </a>
              )}
          </>
        )
      )}
      {!reviewing && command.uncertain && (
        <Notice tone="warning">
          The lifecycle result is unconfirmed.{' '}
          <Button onClick={() => setReviewing(true)}>
            Recover same change
          </Button>
        </Notice>
      )}
      {verified && canOpening && config.resource==='accounts' && <MasterOpeningSummary company={company} account={id} onLeave={guard.leave}/>}
      {verified && <SubjectHistory company={company} entity={ACCOUNTING_AUDIT_ENTITIES_BY_RESOURCE[config.resource]} id={id} />}
      <ConfirmDialog
        open={reviewing}
        title={
          action === 'close'
            ? 'Close this policy?'
            : action === 'activate'
              ? 'Activate this record?'
              : 'Retire this record?'
        }
        confirmLabel={
          command.uncertain
            ? 'Retry same change'
            : command.blocked
              ? 'Reload and review'
              : action === 'close'
                ? 'Save end date'
                : action === 'activate'
                  ? 'Activate record'
                  : 'Retire record'
        }
        busy={command.pending}
        onCancel={() => {
          if (!command.pending) setReviewing(false);
        }}
        onConfirm={() => void apply()}
      >
        <p>
          {action === 'close'
            ? 'Shorten the policy interval. Approved assessments are retained and may prevent closure.'
            : action === 'activate'
              ? 'Activation checks the current references, profiles and company rules.'
              : 'Retirement retains history. Active dependants must be retired or replaced first.'}
        </p>
        {action === 'close' && (
          <TextField
            label="Policy end date"
            type="date"
            value={endDate}
            required
            disabled={blocked}
            error={endError}
            onChange={(event) => {
              setEndDate(event.target.value);
              setEndError('');
            }}
          />
        )}
        <AccountingFailure failure={command.failure} write />
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}

type History = components['schemas']['HistoryItem'];
export function AccountingConfigurationHistory({
  company,
  config,
  id,
  returnTo,
}: {
  company: string;
  config: AccountingResourceConfig;
  id: string;
  returnTo?: string;
}) {
  const back = accountingBack(
      returnTo,
      '/accounting/' + config.resource + '/' + id,
    ),
    list = useServiceList<History>(
      `/v1/companies/${company}/history/${config.resource}/${id}`,
      '',
      accountingRequest,
    );
  const columns: Column<History>[] = [
    { key: 'action', header: 'Action', type: 'text' },
    { key: 'object_version', header: 'Version', type: 'text' },
    { key: 'created_at', header: 'When', type: 'datetime' },
    { key: 'created_by', header: 'Actor', type: 'code', value: row => row.created_by ?? 'System' },
    {
      key: 'changed_fields',
      header: 'Changed fields',
      type: 'custom',
      render: (row) => row.changed_fields.join(', ') || 'No readable changes',
    },
  ];
  return (
    <div className="janso-page">
      <AccountingNavigation
        title={config.singular + ' history'}
        back={back}
        resource={config.resource}
        id={id}
        mode="history"
      />
      <PageHeader
        title={config.singular + ' history'}
        lede="Retained versions and actions. Protected field names and sensitive values are omitted by the service."
      />
      <AccountingFailure failure={list.failure} retry={list.first} />
      {list.loading ? (
        <AccountingLoading />
      ) : (
        !list.failure && (
          <DataTable
            caption="Configuration history"
            columns={columns}
            rows={list.data?.items ?? []}
            rowId={(row) => row.id}
            emptyTitle="No history available"
          />
        )
      )}
      <AccountingPager list={list} noun="revision" />
    </div>
  );
}
