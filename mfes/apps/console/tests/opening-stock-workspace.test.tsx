import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { OpeningStockWorkspace } from '../app/components/OpeningStockWorkspace';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import {
  access,
  COMPANY,
  CONTROL,
  allocation,
  control,
  manifest,
  readiness,
} from './opening-stock-fixtures';
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/components/OpeningStockEntry', () => ({
  OpeningStockEntry: ({
    onAdd,onDirty,
  }: {
    onAdd: (line: ReturnType<typeof allocation>) => void;
    onDirty:(dirty:boolean)=>void;
  }) => (
    <>
    <button onClick={() => onAdd(allocation('opening-b'))}>
      Add verified allocation
    </button>
    <button onClick={()=>onDirty(true)}>Enter unfinished allocation</button>
    <button onClick={()=>onDirty(false)}>Cancel unfinished allocation</button>
    </>
  ),
}));
vi.mock('../app/components/OpeningStockImports', () => ({
  OpeningStockImports: ({onChanged}:{onChanged:()=>void}) => <><p>Draft workbench</p><button onClick={onChanged}>Refresh changed drafts</button></>,
}));
vi.mock('../app/components/OpeningStockHistory', () => ({
  OpeningStockHistory: () => <p>History workbench</p>,
}));
const api = vi.mocked(serviceCall);
let start = false,
  denyManifest = false;
