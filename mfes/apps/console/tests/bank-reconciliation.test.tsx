import {render,screen} from '@testing-library/react';
import {expect,it,vi} from 'vitest';

vi.mock('@janso/ui',()=>({
  Button:({children,...props}:React.ButtonHTMLAttributes<HTMLButtonElement>)=><button {...props}>{children}</button>,
  SearchSelect:({label}:{label:string})=><label>{label}<input /></label>,
  Select:({label}:{label:string})=><label>{label}<select /></label>,
  TextField:({label}:{label:string})=><label>{label}<input /></label>,
  useFormatters:()=>({date:(value:string)=>value,money:(value:string)=>value}),
}));

import {BankReconciliation} from '../app/components/BankReconciliation';

it('keeps bank evidence controls out of a role without statement access',()=>{
  render(<BankReconciliation company="company" permissions={['accounting.bank.read']} />);
  expect(screen.queryByRole('heading',{name:'Bank reconciliation'})).not.toBeInTheDocument();
});

it('shows a read-only bank reconciliation entry point without mutation controls',()=>{
  render(<BankReconciliation company="company" permissions={[
    'accounting.bank.read','accounting.statement.read',
  ]} />);
  expect(screen.getByRole('heading',{name:'Bank reconciliation'})).toBeInTheDocument();
  expect(screen.getByText('Bank ledger')).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Publish CSV mapping'})).not.toBeInTheDocument();
});
