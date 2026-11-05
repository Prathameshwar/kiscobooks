'use client';
import {useEffect,useState} from 'react';
import {Notice,SectionHeader} from '@janso/ui';
import {accountingBody,accountingChange,accountingInitial,accountingRequest,assertAccountingForm} from '../lib/accounting-configuration';
import {accountingResource,type AccountingForm} from '../lib/accounting-configuration-resources';
import {useServiceRead} from '../lib/service-resource';
import {AccountingFailure,AccountingLoading,AccountingFields} from './AccountingConfigurationCommon';

export function useAccountCreationProfile(company:string,kind:string,enabled:boolean){
  const resource=kind==='BANK'?'account-bank-profiles':'account-tax-profiles';
  const needed=enabled&&['BANK','TAX'].includes(kind);
  const loaded=useServiceRead<AccountingForm>(needed?`/v1/companies/${company}/configuration/${resource}/field-set?operation=create`:undefined,accountingRequest,value=>{assertAccountingForm(value,company,accountingResource(resource)!,'create');});
  const read={...loaded,metadata:loaded.data};
  const [values,setValues]=useState<Record<string,unknown>>({});
  const fields=read.metadata?.fields.filter(field=>field.key!=='account_id')??[];
  useEffect(()=>{setValues(read.metadata?accountingInitial(read.metadata.fields.filter(field=>field.key!=='account_id'),null,{}):{});},[read.metadata,resource]);
  function capture(){
    if(!needed)return {body:{},errors:{}};
    if(!read.metadata?.can_create||read.loading||read.failure)return {body:{},errors:{'opening.profile':'Load and complete the account profile before posting its opening.'}};
    const result=accountingBody(fields,values,null);
    return {body:{[kind==='BANK'?'bank_profile':'tax_profile']:result.body},errors:Object.fromEntries(Object.entries(result.errors).map(([key,value])=>['opening.profile.'+key,value]))};
  }
  return {needed,resource,read,fields,values,capture,update:(key:string,value:unknown)=>setValues(current=>accountingChange(fields,current,key,value))};
}

export function AccountCreationProfile({company,profile,disabled,errors}:{company:string;profile:ReturnType<typeof useAccountCreationProfile>;disabled:boolean;errors:Record<string,string>}){
  if(!profile.needed)return null;
  return <section className="janso-flow" aria-label="Account profile for opening">
    <SectionHeader title={profile.resource==='account-bank-profiles'?'Bank details':'Tax details'} description="Complete these details so the account and its opening are ready together."/>
    <AccountingFailure failure={profile.read.failure} retry={profile.read.refresh}/>
    {profile.read.loading?<AccountingLoading/>:profile.read.metadata&&!profile.read.metadata.can_create?<Notice tone="warning">Your access does not allow creating this account profile.</Notice>:<AccountingFields company={company} resource={profile.resource} fields={profile.fields} values={profile.values} onChange={profile.update} disabled={disabled} errors={Object.fromEntries(Object.entries(errors).filter(([key])=>key.startsWith('opening.profile.')).map(([key,value])=>[key.slice('opening.profile.'.length),value]))}/>}
  </section>;
}
