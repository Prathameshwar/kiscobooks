'use client';

import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  Checkbox,
  FormActions,
  FormLayout,
  Notice,
  PageHeader,
  ReviewList,
  SectionHeader,
  Select,
  Stepper,
} from '@janso/ui';
import {
  accountingBody,
  accountingChange,
  accountingInitial,
  accountingRequest,
  assertAccountingForm,
  assertAccountingRecord,
  useAccountingCommand,
} from '../lib/accounting-configuration';
import {
  accountingBack,
  accountingLink,
  accountingResource,
  type AccountingForm,
  type AccountingRecord,
} from '../lib/accounting-configuration-resources';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { useServiceDestination } from '../lib/service-resource';
import { AccessFocusErrors, useAccessDraft } from './AccessCommon';
import {
  AccountingFailure,
  AccountingFields,
  AccountingLoading,
  AccountingNavigation,
} from './AccountingConfigurationCommon';
import {MasterOpeningStep} from './MasterOpeningStep';
import {blankOpening,openingDirty,openingPayload,useMasterOpening} from '../lib/master-opening';

const steps = ['Party details', 'Address and contact', 'Tax and other details', 'Opening balance'];
const groups = {
  party: 'parties',
  address: 'party-addresses',
  contact: 'party-contacts',
  tax_registration: 'party-tax-registrations',
} as const;
type Group = keyof typeof groups;
type Values = Record<string, unknown>;
type Draft = Record<Group, Values>;
const empty = (): Draft => ({
  party: {},
  address: {},
  contact: {},
  tax_registration: {},
});
const groupStep = (group: string) =>
  group === 'opening' ? 3 : group === 'party' ? 0 : group === 'tax_registration' ? 2 : 1;
const errorStep = (key: string) =>
  key === 'party.notes' ? 2 : groupStep(key.split('.')[0]!);

