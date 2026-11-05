import {ErrorState} from '@janso/ui';
import {Providers} from '../providers';
import {ConsoleShell} from '../components/ConsoleShell';
import {NoCompany} from '../components/NoCompany';
import {VoucherDirectory} from '../components/VoucherDirectory';
import {VoucherImport} from '../components/VoucherImport';
import {pageContext} from '../lib/page-context';
import {companyPermission} from '../lib/company-permissions';

export default async function VouchersPage() {
  // One session resolution per request, already carrying the open company (`lib/page-context`).
  const {session,context}=await pageContext();
  const company=session.company.id;
  const permissions=session.permissions.filter(key=>companyPermission(session,key,company));
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/vouchers">
    {/* Two different answers: no company to work in, versus a company this role may not read. */}
    {!company
      ?<NoCompany action="record" context={context} canCreate={companyPermission(session,'company.create')}/>
      :permissions.includes('vouchers.read')
        ?<VoucherDirectory key={company} permissions={permissions} company={company}/>
        :<ErrorState status={403}/>}
    {company&&permissions.includes('vouchers.read')&&permissions.includes('vouchers.import.read')&&<VoucherImport key={'import-'+company} company={company} permissions={permissions}/>}
  </ConsoleShell></Providers>;
}
