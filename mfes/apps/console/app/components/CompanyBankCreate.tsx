'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { components } from '@janso/api-client/identity';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  PageNavigation,
  ReviewList,
  SearchSelect,
  SectionHeader,
  TextField,
} from '@janso/ui';
import { companyCall, companyFailure } from '../lib/company-api';
import { useServiceRead, type ServiceReader } from '../lib/service-resource';
import { accountingUUID } from '../lib/accounting-configuration-resources';
import {
  companyBankBody,
  companyBankFields,
  companyBankReturn,
  type CompanyBankDraft,
} from '../lib/company-bank';
import type { RequestFailure } from '../lib/service-call';
import { useAccessDraft } from './AccessCommon';
import {
  AccountingFailure,
  AccountingLoading,
} from './AccountingConfigurationCommon';

type Bank = components['schemas']['BankItem'];
const reader: ServiceReader = (request) =>
  companyCall('identity', request.path, request);
const blank: CompanyBankDraft = {
  label: '',
  account_name: '',
  bank_name: '',
  branch: '',
  account_number: '',
  iban: '',
  ifsc: '',
  swift: '',
  currency_code: '',
};

/** Identity owns these details. Financial ledgers link to the resulting masked bank identity. */
export function CompanyBankCreate({
  company,
  returnTo,
}: {
  company: string;
  returnTo?: string;
}) {
  const back = companyBankReturn(returnTo),
    form = useRef<HTMLFormElement>(null),
    busy = useRef(false);
  const profile = useServiceRead<components['schemas']['CompanyDetail']>(
    '/v1/companies/' + company,
    reader,
    (value) => {
      if (
        value.id !== company ||
        typeof value.base_currency !== 'string' ||
        !/^[A-Z]{3}$/.test(value.base_currency)
      )
        throw {
          status: 502,
          message: 'Company settings could not be verified.',
        };
    },
  );
  const currencies = useServiceRead<components['schemas']['CurrencyChoice'][]>(
    '/v1/reference/currencies',
    reader,
    (value) => {
      if (
        !Array.isArray(value) ||
        value.some((row) => !/^[A-Z]{3}$/.test(row.code))
      )
        throw {
          status: 502,
          message: 'Currency choices could not be verified.',
        };
    },
  );
  const [draft, setDraft] = useState(blank),
    [dirty, setDirty] = useState(false),
    [pending, setPending] = useState(false),
    [uncertain, setUncertain] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({}),
    [failure, setFailure] = useState<RequestFailure | null>(null),
    [saved, setSaved] = useState<Bank | null>(null);
  const guard = useAccessDraft(!saved && (dirty || uncertain), pending),
    blocked = pending || uncertain;
  useEffect(() => {
    if (profile.data)
      setDraft((current) => ({
        ...current,
        currency_code:
          current.currency_code || profile.data!.base_currency || '',
      }));
  }, [profile.data]);
  function change(key: keyof CompanyBankDraft, value: string) {
    if (blocked) return;
    setDraft((current) => ({ ...current, [key]: value }));
    setDirty(true);
    setErrors((current) => ({ ...current, [key]: '' }));
    setFailure(null);
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (
      busy.current ||
      uncertain ||
      !profile.data ||
      profile.data.status !== 'active' ||
      !currencies.data
    )
      return;
    const next = companyBankBody(draft);
    setErrors(next.errors);
    if (Object.keys(next.errors).length) {
      requestAnimationFrame(() =>
        form.current
          ?.querySelector<HTMLElement>('[aria-invalid="true"]')
          ?.focus(),
      );
      return;
    }
    busy.current = true;
    setPending(true);
    setFailure(null);
    try {
      // This native endpoint has no command receipts. Never attach a replay key or
      // retry an ambiguous create: a second request could create a second bank.
      const result = await companyCall<Bank>(
        'identity',
        '/v1/companies/' + company + '/bank-accounts',
        { method: 'POST', body: next.body },
      );
      if (
        result.company_id !== company ||
        !accountingUUID.test(result.id) ||
        result.is_active !== true
      )
        throw {
          status: 502,
          message: 'The created company bank could not be verified.',
        };
      setSaved(result);
      setDirty(false);
      setDraft(blank);
    } catch (error) {
      const problem = companyFailure(error);
      setFailure(problem);
      setErrors(problem.fields ?? {});
      setUncertain(problem.status >= 500);
    } finally {
      busy.current = false;
      setPending(false);
    }
  }
  return (
    <div className="janso-page">
      <PageNavigation
        back={{ href: back, label: 'bank profile setup' }}
        onNavigate={guard.leave}
        breadcrumbs={[
          { label: 'Accounts', href: '/accounting/accounts' },
          { label: 'New company bank' },
        ]}
      />
      <PageHeader
        title="New company bank"
        lede="Add your company’s bank details, then link them to its bank ledger profile."
      />
      <AccountingFailure
        failure={profile.failure ?? currencies.failure}
        retry={() => {
          profile.refresh();
          currencies.refresh();
        }}
        onLeave={guard.leave}
      />
      {profile.loading || currencies.loading ? (
        <AccountingLoading />
      ) : (
        profile.data &&
        currencies.data &&
        (saved ? (
          <Card>
            <CardHeader title="Company bank ready" />
            <CardBody>
              <div className="janso-flow">
                <Notice tone="success">
                  Company bank created successfully.
                </Notice>
                <ReviewList
                  items={[
                    { label: 'Bank label', value: saved.label },
                    { label: 'Bank name', value: saved.bank_name },
                    { label: 'Account holder', value: saved.account_name },
                    { label: 'Currency', value: saved.currency_code },
                    {
                      label: 'Account number',
                      value: saved.account_last4
                        ? '•••• ' + saved.account_last4
                        : 'Not supplied',
                    },
                    {
                      label: 'IBAN',
                      value: saved.iban_last4
                        ? '•••• ' + saved.iban_last4
                        : 'Not supplied',
                    },
                  ]}
                />
                <p>
                  Return to bank profile setup and select this company bank.
                  Review the ledger before activating it.
                </p>
                <a className="janso-btn janso-btn--primary" href={back}>
                  Continue bank profile setup
                </a>
              </div>
            </CardBody>
          </Card>
        ) : (
          <>
            {failure && <Notice tone="danger">{failure.message}</Notice>}
            {uncertain && (
              <Notice tone="warning">
                The creation result is unconfirmed. Check the available company
                banks in bank profile setup before creating another. This form
                will not repeat the request.
              </Notice>
            )}
            {profile.data.status !== 'active' && (
              <Notice tone="warning">
                Activate the company before adding bank details.
              </Notice>
            )}
            <FormLayout
              aside={
                <>
                  <SectionHeader title="Company bank details" />
                  <p className="janso-fine">
                    For {profile.data.display_name}. Bank details belong to this
                    company; its ledger remains a separate account.
                  </p>
                  <p className="janso-fine">
                    Enter an account number or IBAN. Saved identifiers are
                    masked. This bank will not replace your primary bank.
                  </p>
                  <p className="janso-fine">
                    Foreign currency requires the company’s multicurrency
                    feature and an enabled currency.
                  </p>
                </>
              }
            >
              <form ref={form} onSubmit={submit} noValidate>
                <Card>
                  <CardHeader title="Bank identity and payment details" />
                  <CardBody>
                    <div className="janso-form-grid">
                      {companyBankFields.map(
                        ([key, label, maxLength, required]) => (
                          <TextField
                            key={key}
                            label={label}
                            required={required}
                            maxLength={maxLength}
                            value={draft[key]}
                            disabled={blocked}
                            error={errors[key]}
                            type={
                              key === 'account_number' || key === 'iban'
                                ? 'password'
                                : 'text'
                            }
                            autoComplete="off"
                            spellCheck={false}
                            hint={
                              key === 'account_number'
                                ? 'Provide an account number or an IBAN. Saved values are masked.'
                                : undefined
                            }
                            onChange={(event) =>
                              change(
                                key,
                                ['ifsc', 'swift', 'iban'].includes(key)
                                  ? event.target.value.toUpperCase()
                                  : event.target.value,
                              )
                            }
                          />
                        ),
                      )}
                      <SearchSelect
                        label="Currency"
                        required
                        value={draft.currency_code}
                        options={currencies.data.map((row) => ({
                          id: row.code,
                          label: row.code + ' · ' + row.name,
                        }))}
                        onChange={(value) =>
                          change('currency_code', value ?? '')
                        }
                        disabled={blocked}
                        error={errors.currency_code}
                      />
                    </div>
                  </CardBody>
                  <FormActions cancel={{ href: back, onClick: guard.leave }}>
                    <Button
                      type="submit"
                      loading={pending}
                      disabled={blocked || profile.data.status !== 'active'}
                    >
                      Create company bank
                    </Button>
                  </FormActions>
                </Card>
              </form>
            </FormLayout>
          </>
        ))
      )}
      {guard.confirmation}
    </div>
  );
}
