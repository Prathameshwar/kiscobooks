"use client";
import {useMemo,useRef} from 'react';
import {Button,SearchSelect,Select,TextField} from '@janso/ui';
import type {components} from '@janso/api-client/vouchers';
import {lookup,type Choice,type FieldSet} from '../lib/voucher-fields';
type Party=components['schemas']['PartyInput'];
type Reference=components['schemas']['ReferenceInput'];
export function VoucherRelated({company,metadata,parties,references,onParties,onReferences,disabled}:{company:string;metadata:FieldSet;parties:Party[];references:Reference[];onParties:(value:Party[])=>void;onReferences:(value:Reference[])=>void;disabled:boolean}){
  const choices=useRef(new Map<string,Choice>());
  const loader=useMemo(()=>lookup(company,'parties',rows=>rows.forEach(row=>choices.current.set(row.id,row))),[company]);
  const policy=metadata.configuration.policy;
  const allowed=(field:string,section:'PARTIES'|'REFERENCES')=>!!metadata.native.properties?.[field]&&!metadata.native.properties[field].readOnly&&!policy.forbidden_sections?.includes(section);
  return <>
    {allowed('parties','PARTIES')&&<fieldset className="janso-fieldgroup janso-flow" disabled={disabled}><legend className="janso-fieldgroup__legend">Parties</legend>{parties.map((party,index)=><fieldset className="janso-fieldgroup janso-flow" key={index}><legend className="janso-fieldgroup__legend">Party {index+1}</legend><div className="janso-form-grid">
      <Select label={'Party role '+(index+1)} value={party.role} options={(policy.allowed_party_roles??[]).map(value=>({value,label:value}))} disabled={disabled} onChange={role=>onParties(parties.map((value,i)=>i===index?{...value,role:role as Party['role']}:value))}/>
      <SearchSelect label={'Select party '+(index+1)} value={party.party_id||null} loadOptions={loader} minQueryLength={0} disabled={disabled} onChange={id=>onParties(parties.map((value,i)=>i===index?{...value,party_id:id??'',source_version:choices.current.get(id??'')?.row_version??0}:value))}/>
      </div><div className="janso-custom-actions"><Button type="button" variant="ghost" disabled={disabled} onClick={()=>onParties(parties.filter((_,i)=>i!==index))}>Remove party {index+1}</Button>
    </div></fieldset>)}<Button type="button" disabled={disabled||parties.length>=(policy.max_parties??20)||!policy.allowed_party_roles?.length} onClick={()=>onParties([...parties,{role:policy.allowed_party_roles![0],party_id:'',source_version:0}])}>Add party</Button></fieldset>}
    {allowed('references','REFERENCES')&&<fieldset className="janso-fieldgroup janso-flow" disabled={disabled}><legend className="janso-fieldgroup__legend">References</legend>{references.map((reference,index)=><fieldset className="janso-fieldgroup janso-flow" key={index}><legend className="janso-fieldgroup__legend">Reference {index+1}</legend><div className="janso-form-grid">
      <Select label={'Reference purpose '+(index+1)} value={reference.purpose} options={['SUPPLIER_INVOICE','CUSTOMER_ORDER','EXTERNAL','CHALLAN'].map(value=>({value,label:value.replaceAll('_',' ')}))} disabled={disabled} onChange={value=>onReferences(references.map((row,i)=>i===index?{...row,purpose:value as Reference['purpose']}:row))}/>
      <TextField label={'Reference number '+(index+1)} value={reference.reference} disabled={disabled} required onChange={event=>onReferences(references.map((row,i)=>i===index?{...row,reference:event.target.value}:row))}/>
      <TextField label={'Reference date '+(index+1)} type="date" value={reference.reference_date??''} disabled={disabled} onChange={event=>onReferences(references.map((row,i)=>i===index?{...row,reference_date:event.target.value||null}:row))}/>
      </div><div className="janso-custom-actions"><Button type="button" variant="ghost" disabled={disabled} onClick={()=>onReferences(references.filter((_,i)=>i!==index))}>Remove reference {index+1}</Button>
    </div></fieldset>)}<Button type="button" disabled={disabled||references.length>=30} onClick={()=>onReferences([...references,{purpose:policy.supplier_reference_required?'SUPPLIER_INVOICE':'EXTERNAL',reference:''}])}>Add reference</Button></fieldset>}
  </>;
}
