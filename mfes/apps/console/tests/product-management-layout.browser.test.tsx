import { createRequire } from "node:module";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, cleanup } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { ProductCatalogDetail } from "../app/components/ProductCatalogDetail";
import { ProductCatalogEditor } from "../app/components/ProductCatalogEditor";
import { SimpleProductRecord } from "../app/components/SimpleProductRecord";
import { serviceCall } from "../app/lib/service-call";
import { masterConfig } from "../app/lib/catalog-masters";
import {
  access,
  fields,
  record,
  response,
  COMPANY,
  RECORD,
} from "./product-classification-fixtures";

vi.mock("../app/lib/service-call", async (original) => ({
  ...(await original<typeof import("../app/lib/service-call")>()),
  serviceCall: vi.fn(),
}));
vi.mock("../app/components/ProductModeProvider", () => ({
  useProductMode: () => ({
    company: COMPANY,
    data: {
      company_id: COMPANY,
      row_version: 1,
      policy_generation: 1,
      product_family_sku_enabled: false,
    },
    loading: false,
    failure: null,
    refresh: vi.fn(),
  }),
}));
const root = resolve("../../.."),
  artifact = resolve(root, ".test_artifacts/product-management-ui");
const longName =
  "Banjara warehouse product with a detailed supplier description and a long product label";
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path.includes("/products/field-set"))
      return {
        company_id: COMPANY,
        authoring_version: 1,
        fields: [
          ...fields("catalog.item", "update").map((field) => ({
            ...field,
            key: field.key === "sku" ? "code" : field.key,
          })),
          ...fields("catalog.product_family", "update").filter(
            (field) => field.key === "description",
          ),
        ],
      } as never;
    if (request.path.includes("/products/" + RECORD))
      return {
        ...record("items"),
        code: "STANDARD",
        name: longName,
        description: "A readable multi-line product description.",
        revision: "test-product-revision",
        authoring_version: 1,
        shared_custom_fields: {},
      } as never;
    const result = response(request);
    if (
      request.path.endsWith("/items/" + RECORD) ||
      request.path.endsWith("/product-families/" + RECORD)
    )
      return { ...(result as object), name: longName } as never;
    return result as never;
  });
});

