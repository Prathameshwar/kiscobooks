import { readFileSync } from 'node:fs';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CustomFields } from '../src/components/CustomFields';
import { CustomFieldEditor } from '../src/components/CustomFieldEditor';

it('places field definition controls in a form card with an inline cancel footer', () => {
  render(<CustomFieldEditor sources={[]} fields={[]} currencies={['INR']} busy={false} onSave={vi.fn()} onCancel={vi.fn()}/>);
  const save = screen.getByRole('button', { name: 'Save candidate' });
  expect(save.closest('.janso-card__footer')).not.toBeNull();
  expect(save.closest('form')?.querySelector('.janso-card__body')).not.toBeNull();
});
import { customCondition, customPatch, customValue, type CustomDefinition, type CustomField } from '../src/lib/custom-fields';
const definition = (kind='text'): CustomDefinition => ({key:'cf_note',data_type:kind,is_active:true,is_immutable_after_create:false,validation:{required:false,max_length:512},choices:[]});
const field = (kind='text'): CustomField => ({key:'cf_note',source:'custom',label:'Note',visible:true,required:false,writable:true,custom:definition(kind)});
const rule = (cmp:string,value?:unknown) => ({field:'cf_note',cmp,value});
describe('custom conditions and exact values',() => {
  it.each(['eq','gte','lte','in'])('normalizes decimal %s without binary floating point',cmp => {
    expect(customCondition(rule(cmp,cmp === 'in' ? ['1.00']:'1'),{cf_note:'1.0000'},new Set(['cf_note']))).toBe(true);
  });
  it.each([['ne','2'],['gt','0.99'],['lt','2'],['not_in',['2']],['not_empty',null]])('supports %s', (cmp,value) => {
    expect(customCondition(rule(String(cmp),value),{cf_note:'1.0000'},new Set(['cf_note']))).toBe(true);
  });
  it('handles empty, missing, strict booleans and invalid comparisons',() => {
    expect(customCondition(rule('empty'),{cf_note:[]})).toBe(true);
    expect(customCondition(rule('eq',true),{cf_note:'true'})).toBe(false);
    expect(customCondition(rule('gt','bad'),{cf_note:'1'},new Set(['cf_note']))).toBe(false);
    expect(customCondition(rule('eq','value'),{})).toBe(false);
    expect(customCondition(rule('matches','a+'),{cf_note:'a'})).toBe(false);
    expect(customCondition(rule('matches','[a-z]{2}'),{cf_note:'ab'})).toBe(true);
    expect(customCondition({op:'and',rules:[rule('not_empty'),rule('ne','other')]},{cf_note:'yes'})).toBe(true);
    expect(customCondition({op:'or',rules:[rule('empty'),rule('eq','yes')]},{cf_note:'yes'})).toBe(true);
  });
  it('keeps decimal strings and only authors changed writable fields',() => {
    expect(customValue(definition('integer'),'7')).toBe(7);
    expect(() => customValue(definition('integer'),'9007199254740993')).toThrow();
    expect(customValue(definition('decimal'),'1.2500')).toBe('1.2500');
    expect(customPatch([field()],{cf_note:'same'},{cf_note:'same'})).toEqual({});
    expect(customPatch([field()],{cf_note:''},{cf_note:'old'})).toEqual({cf_note:null});
    expect(customPatch([{...field(),writable:false}],{cf_note:'new'},{})).toEqual({});
  });
});
describe('metadata controls',() => {
  it('writes text, displays field errors and keeps retired history disabled',() => {
    const change=vi.fn();const {rerender}=render(<CustomFields fields={[field()]} values={{cf_note:'old'}} onChange={change} errors={{'custom_fields.cf_note':'Required'}} />);
    fireEvent.change(screen.getByLabelText('Note'),{target:{value:'new'}});expect(change).toHaveBeenCalledWith({cf_note:'new'});
    expect(screen.getByRole('alert')).toHaveTextContent('Required');
    rerender(<CustomFields fields={[{...field(),visible:false,custom:{...definition(),is_active:false}}]} values={{cf_note:'old'}} onChange={change}/>);
    expect(screen.getByLabelText('Note')).toBeDisabled();expect(screen.getByLabelText('Note')).toHaveValue('old');
  });
  it('uses create defaults and update immutability independently',() => {
    const f={...field(),custom:{...definition(),default_value:'suggested',is_immutable_after_create:true}};
    const {rerender}=render(<CustomFields fields={[f]} values={{}} creating onChange={vi.fn()}/>);
    expect(screen.getByLabelText('Note')).toHaveValue('suggested');expect(screen.getByLabelText('Note')).not.toBeDisabled();
    rerender(<CustomFields fields={[f]} values={{}} onChange={vi.fn()}/>);expect(screen.getByLabelText('Note')).toBeDisabled();expect(screen.getByLabelText('Note')).toHaveValue('');
  });
  it('hides conditional fields and clears dependent choices when their parent changes',() => {
    const change=vi.fn();const child={...field(),key:'cf_child',label:'Child',custom:{...definition(),key:'cf_child',depends_on_key:'cf_note'}};
    const hidden={...field(),key:'cf_hidden',custom:{...definition(),key:'cf_hidden',visibility:{field:'cf_note',cmp:'eq',value:'hidden'}}};
    render(<CustomFields fields={[field(),child,hidden]} values={{cf_note:'old',cf_child:'saved'}} onChange={change}/>);
    expect(screen.getAllByLabelText('Note')).toHaveLength(1);fireEvent.change(screen.getByLabelText('Note'),{target:{value:'new'}});
    expect(change).toHaveBeenCalledWith({cf_note:'new',cf_child:null});
  });
  it.each(['integer','decimal','date','datetime','long_text','auto_number'])('renders %s values',kind => {
    render(<CustomFields fields={[field(kind)]} values={{cf_note:kind === 'date' ? '2026-09-15':'value'}} onChange={vi.fn()}/>);
    expect(screen.getByLabelText('Note')).toBeInTheDocument();
  });
  it('boolean choices preserve false',() => {const change=vi.fn();render(<CustomFields fields={[field('boolean')]} values={{cf_note:true}} onChange={change}/>);
    fireEvent.change(screen.getByLabelText('Note'),{target:{value:'false'}});expect(change).toHaveBeenCalledWith({cf_note:false});});
  it('currency amount keeps an exact string and registered currency',() => {const change=vi.fn();render(<CustomFields fields={[field('currency_amount')]} currencies={['INR','USD']} values={{cf_note:{amount:'2.50',currency:'INR'}}} onChange={change}/>);
    fireEvent.change(screen.getByLabelText('Note amount'),{target:{value:'3.1250'}});expect(change).toHaveBeenCalledWith({cf_note:{amount:'3.1250',currency:'INR'}});});
  it('keeps inactive static selections and disables new selections',() => {const f={...field('select'),custom:{...definition('select'),choices:[{value:'red',label:'Red',is_active:false}]}};
    render(<CustomFields fields={[f]} values={{cf_note:'red'}} onChange={vi.fn()}/>);expect(screen.getByLabelText('Note')).toHaveValue('red');expect(screen.getByRole('option',{name:'Red'})).toBeDisabled();});
  it('requires a parent and loader for dynamic choices',() => {const f={...field('dynamic_select'),custom:{...definition('dynamic_select'),option_source_key:'catalog.item_categories',depends_on_key:'cf_parent'}};
    render(<CustomFields fields={[f]} values={{}} onChange={vi.fn()}/>);expect(screen.getByRole('combobox')).toBeDisabled();});
  it('creates a definition and reports save failures',async () => {
    const save=vi.fn().mockRejectedValue(new Error('Conflict'));
    render(<CustomFieldEditor sources={[]} fields={[]} currencies={['INR']} busy={false} onSave={save} onCancel={vi.fn()}/>);
    fireEvent.change(screen.getByLabelText('Field label'),{target:{value:'Note'}});fireEvent.change(screen.getByLabelText('Stable field key'),{target:{value:'cf_note'}});
    fireEvent.submit(screen.getByRole('button',{name:'Save candidate'}).closest('form')!);
    expect(await screen.findByRole('alert')).toHaveTextContent('Conflict');expect(save).toHaveBeenCalled();
  });
});


