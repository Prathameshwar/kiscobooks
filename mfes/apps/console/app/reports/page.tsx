import {ErrorState} from '@janso/ui';
import {Providers} from '../providers';
import {ConsoleShell} from '../components/ConsoleShell';
import {NoCompany} from '../components/NoCompany';
import {ReportsHub} from '../components/ReportsHub';
import {pageContext} from '../lib/page-context';
import {companyPermission} from '../lib/company-permissions';

export default async function ReportsPage(){
  const {session,context}=await pageContext();
  const company=session.company.id;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/reports">
    {!company
      ?<NoCompany action="report on" context={context} canCreate={companyPermission(session,'company.create')}/>
      :companyPermission(session,'report.read',company)
        ?<ReportsHub key={company} company={company}/>
        :<ErrorState status={403}/>}
  </ConsoleShell></Providers>;
}
