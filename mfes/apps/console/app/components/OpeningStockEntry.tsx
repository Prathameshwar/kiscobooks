'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, FormLayout, Checkbox, Notice, ReviewList, SearchSelect, Select, Stepper, TextField, useFormatters, type SearchSelectLoader, type SearchSelectOption } from '@janso/ui';
import type { components as Catalog } from '@janso/api-client/catalog';
import type { components as Accounting } from '@janso/api-client/accounting';
import { openingCatalogRequest, openingRequest, openingBase, decimal, validateAllocation, type Allocation, type Calculation, type Capture, type Manifest, owned } from '../lib/opening-stock';
import { useServiceRead, type ServicePage } from '../lib/service-resource';
import { trackingTitle } from '../lib/stock-tracking-resources';
import { trackingRequest } from '../lib/stock-tracking';
import { TrackingReference } from './StockTrackingCommon';
import { StockReference, OpeningReference } from './VoucherStock';
import { AccountingFailure } from './AccountingConfigurationCommon';

type Binding = Catalog['schemas']['ItemUnitBindingListItem'];
type Revision = Catalog['schemas']['ItemUnitRevisionListItem'];
type Profile = Accounting['schemas']['TrackingSource'];
export function OpeningStockEntry({
  company,
  date,
  currency,
  mode,
  initialItemId,
  disabled,
  onAdd,
  onDirty,
}: {
  company: string;
  date: string;
  currency: string;
  mode: Manifest['opening_mode'];
  initialItemId?: string;
  disabled: boolean;
  onAdd: (line: Allocation) => void;
  onDirty: (dirty: boolean) => void;
}) {
  const [step, setStep] = useState(0),
    [item, setItem] = useState<string | null>(initialItemId ?? null),
    [warehouse, setWarehouse] = useState<string | null>(null),
    [bin, setBin] = useState<string | null>(null);
  const [binding, setBinding] = useState<Binding | null>(null),
    [revision, setRevision] = useState<Revision | null>(null);
  const bindings = useRef(new Map<string, Binding>());
  const serialOptions = useRef(new Map<string, SearchSelectOption>());
  const [quantity, setQuantity] = useState(''),
    [measured, setMeasured] = useState(''),
    [costMode, setCostMode] = useState<Capture['cost_mode']>('VALUE'),
    [costValues, setCostValues] = useState({VALUE:'',RATE:''}),
    [priced, setPriced] = useState('1');
  const value=costValues[costMode];
  const setValue=(entered:string)=>setCostValues(current=>({...current,[costMode]:entered}));
  const [lot, setLot] = useState<string | null>(null),
    [serials, setSerials] = useState<string[]>([]),
    [history, setHistory] = useState(false),
    [received, setReceived] = useState(''),
    [order, setOrder] = useState('1'),
    [zero, setZero] = useState(''),
    [gl, setGl] = useState<string | null>(null);
  const [calculation, setCalculated] = useState<Calculation | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [discard, setDiscard] = useState(false);
  const busyNow=useRef(false),calculatedScope=useRef('');
  // A preview remains usable only for the exact inputs that produced it.
  const inputScope=JSON.stringify({company,date,currency,item,warehouse,binding:binding?.id,revision:revision?.id,quantity,measured,costMode,value,priced,history,received,order});
  const liveInputs=useRef(inputScope);liveInputs.current=inputScope;
  const unitScope=JSON.stringify({company,item,date}),liveUnitScope=useRef(unitScope);liveUnitScope.current=unitScope;
  const calculated=calculatedScope.current===inputScope?calculation:null;
  const heading = useRef<HTMLHeadingElement>(null),
    previousStep = useRef<number | null>(null),
    errorFocus = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (previousStep.current !== null && previousStep.current !== step)
      heading.current?.focus();
    previousStep.current = step;
  }, [step]);
  useEffect(() => {
    if (error) errorFocus.current?.focus();
  }, [error]);
  const [sourceKey, setSourceKey] = useState(() => crypto.randomUUID()),
    format = useFormatters();
  const profile = useServiceRead<Profile>(
    item
      ? `/v1/companies/${company}/stock-tracking/context/${item}?resource=stock`
      : undefined,
    trackingRequest,
    (row) => {
      owned(company)(row);
      if (row.item_id !== item)
        throw {
          status: 502,
          message: 'Product tracking could not be verified.',
        };
      if(![row.lot_tracking,row.serial_tracking,row.expiry_required,row.manufacture_date_required].every(value=>typeof value==='boolean'))
        throw {status:502,message:'Product tracking settings are protected or unavailable.'};
    },
  );
  const dirty = !!(
    quantity ||
    measured ||
    costValues.VALUE ||
    costValues.RATE ||
    priced !== '1' ||
    warehouse ||
    serials.length ||
    lot ||
    received ||
    history ||
    zero ||
    gl ||
    bin ||
    order !== '1'
  );
  const batch = useServiceRead<Accounting['schemas']['BatchDetail']>(
    lot && profile.data?.lot_tracking
      ? `/v1/companies/${company}/stock-tracking/batches/${lot}`
      : undefined,
    trackingRequest,
    (row) => {
      owned(company)(row);
      if (
        row.id !== lot ||
        row.item_id !== item ||
        row.status !== 'ACTIVE' ||
        row.is_held !== false
      )
        throw {
          status: 422,
          message: 'Select an active, unheld batch belonging to this product.',
        };
    },
  );
  useEffect(() => {
    onDirty(dirty);
    return () => onDirty(false);
  }, [dirty, onDirty]);
  useEffect(() => {
    setCalculated(null);
  }, [
    company,
    date,
    currency,
    item,
    warehouse,
    binding,
    revision,
    quantity,
    measured,
    costMode,
    value,
    priced,
    history,
    received,
    order,
  ]);
  useEffect(() => {
    setBinding(null);
    setRevision(null);
    setLot(null);
    setSerials([]);
    serialOptions.current.clear();
    bindings.current.clear();
  }, [company,item,date]);
  const loadUnits: SearchSelectLoader = async ({ cursor, signal }) => {
    if (!item) return { items: [], nextCursor: null };
    const page = await openingCatalogRequest<ServicePage<Binding>>({
          path: `/v1/companies/${company}/items/${item}/unit-bindings?limit=50${cursor ? '&cursor=' + encodeURIComponent(cursor) : ''}`,
      signal,
    });
    page.items.forEach((row) => bindings.current.set(row.id, row));
    return {
      items: page.items.map((row) => ({
        id: row.id,
        label: row.code ?? row.usage_role ?? 'Product unit',
        disabled: !row.unit_id,
      })),
      nextCursor: page.page.has_more ? page.page.next_cursor : null,
    };
  };
  async function selectUnit(id: string | null) {
    if(disabled||busyNow.current)return;
    setBinding(bindings.current.get(id ?? '') ?? null);
    setRevision(null);
    setError('');
    if (!id) return;
    const requestedScope=liveUnitScope.current;
    busyNow.current=true;
    setBusy(true);
    try {
      const page = await openingCatalogRequest<ServicePage<Revision>>({
        path: `/v1/companies/${company}/item-unit-bindings/${id}/revisions?limit=200&as_of=${date}`,
      });
      const effective = page.items.filter(
        (row) =>
          ['FIXED','MEASURED'].includes(row.conversion_mode ?? '') &&
          row.valid_from &&
          row.valid_from <= date &&
          (!row.valid_to || row.valid_to >= date),
      );
      if (page.page.has_more || effective.length !== 1)
        throw new Error(
          'A single product unit revision effective at books begin is required. Review this product’s unit definitions.',
        );
      if(requestedScope!==liveUnitScope.current)return;
      setRevision(effective[0]!);
      setMeasured('');
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : 'Unable to verify this unit. Try selecting it again.',
      );
    } finally {
      busyNow.current=false;
      setBusy(false);
    }
  }
  function capture(): Capture {
    if (
      !binding?.unit_id ||
      !revision ||
      !decimal(quantity, true) ||
      (revision.conversion_mode === 'MEASURED' && !decimal(measured, true)) ||
      !decimal(value) ||
      (costMode === 'RATE' && !decimal(priced, true))
    )
      throw new Error(
        'Enter a positive quantity, effective unit and an explicit cost or value with up to four decimals.',
      );
    if (
      !/^[1-9]\d{0,5}$/.test(order) ||
      (history && (!received || received > date))
    )
      throw new Error(
        'Enter a valid cohort order and an original receipt date on or before books begin.',
      );
    return {
      source_key: sourceKey,
      entered_unit_id: binding.unit_id,
      unit_revision_id: revision.id,
      entered_quantity: quantity,
      ...(revision.conversion_mode === 'MEASURED' ? {measured_base_quantity: measured} : {}),
      cost_mode: costMode,
      ...(costMode === 'RATE'
        ? { unit_cost: value, priced_quantity: priced }
        : {}),
      history_known: history,
      received_on: history ? received : null,
      cohort_order: Number(order),
    };
  }
  async function calculate(destination = 2) {
    if(disabled||busyNow.current)return;
    const requestedScope=liveInputs.current;
    busyNow.current=true;
    setError('');
    setBusy(true);
    setCalculated(null);
    try {
      if (!item || !warehouse)
        throw new Error('Select a product and warehouse.');
      const result = await openingRequest<Calculation>({
        method: 'POST',
        path: openingBase(company) + '/calculate',
        body: {
          stock_date: date,
          item_id: item,
          warehouse_id: warehouse,
          opening: capture(),
          ...(costMode === 'VALUE' ? { received_value: value } : {}),
        },
      });
      owned(company)(result);
      if(requestedScope!==liveInputs.current)
        throw new Error('The allocation changed while calculating. Recalculate the current inputs.');
      if (
        result.unit_revision_id !== revision?.id ||
        result.currency !== currency ||
        !decimal(result.base_quantity, true) ||
        !decimal(result.received_value)
      )
        throw new Error('The calculated conversion could not be verified.');
      calculatedScope.current=requestedScope;
      setCalculated(result);
      setStep(destination);
    } catch (reason) {
      setError(
        reason && typeof reason === 'object' && 'message' in reason
          ? String(reason.message)
          : 'Calculation is unavailable. Try again.',
      );
    } finally {
      busyNow.current=false;
      setBusy(false);
    }
  }
  const loadSerials: SearchSelectLoader = async ({ q, cursor, signal }) => {
    const params = new URLSearchParams({
      item_id: item!,
      status: 'ACTIVE',
      is_held: 'false',
      receipt_eligible: 'true',
      limit: '50',
    });
    if (lot) params.set('lot_id', lot);
    if (q.trim().length >= 2) params.set('q', q.trim());
    if (cursor) params.set('cursor', cursor);
    const page = await trackingRequest<
      ServicePage<Accounting['schemas']['SerialListItem']>
    >({path:`/v1/companies/${company}/stock-tracking/serials?${params}`,signal});
    return {
      items: page.items.map((row) => ({
        id: row.id,
        label: trackingTitle(row),
        disabled: !row.identifiers?.length,
      })),
      nextCursor: page.page.has_more ? page.page.next_cursor : null,
    };
  };
  function reset() {
    setQuantity('');
    setMeasured('');
    setCostValues({VALUE:'',RATE:''});
    setCostMode('VALUE');
    setPriced('1');
    setCalculated(null);
    setWarehouse(null);
    setBin(null);
    setLot(null);
    setSerials([]);
    setHistory(false);
    setReceived('');
    setOrder('1');
    setZero('');
    setGl(null);
    setError('');
    setSourceKey(crypto.randomUUID());
    setStep(0);
    setDiscard(false);
  }
  function add() {
    if(disabled||busyNow.current)return;
    setError('');
    try {
      if (!calculated || calculatedScope.current!==liveInputs.current || !profile.data || profile.failure)
        throw new Error(
          'Calculate and verify the product tracking profile before adding this allocation.',
        );
      if (profile.data.lot_tracking && !lot)
        throw new Error('Select a prepared active batch.');
      if (profile.data.lot_tracking) {
        if (!batch.data || batch.failure)
          throw new Error('Review the selected batch and its tracking dates.');
        if (
          (profile.data.expiry_required && !batch.data.expires_on) ||
          (profile.data.manufacture_date_required &&
            !batch.data.manufactured_on)
        )
          throw new Error(
            'This product requires readable manufacture and expiry dates on its batch. Complete batch preparation first.',
          );
        if (
          batch.data.manufactured_on &&
          batch.data.manufactured_on > (history ? received : date)
        )
          throw new Error(
            'Batch manufacture cannot follow its receipt or opening date.',
          );
        // Opening records existing unexpired stock. Remaining-life restrictions
        // are applied by the owner when stock is issued, not on opening receipt.
        if (
          batch.data.expires_on &&
          batch.data.expires_on < date
        )
          throw new Error(
            'This batch is expired at books begin.',
          );
      }
      if (
        profile.data.serial_tracking &&
        (calculated.base_quantity.replace(/\.0+$/, '') !==
          String(serials.length) ||
          serials.length > 200)
      )
        throw new Error('Select one distinct serial per whole base unit.');
      const line: Allocation = {
        line_id: crypto.randomUUID(),
        item_id: item!,
        warehouse_id: warehouse!,
        bin_id: bin,
        lot_id: profile.data.lot_tracking ? lot : null,
        unit_ids: profile.data.serial_tracking ? serials : [],
        quantity: calculated.base_quantity,
        received_value: calculated.received_value,
        opening: capture(),
        zero_value_reason: zero || null,
        opening_journal_line_id: mode === 'LINKED_GL' ? gl : null,
      };
      const problem = validateAllocation(line, mode);
      if (problem) throw new Error(problem);
      onAdd(line);
      reset();
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : 'Review the allocation.',
      );
    }
  }
  return (
    <FormLayout
      aside={
        <>
          <h2>Opening allocation</h2>
          <ReviewList
            stacked
            items={[
              { label: 'Books begin', value: format.date(date) },
              { label: 'Currency', value: currency },
              {
                label: 'Base quantity',
                value: calculated
                  ? format.quantity(calculated.base_quantity)
                  : 'Calculate after entering cost',
              },
              {
                label: 'Carrying value',
                value: calculated
                  ? format.money(calculated.received_value, { display: 'none' })
                  : 'Not calculated',
              },
              {
                label: 'Accounting treatment',
                value:
                  mode === 'COMBINED'
                    ? 'Inventory and opening offset'
                    : 'Existing inventory opening journal',
              },
            ]}
          />
          <Notice>
            Adding an allocation prepares your worksheet. Save the complete
            company worksheet before creating native opening drafts.
          </Notice>
        </>
      }
    >
      <Card>
        <CardBody>
          <div className="janso-flow">
            <h2 ref={heading} tabIndex={-1}>
              Add product opening
            </h2>
            <div className="janso-master-opening-progress"><Stepper
              orientation="horizontal"
              current={step}
              reached={3}
              onStep={disabled||busy?undefined:setStep}
              steps={[
                {
                  label: 'Product and location',
                  complete:
                    !!revision && !!warehouse && decimal(quantity, true),
                },
                { label: 'Cost and value', complete: !!calculated },
                {
                  label: 'Tracking and history',
                  complete: step === 3 && !!calculated,
                },
                { label: 'Review allocation', complete: false },
              ]}
            /></div>
            <AccountingFailure
              failure={profile.failure ?? batch.failure}
              retry={() => {
                profile.refresh();
                batch.refresh();
              }}
            />
            {error && (
              <div ref={errorFocus} tabIndex={-1}>
                <Notice tone="danger">
                  <span>{error}</span>
                </Notice>
              </div>
            )}
            <fieldset
              className="janso-fieldgroup janso-flow"
              disabled={disabled || busy}
            >
              {step === 0 && (
                <>
                  <div className="janso-form-grid">
                    <TrackingReference
                      company={company}
                      resource="items"
                      label="Product / SKU"
                      value={item}
                      onChange={setItem}
                      required
                    />
                    <StockReference
                      company={company}
                      resource="warehouses"
                      physicalOnly
                      required
                      label="Warehouse"
                      value={warehouse}
                      onChange={(id) => {
                        setWarehouse(id);
                        setBin(null);
                      }}
                      disabled={false}
                    />
                    {warehouse && (
                      <StockReference
                        company={company}
                        resource="warehouse-bins"
                        parent={warehouse}
                        label="Bin (if used)"
                        value={bin}
                        onChange={setBin}
                        disabled={false}
                      />
                    )}
                    <TextField
                      label="Entered quantity"
                      inputMode="decimal"
                      value={quantity}
                      onChange={(event) => setQuantity(event.target.value)}
                      required
                    />
                    <SearchSelect
                      label="Product unit"
                      required
                      value={binding?.id ?? null}
                      selected={
                        binding
                          ? {
                              id: binding.id,
                              label:
                                binding.code ??
                                binding.usage_role ??
                                'Product unit',
                            }
                          : null
                      }
                      loadOptions={loadUnits}
                      scopeKey={`${company}:${item}:${date}`}
                      minQueryLength={0}
                      onChange={(id) => void selectUnit(id)}
                      disabled={!item || busy}
                      hint="Choose a product unit effective at books begin. Measured units require an actual base quantity."
                    />
                  </div>
                  {revision && (
                    <Notice>
                      {revision.conversion_mode === 'MEASURED' ? 'Measured entry: record the actual base quantity. Nominal weight does not determine stock.' : <>Conversion: {revision.numerator} / {revision.denominator} base units.</>} Revision {revision.revision}.
                    </Notice>
                  )}
                  {revision?.conversion_mode === 'MEASURED' && <TextField label="Actual measured base quantity" inputMode="decimal" value={measured} required onChange={event=>setMeasured(event.target.value)} disabled={busy}/>}
                  <Button
                    type="button"
                    onClick={() => setStep(1)}
                    disabled={
                      !item ||
                      !warehouse ||
                      !revision ||
                      !decimal(quantity, true) ||
                      (revision.conversion_mode === 'MEASURED' && !decimal(measured, true))
                    }
                  >
                    Continue to cost
                  </Button>
                </>
              )}
              {step === 1 && (
                <>
                  <div className="janso-form-grid">
                    <Select
                      label="Cost entry"
                      value={costMode}
                      onChange={(mode) =>
                        setCostMode(mode as Capture['cost_mode'])
                      }
                      options={[
                        { value: 'VALUE', label: 'Total carrying value' },
                        { value: 'RATE', label: 'Unit cost' },
                      ]}
                    />
                    <TextField
                      label={
                        (costMode === 'RATE'
                          ? 'Unit cost'
                          : 'Total carrying value') +
                        ' (' +
                        currency +
                        ')'
                      }
                      inputMode="decimal"
                      value={value}
                      onChange={(event) => setValue(event.target.value)}
                      required
                    />
                    {costMode === 'RATE' && (
                      <TextField
                        label="Cost per quantity"
                        inputMode="decimal"
                        value={priced}
                        onChange={(event) => setPriced(event.target.value)}
                      />
                    )}
                  </div>
                  <Notice>
                    Use acquisition carrying cost at books begin, including
                    eligible landed costs. Selling prices are not used.
                  </Notice>
                  <Button
                    type="button"
                    onClick={() => void calculate()}
                    loading={busy}
                  >
                    Calculate and continue
                  </Button>
                </>
              )}
              {step === 2 && (
                <>
                  <Checkbox
                    checked={history}
                    onChange={(event) => setHistory(event.target.checked)}
                  >
                    Original receipt date is known
                  </Checkbox>
                  {history ? (
                    <TextField
                      label="Original receipt date"
                      type="date"
                      max={date}
                      value={received}
                      onChange={(event) => setReceived(event.target.value)}
                      required
                    />
                  ) : (
                    <Notice>Receipt age will be recorded as unknown.</Notice>
                  )}
                  <TextField
                    label="Cohort order"
                    type="number"
                    min={1}
                    max={999999}
                    value={order}
                    onChange={(event) => setOrder(event.target.value)}
                    hint="Order same-date receipts within each product and warehouse."
                  />
                  {profile.data?.lot_tracking && (
                    <>
                      <StockReference
                        company={company}
                        resource="batches"
                        parent={item ?? undefined}
                        label="Prepared batch"
                        required
                        value={lot}
                        onChange={(id) => {
                          setLot(id);
                          setSerials([]);
                        }}
                        disabled={!item}
                      />
                      {batch.data && (
                        <ReviewList
                          items={[
                            {
                              label: 'Manufactured on',
                              value: batch.data.manufactured_on
                                ? format.date(batch.data.manufactured_on)
                                : 'Not recorded',
                            },
                            {
                              label: 'Expires on',
                              value: batch.data.expires_on
                                ? format.date(batch.data.expires_on)
                                : 'Not recorded',
                            },
                          ]}
                        />
                      )}
                    </>
                  )}
                  {profile.data?.serial_tracking && (
                    <>
                      <SearchSelect
                        multiple
                        label="Prepared serials"
                        required
                        value={serials}
                        selected={serials.flatMap(
                          (id) => serialOptions.current.get(id) ?? [],
                        )}
                        loadOptions={loadSerials}
                        scopeKey={`${company}:${item}:${lot}`}
                        minQueryLength={0}
                        maxOptions={200}
                        onChange={(ids, options) => {
                          options.forEach((option) =>
                            serialOptions.current.set(option.id, option),
                          );
                          setSerials(ids);
                        }}
                        hint="One serial per base unit; maximum 200 per allocation."
                      />
                    </>
                  )}
                  <Button
                    type="button"
                    onClick={() => {
                      setStep(3);
                    }}
                    disabled={!profile.data}
                  >
                    Review allocation
                  </Button>
                </>
              )}
              {step === 3 && (
                <>
                  <ReviewList
                    stacked
                    items={[
                      { label: 'Books begin', value: format.date(date) },
                      { label: 'Currency', value: currency },
                      { label: 'Entered quantity', value: quantity },
                      {
                        label: 'Base quantity',
                        value: calculated
                          ? format.quantity(calculated.base_quantity)
                          : 'Recalculate after changes',
                      },
                      {
                        label: 'Carrying value',
                        value: calculated
                          ? format.money(calculated.received_value, {
                              display: 'none',
                            }) +
                            ' ' +
                            currency
                          : 'Not calculated',
                      },
                      {
                        label: 'Receipt history',
                        value: history ? received : 'Unknown',
                      },
                      {
                        label: 'Selected serials',
                        value: String(serials.length),
                      },
                    ]}
                  />
                  {calculated && !/[1-9]/.test(calculated.received_value) && (
                    <TextField
                      label="Zero-value reason"
                      value={zero}
                      onChange={(event) => setZero(event.target.value)}
                      required
                      hint="Company configuration must allow zero-cost stock."
                    />
                  )}
                  {mode === 'LINKED_GL' &&
                    calculated &&
                    /[1-9]/.test(calculated.received_value) && (
                      <OpeningReference
                        company={company}
                        date={date}
                        label="Posted inventory opening line"
                        value={gl}
                        disabled={false}
                        onChange={setGl}
                      />
                    )}
                  {!calculated && (
                    <Button type="button" onClick={() => void calculate(3)}>
                      Recalculate allocation
                    </Button>
                  )}
                  <Button
                    type="button"
                    onClick={add}
                    disabled={!calculated || !profile.data}
                  >
                    Add to worksheet
                  </Button>
                </>
              )}
            </fieldset>
            <div className="janso-form-actions">
              {dirty && (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={busy || disabled}
                  onClick={() => setDiscard(true)}
                >
                  Discard this allocation
                </Button>
              )}
              {step > 0 && (
                <Button
                  variant="ghost"
                  onClick={() => setStep(step - 1)}
                  disabled={disabled||busy}
                >
                  Previous step
                </Button>
              )}
            </div>
            <ConfirmDialog
              open={discard}
              title="Discard this allocation?"
              confirmLabel="Discard allocation"
              onCancel={() => setDiscard(false)}
              onConfirm={reset}
            >
              Only the allocation being entered will be cleared. Allocations
              already added to the worksheet remain.
            </ConfirmDialog>
          </div>
        </CardBody>
      </Card>
    </FormLayout>
  );
}
