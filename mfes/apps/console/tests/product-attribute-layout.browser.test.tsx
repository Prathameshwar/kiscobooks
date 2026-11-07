import { fields } from "./product-classification-fixtures";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ProductAttributeAuthoring } from "../app/components/ProductAttributeAuthoring";
import { serviceCall } from "../app/lib/service-call";
import { attributeFixture } from "./product-authoring-fixtures";
import { reviewProductLayout } from "./product-layout-review";
vi.mock("../app/components/ProductModeProvider", () => ({
  useProductMode: () => ({
    data: { product_family_sku_enabled: true },
    loading: false,
    failure: null,
  }),
}));
vi.mock("../app/lib/service-call", async (original) => ({
  ...(await original<typeof import("../app/lib/service-call")>()),
  serviceCall: vi.fn(),
}));
beforeEach(() => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) =>
    request.path.includes("/field-set")
      ? ({
          company_id: "01900000-0000-7000-8000-000000000001",
          entity_type: "catalog.item",
          fields: fields("catalog.item", "create"),
        } as never)
      : request.path.endsWith("/attribute-form")
        ? (attributeFixture as never)
        : ({ items: [], page: { limit: 50, has_more: false } } as never),
  );
});
it
  .runIf(process.env.QA_PRODUCT_MANAGEMENT_BROWSER === "1")
  .each(["attribute-values", "attribute-configure", "attribute-variant"])(
  "reviews %s across themes and screen widths",
  async (scenario) => {
    const view = render(
      <ProductAttributeAuthoring
        company="01900000-0000-7000-8000-000000000001"
        itemId={attributeFixture.item_id}
        canManage
        canCreate
      />,
    );
    await screen.findByLabelText("Warranty eligible");
    if (scenario === "attribute-configure")
      fireEvent.click(
        screen.getByRole("button", { name: "Configure Profile attributes" }),
      );
    if (scenario === "attribute-variant")
      fireEvent.click(screen.getByRole("button", { name: "Add variant" }));
    if (scenario === "attribute-variant")
      await waitFor(() =>
        expect(screen.getByLabelText("SKU")).not.toBeDisabled(),
      );
    await reviewProductLayout(view.container, scenario);
    cleanup();
  },
  120000,
);
