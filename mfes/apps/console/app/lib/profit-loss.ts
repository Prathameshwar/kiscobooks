export type ProfitMode='default'|'comparison';
export type ComparisonPreset='PREVIOUS'|'LAST_YEAR'|'CUSTOM';
export type ProfitRow={row_kind:string;label:string;section?:string;group_id?:string;group_name?:string;group_code?:string;account_id?:string;account_code?:string;amount:string;previous_amount?:string;change_amount?:string;change_percent?:string|null;imported_ytd_amount?:string|null;previous_imported_ytd_amount?:string|null;currency:string};
export type ProfitSummary={currency:string;sections:Record<string,{current:string;previous:string}>;imported_ytd?:Record<string,boolean>;totals:Record<string,{current:string;previous:string|null}>};

function iso(date:Date){return date.toISOString().slice(0,10);}
export function comparisonDates(from:string,to:string,preset:Exclude<ComparisonPreset,'CUSTOM'>):{from:string;to:string}{
  if(!/^\d{4}-\d{2}-\d{2}$/.test(from)||!/^\d{4}-\d{2}-\d{2}$/.test(to)||from>to)throw new Error('Choose a valid report period.');
  const start=new Date(from+'T00:00:00Z'),end=new Date(to+'T00:00:00Z');
  if(preset==='PREVIOUS'){
    const days=Math.round((end.getTime()-start.getTime())/86400000)+1;
    return {from:iso(new Date(start.getTime()-days*86400000)),to:iso(new Date(start.getTime()-86400000))};
  }
  const previous=(value:string)=>{
    const [year,month,day]=value.split('-').map(Number);
    const last=new Date(Date.UTC(year-1,month,0)).getUTCDate();
    return iso(new Date(Date.UTC(year-1,month-1,Math.min(day,last))));
  };
  return {from:previous(from),to:previous(to)};
}
