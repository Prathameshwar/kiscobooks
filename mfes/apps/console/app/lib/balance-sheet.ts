import type {FiscalYearChoice} from './company-context';
import {comparisonDates} from './profit-loss';

export type BalanceComparisonPreset='YEAR_END'|'MONTH_END'|'LAST_YEAR'|'CUSTOM';
export function balanceComparisonDate(asOf:string,preset:Exclude<BalanceComparisonPreset,'CUSTOM'>,years:readonly FiscalYearChoice[]):string{
  if(!/^\d{4}-\d{2}-\d{2}$/.test(asOf))return '';
  const date=new Date(asOf+'T00:00:00Z');
  if(!Number.isFinite(date.getTime())||date.toISOString().slice(0,10)!==asOf)return '';
  if(preset==='LAST_YEAR')return comparisonDates(asOf,asOf,'LAST_YEAR').to;
  if(preset==='MONTH_END'){date.setUTCDate(0);return date.toISOString().slice(0,10);}
  const year=years.find(item=>item.startDate<=asOf&&item.endDate>=asOf);
  if(!year)return '';
  const start=new Date(year.startDate+'T00:00:00Z');start.setUTCDate(start.getUTCDate()-1);
  return start.toISOString().slice(0,10);
}