beforeEach(() => {
  start = false;
  denyManifest = false;
  api.mockReset();
  api.mockImplementation(async (_endpoint, request) => {
    if (request.path.endsWith('/readiness'))
      return start
        ? ({
            ...readiness,
            control_id: null,
            status: 'NOT_STARTED',
            can_start: true,
            can_confirm_zero: true,
          } as never)
        : (readiness as never);
    if (request.path.endsWith('/manifest')) {
      if (denyManifest)
        throw { status: 403, message: 'Carrying value is protected.' };
      return manifest as never;
    }
    if (request.path.endsWith('/reconciliation')) return control as never;
    if (request.path.endsWith('/accounting-preview'))
      return {
        company_id: COMPANY,
        control_id: CONTROL,
        expected_version: 2,
        manifest_hash: control.manifest_hash,
        currency: 'INR',
        opening_mode: 'COMBINED',
        remaining_value: '12.5',
        additional_gl_value: '12.5',
        entries: [],
        linked_claims: [],
      } as never;
    return control as never;
  });
});
it('keeps accounting treatment locked while a product allocation is unfinished',async()=>{
  start=true;render(<OpeningStockWorkspace company={COMPANY} currency="INR" access={access}/>);
  await userEvent.click(await screen.findByRole('button',{name:'Enter unfinished allocation'}));
  expect(screen.getByRole('combobox',{name:'Accounting treatment'})).toBeDisabled();expect(screen.getByRole('combobox',{name:'Accounting treatment'})).toHaveValue('COMBINED');
});
it('returns to the preceding worksheet page after removing the last allocation on its page',async()=>{
  const original=api.getMockImplementation()!;
  api.mockImplementation(async(...args)=>args[1].path.endsWith('/manifest')?{...manifest,lines:Array.from({length:26},(_,n)=>allocation('cohort-'+n))} as never:original(...args));
  render(<OpeningStockWorkspace company={COMPANY} currency="INR" access={access}/>);
  await userEvent.click(await screen.findByRole('button',{name:/Next page of allocations/}));await userEvent.click(screen.getByRole('button',{name:'Remove allocation'}));
  await waitFor(()=>expect(screen.queryByText('No declared opening allocations')).toBeNull());expect(screen.getAllByRole('cell',{name:'12.50'})).toHaveLength(25);
});
it('allows choosing treatment after cancelling an unfinished allocation and retains worksheet changes when review is cancelled',async()=>{
  start=true;render(<OpeningStockWorkspace company={COMPANY} currency="INR" access={access}/>);await userEvent.click(await screen.findByRole('button',{name:'Enter unfinished allocation'}));await userEvent.click(screen.getByRole('button',{name:'Cancel unfinished allocation'}));
  await userEvent.selectOptions(screen.getByRole('combobox',{name:'Accounting treatment'}),'LINKED_GL');expect(screen.getByRole('combobox',{name:'Accounting treatment'})).toHaveValue('LINKED_GL');await userEvent.selectOptions(screen.getByRole('combobox',{name:'Accounting treatment'}),'COMBINED');
  await userEvent.click(screen.getByRole('button',{name:'Add verified allocation'}));fireEvent.change(screen.getByLabelText('Reason for worksheet change'),{target:{value:'Reviewed opening'}});await userEvent.click(screen.getByRole('button',{name:'Review and save worksheet'}));await userEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Cancel'}));expect(screen.getByRole('cell',{name:'12.50'})).toBeVisible();expect(api.mock.calls.some(([,request])=>request.method==='POST')).toBe(false);
});
it('reviews both worksheet pages and refreshes owner reads after draft preparation',async()=>{
  const original=api.getMockImplementation()!;api.mockImplementation(async(...args)=>args[1].path.endsWith('/manifest')?{...manifest,lines:Array.from({length:26},(_,n)=>allocation('page-'+n))} as never:original(...args));
  render(<OpeningStockWorkspace company={COMPANY} currency="INR" access={access}/>);await userEvent.click(await screen.findByRole('button',{name:/Next page of allocations/}));await userEvent.click(screen.getByRole('button',{name:/Previous page of allocations/}));await userEvent.selectOptions(screen.getByRole('combobox',{name:'Rows per page'}),'50');expect(screen.getAllByRole('cell',{name:'12.50'})).toHaveLength(26);
  await userEvent.click(screen.getByRole('button',{name:'Drafts and imports'}));const prior=api.mock.calls.filter(([,r])=>r.path.endsWith('/'+CONTROL)).length;await userEvent.click(screen.getByRole('button',{name:'Refresh changed drafts'}));await waitFor(()=>expect(api.mock.calls.filter(([,r])=>r.path.endsWith('/'+CONTROL)).length).toBeGreaterThan(prior));
});
it.each(['finalize','reopen','adopt'])('sends %s only after a company-wide review with native versions and reason',async(action)=>{
  const original=api.getMockImplementation()!;let current={...control,status:action==='reopen'?'FINALIZED':'OPEN',blockers:[],missing_source_keys:[],applied_cohorts:1,applied_value:'12.5000'};
  api.mockImplementation(async(...args)=>{
    const request=args[1];if(request.method==='POST'){current={...current,status:action==='finalize'?'FINALIZED':'OPEN'};return current as never;}
    if(request.path.endsWith('/readiness'))return {...readiness,status:action==='adopt'?'LEGACY_ACTIVITY':'OPEN',blockers:action==='adopt'?['LEGACY_ACTIVITY_REQUIRES_REVIEW']:[]} as never;
    if(request.path.endsWith('/'+CONTROL)||request.path.endsWith('/reconciliation'))return current as never;
    if(request.path.endsWith('/accounting-preview'))return {company_id:COMPANY,currency:'INR',remaining_value:'0',additional_gl_value:'0',entries:[{side:'DEBIT',amount:'12.5000',account_id:CONTROL}],linked_claims:[]} as never;
    return original(...args);
  });
  render(<OpeningStockWorkspace company={COMPANY} currency="INR" access={access}/>);await userEvent.click(await screen.findByRole('button',{name:'Reconcile and complete'}));fireEvent.change(screen.getByLabelText('Completion or correction reason'),{target:{value:'Reviewed whole company opening'}});await userEvent.click(screen.getByRole('button',{name:'Refresh reconciliation'}));
  const label=action==='finalize'?'Finalize company opening':action==='reopen'?'Request reviewed reopening':'Review and adopt existing stock history';await waitFor(()=>expect(screen.getByRole('button',{name:label})).toBeEnabled());await userEvent.click(screen.getByRole('button',{name:label}));await userEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Confirm'}));
  await waitFor(()=>expect(api.mock.calls.some(([,request])=>request.method==='POST')).toBe(true));const request=api.mock.calls.find(([,r])=>r.method==='POST')![1];expect(request.path).toContain('/'+action);expect(request.body).toMatchObject(action==='adopt'?{adopt_existing:true,lines:[],reason:'Reviewed whole company opening'}:{expected_version:2,manifest_hash:control.manifest_hash,reason:'Reviewed whole company opening'});
});
it('allows stock readers to review without financial controller actions', async () => {
  render(
    <OpeningStockWorkspace
      company={COMPANY}
      currency="INR"
      access={{ ...access, manage: false }}
    />,
  );
  await screen.findByRole('cell', { name: '12.50' });
  expect(
    screen.queryByRole('button', { name: 'Add verified allocation' }),
  ).not.toBeInTheDocument();
  expect(screen.getByText(/awaits installation activation/)).toBeVisible();
  await userEvent.click(
    screen.getByRole('button', { name: 'Drafts and imports' }),
  );
  expect(screen.getByText('Draft workbench')).toBeVisible();
});
it('fails closed when protected manifest data cannot be read', async () => {
  denyManifest = true;
  render(
    <OpeningStockWorkspace company={COMPANY} currency="INR" access={access} />,
  );
  await screen.findByText('Carrying value is protected.');
  expect(
    screen.queryByRole('button', { name: 'Add verified allocation' }),
  ).not.toBeInTheDocument();
  expect(screen.queryByRole('cell', { name: '12.50' })).not.toBeInTheDocument();
});
it('keeps the full company declaration when appending a product and retries an uncertain save exactly', async () => {
  const original = api.getMockImplementation()!,
    writes: ServiceRequest[] = [];
  api.mockImplementation(async (...args) => {
    const request = args[1];
    if (request.method === 'POST') {
      writes.push(request);
      if (writes.length === 1) throw { status: 503, message: 'Lost response' };
      return control as never;
    }
    return original(...args);
  });
  render(
    <OpeningStockWorkspace company={COMPANY} currency="INR" access={access} />,
  );
  await screen.findByRole('cell', { name: '12.50' });
  await userEvent.click(
    screen.getByRole('button', { name: 'Add verified allocation' }),
  );
  fireEvent.change(screen.getByLabelText('Reason for worksheet change'), {
    target: { value: 'Append reviewed second cohort' },
  });
  await userEvent.click(
    screen.getByRole('button', { name: 'Review and save worksheet' }),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Confirm' }));
  await userEvent.click(
    await screen.findByRole('button', { name: 'Retry the same update' }),
  );
  await waitFor(() => expect(writes).toHaveLength(2));
  expect(writes[0]!.key).toBe(writes[1]!.key);
  expect(writes[0]!.body).toEqual(writes[1]!.body);
  expect(
    (writes[0]!.body as { manifest: typeof manifest }).manifest.lines,
  ).toHaveLength(2);
  expect(writes[0]!.path).toContain('/replace');
});
it('does not offer finalization when declared cohorts are missing', async () => {
  render(
    <OpeningStockWorkspace company={COMPANY} currency="INR" access={access} />,
  );
  await screen.findByRole('cell', { name: '12.50' });
  await userEvent.click(
    screen.getByRole('button', { name: 'Reconcile and complete' }),
  );
  fireEvent.change(screen.getByLabelText('Completion or correction reason'), {
    target: { value: 'Reviewed company reconciliation' },
  });
  await waitFor(() =>
    expect(
      screen.getByRole('button', { name: 'Finalize company opening' }),
    ).toBeDisabled(),
  );
});
it('explicit zero confirmation uses the server accounting generation and narrow permission', async () => {
  start = true;
  render(
    <OpeningStockWorkspace
      company={COMPANY}
      currency="INR"
      access={{ ...access, manage: false }}
    />,
  );
  await screen.findByText('not started');
  await userEvent.click(
    screen.getByRole('button', { name: 'Reconcile and complete' }),
  );
  fireEvent.change(screen.getByLabelText('Completion or correction reason'), {
    target: { value: 'No physical opening stock' },
  });
  await userEvent.click(
    screen.getByRole('button', { name: 'Confirm zero stock opening' }),
  );
  expect(screen.getByRole('dialog')).toHaveTextContent(
    'no physical opening stock',
  );
  await userEvent.click(screen.getByRole('button', { name: 'Confirm' }));
  await waitFor(() =>
    expect(
      api.mock.calls.some(
        ([, request]) =>
          request.path.endsWith('/confirm-zero') &&
          (request.body as { expected_generation: number })
            .expected_generation === 8,
      ),
    ).toBe(true),
  );
});

it('preserves both controllers allocations after a first-registration conflict', async () => {
  start = true;
  const original = api.getMockImplementation()!;
  const writes: ServiceRequest[] = [];
  api.mockImplementation(async (...args) => {
    if (args[1].method === 'POST') {
      writes.push(args[1]);
      if (writes.length === 1) {
        start = false;
        throw { status: 409, message: 'An opening control already exists; resume it.' };
      }
      return control as never;
    }
    return original(...args);
  });
  const user = userEvent.setup();
  render(<OpeningStockWorkspace company={COMPANY} currency="INR" access={access} />);
  await user.click(await screen.findByRole('button', { name: 'Add verified allocation' }));
  fireEvent.change(screen.getByLabelText('Reason for worksheet change'), {
    target: { value: 'My new allocation' },
  });
  await user.click(screen.getByRole('button', { name: 'Review and save worksheet' }));
  await user.click(screen.getByRole('button', { name: 'Confirm' }));
  await user.click(await screen.findByRole('button', { name: 'Reload and review latest state' }));
  await waitFor(() => expect(api.mock.calls.some(([, request]) => request.path.endsWith('/manifest'))).toBe(true));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Review and save worksheet' })).toBeEnabled());
  // Reloading does not silently adopt the competing worksheet's version/hash.
  await user.click(screen.getByRole('button', { name: 'Review and save worksheet' }));
  await user.click(screen.getByRole('button', { name: 'Confirm' }));
  await screen.findByText(/The worksheet changed while you were editing/);
  expect(writes).toHaveLength(1);
  expect(screen.getByRole('textbox', { name: 'Reason for worksheet change' })).toHaveValue('My new allocation');
  // Explicitly discard the local worksheet, inspect the other allocation, then append.
  await user.click(screen.getByRole('button', { name: 'Discard worksheet changes' }));
  expect(await screen.findByRole('cell', { name: '12.50' })).toBeVisible();
  await user.click(screen.getByRole('button', { name: 'Add verified allocation' }));
  await user.click(screen.getByRole('button', { name: 'Review and save worksheet' }));
  await user.click(screen.getByRole('button', { name: 'Confirm' }));
  await waitFor(() => expect(writes).toHaveLength(2));
  expect(writes[1]!.path).toContain('/replace');
  expect(writes[1]!.body).toMatchObject({
    expected_version: control.expected_version,
    manifest_hash: control.manifest_hash,
  });
  const replacement = writes[1]!.body as { manifest: typeof manifest };
  expect(replacement.manifest.lines!.map((line) => line.opening!.source_key)).toEqual(['opening-a', 'opening-b']);
});

it.each(['BOOKS_BEGIN_PERIOD_NOT_OPEN', 'LATER_BOOKS_CLOSED', 'EXECUTION_UNCONFIRMED'])(
  'blocks legacy adoption while the owner reports %s', async (blocker) => {
    const original = api.getMockImplementation()!;
    api.mockImplementation(async (...args) => {
      if (args[1].path.endsWith('/readiness'))
        return { ...readiness, control_id: null, status: 'LEGACY_ACTIVITY',
          blockers: ['LEGACY_ACTIVITY_REQUIRES_REVIEW', blocker] } as never;
      return original(...args);
    });
    const user = userEvent.setup();
    render(<OpeningStockWorkspace company={COMPANY} currency="INR" access={access} />);
    await user.click(await screen.findByRole('button', { name: 'Reconcile and complete' }));
    fireEvent.change(screen.getByLabelText('Completion or correction reason'), {
      target: { value: 'Reviewed legacy opening history' },
    });
    expect(screen.getByRole('button', { name: 'Review and adopt existing stock history' })).toBeDisabled();
  },
);
