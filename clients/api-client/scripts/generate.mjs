import { readFile, writeFile } from "node:fs/promises";
import openapiTS, { astToString } from "openapi-typescript";

const requested = process.argv.find((argument) => argument.startsWith("--service="))?.split("=")[1];
const services = ["catalog", "identity", "accounting", "audit", "vouchers", "reports", "notification", "design"];
if (requested && !services.includes(requested)) throw new Error("Unknown service");
for (const service of requested ? [requested] : services) {
  const source = new URL(`../../../apis/${service}/openapi.json`, import.meta.url);
  const output = new URL(`../src/${service}.d.ts`, import.meta.url);
  const generated = astToString(await openapiTS(source, { defaultNonNullable: false }));
  if (process.argv.includes("--check")) {
    if (await readFile(output, "utf8") !== generated) {
      throw new Error(`${service} client is stale; regenerate after exporting OpenAPI`);
    }
  } else {
    await writeFile(output, generated);
  }
}
