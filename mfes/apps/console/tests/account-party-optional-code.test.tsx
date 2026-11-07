import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { AccountingFields } from '../app/components/AccountingConfigurationCommon';
import { accountingBody } from '../app/lib/accounting-configuration';
import { expenseAccountRequest, supplierRequest } from '../app/lib/purchase-quick-create';
import { COMPANY, form } from './accounting-configuration-fixtures';

it.each(['accounts', 'parties'] as const)('%s Code is optional in the native master form', resource => {
  const code = form(resource).fields.find(field => field.key === 'code')!;
  let entered: unknown;
  render(<AccountingFields company={COMPANY} resource={resource} fields={[code]} values={{code:''}} onChange={(_key,value) => {entered=value;}} />);
  const input = screen.getByRole('textbox', {name:'Code'});
  expect(input).not.toBeRequired();
  expect(input).toHaveAttribute('maxlength','80');
  fireEvent.change(input,{target:{value:'😀'.repeat(41)}});
  expect(entered).toBe('😀'.repeat(40));
  fireEvent.change(input,{target:{value:'a'.repeat(41)}});
  expect(entered).toBe('a'.repeat(40));
  expect(input).toHaveAccessibleDescription(/Leave blank.*eight-character/);
  expect(accountingBody([code], {code:'   '})).toEqual({body:{}, errors:{}});
  expect(accountingBody([code], {code:' 00-Office & rent '}).body).toEqual({code:'00-Office & rent'});
  expect(accountingBody([code], {code:'😀'.repeat(40)}).errors).toEqual({});
  expect(accountingBody([code], {code:'😀'.repeat(41)}).errors.code).toMatch(/40 characters/);
  expect(accountingBody([code], {code:'x'.repeat(41)}).errors.code).toMatch(/40 characters/);
  expect(accountingBody([code], {code:'bad\u0000code'}).errors.code).toMatch(/control characters/);
});

it('Purchase omits blank Account and Party codes and preserves manual identities', () => {
  const supplier = {name:'Supplier', code:' ', countryCode:'IN', gstStatus:'NONE' as const, stateCode:'', gstin:''};
  const account = {name:'Rent', code:' ', groupId:COMPANY, description:''};
  const groups = [{id:COMPANY, name:'Indirect Expenses', head:'Expenses'}];
  expect(supplierRequest(supplier, {tax:false}).body).not.toHaveProperty('code');
  expect(expenseAccountRequest(account, groups).body).not.toHaveProperty('code');
  expect(supplierRequest({...supplier,code:'😀'.repeat(40)}, {tax:false}).errors).toEqual({});
  expect(expenseAccountRequest({...account,code:'😀'.repeat(40)}, groups).errors).toEqual({});
  expect(supplierRequest({...supplier, code:' 00-Office & rent '}, {tax:false}).body?.code).toBe('00-Office & rent');
  expect(expenseAccountRequest({...account, code:'x'.repeat(41)}, groups).errors.code).toMatch(/40 characters/);
});
