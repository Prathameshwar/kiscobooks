'use client';
import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  FormActions,
  Notice,
  SectionHeader,
  TextField,
  useFormatters,
} from '@janso/ui';
import { masterRequest } from '../lib/catalog-master-api';
import { identifierBase, identifierId } from '../lib/units-identifiers';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import {
  IdentifierFailure,
  IdentifierUnitReference,
} from './UnitsIdentifiersCommon';

function exactQuantity(value: unknown) {
  if (typeof value !== 'string' || !/^\d{1,15}(?:\.\d{1,4})?$/.test(value))
    return null;
  const [whole, fraction = ''] = value.split('.');
  return whole!.replace(/^0+(?=\d)/, '') + '.' + fraction.padEnd(4, '0');
}

/** Read-only native calculation; no local floating-point conversion or business write. */
export function UnitConversionCheck({
  company,
  fromUnit,
}: {
  company: string;
  fromUnit?: string;
}) {
  const format = useFormatters();
  const [source, setSource] = useState<string | null>(fromUnit ?? null),
    [target, setTarget] = useState<string | null>(null),
    [quantity, setQuantity] = useState('1'),
    [errors, setErrors] = useState<Record<string, string>>({}),
    [result, setResult] = useState<string | null>(null),
    [failure, setFailure] = useState<RequestFailure | null>(null),
    [pending, setPending] = useState(false),
    busy = useRef(false),
    form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (Object.keys(errors).length)
      form.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus();
  }, [errors]);
  async function check() {
    if (busy.current) return;
    const problems: Record<string, string> = {};
    if (!source || !identifierId.test(source))
      problems.from_unit_id = 'Choose a source unit.';
    if (!target || !identifierId.test(target))
      problems.to_unit_id = 'Choose a target unit.';
    if (!/^\d{1,15}(?:\.\d{1,4})?$/.test(quantity))
      problems.quantity =
        'Enter a non-negative exact quantity with up to four decimal places.';
    setErrors(problems);
    setResult(null);
    setFailure(null);
    if (Object.keys(problems).length) return;
    busy.current = true;
    setPending(true);
    try {
      const value = await masterRequest<{
        from_unit_id: string;
        to_unit_id: string;
        input_quantity: string;
        quantity: string;
      }>({
        path: identifierBase(company, 'units/convert'),
        method: 'POST',
        body: { from_unit_id: source, to_unit_id: target, quantity },
      });
      if (
        value.from_unit_id !== source ||
        value.to_unit_id !== target ||
        exactQuantity(value.input_quantity) !== exactQuantity(quantity) ||
        typeof value.quantity !== 'string' ||
        !/^\d{1,15}(?:\.\d{1,4})?$/.test(value.quantity)
      )
        throw {
          status: 502,
          message: 'The conversion result could not be verified.',
        };
      setResult(value.quantity);
    } catch (error) {
      const problem = requestFailure(error, 'unit conversion');
      setFailure(problem);
      if (problem.fields) setErrors(problem.fields);
    } finally {
      busy.current = false;
      setPending(false);
    }
  }
  const change = () => {
    setErrors({});
    setResult(null);
    setFailure(null);
  };
  return (
    <Card>
      <CardBody>
        <SectionHeader title="Check a quantity conversion" />
        <p className="janso-fine">
          Different units need declared relations to the same canonical root.
          Converting a unit to itself checks its quantity rules. Results follow
          both units' allowed increments.
        </p>
        <IdentifierFailure failure={failure} />
        <form
          ref={form}
          noValidate
          onSubmit={(event) => {
            event.preventDefault();
            void check();
          }}
        >
          <div className="janso-form-grid">
            <IdentifierUnitReference
              company={company}
              label="Convert from unit"
              name="from_unit_id"
              value={source}
              onChange={(value) => {
                setSource(value);
                change();
              }}
              disabled={pending}
              required
              error={errors.from_unit_id}
            />
            <IdentifierUnitReference
              company={company}
              label="Convert to unit"
              name="to_unit_id"
              value={target}
              onChange={(value) => {
                setTarget(value);
                change();
              }}
              disabled={pending}
              required
              error={errors.to_unit_id}
            />
            <TextField
              label="Quantity to convert"
              name="quantity"
              value={quantity}
              onChange={(event) => {
                setQuantity(event.target.value);
                change();
              }}
              disabled={pending}
              required
              inputMode="decimal"
              error={errors.quantity}
            />
          </div>
          <FormActions>
            <Button type="submit" loading={pending}>
              Check conversion
            </Button>
          </FormActions>
        </form>
        {result !== null && (
          <Notice tone="success">
            <p>Converted quantity: {format.quantity(result)}</p>
            {format.quantity(result) !==
              format.quantity(result, { precision: 4 }) && (
              <p className="janso-fine">
                Exact quantity: {format.quantity(result, { precision: 4 })}
              </p>
            )}
          </Notice>
        )}
      </CardBody>
    </Card>
  );
}