export function PartyCreationWizard({
  company,
  companyCountry = 'IN',
  supplier = false,
  returnTo,
  availableResources = [],
  manageableResources = [],
}: {
  company: string;
  companyCountry?: string;
  supplier?: boolean;
  returnTo?: string;
  availableResources?: readonly string[];
  manageableResources?: readonly string[];
}) {
  const command = useAccountingCommand(),
    navigation = useServiceDestination(command.pending);
  const [forms, setForms] = useState<Record<string, AccountingForm> | null>(
      null,
    ),
    [failure, setFailure] = useState<RequestFailure | null>(null),
    [revision, setRevision] = useState(0),
    [step, setStep] = useState(0),
    [reached, setReached] = useState(0),
    [values, setValues] = useState<Draft>(empty),
    [enabled, setEnabled] = useState({
      address: false,
      contact: false,
      tax_registration: false,
    }),
    [role, setRole] = useState(supplier ? 'SUPPLIER' : ''),
    [errors, setErrors] = useState<Record<string, string>>({});
  const initial = useRef(''),
    edited = useRef(new Set<string>()),
    panel = useRef<HTMLElement>(null);
  const opening=useMasterOpening(company,step===3);
  const openingAccount={party:true,role,currencyMode:'BASE'};
  const snapshot = JSON.stringify({ values, enabled, role, opening:opening.draft });
  const dirty =
    !!forms && snapshot !== initial.current && !navigation.destination;
  const guard = useAccessDraft(dirty || command.uncertain, command.pending);
  const back = accountingBack(
    returnTo,
    '/accounting/' + (supplier ? 'suppliers' : 'parties'),
  );
  const title = supplier ? 'New supplier' : 'New party';
  const can = (resource: string) =>
    availableResources.includes(resource) &&
    manageableResources.includes(resource);
  const requested = [
    'parties',
    'party-roles',
    ...(can('party-addresses') && can('party-address-uses')
      ? ['party-addresses', 'party-address-uses']
      : []),
    ...(can('party-contacts') && can('party-contact-uses')
      ? ['party-contacts', 'party-contact-uses']
      : []),
    ...(can('party-tax-registrations') ? ['party-tax-registrations'] : []),
  ].join(',');
  useEffect(() => {
    const controller = new AbortController();
    setForms(null);
    setFailure(null);
    Promise.all(
      requested.split(',').map(async (resource) => {
        const form = await accountingRequest<AccountingForm>({
          path: `/v1/companies/${company}/configuration/${resource}/field-set?operation=create`,
          signal: controller.signal,
        });
        return [
          resource,
          assertAccountingForm(
            form,
            company,
            accountingResource(resource)!,
            'create',
          ),
        ] as const;
      }),
    )
      .then((entries) => {
        if (controller.signal.aborted) return;
        const nextForms = Object.fromEntries(entries),
          next = empty();
        edited.current.clear();
        for (const [group, resource] of Object.entries(groups)) {
          const form = nextForms[resource];
          if (form)
            next[group as Group] = accountingInitial(
              form.fields.filter((field) => field.key !== 'party_id'),
            );
        }
        suggest(nextForms, next);
        const toggles = {
          address: false,
          contact: false,
          tax_registration: false,
        };
        setValues(next);
        setEnabled(toggles);
        setRole(supplier ? 'SUPPLIER' : '');
        setErrors({});
        setStep(0);
        setReached(0);
        initial.current = JSON.stringify({
          values: next,
          enabled: toggles,
          role: supplier ? 'SUPPLIER' : '',
          opening:blankOpening(),
        });
        setForms(nextForms);
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setFailure(requestFailure(error, 'Party creation'));
      });
    return () => controller.abort();
  }, [company, companyCountry, requested, revision, supplier]);
  function suggest(metadata: Record<string, AccountingForm>, draft: Draft) {
    const fill = (group: Group, key: string, value: unknown) => {
      const fields = metadata[groups[group]]?.fields ?? [],
        field = fields.find((item) => item.key === key);
      if (
        edited.current.has(group + '.' + key) ||
        !field?.editable || !field.visible || !field.readable ||
        field.conditional_access || field.control.disabled_reason ||
        draft[group][key] === value
      ) return;
      draft[group] = accountingChange(fields, draft[group], key, value);
    };
    fill('party', 'country_code', /^[A-Z]{2}$/.test(companyCountry) ? companyCountry : 'IN');
    fill('party', 'legal_name', draft.party.name);
    fill('address', 'label', 'Billing address');
    fill('address', 'country_code', draft.party.country_code);
    fill('address', 'mailing_name', draft.party.legal_name || draft.party.name);
    fill('tax_registration', 'country_code', draft.party.country_code);
    fill('tax_registration', 'state_code',
      draft.tax_registration.country_code === draft.address.country_code
        ? draft.address.state_code : null);
    return draft;
  }
  const recoverable = command.failure?.status === 409 && !command.uncertain;
  const locked = command.pending || (command.blocked && !recoverable);
  function changed() {
    if (recoverable || command.failure?.status === 422) command.clear();
    setErrors({});
  }
  function update(group: Group, key: string, value: unknown) {
    if (locked) return;
    changed();
    edited.current.add(group + '.' + key);
    setValues((current) => suggest(forms ?? {}, {
        ...current,
        [group]: accountingChange(
          forms?.[groups[group]]?.fields ?? [], current[group], key, value,
        ),
      }));
  }
  function chooseStep(next: number) {
    setStep(next);
    setReached((current) => Math.max(current, next));
    requestAnimationFrame(() => panel.current?.focus());
  }
  useEffect(() => {
    const key = Object.keys(command.failure?.fields ?? {}).find((key) =>
      key.startsWith('opening.')||Object.keys(groups).some((group) => key.startsWith(group + '.')),
    );
    if (key) chooseStep(errorStep(key));
  }, [command.failure]);
  function available(resource: string) {
    const form = forms?.[resource];
    return !!form?.can_create && form.can_manage && !form.unavailable_reason;
  }
  const fields = (group: Group) =>
    (forms?.[groups[group]]?.fields ?? []).filter(
      (field) => field.key !== 'party_id',
    );
  const canAddress =
    available('party-addresses') && available('party-address-uses');
  const canContact =
    available('party-contacts') && available('party-contact-uses');
  const roleField = forms?.['party-roles']?.fields.find(
    (field) => field.key === 'role',
  );
  const roles =
    roleField?.editable && roleField.visible && !roleField.conditional_access
      ? (roleField.control.choices ?? [])
      : [];
  // A party is created with its role and that role's ledger account, so both are required here.
  const canRole =
    available('party-roles') &&
    (supplier ? roles.includes('SUPPLIER') : roles.length > 0);
  const canLedger = can('accounts');
  const unavailableRequired = (Object.keys(groups) as Group[]).some(
    (group) =>
      (group === 'party' || enabled[group]) &&
      fields(group).some(
        (field) =>
          field.required &&
          (!field.editable || !field.visible || field.conditional_access) &&
          field.initial == null,
      ),
  );
  const createDisabled =
    !available('parties') ||
    !canRole ||
    !canLedger ||
    unavailableRequired ||
    (command.blocked && !command.uncertain);
  function verifyCreated(value:AccountingRecord){
    assertAccountingRecord(value,company);
    if(value.status!=='ACTIVE')throw {status:502,message:'The completed party creation could not be confirmed. Retry this same creation.'};
  }
  function finishSave(saved:AccountingRecord|null){
    if(!saved)return;
    initial.current=snapshot;
    navigation.setDestination(accountingLink(`/accounting/${supplier?'suppliers':'parties'}/${saved.id}`,back));
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!forms || command.pending || createDisabled) return;
    if(command.uncertain){finishSave(await command.retry<AccountingRecord>(verifyCreated));return;}
    const nextErrors: Record<string, string> = {},
      body: Values = {};
    for (const group of Object.keys(groups) as Group[]) {
      if (group !== 'party' && !enabled[group]) continue;
      const form = forms[groups[group]],
        metadata = fields(group);
      if (!form || !available(groups[group])) {
        nextErrors[group + '.section'] =
          'This section is unavailable. Reload the page to review current access.';
        continue;
      }
      const result = accountingBody(metadata, values[group]);
      for (const field of metadata)
        if (
          field.required &&
          (!field.editable || !field.visible || field.conditional_access) &&
          field.initial == null
        )
          result.errors[field.key] =
            'This required field is protected. Ask an administrator with complete field access.';
      for (const [key, message] of Object.entries(result.errors))
        nextErrors[group + '.' + key] = message;
      if (group === 'party') Object.assign(body, result.body);
      else body[group] = result.body;
    }
    if (!role)
      nextErrors['party.role'] =
        'Choose the party role. It decides which ledger account is created.';
    else if (!canRole || !roles.includes(role))
      nextErrors['party.role'] = 'Choose an available party role.';
    else body.role = role;
    const captured=openingPayload(opening.draft,opening.metadata,openingAccount);
    Object.assign(nextErrors,captured.errors);
    if(captured.opening)body.opening=captured.opening;
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      chooseStep(errorStep(Object.keys(nextErrors)[0]!));
      return;
    }
    const saved = await command.execute<AccountingRecord>(
      {
        path: `/v1/companies/${company}/parties/create-with-details`,
        method: 'POST',
        body,
      },
      verifyCreated,
    );
    finishSave(saved);
  }
  const renderFields = (group: Group, keys?: (key: string) => boolean) => (
    <AccountingFields
      company={company}
      resource={groups[group]}
      fields={fields(group).filter((field) => !keys || keys(field.key))}
      values={values[group]}
      disabled={locked || !available(groups[group])}
      onChange={(key, value) => update(group, key, value)}
      errors={Object.fromEntries(
        Object.entries({ ...command.failure?.fields, ...errors })
          .filter(([key]) => key.startsWith(group + '.'))
          .map(([key, message]) => [key.slice(group.length + 1), message]),
      )}
    />
  );
  function toggle(group: keyof typeof enabled, checked: boolean) {
    if (locked) return;
    changed();
    setEnabled((current) => ({ ...current, [group]: checked }));
  }
  return (
    <div className="janso-page janso-master-create">
      <AccountingNavigation
        title={title}
        back={back}
        resource={supplier ? 'suppliers' : 'parties'}
        mode="new"
        availableResources={availableResources}
        onLeave={guard.leave}
      />
      <PageHeader
        title={title}
        lede="Add the party and its optional initial details together. Create from any step when required information is complete."
      />
      <AccountingFailure
        failure={failure}
        retry={() => setRevision((value) => value + 1)}
        onLeave={guard.leave}
      />
      {!forms && !failure ? (
        <AccountingLoading />
      ) : (
        forms && (
          <>
            <Stepper
              orientation="horizontal"
              current={step}
              reached={reached}
              allowFuture
              steps={steps.map((label, index) => ({
                label,
                complete: index===3 ? !Object.keys(openingPayload(opening.draft,opening.metadata,openingAccount).errors).length : !(Object.keys(groups) as Group[]).some(
                  (group) =>
                    (group === 'party' || enabled[group]) &&
                    Object.keys(
                      accountingBody(fields(group), values[group]).errors,
                    ).some((key) => errorStep(group + '.' + key) === index),
                ),
                note: Object.keys(errors).some(
                  (key) => errorStep(key) === index,
                )
                  ? 'Needs attention'
                  : undefined,
              }))}
              onStep={locked ? undefined : chooseStep}
            />
            <p className="janso-fine">
              Step {step + 1} of {steps.length}. Move freely between steps. Address, contact,
              tax information and opening balance are optional.
            </p>
            <FormLayout
              aside={
                <>
                  <SectionHeader title="Creation summary" />
                  <ReviewList
                    stacked
                    items={[
                      {
                        label: 'Party',
                        value: String(
                          values.party.name || 'Enter party details',
                        ),
                      },
                      {
                        label: 'Role',
                        value: role
                          ? role.charAt(0) + role.slice(1).toLowerCase()
                          : 'Choose a role',
                      },
                      {
                        label: 'Ledger account',
                        value: role
                          ? role === 'CUSTOMER'
                            ? 'Created under Sundry Debtors'
                            : 'Created under Sundry Creditors'
                          : 'Created with the role',
                      },
                      {
                        label: 'Address',
                        value: enabled.address
                          ? 'Default for billing and shipping'
                          : 'Add later',
                      },
                      {
                        label: 'Contact',
                        value: enabled.contact
                          ? 'Default general contact'
                          : 'Add later',
                      },
                      {
                        label: 'Tax registration',
                        value: enabled.tax_registration
                          ? 'Included'
                          : 'Add later',
                      },
                      {label:'Opening balance',value:openingDirty(opening.draft)?opening.draft.mode==='bills'?`${opening.draft.bills.length} pending bills`:'Balance entered':'Not entered'},
                    ]}
                  />
                  <p className="janso-fine">
                    The party, its role and its ledger account are created
                    together and become active. Entered addresses and contacts
                    become active defaults. Payment policies can be configured
                    from the saved party.
                  </p>
                </>
              }
            >
              <form noValidate onSubmit={save}>
                <Card>
                  <CardBody>
                    <div className="janso-flow">
                      <AccessFocusErrors
                        fields={{ ...command.failure?.fields, ...errors }}
                      />
                      <AccountingFailure
                        failure={command.failure}
                        onLeave={guard.leave}
                      />
                      {Object.entries(errors).some(([key]) =>
                        key.endsWith('.section'),
                      ) && (
                        <Notice tone="danger">
                          Some selected details are unavailable. Reload to
                          review current access.
                        </Notice>
                      )}
                      {!available('parties') && (
                        <Notice tone="warning">
                          {forms.parties?.unavailable_reason ||
                            'Party creation requires complete create access for this company.'}
                        </Notice>
                      )}
                      {unavailableRequired && (
                        <Notice tone="warning">
                          A required field is hidden or protected. Ask an
                          administrator with complete field access to create
                          this record.
                        </Notice>
                      )}
                      {!canRole && (
                        <Notice tone="warning">
                          {supplier
                            ? 'Supplier creation requires permission to create its supplier role.'
                            : 'Creating a party requires permission to create its role.'}
                        </Notice>
                      )}
                      {!canLedger && (
                        <Notice tone="warning">
                          Every party is created with its ledger account, which
                          needs permission to create accounts.
                        </Notice>
                      )}
                      <section
                        ref={panel}
                        tabIndex={-1}
                        className="janso-flow"
                        aria-label={step===3?'Opening entry':steps[step]}
                      >
                        {step === 0 && (
                          <>
                            <SectionHeader
                              title="Party details"
                              description="Identify the business or person. Required fields are marked."
                            />
                            {renderFields('party', (key) => key !== 'notes')}
                            {canRole && !supplier && (
                              <Select
                                label="Party role"
                                required
                                value={role}
                                disabled={locked}
                                error={errors['party.role']}
                                hint="The role decides the ledger account created with the party."
                                options={[
                                  { value: '', label: 'Choose a role' },
                                  ...roles.map((value) => ({
                                    value,
                                    label:
                                      value.charAt(0) +
                                      value.slice(1).toLowerCase(),
                                  })),
                                ]}
                                onChange={(value) => {
                                  changed();
                                  setRole(value);
                                }}
                              />
                            )}
                            {supplier && (
                              <Notice>
                                The supplier role and its payable account are
                                created and activated with this supplier.
                              </Notice>
                            )}
                          </>
                        )}
                        {step === 3 && <MasterOpeningStep {...opening} onChange={value=>{if(!locked){changed();opening.setDraft(value);}}} draft={opening.draft} account={openingAccount} disabled={locked} errors={{...command.failure?.fields,...errors}}/>}
                        {step === 1 && (
                          <>
                            <SectionHeader
                              title="Address"
                              description="An entered address becomes the default for billing and shipping."
                            />
                            {canAddress ? (
                              <Checkbox
                                checked={enabled.address}
                                disabled={locked}
                                onChange={(event) =>
                                  toggle('address', event.target.checked)
                                }
                              >
                                Add default address
                              </Checkbox>
                            ) : (
                              <Notice>
                                Address setup is unavailable with the current
                                configuration or permissions. You can add it
                                later with appropriate access.
                              </Notice>
                            )}
                            {enabled.address && renderFields('address')}
                            <SectionHeader
                              title="Contact"
                              description="An entered contact becomes the default general contact."
                            />
                            {canContact ? (
                              <Checkbox
                                checked={enabled.contact}
                                disabled={locked}
                                onChange={(event) =>
                                  toggle('contact', event.target.checked)
                                }
                              >
                                Add default contact
                              </Checkbox>
                            ) : (
                              <Notice>
                                Contact setup is unavailable with the current
                                configuration or permissions. You can add it
                                later with appropriate access.
                              </Notice>
                            )}
                            {enabled.contact && renderFields('contact')}
                          </>
                        )}
                        {step === 2 && (
                          <>
                            <SectionHeader
                              title="Tax registration"
                              description="Enter the applicable registration and its validity. No tax treatment or statutory number is inferred."
                            />
                            {available('party-tax-registrations') ? (
                              <Checkbox
                                checked={enabled.tax_registration}
                                disabled={locked}
                                onChange={(event) =>
                                  toggle(
                                    'tax_registration',
                                    event.target.checked,
                                  )
                                }
                              >
                                Add tax registration
                              </Checkbox>
                            ) : (
                              <Notice>
                                Tax registration setup is unavailable with the
                                current configuration or permissions. You can
                                add it later with appropriate access.
                              </Notice>
                            )}
                            {enabled.tax_registration &&
                              renderFields('tax_registration')}
                            <SectionHeader title="Other details" />
                            {renderFields('party', (key) => key === 'notes')}
                          </>
                        )}
                      </section>
                    </div>
                  </CardBody>
                  <FormActions cancel={{ href: back, onClick: guard.leave }}>
                    {step > 0 && (
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={locked}
                        onClick={() => chooseStep(step - 1)}
                      >
                        Previous
                      </Button>
                    )}
                    {step < steps.length-1 && (
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={locked}
                        onClick={() => chooseStep(step + 1)}
                      >
                        Next
                      </Button>
                    )}
                    <Button
                      type="submit"
                      variant="primary"
                      loading={command.pending}
                      disabled={createDisabled}
                    >
                      {command.uncertain
                        ? 'Retry same creation'
                        : supplier
                          ? 'Create supplier'
                          : 'Create party'}
                    </Button>
                  </FormActions>
                </Card>
              </form>
            </FormLayout>
          </>
        )
      )}
      {guard.confirmation}
    </div>
  );
}
