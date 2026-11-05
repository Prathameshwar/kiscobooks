import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {Gstr3bWorkspace} from '../app/components/Gstr3bWorkspace';
import {productFieldRequest} from '../app/lib/product-fields';

vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
const company='01990000-0000-7000-8000-000000000001', registration='01990000-0000-7000-8000-000000000002';
let applicable=true,canConfigure=true,externallyFiled=false,ready=false,canReview=false,legacy=false,unpaid=false,configured=true,preferenceFrom='2026-04-01';
beforeEach(()=>{
 applicable=true;canConfigure=true;externallyFiled=false;ready=false;canReview=false;legacy=false;unpaid=false;configured=true;preferenceFrom='2026-04-01';vi.restoreAllMocks();
 vi.mocked(productFieldRequest).mockReset();
 vi.mocked(productFieldRequest).mockImplementation(async(service,method,path,body)=>{
  if(path.endsWith('/gst-return-context'))return {calculation_version:1,registrations:applicable?[{id:registration,number:'27ABCDE1234F1Z5',legal_name:'Example GST',filing_preferences:configured?[{frequency:'MONTHLY',valid_from:preferenceFrom,valid_to:null}]:[]}]:[],can_configure:canConfigure,can_capture:false,can_review:canReview,can_prepare:canConfigure,rule_version:'GSTR3B_2025_10'};
  if(path.endsWith('/report-definitions'))return {items:applicable?[{definition:{code:'GSTR3B'},run_enabled:true,formats:['PDF','CSV','XLSX']}]:[]};
  if(path.includes('/report-generations?'))return {items:[{id:company,status:'READY'}]};
  if(path.includes('/report-runs?'))return {items:[],page:{next_cursor:null}};
  if(path.endsWith('/gst-review'))return {items:externallyFiled?[{state:'EXTERNALLY_FILED'}]:[]};
  if(service==='identity'&&method==='POST')return {id:company,...body as object};
  if(method==='POST'&&path.endsWith('/report-runs'))return {id:company,status:'COMPLETE',result:{evidence:{gstr3b:{calculation_version:legacy?0:1,registration:{number:'27ABCDE1234F1Z5'},date_from:'2026-10-01',date_to:'2026-10-31',financial_year:'2026-27',status:'NEEDS_ATTENTION',nil:false,form:{'3.1a':{taxable:'1000.00',igst:'180.00',cgst:'0.00',sgst:'0.00',cess:'0.00'}},labels:{'3.1a':'Outward taxable supplies'},issues:ready?[]:[{code:'SOURCE_COVERAGE',message:'Payment completeness evidence is missing.'}],source_count:1,pos_rows:[],payment:{IGST:{normal_unpaid:unpaid?'180.00':'0.00'}},reconciliation:[],portal_json_reason:'Portal upload is not verified.'}}}};
  if(path.includes('/gst-records?'))return {items:[],page:{next_cursor:null}};
  throw new Error('Unexpected '+path);
 });
});
it('uses a statutory month and requires GSTIN, period and source before preparation',async()=>{
 render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 const month=await screen.findByLabelText('Return month');
 expect(screen.getByRole('link',{name:'Company GST settings'})).toHaveAttribute('href','/companies/'+company+'/gst-settings');
 expect(month).toHaveAttribute('type','month');
 expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeDisabled();
 fireEvent.change(month,{target:{value:'2026-10'}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Prepare GSTR-3B'}));
 await screen.findByText('Payment completeness evidence is missing.');
 expect(screen.getByRole('table',{name:'Table 3.1 — amounts in INR'})).toHaveTextContent('1000.00');
 expect(screen.getByText(/NEEDS_ATTENTION/)).toHaveTextContent('Return with activity');
 fireEvent.click(screen.getByRole('button',{name:'Contributors for 3.1a Integrated tax'}));
 await screen.findByRole('button',{name:'Clear table filter (3.1a)'});
 await waitFor(()=>expect(vi.mocked(productFieldRequest).mock.calls.some(call=>call[2].includes('category=3.1a'))).toBe(true));
 fireEvent.click(screen.getByRole('button',{name:'Columns'}));
 expect(screen.getByRole('menuitemcheckbox',{name:'Integrated tax'})).toBeInTheDocument();
 fireEvent.keyDown(screen.getByRole('menu'),{key:'Escape'});
 fireEvent.change(month,{target:{value:'2026-11'}});
 expect(screen.queryByRole('table',{name:'Table 3.1 — amounts in INR'})).not.toBeInTheDocument();
 expect(screen.queryByText('Payment completeness evidence is missing.')).not.toBeInTheDocument();
});
it('prevents preparing a displayed filed return again and allows selecting another period',async()=>{
 externallyFiled=true;
 render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 const month=await screen.findByLabelText('Return month');
 fireEvent.change(month,{target:{value:'2026-10'}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Prepare GSTR-3B'}));
 await screen.findByText(/EXTERNALLY_FILED/);
 expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeDisabled();
 fireEvent.change(month,{target:{value:'2026-11'}});
 expect(screen.queryByText(/EXTERNALLY_FILED/)).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeEnabled();
});
it('explains applicability and hides GST configuration when there is no supported GSTIN',async()=>{
 applicable=false;render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 await screen.findByText(/GSTR-3B requires an Indian GST registration/);
 expect(screen.queryByRole('button',{name:'Prepare GSTR-3B'})).not.toBeInTheDocument();
});
it('keeps setup and exports behind their current authorities',async()=>{
 canConfigure=false;render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 await screen.findByLabelText('GSTIN');
 expect(screen.queryByRole('button',{name:'GST filing setup'})).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Print / PDF'})).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Prepare GSTR-3B'})).not.toBeInTheDocument();
});
it('saves a dated filing preference through its native owner',async()=>{
 configured=false;
 render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 fireEvent.click(await screen.findByRole('button',{name:'GST filing setup'}));
 fireEvent.change(screen.getByLabelText('Effective from'),{target:{value:'2026-10-01'}});
 fireEvent.click(screen.getByRole('button',{name:'Save filing preference'}));
 await screen.findByText('GST filing preference saved.');
 expect(vi.mocked(productFieldRequest).mock.calls.some(call=>call[0]==='identity'&&call[1]==='POST'&&(call[3] as {valid_from?:string})?.valid_from==='2026-10-01')).toBe(true);
});
it('uses calendar quarter choices for QRMP and preserves complete statutory periods',async()=>{
 render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 await screen.findByLabelText('GSTIN');
 fireEvent.change(screen.getByLabelText('Filing frequency'),{target:{value:'QRMP'}});
 expect(screen.queryByLabelText('Return month')).not.toBeInTheDocument();
 expect(screen.getByRole('combobox',{name:'Return quarter'})).toHaveValue('4');
});

it('requires a dated filing preference before enabling preparation',async()=>{
 configured=false;
 render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 fireEvent.change(await screen.findByLabelText('Return month'),{target:{value:'2026-10'}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh'})).toBeEnabled());
 expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeDisabled();
});

it('clears the previous company return immediately when company selection changes',async()=>{
 const view=render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 fireEvent.change(await screen.findByLabelText('Return month'),{target:{value:'2026-10'}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Prepare GSTR-3B'}));
 await screen.findByText('Payment completeness evidence is missing.');
 await waitFor(()=>expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeEnabled());
 view.rerender(<Gstr3bWorkspace company="01990000-0000-7000-8000-000000000099" permissions={['report.read']}/>);
 expect(screen.queryByText('Payment completeness evidence is missing.')).not.toBeInTheDocument();
 expect(screen.queryByRole('table',{name:'Table 3.1 — amounts in INR'})).not.toBeInTheDocument();
 expect(screen.queryByLabelText('Return month')).not.toBeInTheDocument();
 expect(await screen.findByLabelText('Return month')).toHaveValue('');
});

it('prevents new approval of a legacy GSTR-3B preparation',async()=>{
 ready=true;canReview=true;legacy=true;
 render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 fireEvent.change(await screen.findByLabelText('Return month'),{target:{value:'2026-10'}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Prepare GSTR-3B'}));
 await screen.findByText(/predates the final calculation review/);
 expect(screen.getByRole('button',{name:'Mark reviewed'})).toBeDisabled();
 expect(screen.getByRole('button',{name:'Record external filing'})).toBeDisabled();
});
it('requires liability offsets before recording GSTR-3B filing',async()=>{
 ready=true;canReview=true;unpaid=true;
 render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 fireEvent.change(await screen.findByLabelText('Return month'),{target:{value:'2026-10'}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Prepare GSTR-3B'}));
 await screen.findByRole('button',{name:'Mark reviewed'});
 expect(await screen.findByText(/liabilities must be fully offset/)).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Record external filing'})).toBeDisabled();
});
it('clears the previous proof when an invalid replacement file is selected',async()=>{
 ready=true;canReview=true;
 vi.spyOn(crypto.subtle,'digest').mockResolvedValue(new Uint8Array(32).fill(170).buffer);
 render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 fireEvent.change(await screen.findByLabelText('Return month'),{target:{value:'2026-10'}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Prepare GSTR-3B'}));
 await screen.findByRole('button',{name:'Mark reviewed'});
 fireEvent.change(screen.getByLabelText('Review / portal acknowledgement reference'),{target:{value:'Verified proof'}});
 const valid=Object.assign(new File(['proof'],'proof.pdf'),{arrayBuffer:async()=>new ArrayBuffer(4)});
 fireEvent.change(screen.getByLabelText('Review / filing evidence file'),{target:{files:[valid]}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Mark reviewed'})).toBeEnabled());
 const invalid=new File(['invalid'],'too-large.pdf');Object.defineProperty(invalid,'size',{value:11*1024*1024});
 fireEvent.change(screen.getByLabelText('Review / filing evidence file'),{target:{files:[invalid]}});
 await screen.findByText('Choose evidence up to 10 MB.');
 expect(screen.getByRole('button',{name:'Mark reviewed'})).toBeDisabled();
 expect(screen.queryByText(/Evidence: proof.pdf/)).not.toBeInTheDocument();
});

it('requires the dated preference to cover the selected period',async()=>{
 preferenceFrom='2026-11-01';
 render(<Gstr3bWorkspace company={company} permissions={['report.read']}/>);
 fireEvent.change(await screen.findByLabelText('Return month'),{target:{value:'2026-10'}});
 await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh'})).toBeEnabled());
 expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeDisabled();
 expect(screen.getByText(/must cover the complete selected return period/)).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Return month'),{target:{value:'2026-11'}});
 expect(screen.getByRole('button',{name:'Prepare GSTR-3B'})).toBeEnabled();
});
