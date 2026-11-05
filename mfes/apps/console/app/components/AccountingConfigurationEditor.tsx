'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  ConfirmDialog,
  Disclosure,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  ReviewList,
  SectionHeader,
  Stepper,
} from '@janso/ui';
import {
  accountingBase,
  accountingBody,
  accountingInitial,
  accountingChange,
  assertAccountingRecord,
  useAccountingCommand,
  useAccountingRecord,
} from '../lib/accounting-configuration';
import {
  accountingBack,
  accountingLink,
  accountingRoot,
  accountingUUID,
  type AccountingRecord,
  type AccountingResourceConfig,
} from '../lib/accounting-configuration-resources';
import { useServiceDestination } from '../lib/service-resource';
import { useAccessDraft, AccessFocusErrors } from './AccessCommon';
import {
  AccountingFailure,
  AccountingSections,
  AccountingLoading,
  AccountingNavigation,
} from './AccountingConfigurationCommon';
import { accountingDescription } from '../lib/accounting-masters';
import { accountingCreationContext } from '../lib/account-related-actions';
import { PartyCreationWizard } from './PartyCreationWizard';
import {MasterOpeningStep} from './MasterOpeningStep';
import {openingDirty,openingPayload,useMasterOpening} from '../lib/master-opening';
import {AccountCreationProfile,useAccountCreationProfile} from './AccountCreationProfile';

export function AccountingConfigurationEditor(
  props: React.ComponentProps<typeof AccountingConfigurationCore>,
) {
  if (!props.id && props.config.resource === 'parties')
    return <PartyCreationWizard {...props} />;
  return <AccountingConfigurationCore {...props} />;
}

