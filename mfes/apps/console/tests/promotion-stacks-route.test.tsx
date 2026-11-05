import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PromotionStacksRoute } from "../app/components/PromotionStacksRoute";
import { pageContext } from "../app/lib/page-context";
import { sessionFor, companyContextFor } from "./helpers";
vi.mock("../app/lib/page-context", () => ({ pageContext: vi.fn() }));
vi.mock("../app/providers", () => ({
  Providers: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("../app/components/ConsoleShell", () => ({
  ConsoleShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("../app/components/PromotionStacks", () => ({
  PromotionStacks: ({
    detail,
    access,
  }: {
    detail: boolean;
    access: { manage: boolean };
  }) => (
    <p>
      {detail ? "Policy details" : "Policy directory"}:{" "}
      {access.manage ? "editor" : "reader"}
    </p>
  ),
}));
const company = "01990000-0000-7000-8000-000000000001";
async function scope(keys: string[], target = company) {
  const session = await sessionFor({ permissions: keys });
  session.company = { id: company, name: "Company A" };
  session.grants = [
    {
      scope_type: "company",
      scope_id: target,
      permissions: keys,
      valid_from: "2000-01-01",
      valid_to: null,
    },
  ];
  vi.mocked(pageContext).mockResolvedValue({
    session,
    context: companyContextFor(),
  });
}
it("allows a scoped reader and rejects another company grant", async () => {
  await scope(["promotion_stack_policy.read"]);
  render(await PromotionStacksRoute({ record: [], query: {} }));
  expect(screen.getByText("Policy directory: reader")).toBeVisible();
});
it("requires manage authority for a new draft", async () => {
  await scope(["promotion_stack_policy.read"]);
  render(await PromotionStacksRoute({ record: ["drafts", "new"], query: {} }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Promotion stack policy access",
  );
});
it("does not borrow a grant from a different company", async () => {
  await scope(
    ["promotion_stack_policy.read", "promotion_stack_policy.manage"],
    "01990000-0000-7000-8000-000000000002",
  );
  render(await PromotionStacksRoute({ record: [], query: {} }));
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Promotion stack policy access",
  );
});
it.each([
  ["revisions", "new"],
  ["redeem", company],
  ["drafts", "bad-id"],
])("rejects unsupported routes %s/%s", async (...record) => {
  await expect(PromotionStacksRoute({ record, query: {} })).rejects.toThrow();
});