it
  .runIf(process.env.QA_PRODUCT_MANAGEMENT_BROWSER === "1")
  .each([
    "simple-detail",
    "simple-edit",
    "simple-completion",
    "sku-detail",
    "sku-edit",
    "sku-completion",
    "family-detail",
    "family-edit",
    "family-completion",
  ])(
  "reviews %s in desktop, tablet and phone layouts across all themes",
  async (scenario) => {
    const require = createRequire(resolve("package.json"));
    const { chromium } = require(
      process.env.QA_PLAYWRIGHT ||
        resolve(root, ".tools/ui-review-runner/node_modules/playwright"),
    );
    const browser = await chromium.launch({
      executablePath: process.env.QA_BROWSER,
      headless: true,
    });
    mkdirSync(artifact, { recursive: true });
    const stylesheetNames = [
      ...readFileSync(resolve("app/layout.tsx"), "utf8").matchAll(
        /import '@janso\/ui\/styles\/([^']+)'/g,
      ),
    ].map((match) => match[1]!);
    const font = readFileSync(
      resolve("../../packages/ui/src/assets/fonts/InterVariable.woff2"),
    ).toString("base64");
    const css =
      stylesheetNames
        .map((name) =>
          readFileSync(resolve("../../packages/ui/src/styles", name), "utf8"),
        )
        .join("\n")
        .replace(
          "../assets/fonts/InterVariable.woff2",
          "data:font/woff2;base64," + font,
        ) +
      "\n" +
      readFileSync(resolve("app/globals.css"), "utf8") +
      "\n" +
      readFileSync(resolve("app/console.css"), "utf8");
    try {
      const common = {
        company: COMPANY,
        config: masterConfig(
          scenario.startsWith("family") ? "product-families" : "items",
        )!,
        id: RECORD,
        access,
        canManage: true,
      };
      const view = render(
        scenario.startsWith("simple") ? (
          <SimpleProductRecord
            {...common}
            editing={scenario.endsWith("edit")}
            completed={scenario.endsWith("completion")}
          />
        ) : scenario.endsWith("edit") ? (
          <ProductCatalogEditor {...common} />
        ) : (
          <ProductCatalogDetail
            {...common}
            completed={scenario.endsWith("completion")}
          />
        ),
      );
      await screen.findByRole("heading", {
        name: scenario.endsWith("edit")
          ? /Edit product/i
          : scenario.endsWith("completion")
            ? scenario.startsWith("family")
              ? "Product Profile saved"
              : "Product saved"
            : longName,
      });
      await screen
        .findByRole("region", { name: "Record details" })
        .catch(() => undefined);
      // Wait for the actual field controls rather than snapshotting a loading state.
      if (scenario.endsWith('edit')) await screen.findByLabelText("Name");
      else await screen.findByRole('heading', { name: 'Product overview' });
      // Preserve live form state when carrying the rendered component DOM into Chromium.
      view.container.querySelectorAll("input").forEach((input) => {
        input.setAttribute("value", input.value);
        if (input.checked) input.setAttribute("checked", "");
        else input.removeAttribute("checked");
      });
      const markup = view.container.innerHTML;
      writeFileSync(resolve(artifact, scenario + ".html"), markup);
      const measurements: object[] = [];
      for (const theme of ["light", "dark", "ledger"])
        for (const width of [1440, 768, 390, 320]) {
          const page = await browser.newPage({
            viewport: { width, height: 1000 },
          });
          await page.setContent(
            `<!doctype html><html data-theme="${theme}"><head><style>${css} body { overflow:auto; }</style></head><body class="janso-root">${markup}</body></html>`,
          );
          await page.evaluate((theme: string) => {
            document.documentElement.style.colorScheme =
              theme === "dark" ? "dark" : "light";
            return document.fonts.ready;
          }, theme);
          const geometry = await page.evaluate(() => {
            const rect = (element: Element) => {
              const box = element.getBoundingClientRect();
              return {
                left: box.left,
                right: box.right,
                top: box.top,
                width: box.width,
              };
            };
            const textarea = document.querySelector("textarea");
            const grid = textarea?.closest(".janso-form-grid");
            const firstGrid = document.querySelector(".janso-form-grid");
            return {
              width: document.documentElement.clientWidth,
              scrollWidth: document.documentElement.scrollWidth,
              columns: firstGrid
                ? getComputedStyle(firstGrid).gridTemplateColumns.split(" ")
                    .length
                : 0,
              controls: [...document.querySelectorAll(".janso-field")].map(
                rect,
              ),
              textarea: textarea ? rect(textarea) : null,
              grid: grid ? rect(grid) : null,
            };
          });
          expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width + 1);
          if (scenario.endsWith("edit"))
            expect(geometry.columns).toBeLessThanOrEqual(2);
          for (const field of geometry.controls) {
            expect(field.left).toBeGreaterThanOrEqual(-1);
            expect(field.right).toBeLessThanOrEqual(width + 1);
          }
          if (scenario === "simple-edit" && geometry.textarea && geometry.grid)
            expect(geometry.textarea.width).toBeCloseTo(geometry.grid.width, 0);
          const focusable = page
            .locator("input:not([disabled]),button:not([disabled]),a[href]")
            .first();
          await focusable.focus();
          expect(
            await focusable.evaluate(
              (element: Element) => element === document.activeElement,
            ),
          ).toBe(true);
          measurements.push({ scenario, theme, width, ...geometry });
          if (
            (width === 1440 && theme === "light") ||
            (width === 390 && theme !== "light")
          )
            await page.screenshot({
              path: resolve(artifact, `${scenario}-${theme}-${width}.png`),
              fullPage: true,
            });
          await page.close();
        }
      writeFileSync(
        resolve(artifact, scenario + "-geometry.json"),
        JSON.stringify(measurements, null, 2),
      );
      cleanup();
    } finally {
      await browser.close();
    }
  },
  120000,
);