it('evaluates negated and missing-value conditions like the owner',() => {
  expect(customCondition({op:'not',rules:[rule('eq','no')]},{cf_note:'yes'})).toBe(true);
  expect(customCondition(rule('ne','value'),{})).toBe(true);
  expect(customCondition(rule('eq',null),{})).toBe(true);
});
it('uses displayed create defaults in visibility conditions',() => {
  const parent={...field('boolean'),custom:{...definition('boolean'),default_value:true}};
  const child={...field(),key:'cf_child',label:'Required child',custom:{...definition(),key:'cf_child',visibility:{field:'cf_note',cmp:'eq',value:true}}};
  render(<CustomFields fields={[parent,child]} creating values={{}} onChange={vi.fn()}/>);
  expect(screen.getByLabelText('Required child')).toBeInTheDocument();
});


it('normalizes equivalent native timestamps without dropping microseconds',() => {
  expect(customCondition({field:'created_at',cmp:'eq',value:'2026-09-15T08:30:00.123456+05:30'},{created_at:'2026-09-15T03:00:00.123456Z'})).toBe(true);
  expect(customCondition({field:'created_at',cmp:'eq',value:'2026-09-15T03:00:00.123457Z'},{created_at:'2026-09-15T03:00:00.123456Z'})).toBe(false);
});


