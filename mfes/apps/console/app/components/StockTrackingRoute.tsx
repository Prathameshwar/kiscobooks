import { ErrorState } from "@janso/ui";
import { NoCompany } from "./NoCompany";
import { StockTrackingPage } from "./StockTrackingPage";
import { companyPermission } from "../lib/company-permissions";
import type { Session } from "../session";
import type { trackingRoute } from "../lib/stock-tracking-route";
import type { CompanyContext } from "../lib/company-context";
export function StockTrackingRoute({
  route,
  itemId,
  session,
  context,
}: {
  route: NonNullable<ReturnType<typeof trackingRoute>>;
  itemId?: string;
  session: Session;
  context: CompanyContext;
}) {
  const company = session.company.id,
    family = route.kind === "batches" ? "batch" : "serial",
    permission = "accounting." + family;
  const access = {
    manage: companyPermission(session, permission + ".manage", company),
    hold: companyPermission(session, permission + ".hold", company),
  };
  const recoveryScope = session.organisation.id && session.user.id
    ? session.organisation.id + ':' + session.user.id : undefined;
  if (!company)
    return (
      <NoCompany
        context={context}
        action="configure"
        canCreate={companyPermission(session, "company.create")}
      />
    );
  if (
    !companyPermission(session, permission + ".read", company) ||
    (['new', 'register', 'replace'].includes(route.page) && !access.manage) ||
    (route.page === "edit" && !access.manage && !access.hold)
  )
    return <ErrorState status={403} />;
  return (
    <StockTrackingPage
      key={recoveryScope + ':' + company + ":" + route.kind + ":" + (route.id ?? route.page)}
      company={company}
      {...route}
      itemId={itemId}
      access={access}
      recoveryScope={recoveryScope}
    />
  );
}
