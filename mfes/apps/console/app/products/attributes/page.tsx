import { notFound } from "next/navigation";
import { ErrorState } from "@janso/ui";
import { Providers } from "../../providers";
import { ConsoleShell } from "../../components/ConsoleShell";
import { NoCompany } from "../../components/NoCompany";
import { ProductAttributeAuthoring } from "../../components/ProductAttributeAuthoring";
import { pageContext } from "../../lib/page-context";
import { companyPermission } from "../../lib/company-permissions";
import { trackingId as catalogId } from "../../lib/stock-tracking-resources";
export default async function ProductAttributesPage({
  searchParams,
}: {
  searchParams?: Promise<{
    item_id?: string | string[];
    family_id?: string | string[];
  }>;
}) {
  const query = await searchParams;
  for (const value of [query?.item_id, query?.family_id])
    if (
      value !== undefined &&
      (typeof value !== "string" || !catalogId.test(value))
    )
      notFound();
  if (query?.item_id && query?.family_id) notFound();
  const { session, context } = await pageContext(),
    company = session.company.id;
  return (
    <Providers session={session}>
      <ConsoleShell
        session={session}
        context={context}
        activeHref="/products/attributes"
      >
        {company ? (
          companyPermission(session, "item.read", company) ? (
            <ProductAttributeAuthoring
              key={company}
              company={company}
              itemId={query?.item_id as string | undefined}
              familyId={query?.family_id as string | undefined}
              canManage={companyPermission(session, "item.update", company)}
              canCreate={companyPermission(session, "item.create", company)}
            />
          ) : (
            <ErrorState status={403} />
          )
        ) : (
          <NoCompany
            context={context}
            action="configure"
            canCreate={companyPermission(session, "company.create")}
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
