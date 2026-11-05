import {expect,it} from 'vitest';
import {allowedReportRequest} from '../app/lib/report-request-policy';

const id='01234567-89ab-4cde-8fab-0123456789ab';
const base=`/v2/companies/${id}/report-runs/${id}`;
it('allows scoped result queries and signed GET row detail',()=>{
  expect(allowedReportRequest('POST',base+'/queries')).toBe(true);
  expect(allowedReportRequest('GET',base+'/rows/251?token=signed')).toBe(true);
  expect(allowedReportRequest('POST',base+'/rows/251')).toBe(false);
  expect(allowedReportRequest('GET',base+'/queries')).toBe(false);
  expect(allowedReportRequest('GET',base+'/rows/0')).toBe(false);
  expect(allowedReportRequest('GET',base+'/rows/-1')).toBe(false);
  expect(allowedReportRequest('GET',base+'/rows/1/../../exports')).toBe(false);
});
it('allows only bounded and typed hierarchy branch reads',()=>{
  expect(allowedReportRequest('GET',base+'/hierarchy?parent=group:'+id+'&period=CURRENT&show_zero=false&limit=200')).toBe(true);
  for(const suffix of ['?limit=201','?parent=foreign','?period=other','?show_zero=1','?limit=50&limit=20','?download=true'])expect(allowedReportRequest('GET',base+'/hierarchy'+suffix)).toBe(false);
  expect(allowedReportRequest('POST',base+'/hierarchy')).toBe(false);
});
