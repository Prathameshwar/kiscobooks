'use client';
import type {FiscalYearChoice} from '../lib/company-context';
import type {TaxReportCode} from '../lib/tax-workspace';
import {NativeBookWorkspace} from './NativeBookWorkspace';
export function TaxReportWorkspace(props:{report:TaxReportCode;company:string;companyName:string;actor:string;permissions:readonly string[];year?:FiscalYearChoice|null}){
 return <NativeBookWorkspace book="tax-report" taxReport={props.report} company={props.company} companyName={props.companyName} actor={props.actor} permissions={props.permissions} year={props.year}/>;
}
