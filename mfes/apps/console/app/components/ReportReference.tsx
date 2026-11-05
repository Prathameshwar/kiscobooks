'use client';
import {useEffect,useMemo,useRef,useState} from 'react';
import {SearchSelect,type SearchSelectOption} from '@janso/ui';
import {reportLookup,reportReference,type ReportReferenceSource} from '../lib/report-references';

export function ReportReference({company,code,source,item,generation,label,value,onChange,disabled,required,onStateChange}:{company:string;code:string;source:ReportReferenceSource;item?:string;generation?:string;label:string;value:string;onChange:(value:string)=>void;disabled:boolean;required:boolean;onStateChange?:(ready:boolean)=>void}){
  const [selected,setSelected]=useState<SearchSelectOption|null>(null),[error,setError]=useState('');
  const accountKind=source==='accounts'?(code.startsWith('BANK_')?'BANK':code==='CASH_BOOK'?'CASH':undefined):undefined;
  const load=useMemo(()=>reportLookup(company,source,item,generation,accountKind),[company,source,item,generation,accountKind]);
  const stateChange=useRef(onStateChange);stateChange.current=onStateChange;
  useEffect(()=>{
    const controller=new AbortController();setSelected(null);setError('');stateChange.current?.(!value);
    if(value)void reportReference(company,source,value,controller.signal,generation,item,accountKind).then(option=>{if(!controller.signal.aborted){setSelected(option);stateChange.current?.(true);}}).catch(error=>{if(!controller.signal.aborted){setError(error instanceof Error?error.message:'Unable to read the report reference.');stateChange.current?.(false);}});
    return ()=>controller.abort();
  },[company,source,value,generation,item,accountKind]);
  return <SearchSelect label={label} required={required} value={value||null} selected={selected} error={error} loadOptions={load} scopeKey={[company,code,source,item,generation].join(':')} minQueryLength={0} disabled={disabled} onChange={value=>onChange(value??'')}/>;
}
