import { ErrorState } from "@janso/ui";
import { notFound } from "next/navigation";
import { Providers } from "../providers";
import { pageContext } from "../lib/page-context";
import { companyPermission } from "../lib/company-permissions";
import { ConsoleShell } from "./ConsoleShell";
import { NoCompany } from "./NoCompany";
import { PromotionStacks } from "./PromotionStacks";
export async function PromotionStacksRoute({
  record,
  query,
}: {
  record: string[];
  query: Record<string, string | string[] | undefined>;
}) {
  const creating = record[0] === "drafts" && record[1] === "new";
  const published = record[0] === "revisions";
  const id = !creating ? record[1]?.toLowerCase() : undefined;
  if (
    record.length &&
    (record.length !== 2 ||
      !["drafts", "revisions"].includes(record[0]!) ||
      (!creating &&
        !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(record[1]!)))
  )
    notFound();
  const { session, context } = await pageContext(),
    company = session.company.id;
  const read = companyPermission(
      session,
      "promotion_stack_policy.read",
      company,
    ),
    manage = companyPermission(
      session,
      "promotion_stack_policy.manage",
      company,
    ),
    publish = companyPermission(
      session,
      "promotion_stack_policy.publish",
      company,
    );
  return (
    <Providers session={session}>
      <ConsoleShell
        session={session}
        context={context}
        activeHref="/masters/promotion-stack-policies"
      >
        {!company ? (
          <NoCompany
            action="manage promotion definitions for"
            context={context}
            canCreate={companyPermission(session, "company.create")}
          />
        ) : !read || (creating && !manage) ? (
          <ErrorState
            status={403}
            detail="Promotion stack policy access is required for this company."
          />
        ) : (
          <PromotionStacks
            key={company + ":" + record.join(":")}
            company={company}
            detail={!!record.length}
            id={id}
            published={published}
            access={{ manage, publish }}
            returnTo={
              typeof query.returnTo === "string" ? query.returnTo : undefined
            }
          />
        )}
      </ConsoleShell>
    </Providers>
  );
}
