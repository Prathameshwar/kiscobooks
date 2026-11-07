import { createRequire } from "node:module";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect } from "vitest";
/** Reviews actual rendered controls with the application's own CSS and bundled font. */
export async function reviewProductLayout(
  container: HTMLElement,
  scenario: string,
) {
  const root = resolve("../../.."),
    artifact = resolve(root, ".test_artifacts/product-management-ui");
  const require = createRequire(resolve("package.json")),
    { chromium } = require(process.env.QA_PLAYWRIGHT!);
  const browser = await chromium.launch({
    executablePath: process.env.QA_BROWSER,
    headless: true,
  });
  const styles = [
    ...readFileSync(resolve("app/layout.tsx"), "utf8").matchAll(
      /import '@janso\/ui\/styles\/([^']+)'/g,
    ),
  ].map((match) => match[1]!);
  const font = readFileSync(
    resolve("../../packages/ui/src/assets/fonts/InterVariable.woff2"),
  ).toString("base64");
  const css =
    styles
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
  container.querySelectorAll("input").forEach((input) => {
    input.setAttribute("value", input.value);
    input.toggleAttribute("checked", input.checked);
  });
  container.querySelectorAll("textarea").forEach((input) => {
    input.textContent = input.value;
  });
  container.querySelectorAll("select").forEach((select) => {
    [...select.options].forEach((option) =>
      option.toggleAttribute("selected", option.selected),
    );
  });
  mkdirSync(artifact, { recursive: true });
  const results: object[] = [];
  try {
    for (const theme of ["light", "dark", "ledger"])
      for (const width of [1440, 768, 390, 320]) {
        const page = await browser.newPage({
          viewport: { width, height: 1000 },
        });
        await page.setContent(
          `<!doctype html><html data-theme="${theme}"><head><style>${css} body{overflow:auto}</style></head><body class="janso-root">${container.innerHTML}</body></html>`,
        );
        await page.evaluate((theme: string) => {
          document.documentElement.style.colorScheme =
            theme === "dark" ? "dark" : "light";
          return document.fonts.ready;
        }, theme);
        const geometry = await page.evaluate(() => ({
          width: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
          fields: [...document.querySelectorAll(".janso-field")].map(
            (element) => {
              const b = element.getBoundingClientRect();
              return { left: b.left, right: b.right, width: b.width };
            },
          ),
          grids: [...document.querySelectorAll(".janso-form-grid")].map(
            (element) =>
              getComputedStyle(element).gridTemplateColumns.split(" ").length,
          ),
        }));
        expect(geometry.scrollWidth).toBeLessThanOrEqual(width + 1);
        for (const field of geometry.fields) {
          expect(field.left).toBeGreaterThanOrEqual(-1);
          expect(field.right).toBeLessThanOrEqual(width + 1);
        }
        for (const columns of geometry.grids)
          expect(columns).toBeLessThanOrEqual(width <= 600 ? 1 : 2);
        const control = page
          .locator(
            "a[href],button:not([disabled]),input:not([disabled]),select:not([disabled])",
          )
          .first();
        await control.focus();
        expect(
          await control.evaluate(
            (element: Element) => element === document.activeElement,
          ),
        ).toBe(true);
        results.push({ scenario, theme, width, ...geometry });
        if (
          (width === 1440 && theme === "light") ||
          (width === 390 && theme === "dark")
        )
          await page.screenshot({
            path: resolve(artifact, `${scenario}-${theme}-${width}.png`),
            fullPage: true,
          });
        await page.close();
      }
    writeFileSync(
      resolve(artifact, scenario + "-geometry.json"),
      JSON.stringify(results, null, 2),
    );
  } finally {
    await browser.close();
  }
}