it('authors a bounded searchable text field with conditional requiredness',async () => {
  const save=vi.fn().mockResolvedValue(undefined);
  render(<CustomFieldEditor sources={[]} fields={[{key:'sellable',label:'Sellable'}]} currencies={['INR']} busy={false} onSave={save} onCancel={vi.fn()}/>);
  const enter=(label:string,value:string)=>fireEvent.change(screen.getByLabelText(label),{target:{value}});
  enter('Field label','Compliance note');enter('Stable field key','cf_compliance');enter('Help text','Enter the certificate number');
  enter('Available for new values','no');enter('Required','yes');enter('Lock after product creation','yes');enter('Searchable','yes');enter('Unique value','company');enter('Case sensitive','no');
  enter('Maximum characters','20');enter('Validation pattern','[A-Z]{2}');enter('Pattern error message','Use two capitals');
  enter('Show field when','sellable');enter('Comparison','ne');enter('Compared value','false');enter('Default for new products','AB');
  fireEvent.submit(screen.getByRole('button',{name:'Save candidate'}).closest('form')!);
  await waitForSave(save);
  expect(save.mock.calls[0]?.[0]).toMatchObject({label:'Compliance note',help_text:'Enter the certificate number',definition:{key:'cf_compliance',is_active:false,is_searchable:true,is_immutable_after_create:true,default_value:'AB',visibility:{field:'sellable',cmp:'ne',value:false},validation:{required:true,max_length:20,regex:'[A-Z]{2}',regex_message:'Use two capitals',unique_within:'company',case_sensitive:false}}});
});
async function waitForSave(save: ReturnType<typeof vi.fn>) { await Promise.resolve();expect(save).toHaveBeenCalledOnce(); }
it('authors numeric limits and calendar sequence configuration',async () => {
  const save=vi.fn().mockResolvedValue(undefined),cancel=vi.fn();
  const {rerender}=render(<CustomFieldEditor sources={[]} fields={[]} currencies={[]} busy={false} onSave={save} onCancel={cancel}/>);
  fireEvent.change(screen.getByLabelText('Value type'),{target:{value:'decimal'}});
  fireEvent.change(screen.getByLabelText('Minimum value'),{target:{value:'1.25'}});fireEvent.change(screen.getByLabelText('Maximum value'),{target:{value:'10.25'}});
  fireEvent.change(screen.getByLabelText('Default for new products'),{target:{value:'2.50'}});
  fireEvent.submit(screen.getByRole('button',{name:'Save candidate'}).closest('form')!);await waitForSave(save);
  expect(save.mock.calls[0]?.[0].definition).toMatchObject({data_type:'decimal',default_value:'2.50',validation:{min:'1.25',max:'10.25'}});
  save.mockClear();fireEvent.change(screen.getByLabelText('Value type'),{target:{value:'auto_number'}});
  fireEvent.change(screen.getByLabelText('Prefix'),{target:{value:'SKU-'}});fireEvent.change(screen.getByLabelText('Starting number'),{target:{value:'5'}});
  fireEvent.change(screen.getByLabelText('Minimum digits'),{target:{value:'4'}});fireEvent.change(screen.getByLabelText('Reset numbering'),{target:{value:'month'}});
  fireEvent.submit(screen.getByRole('button',{name:'Save candidate'}).closest('form')!);await waitForSave(save);
  expect(save.mock.calls[0]?.[0].definition.sequence_config).toEqual({prefix:'SKU-',start:5,padding:4,reset:'month'});
  fireEvent.click(screen.getByRole('button',{name:'Cancel'}));expect(cancel).toHaveBeenCalledOnce();
  rerender(<CustomFieldEditor sources={[]} fields={[]} currencies={[]} busy onSave={save} onCancel={cancel}/>);expect(screen.getByLabelText('Prefix')).toBeDisabled();
});
it('keeps option identities stable while relabelling and retiring choices',async () => {
  const save=vi.fn().mockResolvedValue(undefined);
  render(<CustomFieldEditor initial={{label:'Colour',help_text:null,definition:{...definition('select'),choices:[{value:'red',label:'Red',is_active:true}]}}} sources={[]} fields={[]} currencies={[]} busy={false} onSave={save} onCancel={vi.fn()}/>);
  expect(screen.getByLabelText('Stable field key')).toBeDisabled();expect(screen.getByLabelText('Option 1 key')).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Option 1 label'),{target:{value:'Old red'}});fireEvent.change(screen.getByLabelText('Option 1 active'),{target:{value:'no'}});
  fireEvent.click(screen.getByRole('button',{name:'Add option'}));fireEvent.change(screen.getByLabelText('Option 2 key'),{target:{value:'blue'}});fireEvent.change(screen.getByLabelText('Option 2 label'),{target:{value:'Blue'}});
  fireEvent.submit(screen.getByRole('button',{name:'Save candidate'}).closest('form')!);await waitForSave(save);
  expect(save.mock.calls[0]?.[0].definition.choices).toEqual([{value:'red',label:'Old red',is_active:false},{value:'blue',label:'Blue',is_active:true}]);
});
it('configures a registered dependent option source and removes visibility explicitly',async () => {
  const save=vi.fn().mockResolvedValue(undefined);
  render(<CustomFieldEditor sources={['catalog.item_categories']} fields={[{key:'cf_scheme',label:'Scheme'}]} currencies={[]} busy={false} onSave={save} onCancel={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText('Value type'),{target:{value:'dynamic_select'}});fireEvent.change(screen.getByLabelText('Option source'),{target:{value:'catalog.item_categories'}});
  fireEvent.change(screen.getByLabelText('Parent reference field'),{target:{value:'cf_scheme'}});fireEvent.change(screen.getByLabelText('Show field when'),{target:{value:'cf_scheme'}});
  fireEvent.change(screen.getByLabelText('Comparison'),{target:{value:'not_empty'}});fireEvent.change(screen.getByLabelText('Show field when'),{target:{value:''}});
  fireEvent.submit(screen.getByRole('button',{name:'Save candidate'}).closest('form')!);await waitForSave(save);
  expect(save.mock.calls[0]?.[0].definition).toMatchObject({data_type:'dynamic_select',option_source_key:'catalog.item_categories',depends_on_key:'cf_scheme',visibility:null});
});
it('edits multiline content, currency, and static selections',async () => {
  const change=vi.fn();const {rerender}=render(<CustomFields fields={[field('long_text')]} values={{cf_note:'old'}} errors={{cf_note:'Check text'}} onChange={change}/>);
  fireEvent.change(screen.getByLabelText('Note'),{target:{value:'Line 1\nLine 2'}});expect(change).toHaveBeenLastCalledWith({cf_note:'Line 1\nLine 2'});
  rerender(<CustomFields fields={[field('currency_amount')]} values={{}} currencies={['INR','USD']} onChange={change}/>);
  fireEvent.change(screen.getByLabelText('Note currency'),{target:{value:'USD'}});expect(change).toHaveBeenLastCalledWith({cf_note:{amount:'',currency:'USD'}});
  const options={...definition('select'),choices:[{value:'red',label:'Red',is_active:true}]};
  rerender(<CustomFields fields={[{...field('select'),custom:options}]} values={{}} onChange={change}/>);
  fireEvent.change(screen.getByLabelText('Note'),{target:{value:'red'}});expect(change).toHaveBeenLastCalledWith({cf_note:'red'});
  rerender(<CustomFields fields={[{...field('multi_select'),custom:{...options,data_type:'multi_select'}}]} values={{cf_note:[]}} onChange={change}/>);
  fireEvent.keyDown(screen.getByRole('combobox'),{key:'ArrowDown'});fireEvent.click(await screen.findByRole('option',{name:'Red'}));expect(change).toHaveBeenLastCalledWith({cf_note:['red']});
});
it('loads and saves a dynamic selection after its parent is available',async () => {
  const change=vi.fn(),loader=vi.fn().mockResolvedValue({items:[{id:'choice',label:'Category choice'}],nextCursor:null});
  const f={...field('dynamic_select'),custom:{...definition('dynamic_select'),option_source_key:'catalog.item_categories',depends_on_key:'cf_parent'}};
  render(<CustomFields fields={[f]} values={{cf_parent:'scheme'}} onChange={change} loadOptions={() => loader}/>);
  fireEvent.change(screen.getByRole('combobox'),{target:{value:'Cat'}});fireEvent.click(await screen.findByRole('option',{name:'Category choice'}));expect(change).toHaveBeenCalledWith({cf_parent:'scheme',cf_note:'choice'});
});


it('does not reinterpret custom text as a native UUID or timestamp',() => {
 const id='aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
 expect(customCondition(rule('eq',id.toUpperCase()),{cf_note:id})).toBe(false);
 expect(customCondition({field:'base_unit_id',cmp:'eq',value:id.toUpperCase()},{base_unit_id:id})).toBe(true);
 expect(customCondition({field:'base_unit_id',cmp:'ne',value:'invalid'},{base_unit_id:id})).toBe(false);
 expect(customCondition(rule('eq','2026-09-15T03:00:00Z'),{cf_note:'2026-09-15T03:00:00+00:00'})).toBe(false);
});

const sharedCases = JSON.parse(readFileSync('../../../libs/platform/tests/fixtures/custom-field-conditions.json','utf8')) as {name:string;rule:Record<string,unknown>;values:Record<string,unknown>;numeric:string[];expected:boolean}[];
it.each(sharedCases)('shared Python/TypeScript condition: $name',row => {
  expect(customCondition(row.rule,row.values,new Set(row.numeric))).toBe(row.expected);
});
it('clears an optional currency amount to null',() => {
  const onChange=vi.fn();render(<CustomFields fields={[field('currency_amount')]} values={{cf_note:{amount:'1.00',currency:'INR'}}} currencies={['INR']} onChange={onChange}/>);
  fireEvent.change(screen.getByLabelText('Note amount'),{target:{value:''}});expect(onChange).toHaveBeenCalledWith({cf_note:null});
});

it('authors string minimum length and currency precision/bounds',async () => {
  const save=vi.fn().mockResolvedValue(undefined);
  render(<CustomFieldEditor sources={[]} fields={[]} currencies={['INR']} busy={false} onSave={save} onCancel={vi.fn()}/>);
  fireEvent.change(screen.getByLabelText('Minimum characters'),{target:{value:'2'}});
  fireEvent.change(screen.getByLabelText('Value type'),{target:{value:'currency_amount'}});
  fireEvent.change(screen.getByLabelText('Decimal places'),{target:{value:'2'}});
  fireEvent.change(screen.getByLabelText('Minimum value'),{target:{value:'0.01'}});
  fireEvent.change(screen.getByLabelText('Maximum value'),{target:{value:'999.99'}});
  fireEvent.submit(screen.getByRole('button',{name:'Save candidate'}).closest('form')!);
  expect(save).toHaveBeenCalledWith(expect.objectContaining({definition:expect.objectContaining({validation:expect.objectContaining({min_length:2,decimal_places:2,min:'0.01',max:'999.99'})})}));
});
