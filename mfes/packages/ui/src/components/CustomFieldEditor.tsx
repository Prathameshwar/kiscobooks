'use client';
import { useState } from 'react';
import { Button } from './Button';
import { TextField } from './TextField';
import { Select } from './Select';
import { CustomFields } from './CustomFields';
import { Card, CardBody } from './Card';
import { FormActions } from './FormLayout';
import { FieldGroup } from './FieldGroup';
import { SectionHeader } from './SectionHeader';
import { customValue, type CustomDefinition } from '../lib/custom-fields';

export type DefinitionDraft = { label: string; help_text: string | null; definition: CustomDefinition };
const kinds = ['text','long_text','integer','decimal','boolean','date','datetime','currency_amount','select','multi_select','dynamic_select','auto_number'];
const empty = (): DefinitionDraft => ({ label: '', help_text: null, definition: {
  key: 'cf_', data_type: 'text', is_active: true, is_searchable: false, is_immutable_after_create: false,
  validation: { required: false, max_length: 512, decimal_places: 4, unique_within: 'none', case_sensitive: true }, choices: [], default_value: null,
}});
export function CustomFieldEditor({ initial, sources, fields, currencies, busy, onSave, onCancel }: {
  initial?: DefinitionDraft; sources: readonly string[]; fields: readonly {key: string; label: string}[];
  currencies: readonly string[]; busy: boolean; onSave: (value: DefinitionDraft) => Promise<void>; onCancel: () => void;
}) {
  const [draft, setDraft] = useState<DefinitionDraft>(initial ?? empty);
  const [error, setError] = useState('');
  const d = draft.definition;
  function change(patch: Partial<CustomDefinition>) { setDraft({ ...draft, definition: { ...d, ...patch } }); }
  function rule(patch: Partial<CustomDefinition['validation']>) { change({ validation: { ...d.validation, ...patch } }); }
  function kind(value: string) { change({ data_type: value, choices: ['select','multi_select'].includes(value) ? [{value:'option_1',label:'First option',is_active:true}] : [],
    is_searchable: false, validation: {...d.validation, unique_within:'none'}, default_value:null, option_source_key:null, depends_on_key:null,
    sequence_config: value === 'auto_number' ? {prefix:'',padding:1,start:1,reset:'never'} : null }); }
  const yesNo = [{value:'yes',label:'Yes'},{value:'no',label:'No'}];
  return <form aria-label="Field definition editor" onSubmit={async event => { event.preventDefault(); setError('');
    try { await onSave({...draft, definition: {...d, default_value: customValue(d, d.default_value)}}); }
    catch (reason) { setError(reason instanceof Error ? reason.message : 'Unable to save the definition'); }
  }}><Card><CardBody><div className="janso-flow"><SectionHeader title={initial ? 'Edit field definition' : 'New field definition'} description="Define the field, its validation and defaults before reviewing adoption." /><div className="janso-form-grid">
    <TextField label="Field label" value={draft.label} required maxLength={150} disabled={busy} onChange={event => setDraft({...draft,label:event.target.value})} />
    <TextField label="Stable field key" value={d.key} required pattern="cf_[a-z][a-z0-9_]{0,56}" maxLength={60} disabled={busy || !!initial}
      hint="Start with cf_. This identifies saved values and cannot change later." onChange={event => change({key:event.target.value})} />
    <Select label="Value type" value={d.data_type} disabled={busy || !!initial} options={kinds.map(value => ({value,label:value.replaceAll('_',' ')}))} onChange={kind} />
    <TextField label="Help text" value={draft.help_text ?? ''} maxLength={500} disabled={busy} onChange={event => setDraft({...draft,help_text:event.target.value || null})} />
    <Select label="Available for new values" value={d.is_active ? 'yes':'no'} options={yesNo} disabled={busy} onChange={v => change({is_active:v === 'yes'})} />
    <Select label="Required" value={d.validation.required ? 'yes':'no'} options={yesNo} disabled={busy} onChange={v => rule({required:v === 'yes'})} />
    <Select label="Lock after product creation" value={d.is_immutable_after_create ? 'yes':'no'} options={yesNo} disabled={busy} onChange={v => change({is_immutable_after_create:v === 'yes'})} />
    <Select label="Searchable" value={d.is_searchable ? 'yes':'no'} options={yesNo} disabled={busy || d.data_type === 'long_text'} onChange={v => change({is_searchable:v === 'yes',validation:{...d.validation,unique_within:'none'}})} />
    <Select label="Unique value" value={d.validation.unique_within ?? 'none'} options={['none','company','tenant'].map(value => ({value,label:value}))}
      disabled={busy || !d.is_searchable || ['long_text','multi_select'].includes(d.data_type)} onChange={v => rule({unique_within:v})} />
    <Select label="Case sensitive" value={d.validation.case_sensitive ? 'yes':'no'} options={yesNo} disabled={busy} onChange={v => rule({case_sensitive:v === 'yes'})} />
    {['integer','decimal','currency_amount'].includes(d.data_type) && <>
      <TextField label="Minimum value" value={d.validation.min ?? ''} inputMode="decimal" disabled={busy} onChange={e => rule({min:e.target.value || null})} />
      <TextField label="Maximum value" value={d.validation.max ?? ''} inputMode="decimal" disabled={busy} onChange={e => rule({max:e.target.value || null})} />
    </>}
    {['decimal','currency_amount'].includes(d.data_type) && <TextField label="Decimal places" type="number" min={0} max={4} value={d.validation.decimal_places ?? 4} disabled={busy} onChange={e => rule({decimal_places:Number(e.target.value)})} />}
    {['text','long_text'].includes(d.data_type) && <>
      <TextField label="Minimum characters" type="number" min={0} max={4096} value={d.validation.min_length ?? 0} disabled={busy} onChange={e => rule({min_length:Number(e.target.value)})} />
      <TextField label="Maximum characters" type="number" min={1} max={4096} value={d.validation.max_length} disabled={busy} onChange={e => rule({max_length:Number(e.target.value)})} />
      <TextField label="Validation pattern" value={d.validation.regex ?? ''} disabled={busy} maxLength={256} hint="Use literals, character classes and fixed repetitions." onChange={e => rule({regex:e.target.value || null})} />
      <TextField label="Pattern error message" value={d.validation.regex_message ?? ''} disabled={busy} maxLength={200} onChange={e => rule({regex_message:e.target.value || null})} />
    </>}
    {['select','multi_select'].includes(d.data_type) && <div className="janso-form-grid__full"><FieldGroup title="Options">
      {d.choices.map((choice,index) => <div key={index} className="janso-form-grid">
        <TextField label={'Option '+(index+1)+' key'} value={choice.value} disabled={busy || !!initial?.definition.choices.some(c => c.value === choice.value)} required maxLength={200}
          onChange={e => change({choices:d.choices.map((c,i) => i === index ? {...c,value:e.target.value}:c)})} />
        <TextField label={'Option '+(index+1)+' label'} value={choice.label} disabled={busy} required maxLength={200}
          onChange={e => change({choices:d.choices.map((c,i) => i === index ? {...c,label:e.target.value}:c)})} />
        <Select label={'Option '+(index+1)+' active'} value={choice.is_active ? 'yes':'no'} options={yesNo} disabled={busy}
          onChange={v => change({choices:d.choices.map((c,i) => i === index ? {...c,is_active:v === 'yes'}:c)})} />
      </div>)}
      <Button type="button" variant="ghost" disabled={busy || d.choices.length >= 200} onClick={() => change({choices:[...d.choices,{value:'option_'+(d.choices.length+1),label:'New option',is_active:true}]})}>Add option</Button>
    </FieldGroup></div>}
    {d.data_type === 'dynamic_select' && <>
      <Select label="Option source" value={d.option_source_key ?? ''} options={sources.map(value => ({value,label:value.replace('catalog.','').replaceAll('_',' ')}))} required disabled={busy} onChange={v => change({option_source_key:v})} />
      <Select label="Parent reference field" value={d.depends_on_key ?? ''} options={fields.filter(f => f.key !== d.key).map(f => ({value:f.key,label:f.label}))}
        placeholder="No parent" disabled={busy} onChange={v => change({depends_on_key:v || null})} />
    </>}
    {d.sequence_config && <div className="janso-form-grid__full"><FieldGroup title="Automatic numbering"><div className="janso-form-grid">
      <TextField label="Prefix" value={d.sequence_config.prefix} disabled={busy} maxLength={64} onChange={e => change({sequence_config:{...d.sequence_config!,prefix:e.target.value}})} />
      <TextField label="Starting number" type="number" min={1} max={Number.MAX_SAFE_INTEGER} value={d.sequence_config.start} disabled={busy} onChange={e => change({sequence_config:{...d.sequence_config!,start:Number(e.target.value)}})} />
      <TextField label="Minimum digits" type="number" min={1} max={20} value={d.sequence_config.padding} disabled={busy} onChange={e => change({sequence_config:{...d.sequence_config!,padding:Number(e.target.value)}})} />
      <Select label="Reset numbering" value={d.sequence_config.reset} options={[{value:'never',label:'Never'},{value:'calendar_year',label:'Calendar year'},{value:'month',label:'Each month'}]}
        disabled={busy} onChange={v => change({sequence_config:{...d.sequence_config!,reset:v}})} />
    </div></FieldGroup></div>}
    <Select label="Show field when" value={d.visibility ? String(d.visibility.field ?? '__advanced') : ''} placeholder="Always"
      options={[...fields.filter(f => f.key !== d.key).map(f => ({value:f.key,label:f.label})), ...(d.visibility?.op ? [{value:'__advanced',label:'Existing combined conditions'}]:[])]}
      disabled={busy} onChange={v => change({visibility:v ? {field:v,cmp:'eq',value:''}:null})} />
    {d.visibility && !d.visibility.op && <>
      <Select label="Comparison" value={String(d.visibility.cmp)} options={['eq','ne','gt','gte','lt','lte','empty','not_empty'].map(value => ({value,label:value.replaceAll('_',' ')}))} disabled={busy}
        onChange={v => change({visibility:{...d.visibility,cmp:v,...(['empty','not_empty'].includes(v) ? {}:{value:d.visibility?.value ?? ''})}})} />
      {!['empty','not_empty'].includes(String(d.visibility.cmp)) && <TextField label="Compared value" value={String(d.visibility.value ?? '')} disabled={busy}
        onChange={e => change({visibility:{...d.visibility,value:e.target.value === 'true' ? true : e.target.value === 'false' ? false : e.target.value}})} />}
    </>}
    </div>{!['auto_number','dynamic_select'].includes(d.data_type) && <CustomFields currencies={currencies} creating disabled={busy}
      fields={[{key:d.key,source:'custom',label:'Default for new products',visible:true,required:false,writable:true,custom:{...d,is_active:true,visibility:null,validation:{...d.validation,required:false}}}]}
      values={{[d.key]:d.default_value}} onChange={v => change({default_value:v[d.key]})} />}
    {error && <p role="alert">{error}</p>}
    <p>Save a candidate, then review and adopt it. For existing products, adopt an optional field, fill its values, then require it.</p>
    </div></CardBody><FormActions cancel={{ onCancel, disabled: busy }}><Button type="submit" loading={busy}>Save candidate</Button></FormActions></Card>
  </form>;
}
