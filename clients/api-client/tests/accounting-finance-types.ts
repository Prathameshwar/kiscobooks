import type { components } from "../src/accounting.js";
import { createAccountingClient } from "../src/index.js";

type Schema = components["schemas"];
const line: Schema["JournalLineCreate"] = { account_id: "account", side: "DEBIT", currency: "INR", amount: "10.1234", exchange_rate: "1" };
// @ts-expect-error Financial money must be an exact decimal string.
const floating: Schema["JournalLineCreate"]["amount"] = 0.1;
// @ts-expect-error Ordinary clients cannot author realized FX journal components.
const fx: Schema["JournalLineCreate"] = { ...line, component: "FX" };
const credit: Schema["CreditRequest"] = { account_id: "account", currency: "INR", amount: "10", exchange_rate: "1", posting_date: "2026-04-02", source_system: "billing", source_type: "invoice", source_id: "source", expires_at: "2026-04-02T12:00:00Z" };
const charge: Schema["ChargeRequest"] = { item_id: "item", policy_id: "policy", coverage_end_date: "2026-04-20", posting_date: "2026-04-20", due_date: "2026-05-01", exchange_rate: "1" };
async function financialConsumers(client: ReturnType<typeof createAccountingClient>) {
  const params = { path: { company_id: "company" }, header: { "Idempotency-Key": "stable-command-key" } };
  const opening = await client.POST("/v1/companies/{company_id}/opening-batches", { params, body: { posting_date: "2026-04-01", description: "Explicit zero opening" } });
  const reservation = await client.POST("/v1/companies/{company_id}/credit-reservations", { params, body: credit });
  const assessment = await client.POST("/v1/companies/{company_id}/charge-assessments", { params, body: charge });
  const reconciliation = await client.GET("/v1/companies/{company_id}/subledger/reconciliation", { params: { path: params.path, query: { account_id: "account", as_of: "2026-04-30", currency: "INR" } } });
  const amount: string | null | undefined = reservation.data?.amount;
  const difference: string | undefined = reconciliation.data?.difference;
  return { opening, assessment, amount, difference };
}
void financialConsumers;
void floating;
void fx;
