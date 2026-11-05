import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { OpeningStockEntry } from '../app/components/OpeningStockEntry';
import { serviceCall } from '../app/lib/service-call';
import { renderWithProviders } from './helpers';
import { Providers } from '../app/providers';
import {
  COMPANY,
  ITEM,
  UNIT,
  REVISION,
  WAREHOUSE,
} from './opening-stock-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/components/StockTrackingCommon', () => ({
  TrackingReference: ({
    label,
    value,
    onChange,
  }: {
    label: string;
    value: string;
    onChange: (id: string) => void;
  }) => (
    <input
      aria-label={label}
      value={value ?? ''}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
}));
vi.mock('../app/components/VoucherStock', () => ({
  StockReference: ({
    label,
    value,
    onChange,
  }: {
    label: string;
    value: string;
    onChange: (id: string) => void;
  }) => (
    <input
      aria-label={label}
      value={value ?? ''}
      onChange={(event) => onChange(event.target.value)}
    />
  ),
  OpeningReference: ({label,value,onChange}:{label:string;value:string;onChange:(id:string)=>void})=><input aria-label={label} value={value??''} onChange={event=>onChange(event.target.value)}/>,
}));
vi.mock('@janso/ui', async (original) => ({
  ...(await original<typeof import('@janso/ui')>()),
  SearchSelect: ({
    label,
    loadOptions,
    onChange,
    multiple,
  }: {
    label: string;
    loadOptions: (query: { q: string }) => Promise<{ items: { id: string }[] }>;
    onChange: (id: string|string[],options?:unknown[]) => void;
    multiple?:boolean;
  }) => (
    <button
      onClick={() =>
        void loadOptions({ q: '' }).then((result) =>
          multiple?onChange(result.items.map(item=>item.id),result.items):onChange(result.items[0]!.id),
        )
      }
    >
      {label}
    </button>
  ),
}));
let serial = false,
  measuredEntry = false,
  lotTracking = false,
  expiresOn = '2026-04-01';
