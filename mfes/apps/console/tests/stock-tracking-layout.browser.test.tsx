import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, it, vi } from "vitest";
import { StockTrackingPage } from "../app/components/StockTrackingPage";
import { serviceCall } from "../app/lib/service-call";
import {
  COMPANY,
  ITEM,
  RECORD,
  EVENT,
  trackingFixture,
} from "./stock-tracking-fixtures";
import { reviewProductLayout } from "./product-layout-review";
vi.mock("../app/components/ProductModeProvider", () => ({
  useProductMode: () => ({ data: { product_family_sku_enabled: true } }),
}));
vi.mock("../app/lib/service-call", async (original) => ({
  ...(await original<typeof import("../app/lib/service-call")>()),
  serviceCall: vi.fn(),
}));
beforeEach(() => {
  vi.mocked(serviceCall).mockImplementation(
    async (_endpoint, request) => (() => { const row = trackingFixture(request); if ("code" in row) return {...row,code:"BANJARA-"+"B".repeat(92)}; if ("identifiers" in row) return {...row,identifiers:[{identifier_type:"SERIAL",slot:1,value:"BANJARA-"+"S".repeat(112)}]}; return row; })() as never,
  );
});
for (const kind of ["batches", "serials"] as const)
  it
    .runIf(
      process.env.QA_PRODUCT_MANAGEMENT_BROWSER === "1" &&
        (!process.env.QA_TRACKING_KIND ||
          process.env.QA_TRACKING_KIND === kind),
    )
    .each(["list", "new", "detail", "edit", "history", "event"] as const)(
    "reviews " + kind + " %s across themes and widths",
    async (scenario) => {
      const view = render(
        <StockTrackingPage
          company={COMPANY}
          kind={kind}
          id={scenario === "list" || scenario === "new" ? undefined : RECORD}
          itemId={ITEM}
          page={scenario === "event" ? "history" : scenario}
          eventId={scenario === "event" ? EVENT : undefined}
          access={{ manage: true, hold: true }}
        />,
      );
      if (scenario === "list")
        await screen.findByRole("link", { name: "View details" });
      else if (scenario === "new")
        await screen.findByLabelText(
          kind === "batches" ? "Batch code" : "SERIAL 1",
        );
      else if (scenario === "edit") await screen.findByLabelText("Reason");
      else if (scenario === "history")
        await screen.findByRole("link", { name: "View event" });
      else if (scenario === "event")
        await screen.findByRole("heading", { name: "correct" });
      else
        await screen.findByRole("heading", { name: /BANJARA-/ });
      await reviewProductLayout(view.container, kind + "-" + scenario);
      cleanup();
    },
    120000,
  );
