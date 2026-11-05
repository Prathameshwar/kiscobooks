'use client';
import { useEffect, useState } from 'react';
import {
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
  Select,
  TextField,
  useFormatters,
  type Column,
} from '@janso/ui';
import {
  accountingRequest,
  useAccountingCommand,
  useAccountingRead,
} from '../lib/accounting-configuration';
import {
  accountingBack,
  accountingLink,
} from '../lib/accounting-configuration-resources';
import {
  exchangeCandidate,
  exchangePurposes,
  verifyExchangeContext,
  verifyExchangeItem,
  verifyExchangeQuote,
  type ExchangeContext,
  type ExchangeQuote,
  type ExchangeQuoteItem,
} from '../lib/accounting-exchange-rates';
import { useServiceDestination, useServiceList } from '../lib/service-resource';
import { validMasterDate } from '../lib/catalog-masters';
import { AccessFocusErrors, useAccessDraft } from './AccessCommon';
import {
  AccountingFailure,
  AccountingLoading,
  AccountingNavigation,
  AccountingPager,
} from './AccountingConfigurationCommon';
const root = '/accounting/exchange-rates';
const base = (company: string) => `/v1/companies/${company}/exchange-rates`;
const purposes = exchangePurposes.map((value) => ({
  value,
  label: value.replaceAll('_', ' ').toLowerCase(),
}));
function useCurrencyContext(company: string) {
  return useAccountingRead<ExchangeContext>(
    base(company) + '/context',
    (value) => verifyExchangeContext(value, company),
  );
}
export function AccountingExchangeDirectory({
  company,
  canManage,
  initialQuery = '',
}: {
  company: string;
  canManage: boolean;
  initialQuery?: string;
}) {
  const initial = new URLSearchParams(initialQuery),
    back = accountingBack(initial.get('returnTo') ?? undefined),
    context = useCurrencyContext(company);
  const [filters, setFilters] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      ['from_currency', 'purpose', 'status', 'effective_date'].map((key) => [
        key,
        initial.get(key) ?? '',
      ]),
    ),
  );
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters))
    if (
      value &&
      (key !== 'effective_date' || validMasterDate(value)) &&
      (key !== 'from_currency' || /^[A-Z]{3}$/.test(value)) &&
      (key !== 'purpose' ||
        exchangePurposes.some((purpose) => purpose === value)) &&
      (key !== 'status' ||
        ['CANDIDATE', 'APPROVED', 'WITHDRAWN'].includes(value))
    )
      params.set(key, value);
  const list = useServiceList<ExchangeQuoteItem>(
      base(company),
      params.toString(),
      accountingRequest,
      verifyExchangeItem,
      !!context.data,
    ),
    here = accountingLink(root + (params.size ? '?' + params : ''), back);
  useEffect(() => {
    if (context.data) window.history.replaceState(null, '', here);
  }, [here, !!context.data]);
  const change = (key: string, value: string) =>
    setFilters((current) => ({ ...current, [key]: value }));
  const columns: Column<ExchangeQuoteItem>[] = [
    { key: 'from_currency', header: 'From', type: 'text' },
    { key: 'to_currency', header: 'To', type: 'text' },
    { key: 'rate', header: 'Exact rate', type: 'text' },
    { key: 'effective_date', header: 'Effective date', type: 'date' },
    { key: 'purpose', header: 'Purpose', type: 'text' },
    {
      key: 'status',
      header: 'Status',
      type: 'custom',
      render: (row) => (
        <Badge
          tone={
            row.status === 'APPROVED'
              ? 'success'
              : row.status === 'WITHDRAWN'
                ? 'neutral'
                : 'warn'
          }
        >
          {row.status.toLowerCase()}
        </Badge>
      ),
    },
    {
      key: 'id',
      header: 'Quote',
      type: 'custom',
      render: (row) => (
        <a
          className="janso-link"
          href={accountingLink(root + '/' + row.id, here)}
        >
          View quote
        </a>
      ),
    },
  ];
  return (
    <div className="janso-page">
      <AccountingNavigation title="Exchange rates" back={back} />
      <PageHeader
        title="Exchange rates"
        lede="Source-backed currency quotes. Each candidate needs an independent reviewer before it can be used."
        actions={
          canManage &&
          context.data?.multi_currency &&
          context.data.allowed_currencies.some(
            (currency) => currency !== context.data?.base_currency,
          ) ? (
            <a
              className="janso-btn janso-btn--primary"
              href={accountingLink(root + '/new', here)}
            >
              New exchange rate
            </a>
          ) : undefined
        }
      />
      {!canManage && <Notice>Read-only access for this company.</Notice>}
      {context.data && !context.data.multi_currency && (
        <Notice>
          Multi-currency is disabled for this company. Existing quotes remain
          available for review.
        </Notice>
      )}
      <AccountingFailure failure={context.failure} retry={context.refresh} />
      <Card>
        <CardHeader
          title="Currency quote register"
          action={
            <Button
              variant="ghost"
              disabled={list.loading}
              onClick={list.first}
            >
              Refresh
            </Button>
          }
        />
        <CardBody>
          <div className="janso-form-grid">
            <Select
              label="Currency"
              value={filters.from_currency}
              options={[
                { value: '', label: 'All currencies' },
                ...[
                  ...new Set([
                    ...(context.data?.allowed_currencies ?? []),
                    ...(filters.from_currency ? [filters.from_currency] : []),
                  ]),
                ].map((value) => ({ value, label: value })),
              ]}
              onChange={(value) => change('from_currency', value)}
            />
            <Select
              label="Purpose"
              value={filters.purpose}
              options={[{ value: '', label: 'All purposes' }, ...purposes]}
              onChange={(value) => change('purpose', value)}
            />
            <Select
              label="Status"
              value={filters.status}
              options={[
                { value: '', label: 'All statuses' },
                ...['CANDIDATE', 'APPROVED', 'WITHDRAWN'].map((value) => ({
                  value,
                  label: value.toLowerCase(),
                })),
              ]}
              onChange={(value) => change('status', value)}
            />
            <TextField
              label="Effective date"
              type="date"
              value={filters.effective_date}
              onChange={(event) => change('effective_date', event.target.value)}
              error={
                filters.effective_date &&
                !validMasterDate(filters.effective_date)
                  ? 'Enter a valid date.'
                  : undefined
              }
            />
          </div>
          {params.size > 0 && !!list.data?.items.length && (
            <Button
              variant="ghost"
              onClick={() =>
                setFilters({
                  from_currency: '',
                  purpose: '',
                  status: '',
                  effective_date: '',
                })
              }
            >
              Clear filters
            </Button>
          )}
          <AccountingFailure failure={list.failure} retry={list.first} />
          {context.loading ||
          list.loading ||
          (!!context.data && !list.data && !list.failure) ? (
            <AccountingLoading />
          ) : (
            context.data &&
            !list.failure && (
              <DataTable
                caption="Exchange quotes"
                columns={columns}
                rows={list.data?.items ?? []}
                rowId={(row) => row.id}
                rowLabel={(row) => row.from_currency + ' ' + row.effective_date}
                filtered={params.size > 0}
                onClearFilters={() =>
                  setFilters({
                    from_currency: '',
                    purpose: '',
                    status: '',
                    effective_date: '',
                  })
                }
                emptyTitle={
                  params.size ? 'No matching quotes' : 'No exchange quotes yet'
                }
                emptyBody="Create a quote from a reviewed source, then ask a different user to approve it."
                rowActions={(row) => [
                  {
                    id: 'view',
                    label: 'View quote',
                    href: accountingLink(root + '/' + row.id, here),
                  },
                ]}
              />
            )
          )}
          <AccountingPager list={list} noun="quote" />
        </CardBody>
      </Card>
    </div>
  );
}
export function AccountingExchangeEditor({
  company,
  returnTo,
}: {
  company: string;
  returnTo?: string;
}) {
  const context = useCurrencyContext(company),
    command = useAccountingCommand(),
    navigation = useServiceDestination(command.pending),
    back = accountingBack(returnTo, root);
  const [values, setValues] = useState({
      from_currency: '',
      purpose: 'ACCOUNTING',
      effective_date: '',
      rate: '',
      source_reference: '',
    }),
    [errors, setErrors] = useState<Record<string, string>>({});
  const dirty =
      !navigation.destination &&
      Object.entries(values).some(([key, value]) =>
        key === 'purpose' ? value !== 'ACCOUNTING' : !!value,
      ),
    guard = useAccessDraft(dirty || command.uncertain, command.pending);
  const change = (key: string, value: string) => {
    if (!command.blocked) {
      setValues((current) => ({ ...current, [key]: value }));
      setErrors({});
    }
  };
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (
      !context.data ||
      command.pending ||
      (command.blocked && !command.uncertain)
    )
      return;
    const result = exchangeCandidate(values, context.data);
    setErrors(result.errors);
    if (Object.keys(result.errors).length) return;
    const saved = await command.execute<ExchangeQuote>(
      {
        path: base(company) + '/candidates',
        method: 'POST',
        body: result.body,
      },
      (value) => verifyExchangeQuote(value, company),
    );
    if (saved)
      navigation.setDestination(accountingLink(root + '/' + saved.id, back));
  }
  return (
    <div className="janso-page">
      <AccountingNavigation
        title="New exchange rate"
        back={back}
        onLeave={guard.leave}
        resource="exchange-rates"
        mode="new"
      />
      <PageHeader
        title="New exchange rate"
        lede="Record an exact quote and its source. A different user must approve it before use."
      />
      <AccountingFailure
        failure={context.failure}
        retry={context.refresh}
        onLeave={guard.leave}
      />
      {context.loading ? (
        <AccountingLoading />
      ) : (
        context.data && (
          <>
            {!context.data.multi_currency ||
            !context.data.allowed_currencies.some(
              (currency) => currency !== context.data?.base_currency,
            ) ? (
              <Notice tone="warning">
                Enable multi-currency and at least one foreign currency in
                company configuration before creating a quote.
              </Notice>
            ) : (
              <form noValidate onSubmit={(event) => void save(event)}>
                <AccessFocusErrors
                  fields={{ ...command.failure?.fields, ...errors }}
                />
                <AccountingFailure failure={command.failure} write />
                {command.uncertain && (
                  <Notice tone="warning">
                    The result is unconfirmed. Editing is locked; retry the same
                    save to recover the quote.
                  </Notice>
                )}
                <Card>
                  <CardHeader title="Currency and purpose" />
                  <CardBody>
                    <div className="janso-form-grid">
                      <Select
                        label="From currency"
                        required
                        value={values.from_currency}
                        options={context.data.allowed_currencies
                          .filter(
                            (currency) =>
                              currency !== context.data?.base_currency,
                          )
                          .map((value) => ({ value, label: value }))}
                        placeholder="Choose a foreign currency"
                        disabled={command.blocked}
                        error={
                          errors.from_currency ??
                          command.failure?.fields?.from_currency
                        }
                        onChange={(value) => change('from_currency', value)}
                      />
                      <TextField
                        label="To currency"
                        value={context.data.base_currency}
                        readOnly
                        hint="The company's base currency."
                      />
                      <Select
                        label="Purpose"
                        required
                        value={values.purpose}
                        options={purposes}
                        disabled={command.blocked}
                        error={
                          errors.purpose ?? command.failure?.fields?.purpose
                        }
                        onChange={(value) => change('purpose', value)}
                      />
                    </div>
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Effective date and exact rate" />
                  <CardBody>
                    <div className="janso-form-grid">
                      <TextField
                        label="Effective date"
                        type="date"
                        required
                        value={values.effective_date}
                        disabled={command.blocked}
                        error={
                          errors.effective_date ??
                          command.failure?.fields?.effective_date
                        }
                        onChange={(event) =>
                          change('effective_date', event.target.value)
                        }
                      />
                      <TextField
                        label="Exchange rate"
                        inputMode="decimal"
                        required
                        value={values.rate}
                        disabled={command.blocked}
                        error={errors.rate ?? command.failure?.fields?.rate}
                        hint="Base-currency units for one foreign-currency unit. Up to 12 decimal places; no rounding."
                        onChange={(event) => change('rate', event.target.value)}
                      />
                    </div>
                  </CardBody>
                </Card>
                <Card>
                  <CardHeader title="Source evidence" />
                  <CardBody>
                    <TextField
                      label="Source reference"
                      required
                      maxLength={500}
                      value={values.source_reference}
                      disabled={command.blocked}
                      error={
                        errors.source_reference ??
                        command.failure?.fields?.source_reference
                      }
                      hint={
                        values.purpose === 'GST_GOODS'
                          ? 'Use the official Customs notification for GST goods.'
                          : 'Identify the reviewed bank, treasury or other source quotation.'
                      }
                      onChange={(event) =>
                        change('source_reference', event.target.value)
                      }
                    />
                  </CardBody>
                </Card>
                {command.blocked && !command.uncertain && (
                  <Button
                    onClick={() => {
                      command.clear();
                      context.refresh();
                    }}
                  >
                    Reload and review
                  </Button>
                )}
                <div className="janso-form-actions">
                  <Button
                    type="submit"
                    loading={command.pending}
                    disabled={command.blocked && !command.uncertain}
                  >
                    {command.uncertain
                      ? 'Retry same save'
                      : 'Create exchange rate'}
                  </Button>
                  <a
                    className="janso-btn janso-btn--ghost"
                    href={back}
                    onClick={guard.leave}
                  >
                    Cancel
                  </a>
                </div>
              </form>
            )}
          </>
        )
      )}
      {guard.confirmation}
    </div>
  );
}
export function AccountingExchangeDetail({
  company,
  id,
  userId,
  canManage,
  returnTo,
}: {
  company: string;
  id: string;
  userId?: string;
  canManage: boolean;
  returnTo?: string;
}) {
  const read = useAccountingRead<ExchangeQuote>(
      base(company) + '/quotes/' + id,
      (value) => verifyExchangeQuote(value, company, id),
    ),
    command = useAccountingCommand(),
    format = useFormatters(),
    back = accountingBack(returnTo, root);
  const [action, setAction] = useState<'approve' | 'withdraw' | null>(null),
    [reviewing, setReviewing] = useState(false),
    [reason, setReason] = useState(''),
    [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [saved, setSaved] = useState<ExchangeQuote | null>(null);
  const row = saved ?? read.data,
    blocked = command.pending || command.uncertain,
    guard = useAccessDraft(!!action || command.uncertain, command.pending),
    own = !!row && row.created_by === userId;
  async function decide() {
    if (!row || !action || !canManage || command.pending) return;
    if (command.blocked && !command.uncertain) {
      command.clear();
      setAction(null);
      setReviewing(false);
      setSaved(null);
      read.refresh();
      return;
    }
    if (
      reason.trim().length < 3 ||
      reason.trim().length > 500 ||
      /[\x00-\x1f\x7f]/.test(reason)
    ) {
      setError('Enter a review reason between 3 and 500 printable characters.');
      return;
    }
    const result = await command.execute<ExchangeQuote>(
      {
        path: base(company) + '/' + id + '/' + action,
        method: 'POST',
        body: { expected_version: row.row_version, reason: reason.trim() },
      },
      (value) => {
        verifyExchangeQuote(value, company, id);
        if (
          value.row_version <= row.row_version ||
          value.status !== (action === 'approve' ? 'APPROVED' : 'WITHDRAWN')
        )
          throw {
            status: 502,
            message: 'The review result could not be verified.',
          };
      },
    );
    if (result) {
      setSaved(result);
      setMessage(
        action === 'approve'
          ? 'Exchange rate approved successfully.'
          : 'Exchange rate withdrawn. Its evidence and usage history are retained.',
      );
      setAction(null);
      setReviewing(false);
    }
  }
  const items =
    row && canManage
      ? [
          ...(row.status === 'CANDIDATE'
            ? [
                {
                  id: 'approve',
                  label: 'Approve quote',
                  disabledReason: blocked
                    ? 'Resolve the unconfirmed review first'
                    : own || !userId
                      ? 'A different user must review this quote'
                      : undefined,
                },
              ]
            : []),
          ...(row.status === 'APPROVED'
            ? [
                {
                  id: 'withdraw',
                  label: 'Withdraw quote',
                  destructive: true,
                  disabledReason: blocked
                    ? 'Resolve the unconfirmed review first'
                    : undefined,
                },
              ]
            : []),
        ]
      : [];
  return (
    <div className="janso-page">
      <AccountingNavigation
        title="Exchange rate details"
        back={back}
        onLeave={guard.leave}
        resource="exchange-rates"
        id={id}
        mode="detail"
      />
      <PageHeader
        title={
          row
            ? row.from_currency + ' to ' + row.to_currency
            : 'Exchange rate details'
        }
        lede="Review the exact quote, source evidence and approval decision."
        actions={
          items.length ? (
            <Menu
              label="Quote actions"
              items={items}
              onSelect={(value) => {
                if (value === 'approve' || value === 'withdraw') {
                  command.clear();
                  setReason('');
                  setError('');
                  setAction(value);
                  setReviewing(true);
                }
              }}
            />
          ) : undefined
        }
      />
      <AccountingFailure
        failure={read.failure}
        retry={() => {
          setSaved(null);
          read.refresh();
        }}
      />
      {read.loading ? (
        <AccountingLoading />
      ) : (
        row && (
          <>
            {message && <Notice tone="success">{message}</Notice>}
            {row.status === 'CANDIDATE' && (
              <Notice>
                {own
                  ? 'Quote saved as a candidate. Ask another authorised user to review and approve it.'
                  : 'This candidate becomes available for use after independent approval.'}
              </Notice>
            )}
            {row.status === 'WITHDRAWN' && (
              <Notice>
                Withdrawn quotes retain their evidence and existing usage
                history. Create a new candidate when a replacement is needed.
              </Notice>
            )}
            <Card>
              <CardHeader title="Quote details" />
              <CardBody>
                <ReviewList
                  items={[
                    {
                      label: 'Status',
                      value: (
                        <Badge
                          tone={
                            row.status === 'APPROVED'
                              ? 'success'
                              : row.status === 'CANDIDATE'
                                ? 'warn'
                                : 'neutral'
                          }
                        >
                          {row.status.toLowerCase()}
                        </Badge>
                      ),
                    },
                    { label: 'From currency', value: row.from_currency },
                    { label: 'To currency', value: row.to_currency },
                    { label: 'Exact exchange rate', value: row.rate },
                    {
                      label: 'Purpose',
                      value: row.purpose.replaceAll('_', ' ').toLowerCase(),
                    },
                    {
                      label: 'Effective date',
                      value: format.date(row.effective_date),
                    },
                    { label: 'Version', value: String(row.row_version) },
                  ]}
                />
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="Source evidence" />
              <CardBody>
                <ReviewList
                  items={[
                    { label: 'Source', value: row.source_kind.toLowerCase() },
                    { label: 'Reference', value: row.source_reference },
                    {
                      label: 'Document hash',
                      value: (
                        <span className="console-audit-detail__value">
                          {row.source_sha256}
                        </span>
                      ),
                    },
                  ]}
                />
              </CardBody>
            </Card>
            {(row.approval_reason || row.withdrawal_reason) && (
              <Card>
                <CardHeader title="Review decisions" />
                <CardBody>
                  <ReviewList
                    items={[
                      ...(row.approval_reason
                        ? [
                            {
                              label: 'Approval reason',
                              value: row.approval_reason,
                            },
                            {
                              label: 'Approved at',
                              value: row.approved_at
                                ? format.dateTime(row.approved_at)
                                : 'Not recorded',
                            },
                          ]
                        : []),
                      ...(row.withdrawal_reason
                        ? [
                            {
                              label: 'Withdrawal reason',
                              value: row.withdrawal_reason,
                            },
                            {
                              label: 'Withdrawn at',
                              value: row.withdrawn_at
                                ? format.dateTime(row.withdrawn_at)
                                : 'Not recorded',
                            },
                          ]
                        : []),
                    ]}
                  />
                </CardBody>
              </Card>
            )}
          </>
        )
      )}
      {command.uncertain && !reviewing && (
        <Notice tone="warning">
          The review result is unconfirmed.{' '}
          <Button onClick={() => setReviewing(true)}>
            Recover same review
          </Button>
        </Notice>
      )}
      <ConfirmDialog
        open={reviewing}
        title={
          action === 'approve' ? 'Approve this quote?' : 'Withdraw this quote?'
        }
        confirmLabel={
          command.uncertain
            ? 'Retry same review'
            : command.blocked
              ? 'Reload and review'
              : action === 'approve'
                ? 'Approve quote'
                : 'Withdraw quote'
        }
        busy={command.pending}
        onCancel={() => {
          if (!command.pending) {
            setReviewing(false);
            if (!command.uncertain) setAction(null);
          }
        }}
        onConfirm={() => void decide()}
      >
        <p>
          {action === 'approve'
            ? 'Confirm that you independently checked the source, date, currency pair and exact rate.'
            : 'Withdraw this quote from future selection. Previously posted usage remains unchanged.'}
        </p>
        <TextField
          label="Review reason"
          required
          maxLength={500}
          value={reason}
          disabled={blocked}
          error={error || command.failure?.fields?.reason}
          onChange={(event) => {
            setReason(event.target.value);
            setError('');
          }}
        />
        <AccessFocusErrors
          fields={error ? { reason: error } : (command.failure?.fields ?? {})}
        />
        <AccountingFailure failure={command.failure} write />
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
