import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import InventoryPage from "../app/inventory/[[...segments]]/page";
import ProductAttributesPage from "../app/products/attributes/page";
import { pageContext } from "../app/lib/page-context";
import { trackingRoute } from "../app/lib/stock-tracking-route";
import { companyContextFor, sessionFor } from "./helpers";
import { COMPANY, ITEM, RECORD, EVENT } from "./stock-tracking-fixtures";
vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("not found");
  },
}));
vi.mock("../app/providers", () => ({
  Providers: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("../app/components/ConsoleShell", () => ({
  ConsoleShell: ({ children }: { children: React.ReactNode }) => children,
}));
vi.mock("../app/components/StockTrackingPage", () => ({
  StockTrackingPage: () => <p>Tracking page</p>,
}));
vi.mock("../app/components/ProductAttributeAuthoring", () => ({
  ProductAttributeAuthoring: () => <p>Attribute page</p>,
}));
vi.mock("../app/lib/page-context", () => ({ pageContext: vi.fn() }));
beforeEach(async () => {
  const session = await sessionFor();
  session.company = { id: COMPANY, name: "Test" };
  session.grants = [
    {
      scope_type: "company",
      scope_id: COMPANY,
      valid_from: "2020-01-01",
      valid_to: null,
      permissions: [
        "item.read",
        "accounting.batch.read",
        "accounting.serial.read",
      ],
    },
  ];
  vi.mocked(pageContext).mockResolvedValue({
    session,
    context: companyContextFor(),
  });
});
it.each(["batches", "serials"])(
  "opens %s details but denies ungranted edit and create",
  async (kind) => {
    const view = render(
      await InventoryPage({
        params: Promise.resolve({ segments: [kind, RECORD] }),
      }),
    );
    expect(screen.getByText("Tracking page")).toBeVisible();
    view.unmount();
    for (const tail of [["new"], [RECORD, "edit"]]) {
      const denied = render(
        await InventoryPage({
          params: Promise.resolve({ segments: [kind, ...tail] }),
        }),
      );
      expect(screen.queryByText("Tracking page")).toBeNull();
      denied.unmount();
    }
  },
);
it.each(["other-company", "department", "expired"])(
  "does not borrow %s authority",
  async (reason) => {
    const { session, context } = await pageContext();
    if (reason === "other-company") session.grants![0]!.scope_id = ITEM;
    if (reason === "department") session.grants![0]!.scope_type = "department";
    if (reason === "expired") session.grants![0]!.valid_to = "2020-01-01";
    vi.mocked(pageContext).mockResolvedValue({ session, context });
    render(
      await InventoryPage({
        params: Promise.resolve({ segments: ["batches"] }),
      }),
    );
    expect(screen.queryByText("Tracking page")).toBeNull();
  },
);
it("opens standalone authoring with item read access", async () => {
  render(
    await ProductAttributesPage({
      searchParams: Promise.resolve({ item_id: ITEM }),
    }),
  );
  expect(screen.getByText("Attribute page")).toBeVisible();
});
it("rejects invalid routes and ambiguous product selectors", async () => {
  for (const segments of [
    ["batches", "bad"],
    ["serials", RECORD, "delete"],
    ["serials", RECORD, "history", "bad"],
  ])
    expect(() => trackingRoute(segments)).toThrow();
  await expect(
    ProductAttributesPage({
      searchParams: Promise.resolve({ item_id: ITEM, family_id: RECORD }),
    }),
  ).rejects.toThrow("not found");
  expect(trackingRoute(["batches", RECORD, "history", EVENT])).toMatchObject({
    page: "history",
    eventId: EVENT,
  });
});
