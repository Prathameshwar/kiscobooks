'use client';
import {GroupedBarChart,Notice,useFormatters} from '@janso/ui';
import {analyticsKpis,isAnalyticsReport,type AnalyticsSummary} from '../lib/analytics-workspace';
import {useMediaQuery} from '../lib/use-media-query';

export function AnalyticsInsights({summary,parameters={}}:{summary:AnalyticsSummary;parameters?:Record<string,unknown>}){
 const format=useFormatters(),mobile=useMediaQuery('(max-width: 640px)');
 if(!isAnalyticsReport(summary.code))return null;
 const evidenceLimits=summary.notices.filter(note=>/unavailable|lack complete|incomplete|imported YTD|not additive/i.test(note));
 const show=(key:string,value:string|number|null|undefined)=>value==null?'Unavailable':typeof value==='number'?String(value):key.endsWith('_percent')||key.endsWith('_rate')?format.quantity(value)+'%':format.money(value,{display:'none'});
 const currencies=[...new Set([...Object.keys(summary.amounts.CURRENT??{}),...(summary.comparison_present?Object.keys(summary.amounts.COMPARATIVE??{}):[])])];
 const filterLabels:Record<string,string>={party_id:'Buyer',item_id:'Product',group_id:'Product group',currency:'Currency'};
 return <section className="janso-flow janso-analytics-insights" aria-label="Business insights">
  {!!Object.keys(summary.selected_filters??{}).length&&<ul className="janso-analytics-applied" aria-label="Applied report filters">{Object.entries(summary.selected_filters??{}).filter(([key])=>filterLabels[key]).map(([key,value])=><li key={key} title={value}>{filterLabels[key]}: {value.replace(/ \([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\)$/i,'')}</li>)}</ul>}
  {summary.comparison_present&&typeof parameters.comparative_from==='string'&&typeof parameters.comparative_to==='string'&&<p className="janso-day-book__muted">Comparison period {format.date(parameters.comparative_from)} – {format.date(parameters.comparative_to)}</p>}
  {evidenceLimits.map(note=><Notice key={note} tone="warning">{note}</Notice>)}
  <details className="janso-day-book__surface"><summary>How these figures are calculated</summary><div className="janso-flow">{summary.notices.filter(note=>!evidenceLimits.includes(note)).map(note=><Notice key={note}>{note}</Notice>)}</div></details>
  {currencies.map(currency=>{
   const amounts=summary.amounts.CURRENT?.[currency];
   const trends=summary.trends.filter(row=>row.period==='CURRENT'&&row.currency===currency).slice(-24);
   const prior=summary.amounts.COMPARATIVE?.[currency];
   const trendKey=summary.code==='SALES_PERFORMANCE'||summary.code==='CUSTOMER_INSIGHTS'?'net_sales':'amount';
   const usable=trends.filter(row=>typeof row[trendKey]==='string');
   const trendTitle=summary.code==='PROFIT_MARGIN_ANALYSIS'?'Net profit trend':summary.code==='EXPENSE_PROFIT_LEAKAGE'?'Expense trend':summary.code==='CASH_WORKING_CAPITAL'?'Net cash movement trend':'Net sales trend';
   return <section key={currency} className="janso-flow janso-analytics-currency" aria-label={currency+' insights'}>
    <p className="janso-day-book__muted">{currency} · Applied period {format.date(summary.date_from)} – {format.date(summary.date_to)}</p>
    {!amounts&&<p className="janso-day-book__muted">No current-period activity for this currency.</p>}
    <dl className="janso-day-book__summary">{analyticsKpis[summary.code].map(([key,label])=><div key={key}><dt>{label}</dt><dd>{amounts?show(key,amounts[key]):'No activity'}</dd>{summary.comparison_present&&<span>Comparison: {show(key,prior?.[key])}</span>}</div>)}</dl>
    {usable.length>0&&<div className="janso-day-book__surface janso-analytics-trend"><h2>{trendTitle}</h2><GroupedBarChart ariaLabel={currency+' '+trendTitle.toLowerCase()} categories={usable.map(row=>format.date(String(row.date)))} series={[{key:'current',label:'Current period',slot:1,values:usable.map(row=>String(row[trendKey]))}]} width={mobile?320:720} height={220} formatValue={value=>format.money(value,{display:'none'})}/>{summary.trends.filter(row=>row.period==='CURRENT'&&row.currency===currency).length>24&&<p className="janso-day-book__muted">Chart shows the latest 24 intervals for the applied period.</p>}</div>}
   </section>;
  })}
  {!!summary.inventory_as_of&&<p className="janso-day-book__muted">Inventory evidence as of {format.date(summary.inventory_as_of)}. Stock costs require matching movement dates and currency.</p>}
 </section>;
}
