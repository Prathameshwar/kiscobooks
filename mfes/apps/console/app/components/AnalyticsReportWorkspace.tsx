'use client';
import type {FiscalYearChoice} from '../lib/company-context';
import type {AnalyticsCode} from '../lib/analytics-workspace';
import {NativeBookWorkspace} from './NativeBookWorkspace';
export function AnalyticsReportWorkspace(props:{report:AnalyticsCode;company:string;companyName:string;actor:string;permissions:readonly string[];year?:FiscalYearChoice|null;initialRun?:string}){
 return <NativeBookWorkspace {...props} book="tax-report" analyticsReport={props.report}/>;
}
