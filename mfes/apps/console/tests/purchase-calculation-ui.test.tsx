import {useState} from 'react';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
import {PurchaseCalculationPresetsEditor} from '../app/components/PurchaseCalculationPresetsEditor';
import {PurchaseCalculationPicker} from '../app/components/PurchaseCalculationPicker';
import {VoucherTypeRulesEditor} from '../app/components/VoucherTypeRulesEditor';
import {componentsFromPreset,purchaseCalculationStarters,type PurchaseCalculationPolicy} from '../app/lib/purchase-calculation';
import {serviceCall} from '../app/lib/service-call';
import {COMPANY,RETAIL,detail,fullPolicy,service,writes} from './voucher-type-fixtures';

vi.mock('../app/lib/service-call',async original=>({...await original<typeof import('../app/lib/service-call')>(),serviceCall:vi.fn()}));
vi.mock('../app/lib/navigate',()=>({goTo:vi.fn()}));
beforeEach(()=>{vi.mocked(serviceCall).mockReset();});
const policy=():PurchaseCalculationPolicy=>({presets:[structuredClone(purchaseCalculationStarters[1]!)],default_preset:'sequential'});
function Editor(){const [value,setValue]=useState<PurchaseCalculationPolicy>({presets:[],default_preset:null});return <PurchaseCalculationPresetsEditor value={value} onChange={setValue}/>;}

it('adds a starter, selects a default, previews its amounts and validates edited values',()=>{
 render(<Editor/>);
 fireEvent.change(screen.getByLabelText('Starting recipe'),{target:{value:'sequential'}});
 fireEvent.click(screen.getByRole('button',{name:'Add calculation formula'}));
 fireEvent.change(screen.getByLabelText('Default calculation formula'),{target:{value:'sequential-1'}});
 expect(screen.getByLabelText('Default calculation formula')).toHaveValue('sequential-1');
 expect(screen.getByText(/1008.90|1,008.90/)).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText('Two-stage trade discount step 2 value (%)'),{target:{value:'101'}});
 expect(screen.getByText(/percentages cannot exceed 100/)).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Remove formula Two-stage trade discount'}));
 expect(screen.getByLabelText('Default calculation formula')).toHaveValue('');
});

it('requires confirmation before replacing bill steps and respects read-only access',()=>{
 const onApply=vi.fn(),value=policy();
 const {rerender}=render(<PurchaseCalculationPicker policy={value} components={[{...componentsFromPreset(value.presets[0]!)[0]!,value:'3'}]} onApply={onApply}/>);
 fireEvent.click(screen.getByRole('button',{name:'Apply calculation formula'}));
 expect(screen.getByRole('dialog')).toHaveAccessibleName('Replace discount and charge steps?');
 expect(onApply).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Keep current steps'}));
 expect(onApply).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole('button',{name:'Apply calculation formula'}));
 fireEvent.click(screen.getByRole('button',{name:'Apply formula'}));
 expect(onApply).toHaveBeenCalledWith(componentsFromPreset(value.presets[0]!));
 rerender(<PurchaseCalculationPicker policy={value} components={[]} disabled onApply={onApply}/>);
 expect(screen.getByLabelText('Calculation formula')).toBeDisabled();
 expect(screen.getByRole('button',{name:'Apply calculation formula'})).toBeDisabled();
});

it('retains a saved formula removed from current configuration without changing its steps',()=>{
 const onApply=vi.fn();
 render(<PurchaseCalculationPicker policy={{presets:[purchaseCalculationStarters[0]!],default_preset:'standard'}} components={componentsFromPreset(purchaseCalculationStarters[1]!)} onApply={onApply}/>);
 expect(screen.getByLabelText('Calculation formula')).toHaveValue('sequential');
 expect(screen.getByRole('option',{name:'Saved bill formula'})).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Apply calculation formula'})).toBeDisabled();
 expect(onApply).not.toHaveBeenCalled();
});

it('saves the formula through the existing versioned type API, preserving other invoice rules',async()=>{
 vi.mocked(serviceCall).mockImplementation(service({one:detail({kind:'PURCHASE',policy:{...fullPolicy,invoice:{manual_discounts_allowed:true,max_components:7}}})}));
 render(<VoucherTypeRulesEditor company={COMPANY} id={RETAIL}/>);
 fireEvent.change(await screen.findByLabelText('Starting recipe'),{target:{value:'sequential'}});
 fireEvent.click(screen.getByRole('button',{name:'Add calculation formula'}));
 fireEvent.change(screen.getByLabelText('Default calculation formula'),{target:{value:'sequential-1'}});
 fireEvent.click(screen.getByRole('button',{name:'Save as revision 3'}));
 await waitFor(()=>expect(writes()).toHaveLength(1));
 expect(writes()[0]![1].body).toMatchObject({expected_version:3,policy:{invoice:{manual_discounts_allowed:true,max_components:7},purchase_calculation:{default_preset:'sequential-1',presets:[{key:'sequential-1',steps:[{value:'10'},{value:'5'}]}]}}});
});

it('blocks formulas excluded by invoice permissions until the entry rules allow them',async()=>{
 vi.mocked(serviceCall).mockImplementation(service({one:detail({kind:'PURCHASE',policy:{...fullPolicy,invoice:{}}})}));
 render(<VoucherTypeRulesEditor company={COMPANY} id={RETAIL}/>);
 fireEvent.change(await screen.findByLabelText('Starting recipe'),{target:{value:'sequential'}});
 fireEvent.click(screen.getByRole('button',{name:'Add calculation formula'}));
 expect(screen.getByText('Allow Purchase discounts before adding discount steps.')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Save as revision 3'}));
 expect(writes()).toHaveLength(0);
 fireEvent.click(screen.getByRole('checkbox',{name:'Allow Purchase discounts'}));
 fireEvent.click(screen.getByRole('button',{name:'Save as revision 3'}));
 await waitFor(()=>expect(writes()).toHaveLength(1));
});