function AccountingConfigurationCore({
  company,
  config,
  id,
  returnTo,
  prefills = {},
  supplier = false,
  availableResources = [],
  canCreateCompanyBank = false,
}: {
  company: string;
  companyCountry?: string;
  config: AccountingResourceConfig;
  id?: string;
  returnTo?: string;
  prefills?: Record<string, string>;
  supplier?: boolean;
  availableResources?: readonly string[];
  manageableResources?: readonly string[];
  canCreateCompanyBank?: boolean;
}) {
  const rawRead = useAccountingRecord(company, config, id, true),
    command = useAccountingCommand(),
    navigation = useServiceDestination(command.pending);
  const metadata = useMemo(() => {
    if (
      !rawRead.metadata ||
      id ||
      config.resource !== 'accounts' ||
      (prefills.kind === 'PARTY' &&
        accountingUUID.test(prefills.party_id ?? ''))
    )
      return rawRead.metadata;
    return {
      ...rawRead.metadata,
      fields: rawRead.metadata.fields.map((field) =>
        field.key !== 'kind'
          ? field
          : {
              ...field,
              initial: field.initial === 'PARTY' ? 'GENERAL' : field.initial,
              control: {
                ...field.control,
                choices: field.control.choices?.filter(
                  (choice) => choice !== 'PARTY',
                ),
              },
            },
      ),
    };
  }, [rawRead.metadata, id, config.resource, prefills.kind, prefills.party_id]);
  const read = { ...rawRead, metadata };
  const [values, setValues] = useState<Record<string, unknown> | null>(null),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [unchanged, setUnchanged] = useState(false),
    [discard, setDiscard] = useState(false);
  const accountCreate=!id&&config.resource==='accounts';
  const creditPolicy = config.resource === 'party-credit-policies';
  const [accountStep,setAccountStep]=useState(0);
  const opening=useMasterOpening(company,accountCreate&&accountStep===1);
  const openingAccount={party:values?.kind==='PARTY',role:String(values?.party_role??''),kind:String(values?.kind??''),currencyMode:String(values?.currency_mode??'BASE'),currency:String(values?.currency??''),inventory:values?.inventory_affected===true};
  const creationProfile=useAccountCreationProfile(company,openingAccount.kind,accountCreate);
  const initial = useRef(''),
    dirty =
      !navigation.destination &&
      !!values &&
      (JSON.stringify(values) !== initial.current||accountCreate&&openingDirty(opening.draft)),
    guard = useAccessDraft(dirty || command.uncertain, command.pending);
  const back = accountingBack(
      returnTo,
      accountingRoot + '/' + (supplier ? 'suppliers' : config.resource),
    ),
    title = id
      ? 'Edit ' + (supplier ? 'supplier' : config.singular.toLowerCase())
      : 'New ' + (supplier ? 'supplier' : config.singular.toLowerCase());
  const detail = id
    ? accountingLink(
        accountingRoot +
          '/' +
          (supplier ? 'suppliers' : config.resource) +
          '/' +
          id,
        back,
      )
    : back;
  const context = !id ? accountingCreationContext(config, back) : null,
    contextMismatch =
      !!context &&
      prefills[context.key]?.toLowerCase() !== context.ownerId.toLowerCase();
  useEffect(() => {
    if (read.metadata) {
      const next = accountingInitial(
        read.metadata.fields,
        read.record,
        prefills,
      );
      if (contextMismatch && context) next[context.key] = null;
      setValues(next);
      initial.current = JSON.stringify(next);
      setErrors({});
      setUnchanged(false);
    } else setValues(null);
  }, [read.metadata, read.record]);
  const recoverableCreate =
    !id && command.failure?.status === 409 && !command.uncertain;
  useEffect(()=>{setAccountStep(0);},[company]);
  useEffect(()=>{if(accountCreate&&Object.keys(command.failure?.fields??{}).some(key=>key.startsWith('opening.')))setAccountStep(1);},[accountCreate,command.failure]);
  function update(key: string, value: unknown) {
    if (
      !values ||
      (command.blocked && !recoverableCreate) ||
      contextMismatch ||
      (context && key === context.key)
    )
      return;
    if (recoverableCreate || command.failure?.status === 422) command.clear();
    const next = accountingChange(
      read.metadata?.fields ?? [],
      values,
      key,
      value,
    );
    setValues(next);
    setErrors({});
    setUnchanged(false);
  }
  function reload() {
    command.clear();
    read.refresh();
  }
  const unavailableRequired =
    !id &&
    !read.metadata?.unavailable_reason &&
    read.metadata?.fields.some(
      (field) => field.required && !field.editable && field.initial == null,
    );
  function finishSave(saved:AccountingRecord|null){
    if(!saved)return;
    initial.current=JSON.stringify(values);
    const destination=accountingRoot+'/'+(supplier&&id?'suppliers':config.resource)+'/'+saved.id+(supplier&&!id?'?setup=SUPPLIER':'');
    navigation.setDestination(accountingLink(destination,back));
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (
      !values ||
      !read.metadata ||
      command.pending ||
      unavailableRequired ||
      contextMismatch ||
      !read.metadata.can_manage ||
      (!id && !read.metadata.can_create)
    )
      return;
    if(command.uncertain){finishSave(await command.retry<AccountingRecord>(value=>assertAccountingRecord(value,company,id)));return;}
    const result = accountingBody(read.metadata.fields, values, read.record);
    if(accountCreate){
      const captured=openingPayload(opening.draft,opening.metadata,openingAccount);
      Object.assign(result.errors,captured.errors);
      if(captured.opening){result.body.opening=captured.opening;const profile=creationProfile.capture();Object.assign(result.body,profile.body);Object.assign(result.errors,profile.errors);}
      if(Object.keys(result.errors).length)setAccountStep(Object.keys(result.errors).some(key=>key.startsWith('opening.'))?1:0);
    }
    setErrors(result.errors);
    if (
      Object.keys(result.errors).length ||
      (command.blocked && !command.uncertain)
    )
      return;
    if (id && !command.uncertain && Object.keys(result.body).length === 1) {
      initial.current = JSON.stringify(values);
      setUnchanged(true);
      return;
    }
    const saved = await command.execute<AccountingRecord>(
      {
        path: accountingBase(company, config) + (id ? '/' + id : ''),
        method: id ? 'PATCH' : 'POST',
        body: result.body,
      },
      (value) => assertAccountingRecord(value, company, id),
    );
    finishSave(saved);
  }
  return (
    <div className={accountCreate ? 'janso-page janso-master-create' : 'janso-page'}>
      <AccountingNavigation
        title={title}
        back={id ? detail : back}
        onLeave={guard.leave}
        availableResources={availableResources}
        resource={supplier ? 'suppliers' : config.resource}
        id={id}
        mode={id ? 'edit' : 'new'}
      />
      <PageHeader
        title={title}
        lede={
          creditPolicy ? undefined : accountCreate ? 'Create an account and optionally post its opening balance.' : id && config.resource === 'parties' ? (
            <>
              {read.record?.name &&
              read.metadata?.fields.some(
                (field) =>
                  field.key === 'name' &&
                  field.readable &&
                  field.visible &&
                  !field.conditional_access,
              ) ? (
                <>
                  Editing <strong>{String(read.record.name)}</strong>.{' '}
                </>
              ) : null}
              Update the shared party identity. Customer and supplier roles
              continue to use this same record.
            </>
          ) : supplier ? (
            'Create the shared party identity first, then add and activate its supplier role.'
          ) : (
            accountingDescription(config)
          )
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
        read.metadata &&
        values && (
          <>
            {creditPolicy && (
              <Disclosure summary={
                <span className="janso-fine">
                  Credit policy guidance{context && !contextMismatch ? ' · Party fixed' : ''}
                </span>
              }>
                {context && !contextMismatch && (
                  <p>
                    The party is fixed to the party you opened.{' '}
                    <a className="janso-link" href={context.href} onClick={guard.leave}>
                      Back to party
                    </a>
                  </p>
                )}
                {read.metadata.notices?.map((message) => <p key={message}>{message}</p>)}
                {read.metadata.lifecycle === 'dates' && (
                  <p>
                    Once an interval takes effect, create a new interval to change
                    its terms. Only its permitted end date can be shortened.
                  </p>
                )}
              </Disclosure>
            )}
            {context && (!creditPolicy || contextMismatch) && (
              <Notice tone={contextMismatch ? 'warning' : 'info'}>
                {contextMismatch
                  ? `The ${context.label} context does not match. Return to the ${context.label} and open this creation action again.`
                  : `This record belongs to the ${context.label} you opened. The ${context.label} selection is protected for this creation.`}{' '}
                <a
                  className="janso-link"
                  href={context.href}
                  onClick={guard.leave}
                >
                  Back to {context.label}
                </a>
              </Notice>
            )}
            {read.metadata.unavailable_reason && (
              <Notice tone="warning">
                {read.metadata.unavailable_reason}{' '}
                <a
                  className="janso-link"
                  href={accountingLink(
                    '/companies/' + company + '/configuration',
                    accountingLink(
                      '/accounting/' + config.resource + (id ? '/' + id : ''),
                      back,
                    ),
                  )}
                  onClick={guard.leave}
                >
                  Open Company Config
                </a>
              </Notice>
            )}
            {!creditPolicy && read.metadata.notices?.map((message) => (
              <Notice key={message}>{message}</Notice>
            ))}
            {config.resource === 'account-bank-profiles' &&
              read.metadata.can_manage &&
              read.metadata.fields.some(
                (field) =>
                  field.key === 'company_bank_id' &&
                  field.editable &&
                  field.visible &&
                  !field.conditional_access,
              ) && (
                <Notice>
                  Choose an active company bank for this ledger.{' '}
                  {canCreateCompanyBank ? (
                    <a
                      className="janso-link"
                      onClick={guard.leave}
                      href={
                        '/companies/' +
                        company +
                        '/bank-accounts/new?' +
                        new URLSearchParams({
                          returnTo:
                            '/accounting/account-bank-profiles/' +
                            (id ? id + '/edit' : 'new') +
                            '?' +
                            new URLSearchParams({
                              ...(!id && prefills.account_id
                                ? { account_id: prefills.account_id }
                                : {}),
                              returnTo: back,
                            }),
                        })
                      }
                    >
                      Add company bank
                    </a>
                  ) : (
                    <span>
                      Ask a company administrator to add a company bank if none
                      is available.
                    </span>
                  )}
                </Notice>
              )}
            {!read.metadata.can_manage && !read.metadata.unavailable_reason && (
              <Notice>
                Read-only access. This company requires the resource's manage
                permission.
              </Notice>
            )}
            {unavailableRequired && (
              <Notice tone="warning">
                A required field is hidden or protected. Ask an administrator
                with complete field access to create this record.
              </Notice>
            )}
            {!creditPolicy && read.metadata.lifecycle === 'dates' && (
              <Notice>
                Policies are dated. Once an interval takes effect, create a new
                interval to change its terms; only its permitted end date can be
                shortened.
              </Notice>
            )}
            {config.resource === 'party-identifiers' && (
              <Notice>
                Record business identifiers only. Full national personal
                identity numbers are prohibited.
              </Notice>
            )}
            {config.resource.startsWith('withholding-') && (
              <Notice>
                Use an official source and its document hash. No statutory rate
                is inferred or supplied by this form.
              </Notice>
            )}
            <FormLayout
              aside={
                <>
                  {!(id && config.resource === 'parties') && (
                    <SectionHeader title="Before you save" />
                  )}
                  {id && config.resource === 'parties' && read.record && (
                    <section className="janso-flow" aria-label="Saved party">
                      <SectionHeader title="Saved party" />
                      <ReviewList
                        stacked
                        items={['name', 'code', 'status'].map((key) => ({
                          label:
                            key === 'name'
                              ? 'Name'
                              : key === 'code'
                                ? 'Code'
                                : 'Status',
                          value: read.metadata!.fields.some(
                            (field) =>
                              field.key === key &&
                              field.readable &&
                              field.visible &&
                              !field.conditional_access,
                          )
                            ? String(read.record![key] ?? 'Not set')
                            : 'Protected',
                        }))}
                      />
                      <a
                        className="janso-link"
                        href={detail}
                        onClick={guard.leave}
                      >
                        View saved details
                      </a>
                    </section>
                  )}
                  <p className="janso-fine">
                    Changes apply to this company. Required fields are marked;
                    protected fields keep their saved values.
                  </p>
                  {config.resource === 'accounts' ? (
                    <>
                      <SectionHeader title="Account setup" />
                      <p className="janso-fine">
                        {values.kind === 'PARTY'
                          ? 'Select the matching active customer, supplier or other party role, then choose its party identity.'
                          : values.kind === 'BANK'
                            ? accountCreate ? 'With an opening, select the company bank here. Creation activates the account and posts the opening together.' : 'Save the bank account as a draft, complete its bank profile, then activate it.'
                            : values.kind === 'TAX'
                              ? accountCreate ? 'With an opening, complete the tax details here. Creation activates the account and posts the opening together.' : 'Save the tax account as a draft, complete its tax profile, then activate it.'
                              : values.kind === 'CASH'
                                ? 'Choose an asset group for cash on hand. Cash accounts use base or fixed currency; a bank profile is not required.'
                                : values.kind === 'INVENTORY_CONTROL' ||
                                    values.kind === 'ASSET_CONTROL'
                                  ? 'Choose an asset group for this control account. Review whether postings should be restricted to source documents before activation.'
                                  : "Choose a group that matches the ledger's financial purpose. Review the posting controls before activation."}
                      </p>
                      <p className="janso-fine">
                        {accountCreate
                          ? "Opening balance is optional. An entered opening is posted automatically when you create the account."
                          : 'Master records do not contain editable balances. Financial documents record account movements.'}
                      </p>
                      <nav
                        className="janso-page-navigation"
                        aria-label="Account setup references"
                      >
                        {[
                          [
                            'accounting-setup',
                            '/accounting/setup',
                            'Review chart setup',
                          ],
                          [
                            'account-groups',
                            '/accounting/account-groups',
                            'Manage account groups',
                          ],
                          ['parties', '/accounting/parties', 'Manage parties'],
                        ]
                          .filter(([resource]) =>
                            availableResources.includes(resource!),
                          )
                          .map(([resource, href, label]) => (
                            <a
                              key={resource}
                              className="janso-link"
                              href={accountingLink(href!, back)}
                              onClick={guard.leave}
                            >
                              {label}
                            </a>
                          ))}
                      </nav>
                    </>
                  ) : config.resource === 'parties' ? (
                    <>
                      <SectionHeader
                        title={id ? 'Editing this party' : 'Party setup'}
                      />
                      {id ? (
                        <>
                          <p className="janso-fine">
                            Update names, classification and notes where
                            permitted. Protected identifiers retain their saved
                            values.
                          </p>
                          <p className="janso-fine">
                            Manage addresses, contacts, customer or supplier
                            roles and commercial policies from the party details
                            page.
                          </p>
                        </>
                      ) : (
                        <ol>
                          <li>Save the shared party identity.</li>
                          <li>Review and activate the party.</li>
                          <li>Add and activate customer or supplier roles.</li>
                          <li>
                            Complete contacts, addresses and commercial
                            defaults.
                          </li>
                        </ol>
                      )}
                      <p className="janso-fine">
                        An existing party can hold both customer and supplier
                        roles. Reuse its identity.
                      </p>
                    </>
                  ) : (
                    <p className="janso-fine">
                      Activation, publication and financial operations remain
                      separate actions.
                    </p>
                  )}
                </>
              }
            >
              <form
                noValidate
                aria-label={title}
                onSubmit={(event) => void save(event)}
              >
                <Card>
                  <CardBody>
                    <div className="janso-flow">
                      <AccessFocusErrors
                        fields={{ ...command.failure?.fields, ...errors }}
                      />
                      {recoverableCreate ? (
                        <Notice tone="warning">
                          <p>{command.failure?.message}</p>
                          <p>
                            Your values are retained. Correct the conflicting
                            details and save again, or reload to review the
                            current settings.
                          </p>
                        </Notice>
                      ) : (
                        <AccountingFailure
                          failure={command.failure}
                          write
                          onLeave={guard.leave}
                        />
                      )}
                      {Object.keys(errors).length > 0 && (
                        <Notice tone="danger">
                          <p>Check the highlighted fields before saving.</p>
                          <ul>
                            {[...new Set(Object.values(errors))].map(
                              (message) => (
                                <li key={message}>{message}</li>
                              ),
                            )}
                          </ul>
                        </Notice>
                      )}
                      {command.uncertain && (
                        <Notice tone="warning">
                          Editing is disabled while the result is unconfirmed.
                          Retry this exact save to recover its result.
                        </Notice>
                      )}
                      {unchanged && <Notice>No changes to save.</Notice>}
                      {accountCreate&&<div className="janso-master-opening-progress"><Stepper orientation="horizontal" allowFuture current={accountStep} reached={accountStep} steps={[{label:'Account details'},{label:'Opening balance'}]} onStep={command.pending||command.blocked&&!recoverableCreate?undefined:setAccountStep}/></div>}
                      {accountCreate&&accountStep===1?<><MasterOpeningStep {...opening} account={openingAccount} onChange={value=>{if(!command.pending&&(!command.blocked||recoverableCreate)){if(command.failure)command.clear();opening.setDraft(value);setErrors({});}}} disabled={command.pending||command.blocked&&!recoverableCreate} errors={{...command.failure?.fields,...errors}}/>{openingDirty(opening.draft)&&<AccountCreationProfile company={company} profile={creationProfile} disabled={command.pending||command.blocked&&!recoverableCreate} errors={{...command.failure?.fields,...errors}}/>}</>:<AccountingSections
                        withinForm
                        company={company}
                        resource={config.resource}
                        fields={read.metadata.fields.map((field) =>
                          context && field.key === context.key
                            ? { ...field, editable: false }
                            : field,
                        )}
                        values={values}
                        onChange={update}
                        disabled={
                          (command.blocked && !recoverableCreate) ||
                          !read.metadata.can_manage ||
                          contextMismatch
                        }
                        errors={{ ...command.failure?.fields, ...errors }}
                      />}
                      {command.failure?.status === 409 ||
                      command.failure?.status === 403 ? (
                        <Button type="button" onClick={() => setDiscard(true)}>
                          Reload and review
                        </Button>
                      ) : null}
                    </div>
                  </CardBody>
                  <FormActions
                    cancel={{ href: id ? detail : back, onClick: guard.leave }}
                  >
                    {accountCreate&&<Button type="button" variant="ghost" disabled={command.pending||command.blocked&&!recoverableCreate} onClick={()=>setAccountStep(value=>value===0?1:0)}>{accountStep===0?'Next':'Previous'}</Button>}
                    <Button
                      type="submit"
                      loading={command.pending}
                      disabled={
                        !!unavailableRequired ||
                        contextMismatch ||
                        !read.metadata.can_manage ||
                        (!id && !read.metadata.can_create) ||
                        (command.blocked && !command.uncertain) ||
                        (!!id && !dirty && !command.uncertain)
                      }
                    >
                      {command.uncertain
                        ? 'Retry same save'
                        : id
                          ? 'Save changes'
                          : 'Create ' +
                            (supplier
                              ? 'party for supplier'
                              : config.singular.toLowerCase())}
                    </Button>
                  </FormActions>
                </Card>
              </form>
            </FormLayout>
          </>
        )
      )}
      <ConfirmDialog
        open={discard}
        title="Discard unsaved changes and reload?"
        confirmLabel="Discard and reload"
        onCancel={() => setDiscard(false)}
        onConfirm={() => {
          setDiscard(false);
          reload();
        }}
      >
        Reloading replaces this form with the current saved record and field
        settings.
      </ConfirmDialog>
      {guard.confirmation}
    </div>
  );
}
