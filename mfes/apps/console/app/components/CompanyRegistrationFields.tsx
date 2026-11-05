'use client';

import { FieldGroup, FieldPair, Select, TextField, Toggle } from '@janso/ui';
import type { components } from '@janso/api-client/identity';

type Registration = components['schemas']['InitialTaxRegistration'];
type Choice = components['schemas']['TaxRegistrationChoice'];

export function newTaxRegistration(choice: Choice | undefined): Registration | undefined {
  return choice ? { number: '', regime: choice.regimes[0]?.value ?? '', valid_from: '' } : undefined;
}

export function CompanyRegistrationFields({ choice, value, error, onChange }: {
  choice: Choice;
  value: Registration | null | undefined;
  error: (key: string) => string | undefined;
  onChange: (value: Registration | undefined) => void;
}) {
  function change(key: keyof Registration, entry: string) {
    onChange({ number: '', regime: choice.regimes[0]?.value ?? '', valid_from: '', ...value, [key]: entry });
  }
  const gst = choice.tax_system === 'gst_in';
  return (
    <FieldGroup
      title={gst ? 'GST registration' : choice.tax_system.startsWith('vat_') ? 'VAT registration' : 'Tax registration'}
      headerEnd={<label className="janso-check">
        <Toggle label="Add registration later" checked={!value}
          onChange={later => onChange(later ? undefined : newTaxRegistration(choice))} />
        <span>Add registration later</span>
      </label>}
      hint={gst
        ? 'Save GST details to set up tax ledgers. Registration must cover the purchase bill date.'
        : 'Save registration details to set up tax ledgers.'}
    >
      {value ? <>
        <TextField
          label={choice.number_label} value={value?.number ?? ''} maxLength={gst ? 15 : 40}
          required={!!value} error={error('number')} autoCapitalize="characters" spellCheck={false}
          hint={gst ? 'Enter the 15-character GSTIN for the selected state.' : 'Use the number shown on your registration certificate.'}
          onChange={event => change('number', event.target.value.toUpperCase())}
        />
        <FieldPair>
          <Select label="Registration type" required={!!value} error={error('regime')}
            value={value?.regime ?? choice.regimes[0]?.value ?? ''} options={choice.regimes}
            onChange={entry => change('regime', entry)} />
          <TextField label="Registration effective date" type="date" required={!!value}
            value={value?.valid_from ?? ''} error={error('valid_from')}
            hint="The date this registration takes effect, as shown on your certificate."
            onChange={event => change('valid_from', event.target.value)} />
        </FieldPair>
      </> : <p className="janso-fine">Add registration in company settings later.{gst ? ' GST on purchases will remain unavailable until a registration is saved.' : ''}</p>}
    </FieldGroup>
  );
}
