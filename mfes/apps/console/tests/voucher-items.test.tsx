import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {useState} from 'react';
import type {components} from '@janso/api-client/vouchers';
import {VoucherItems} from '../app/components/VoucherItems';
import {VoucherRelated} from '../app/components/VoucherRelated';
import {VoucherFulfillment,initialFulfillmentTerms} from '../app/components/VoucherFulfillment';
import type {FieldSet} from '../app/lib/voucher-fields';
import {productFieldRequest as request} from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields',()=>({productFieldRequest:vi.fn()}));
vi.mock('@janso/ui',async original=>({...await original<typeof import('@janso/ui')>(),SearchSelect:({label,disabled}:{label:string;disabled:boolean})=><input aria-label={label} disabled={disabled}/>}));
const metadata={native:{properties:{lines:{items:{properties:{description:{},item:{properties:{item_id:{},unit_id:{},actual_quantity:{},billed_quantity:{readOnly:true}}}}}},parties:{},references:{}}},custom:[],configuration:{type_revision_id:'type',policy:{max_lines:1,max_parties:1,allowed_party_roles:['SUPPLIER'],forbidden_sections:[]}}} as unknown as FieldSet;
it('preserves exact quantities, read restrictions, line identity and configured limits',()=>{
 function Form(){const [lines,setLines]=useState<components['schemas']['LineInput'][]>([]);return <><VoucherItems company="company" currency="INR" metadata={metadata} lines={lines} onChange={setLines} disabled={false}/><output data-testid="value">{JSON.stringify(lines)}</output></>;}
 render(<Form/>);fireEvent.click(screen.getByRole('button',{name:'Add item'}));expect(screen.getByRole('button',{name:'Add item'})).toBeDisabled();
 const key=JSON.parse(screen.getByTestId('value').textContent!)[0].line_key;
 fireEvent.change(screen.getByLabelText('Actual quantity 1'),{target:{value:'10.0001'}});expect(screen.getByLabelText('Billed quantity 1')).toBeDisabled();
 const line=JSON.parse(screen.getByTestId('value').textContent!)[0];expect(line.line_key).toBe(key);expect(line.item.actual_quantity).toBe('10.0001');
 fireEvent.click(screen.getByRole('button',{name:'Remove item 1'}));expect(screen.getByRole('button',{name:'Add item'})).not.toBeDisabled();
});
it('does not offer a forbidden item section',()=>{render(<VoucherItems company="company" currency="INR" metadata={{...metadata,configuration:{...metadata.configuration,policy:{...metadata.configuration.policy,forbidden_sections:['ITEMS']}}}} lines={[]} onChange={vi.fn()} disabled={false}/>);expect(screen.queryByRole('button',{name:'Add item'})).not.toBeInTheDocument();});
it('captures planned order units while actual and billed units remain zero',()=>{
 const order={...metadata,native:{properties:{lines:{items:{properties:{description:{},item:{properties:{item_id:{},unit_id:{},actual_quantity:{},billed_quantity:{},planned_quantity:{}}}}}}}},configuration:{...metadata.configuration,kind:'SALES_ORDER',profile:'QUOTATION'}} as unknown as FieldSet;
 function Form(){const [lines,setLines]=useState<components['schemas']['LineInput'][]>([]);return <><VoucherItems company="company" currency="INR" metadata={order} lines={lines} onChange={setLines} disabled={false}/><output data-testid="order-lines">{JSON.stringify(lines)}</output></>;}
 render(<Form/>);fireEvent.click(screen.getByRole('button',{name:'Add item'}));
 expect(screen.queryByLabelText('Actual quantity 1')).not.toBeInTheDocument();
 expect(screen.queryByLabelText('Billed quantity 1')).not.toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Planned quantity 1'),{target:{value:'10.0001'}});
 const item=JSON.parse(screen.getByTestId('order-lines').textContent!)[0].item;
 expect(item).toMatchObject({planned_quantity:'10.0001',actual_quantity:'0',billed_quantity:'0'});
});
it('resolves a scanner value to the existing voucher item and unit contract',async()=>{
 vi.mocked(request).mockResolvedValueOnce({item_id:'item-1',item_version:7,unit_id:'unit-1',name:'Tea box',sku:'TEA-BOX',usage_role:'PACK',lot_hint:null,expiry_yymmdd_hint:null,serial_hint:null} as never);
 function Form(){const [lines,setLines]=useState<components['schemas']['LineInput'][]>([]);return <><VoucherItems company="company" currency="INR" metadata={metadata} lines={lines} onChange={setLines} disabled={false} asOf="2026-10-12" canScan/><output data-testid="scan-lines">{JSON.stringify(lines)}</output></>;}
 render(<Form/>);fireEvent.click(screen.getByRole('button',{name:'Add item'}));
 fireEvent.change(screen.getByLabelText('Scan barcode 1'),{target:{value:'CODE-1'}});
 fireEvent.click(screen.getByRole('button',{name:'Resolve barcode 1'}));
 await waitFor(()=>expect(JSON.parse(screen.getByTestId('scan-lines').textContent!)[0].item).toMatchObject({item_id:'item-1',item_version:7,unit_id:'unit-1'}));
 expect(request).toHaveBeenCalledWith('catalog','POST','/v1/companies/company/barcodes/resolve',{scan_value:'CODE-1',as_of:'2026-10-12'});
});
it('does not silently discard GS1 tracking data from a scan',async()=>{
 vi.mocked(request).mockResolvedValueOnce({item_id:'item-1',item_version:7,unit_id:'unit-1',name:'Medicine',sku:'MED',lot_hint:'LOT7',expiry_yymmdd_hint:null,serial_hint:null} as never);
 function Form(){const [lines,setLines]=useState<components['schemas']['LineInput'][]>([]);return <><VoucherItems company="company" currency="INR" metadata={metadata} lines={lines} onChange={setLines} disabled={false} asOf="2026-10-12" canScan/><output data-testid="scan-lines">{JSON.stringify(lines)}</output></>;}
 render(<Form/>);fireEvent.click(screen.getByRole('button',{name:'Add item'}));
 fireEvent.change(screen.getByLabelText('Scan barcode 1'),{target:{value:'GS1'}});
 fireEvent.click(screen.getByRole('button',{name:'Resolve barcode 1'}));
 await waitFor(()=>expect(screen.getByText(/this voucher form cannot record/i)).toBeInTheDocument());
 expect(JSON.parse(screen.getByTestId('scan-lines').textContent!)[0].item.item_id).toBe('');
});
it('refuses an alternate pack in physical entry before changing the current product',async()=>{
 vi.mocked(request).mockReset().mockResolvedValueOnce({item_id:'item-1',item_version:7,unit_id:'box',name:'Tea box',sku:'TEA',usage_role:'PACK',numerator:'12',denominator:'1'} as never);
 const physical={...metadata,configuration:{...metadata.configuration,kind:'RECEIPT_NOTE',profile:'STANDARD',policy:{stock:{}}}} as unknown as FieldSet;
 const onChange=vi.fn();
 render(<VoucherItems company="company" currency="INR" metadata={physical} lines={[{line_key:'line',line_kind:'ITEM',item:{item_id:'existing',item_version:2,unit_id:'pcs',actual_quantity:'3',billed_quantity:'0'}}]} onChange={onChange} disabled={false} asOf="2026-10-31" canScan/>);
 fireEvent.change(screen.getByLabelText('Scan barcode 1'),{target:{value:'PACK'}});
 fireEvent.click(screen.getByRole('button',{name:'Resolve barcode 1'}));
 await screen.findByText(/use its base-unit barcode/i);
 expect(onChange).not.toHaveBeenCalled();
});
it('rejects scanner whitespace instead of resolving a different code',async()=>{
 vi.mocked(request).mockClear();
 function Form(){const [lines,setLines]=useState<components['schemas']['LineInput'][]>([]);return <VoucherItems company="company" currency="INR" metadata={metadata} lines={lines} onChange={setLines} disabled={false} asOf="2026-10-12" canScan/>;}
 render(<Form/>);fireEvent.click(screen.getByRole('button',{name:'Add item'}));
 fireEvent.change(screen.getByLabelText('Scan barcode 1'),{target:{value:' CODE-1'}});
 fireEvent.click(screen.getByRole('button',{name:'Resolve barcode 1'}));
 await waitFor(()=>expect(screen.getByText(/leading or trailing whitespace/i)).toBeInTheDocument());
 expect(request).not.toHaveBeenCalled();
});
it('adds configured party and reference input without inventing a ledger',()=>{
 const parties=vi.fn(),references=vi.fn();render(<VoucherRelated company="company" metadata={metadata} parties={[]} references={[]} onParties={parties} onReferences={references} disabled={false}/>);
 fireEvent.click(screen.getByRole('button',{name:'Add party'}));expect(parties).toHaveBeenCalledWith([{role:'SUPPLIER',party_id:'',source_version:0}]);
 fireEvent.click(screen.getByRole('button',{name:'Add reference'}));expect(references).toHaveBeenCalledWith([{purpose:'EXTERNAL',reference:''}]);
});
it('uses typed quotation terms and does not offer them for other kinds',()=>{
 const quote={...metadata,native:{properties:{fulfillment_terms:{}}},configuration:{...metadata.configuration,kind:'SALES_ORDER',profile:'QUOTATION'}} as unknown as FieldSet;
 expect(initialFulfillmentTerms(metadata)).toBeNull();
 function Form(){const [terms,setTerms]=useState(initialFulfillmentTerms(quote));return <><VoucherFulfillment metadata={quote} value={terms} onChange={setTerms} disabled={false}/><output data-testid="terms">{JSON.stringify(terms)}</output></>;}
 render(<Form/>);fireEvent.change(screen.getByLabelText('Quote valid until'),{target:{value:'2026-04-30'}});
 expect(JSON.parse(screen.getByTestId('terms').textContent!)).toMatchObject({purpose:'QUOTE',valid_until:'2026-04-30'});
});