beforeEach(() => {
  serial = false;
  measuredEntry = false;
  lotTracking = false;
  expiresOn = '2026-04-01';
  vi.mocked(serviceCall)
    .mockReset()
    .mockImplementation(async (_endpoint, request) => {
      if (request.path.includes('/context/'))
        return {
          company_id: COMPANY,
          item_id: ITEM,
          lot_tracking: lotTracking,
          expiry_required: lotTracking,
          manufacture_date_required: lotTracking,
          serial_tracking: serial,
        } as never;
      if (request.path.includes('/stock-tracking/batches/'))
        return {
          id: WAREHOUSE,
          company_id: COMPANY,
          item_id: ITEM,
          status: 'ACTIVE',
          is_held: false,
          manufactured_on: '2026-01-01',
          expires_on: expiresOn,
        } as never;
      if(request.path.includes('/stock-tracking/serials?'))return {items:Array.from({length:24},(_,n)=>({id:'01990000-0000-7000-8000-'+String(100+n).padStart(12,'0'),identifiers:[{identifier_type:'SERIAL',value:'SER-'+n}]})),page:{has_more:false}} as never;
      if (request.path.includes('/unit-bindings?'))
        return {
          items: [{ id: UNIT, unit_id: UNIT, code: 'BOX' }],
          page: { has_more: false },
        } as never;
      if (request.path.includes('/revisions?'))
        return {
          items: [
            {
              id: REVISION,
              conversion_mode: measuredEntry ? 'MEASURED' : 'FIXED',
              numerator: measuredEntry ? null : '12',
              denominator: measuredEntry ? null : '1',
              valid_from: '2026-01-01',
              valid_to: null,
              revision: 1,
            },
          ],
          page: { has_more: false },
        } as never;
      if (request.path.endsWith('/calculate'))
        return {
          company_id: COMPANY,
          currency: 'INR',
          unit_revision_id: REVISION,
          base_quantity: '24.0000',
          received_value: '120.0000',
          derived_unit_cost: '60',
          derived_base_unit_cost: '5',
        } as never;
      throw new Error('Unexpected test path');
    });
});
async function fill() {
  fireEvent.change(screen.getByLabelText('Warehouse'), {
    target: { value: WAREHOUSE },
  });
  fireEvent.change(screen.getByLabelText('Entered quantity'), {
    target: { value: '2' },
  });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Product unit' }));
    await Promise.resolve();
  });
  await screen.findByText(/Conversion: 12/);
  await userEvent.click(
    screen.getByRole('button', { name: 'Continue to cost' }),
  );
  fireEvent.change(screen.getByLabelText('Total carrying value (INR)'), {
    target: { value: '120' },
  });
  await userEvent.click(
    screen.getByRole('button', { name: 'Calculate and continue' }),
  );
  await screen.findByRole('checkbox', {
    name: 'Original receipt date is known',
  });
}
it('builds an exact allocation from an authoritative non-base-unit calculation', async () => {
  const add = vi.fn(),
    dirty = vi.fn();
  await mountOpening(
    <OpeningStockEntry
      company={COMPANY}
      initialItemId={ITEM}
      date="2026-04-01"
      currency="INR"
      mode="COMBINED"
      disabled={false}
      onAdd={add}
      onDirty={dirty}
    />,
  );
  await fill();
  const requests = vi.mocked(serviceCall).mock.calls.map((call) => call[1].path);
  expect(requests.find((path) => path.includes('/unit-bindings?'))).toBe(
    `/v1/companies/${COMPANY}/items/${ITEM}/unit-bindings?limit=50`,
  );
  expect(requests.find((path) => path.includes('/revisions?'))).toContain('as_of=2026-04-01');
  await userEvent.click(
    screen.getByRole('button', { name: 'Review allocation' }),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Add to worksheet' }),
  );
  expect(add).toHaveBeenCalledOnce();
  expect(dirty).toHaveBeenLastCalledWith(false);
  expect(add.mock.calls[0]![0]).toMatchObject({
    quantity: '24.0000',
    received_value: '120.0000',
    opening: {
      entered_quantity: '2',
      unit_revision_id: REVISION,
      history_known: false,
    },
  });
});
it('captures actual measured opening quantities instead of a nominal ratio', async () => {
  measuredEntry = true;
  const add = vi.fn();
  await mountOpening(<OpeningStockEntry company={COMPANY} initialItemId={ITEM}
    date="2026-04-01" currency="INR" mode="COMBINED" disabled={false}
    onAdd={add} onDirty={() => {}} />);
  fireEvent.change(screen.getByLabelText('Warehouse'), {target:{value:WAREHOUSE}});
  fireEvent.change(screen.getByLabelText('Entered quantity'), {target:{value:'2'}});
  await userEvent.click(screen.getByRole('button',{name:'Product unit'}));
  await screen.findByLabelText('Actual measured base quantity');
  expect(screen.getByRole('button',{name:'Continue to cost'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Actual measured base quantity'),{target:{value:'24'}});
  await userEvent.click(screen.getByRole('button',{name:'Continue to cost'}));
  fireEvent.change(screen.getByLabelText('Total carrying value (INR)'),{target:{value:'120'}});
  await userEvent.click(screen.getByRole('button',{name:'Calculate and continue'}));
  await screen.findByRole('checkbox',{name:'Original receipt date is known'});
  await userEvent.click(screen.getByRole('button',{name:'Review allocation'}));
  await userEvent.click(screen.getByRole('button',{name:'Add to worksheet'}));
  expect(add.mock.calls[0]![0].opening).toMatchObject({entered_quantity:'2',measured_base_quantity:'24'});
  const body = vi.mocked(serviceCall).mock.calls.find(call=>call[1].path.endsWith('/calculate'))![1].body;
  expect(body).toMatchObject({opening:{entered_quantity:'2',measured_base_quantity:'24'}});
});
it('requires one selected serial per base unit', async () => {
  serial = true;
  const add = vi.fn();
  await mountOpening(
    <OpeningStockEntry
      company={COMPANY}
      initialItemId={ITEM}
      date="2026-04-01"
      currency="INR"
      mode="COMBINED"
      disabled={false}
      onAdd={add}
      onDirty={() => {}}
    />,
  );
  await fill();
  await userEvent.click(
    screen.getByRole('button', { name: 'Review allocation' }),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Add to worksheet' }),
  );
  expect(screen.getByRole('alert')).toHaveTextContent('one distinct serial');
  expect(add).not.toHaveBeenCalled();
});

it.each([
  ['2026-04-01', true],
  ['2026-03-31', false],
])('applies inclusive expiry at books begin (%s)', async (expiry, allowed) => {
  lotTracking = true;
  expiresOn = expiry;
  const add = vi.fn();
  await mountOpening(
    <OpeningStockEntry
      company={COMPANY}
      initialItemId={ITEM}
      date="2026-04-01"
      currency="INR"
      mode="COMBINED"
      disabled={false}
      onAdd={add}
      onDirty={() => {}}
    />,
  );
  await fill();
  fireEvent.change(screen.getByLabelText('Prepared batch'), {
    target: { value: WAREHOUSE },
  });
  await screen.findByText('Manufactured on');
  await userEvent.click(
    screen.getByRole('button', { name: 'Review allocation' }),
  );
  await userEvent.click(
    screen.getByRole('button', { name: 'Add to worksheet' }),
  );
  if (allowed) expect(add).toHaveBeenCalledOnce();
  else {
    expect(add).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent('expired');
  }
});

async function mountOpening(ui: React.ReactElement) {
  let mounted!:Awaited<ReturnType<typeof renderWithProviders>>;
  await act(async () => {
    mounted=await renderWithProviders(ui);
  });
  return {...mounted,rerender:(element:React.ReactNode)=>mounted.rerender(<Providers session={mounted.session}>{element}</Providers>)};
}

const openingEditor=(onAdd=vi.fn(),date='2026-04-01',currency='INR')=><OpeningStockEntry company={COMPANY} initialItemId={ITEM} date={date} currency={currency} mode="COMBINED" disabled={false} onAdd={onAdd} onDirty={()=>{}}/>;
it('keeps separate exact values when switching between total value and unit cost',async()=>{
  await mountOpening(openingEditor());await fill();await userEvent.click(screen.getByRole('button',{name:'Previous step'}));
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Cost entry'}),'RATE');expect(screen.getByLabelText('Unit cost (INR)')).toHaveValue('');
  fireEvent.change(screen.getByLabelText('Unit cost (INR)'),{target:{value:'60.0001'}});
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Cost entry'}),'VALUE');expect(screen.getByLabelText('Total carrying value (INR)')).toHaveValue('120');
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Cost entry'}),'RATE');expect(screen.getByLabelText('Unit cost (INR)')).toHaveValue('60.0001');
});
it('resets cost mode and cost-per quantity when an allocation is discarded',async()=>{
  await mountOpening(openingEditor());await fill();await userEvent.click(screen.getByRole('button',{name:'Previous step'}));await userEvent.selectOptions(screen.getByRole('combobox',{name:'Cost entry'}),'RATE');
  fireEvent.change(screen.getByLabelText('Cost per quantity'),{target:{value:'10'}});await userEvent.click(screen.getByRole('button',{name:'Discard this allocation'}));await userEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Discard allocation'}));
  await userEvent.click(within(screen.getByRole('navigation',{name:'Setup progress'})).getByRole('button',{name:/Cost and value/}));expect(screen.getByRole('combobox',{name:'Cost entry'})).toHaveValue('VALUE');
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Cost entry'}),'RATE');expect(screen.getByLabelText('Cost per quantity')).toHaveValue('1');expect(screen.getByLabelText('Unit cost (INR)')).toHaveValue('');
});
it.each(['date','currency'])('invalidates a calculation when its %s changes',async(field)=>{
  const add=vi.fn(),view=await mountOpening(openingEditor(add));await fill();await userEvent.click(screen.getByRole('button',{name:'Review allocation'}));
  view.rerender(openingEditor(add,field==='date'?'2026-04-02':'2026-04-01',field==='currency'?'USD':'INR'));
  expect(screen.getByRole('button',{name:'Add to worksheet'})).toBeDisabled();expect(add).not.toHaveBeenCalled();
});
it('rejects an in-flight calculation after the opening date changes and locks step navigation while calculating',async()=>{
  const add=vi.fn(),view=await mountOpening(openingEditor(add));await fill();await userEvent.click(screen.getByRole('button',{name:'Previous step'}));
  const original=vi.mocked(serviceCall).getMockImplementation()!;let resolve!:(value:unknown)=>void;
  vi.mocked(serviceCall).mockImplementation(async(...args)=>args[1].path.endsWith('/calculate')?await new Promise<unknown>(done=>{resolve=done;}) as never:original(...args));
  await userEvent.click(screen.getByRole('button',{name:'Calculate and continue'}));
  expect(within(screen.getByRole('navigation',{name:'Setup progress'})).getByRole('button',{name:/Product and location/})).toBeDisabled();
  view.rerender(openingEditor(add,'2026-04-02'));
  await act(async()=>resolve({company_id:COMPANY,currency:'INR',unit_revision_id:REVISION,base_quantity:'24.0000',received_value:'120.0000'}));
  await userEvent.click(within(screen.getByRole('navigation',{name:'Setup progress'})).getByRole('button',{name:/Review allocation/}));
  expect(screen.getByRole('button',{name:'Add to worksheet'})).toBeDisabled();expect(add).not.toHaveBeenCalled();
});
it('fails closed when the product tracking flags are protected',async()=>{
  const original=vi.mocked(serviceCall).getMockImplementation()!;
  vi.mocked(serviceCall).mockImplementation(async(...args)=>args[1].path.includes('/context/')?{company_id:COMPANY,item_id:ITEM,lot_tracking:null,serial_tracking:null} as never:original(...args));
  await mountOpening(openingEditor());await waitFor(()=>expect(screen.getByText('Product tracking settings are protected or unavailable.')).toBeVisible());
  await userEvent.click(within(screen.getByRole('navigation',{name:'Setup progress'})).getByRole('button',{name:/Review allocation/}));expect(screen.getByRole('button',{name:'Add to worksheet'})).toBeDisabled();
});
it('records batches, distinct serials and receipt history after recalculating the current inputs',async()=>{
  lotTracking=true;serial=true;const add=vi.fn();await mountOpening(openingEditor(add));await fill();
  fireEvent.change(screen.getByLabelText('Prepared batch'),{target:{value:WAREHOUSE}});await screen.findByText('Manufactured on');await userEvent.click(screen.getByRole('button',{name:'Prepared serials'}));
  await userEvent.click(screen.getByRole('checkbox',{name:'Original receipt date is known'}));fireEvent.change(screen.getByLabelText('Original receipt date'),{target:{value:'2026-03-01'}});fireEvent.change(screen.getByLabelText('Cohort order'),{target:{value:'2'}});
  await userEvent.click(screen.getByRole('button',{name:'Review allocation'}));expect(screen.getByRole('button',{name:'Add to worksheet'})).toBeDisabled();await userEvent.click(screen.getByRole('button',{name:'Recalculate allocation'}));await waitFor(()=>expect(screen.getByRole('button',{name:'Add to worksheet'})).toBeEnabled());await userEvent.click(screen.getByRole('button',{name:'Add to worksheet'}));
  expect(add.mock.calls[0]![0]).toMatchObject({lot_id:WAREHOUSE,quantity:'24.0000',opening:{history_known:true,received_on:'2026-03-01',cohort_order:2}});expect(add.mock.calls[0]![0].unit_ids).toHaveLength(24);expect(new Set(add.mock.calls[0]![0].unit_ids).size).toBe(24);
});
it('requires a zero-value explanation before adding stock with no carrying cost',async()=>{
  const original=vi.mocked(serviceCall).getMockImplementation()!,add=vi.fn();vi.mocked(serviceCall).mockImplementation(async(...args)=>{const value=await original(...args);return args[1].path.endsWith('/calculate')?{...(value as object),received_value:'0.0000'} as never:value;});
  await mountOpening(openingEditor(add));await fill();await userEvent.click(screen.getByRole('button',{name:'Review allocation'}));await userEvent.click(screen.getByRole('button',{name:'Add to worksheet'}));expect(add).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Zero-value reason'),{target:{value:'Reviewed fully written-down stock'}});await userEvent.click(screen.getByRole('button',{name:'Add to worksheet'}));expect(add.mock.calls[0]![0]).toMatchObject({received_value:'0.0000',zero_value_reason:'Reviewed fully written-down stock'});
});
it('keeps unit cost and cost-per quantity exact and requires linked opening coverage',async()=>{
  const add=vi.fn();await mountOpening(<OpeningStockEntry company={COMPANY} initialItemId={ITEM} date="2026-04-01" currency="INR" mode="LINKED_GL" disabled={false} onAdd={add} onDirty={()=>{}}/>);await fill();await userEvent.click(screen.getByRole('button',{name:'Previous step'}));await userEvent.selectOptions(screen.getByRole('combobox',{name:'Cost entry'}),'RATE');
  fireEvent.change(screen.getByLabelText('Unit cost (INR)'),{target:{value:'60.0001'}});fireEvent.change(screen.getByLabelText('Cost per quantity'),{target:{value:'2'}});await userEvent.click(screen.getByRole('button',{name:'Calculate and continue'}));await userEvent.click(screen.getByRole('button',{name:'Review allocation'}));await userEvent.click(screen.getByRole('button',{name:'Add to worksheet'}));expect(add).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Posted inventory opening line'),{target:{value:REVISION}});await userEvent.click(screen.getByRole('button',{name:'Add to worksheet'}));expect(add.mock.calls[0]![0]).toMatchObject({opening_journal_line_id:REVISION,opening:{cost_mode:'RATE',unit_cost:'60.0001',priced_quantity:'2'}});
});
it('retains an allocation when discarding is cancelled and recovers unavailable tracking reads',async()=>{
  const original=vi.mocked(serviceCall).getMockImplementation()!;let fail=true;
  vi.mocked(serviceCall).mockImplementation(async(...args)=>{if(fail&&args[1].path.includes('/context/'))throw {status:503,message:'Tracking unavailable'};return original(...args);});
  await mountOpening(openingEditor());await screen.findByText('Tracking unavailable');fail=false;await userEvent.click(screen.getByRole('button',{name:'Reload configuration'}));await waitFor(()=>expect(screen.queryByText('Tracking unavailable')).toBeNull());
  fireEvent.change(screen.getByLabelText('Entered quantity'),{target:{value:'2.0001'}});await userEvent.click(screen.getByRole('button',{name:'Discard this allocation'}));await userEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Cancel'}));expect(screen.getByLabelText('Entered quantity')).toHaveValue('2.0001');
});

it.each([['2026-04-11', true], ['2026-04-01', true], ['2026-03-31', false]])(
  'uses opening expiry rather than the outward-issue remaining-life threshold (%s)',
  async (expiry, allowed) => {
    lotTracking = true;
    expiresOn = expiry;
    const original = vi.mocked(serviceCall).getMockImplementation()!;
    vi.mocked(serviceCall).mockImplementation(async (...args) => {
      const result = await original(...args);
      if (args[1].path.includes('/context/'))
        return { ...(result as object), minimum_remaining_life_days: 30 } as never;
      return result;
    });
    const add = vi.fn();
    await mountOpening(<OpeningStockEntry company={COMPANY} initialItemId={ITEM}
      date="2026-04-01" currency="INR" mode="COMBINED" disabled={false}
      onAdd={add} onDirty={() => {}} />);
    await fill();
    fireEvent.change(screen.getByLabelText('Prepared batch'), { target: { value: WAREHOUSE } });
    await screen.findByText('Manufactured on');
    await userEvent.click(screen.getByRole('button', { name: 'Review allocation' }));
    await userEvent.click(screen.getByRole('button', { name: 'Add to worksheet' }));
    if (allowed) expect(add).toHaveBeenCalledOnce();
    else {
      expect(add).not.toHaveBeenCalled();
      expect(screen.getByRole('alert')).toHaveTextContent('expired');
    }
  },
);
