import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ProductCatalogPage } from "../app/components/ProductCatalogPage";
import { pageContext } from "../app/lib/page-context";
import {
  masterReferencePath,
  masterReturnQuery,
} from "../app/lib/master-navigation";
import { COMPANY, RECORD, SOURCE } from "./product-classification-fixtures";
import { sessionFor, companyContextFor } from "./helpers";

vi.mock("../app/lib/page-context", () => ({ pageContext: vi.fn() }));
vi.mock("../app/providers", () => ({
  Providers: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("../app/components/ConsoleShell", () => ({
  ConsoleShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not found");
  },
}));

beforeEach(async () => {
  const session = await sessionFor();
  session.company = { id: COMPANY, name: "Test company" };
  session.grants = [
    {
      scope_type: "company",
      scope_id: COMPANY,
      valid_from: "2020-01-01",
      valid_to: null,
      permissions: ["item.read", "item.update", "item.create"],
    },
  ];
  vi.mocked(pageContext).mockResolvedValue({
    session,
    context: companyContextFor(),
  });
});

it.each([[RECORD], [RECORD, "edit"], [RECORD, "created"]])(
  "restores SKU route %s",
  async (...record) => {
    const page = await ProductCatalogPage({ resource: "items", record });
    expect(page).toBeTruthy();
  },
);
it.each([["new"], [RECORD], [RECORD, "edit"], [RECORD, "created"]])(
  "restores Product Profile route %s",
  async (...record) => {
    expect(
      await ProductCatalogPage({ resource: "product-families", record }),
    ).toBeTruthy();
  },
);

it("keeps record editing denied for a grant belonging to another company", async () => {
  const { session, context } = await pageContext();
  session.grants![0]!.scope_id = SOURCE;
  vi.mocked(pageContext).mockResolvedValue({ session, context });
  render(
    await ProductCatalogPage({ resource: "items", record: [RECORD, "edit"] }),
  );
  expect(
    screen.getByText(/need the product or classification permissions/),
  ).toBeVisible();
});

it("restores safe record and completion return paths but rejects invalid record IDs", () => {
  expect(masterReferencePath("items", RECORD)).toBe("/masters/items/" + RECORD);
  expect(
    masterReturnQuery(
      new URL(
        "/masters/items/" + RECORD + "/created",
        "https://console.invalid",
      ),
    ),
  ).not.toBeNull();
  expect(
    masterReturnQuery(
      new URL("/masters/items/not-an-id/edit", "https://console.invalid"),
    ),
  ).toBeNull();
});
