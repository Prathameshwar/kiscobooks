import type { components } from "../src/accounting.js";
import type { components as IdentityComponents } from "../src/identity.js";
import { createAccountingClient } from "../src/index.js";

const ledger: components["schemas"]["AccountCreate"] = {
  code: "SALES", name: "Sales", group_id: "group", inventory_affected: true,
  rounding_method: "NORMAL", rounding_limit: "0.5000", sort_order: 10,
};
// @ts-expect-error Decimal input contracts require exact strings.
const floatLimit: components["schemas"]["AccountCreate"]["rounding_limit"] = 0.5;
// @ts-expect-error Duty classification is a closed native vocabulary.
const wrongDuty: components["schemas"]["AccountTaxProfileCreate"]["duty_type"] = "UNKNOWN";
const aliasPolicy: IdentityComponents["schemas"]["PolicyWrite"]["entity_type"] = "accounting.account_group_alias";
const aliasPolicyResult: IdentityComponents["schemas"]["PolicyItem"]["entity_type"] = aliasPolicy;

async function listRegistrationAddresses(client: ReturnType<typeof createAccountingClient>) {
  const result = await client.GET("/v1/companies/{company_id}/party-registration-addresses", {
    params: { path: { company_id: "company" }, query: { party_id: "party", as_of: "2026-09-14" } },
  });
  const registration: string | null | undefined = result.data?.items[0]?.registration_id;
  const address: string | null | undefined = result.data?.items[0]?.address_id;
  return { registration, address };
}
void listRegistrationAddresses;

async function exportEveryMaster(client: ReturnType<typeof createAccountingClient>) {
  const params = { path: { company_id: "company" } };
  const account_head = await client.GET("/v1/companies/{company_id}/exports/account-heads", { params });
  const account_headId: string | undefined = account_head.data?.items[0]?.id;
  const accounting_setup = await client.GET("/v1/companies/{company_id}/exports/accounting-setup", { params });
  const accounting_setupId: string | undefined = accounting_setup.data?.items[0]?.id;
  const account_group = await client.GET("/v1/companies/{company_id}/exports/account-groups", { params });
  const account_groupId: string | undefined = account_group.data?.items[0]?.id;
  const account_group_alias = await client.GET("/v1/companies/{company_id}/exports/account-group-aliases", { params });
  const account_group_aliasId: string | undefined = account_group_alias.data?.items[0]?.id;
  const account_group_closure = await client.GET("/v1/companies/{company_id}/exports/group-paths", { params });
  const account_group_closureId: string | undefined = account_group_closure.data?.items[0]?.id;
  const party = await client.GET("/v1/companies/{company_id}/exports/parties", { params });
  const partyId: string | undefined = party.data?.items[0]?.id;
  const party_role = await client.GET("/v1/companies/{company_id}/exports/party-roles", { params });
  const party_roleId: string | undefined = party_role.data?.items[0]?.id;
  const payment_term = await client.GET("/v1/companies/{company_id}/exports/payment-terms", { params });
  const payment_termId: string | undefined = payment_term.data?.items[0]?.id;
  const payment_term_line = await client.GET("/v1/companies/{company_id}/exports/payment-term-lines", { params });
  const payment_term_lineId: string | undefined = payment_term_line.data?.items[0]?.id;
  const account = await client.GET("/v1/companies/{company_id}/exports/accounts", { params });
  const accountId: string | undefined = account.data?.items[0]?.id;
  const account_alias = await client.GET("/v1/companies/{company_id}/exports/account-aliases", { params });
  const account_aliasId: string | undefined = account_alias.data?.items[0]?.id;
  const account_external_key = await client.GET("/v1/companies/{company_id}/exports/account-external-keys", { params });
  const account_external_keyId: string | undefined = account_external_key.data?.items[0]?.id;
  const party_address = await client.GET("/v1/companies/{company_id}/exports/party-addresses", { params });
  const party_addressId: string | undefined = party_address.data?.items[0]?.id;
  const party_tax_registration = await client.GET("/v1/companies/{company_id}/exports/party-tax-registrations", { params });
  const party_tax_registrationId: string | undefined = party_tax_registration.data?.items[0]?.id;
  const party_address_use = await client.GET("/v1/companies/{company_id}/exports/party-address-uses", { params });
  const party_address_useId: string | undefined = party_address_use.data?.items[0]?.id;
  const party_contact = await client.GET("/v1/companies/{company_id}/exports/party-contacts", { params });
  const party_contactId: string | undefined = party_contact.data?.items[0]?.id;
  const party_contact_use = await client.GET("/v1/companies/{company_id}/exports/party-contact-uses", { params });
  const party_contact_useId: string | undefined = party_contact_use.data?.items[0]?.id;
  const party_identifier = await client.GET("/v1/companies/{company_id}/exports/party-identifiers", { params });
  const party_identifierId: string | undefined = party_identifier.data?.items[0]?.id;
  const party_registration_address = await client.GET("/v1/companies/{company_id}/exports/party-registration-addresses", { params });
  const party_registration_addressId: string | undefined = party_registration_address.data?.items[0]?.id;
  const party_bank_account = await client.GET("/v1/companies/{company_id}/exports/party-bank-accounts", { params });
  const party_bank_accountId: string | undefined = party_bank_account.data?.items[0]?.id;
  const party_commercial_type = await client.GET("/v1/companies/{company_id}/exports/party-commercial-types", { params });
  const party_commercial_typeId: string | undefined = party_commercial_type.data?.items[0]?.id;
  const party_commercial_type_membership = await client.GET("/v1/companies/{company_id}/exports/party-commercial-type-memberships", { params });
  const party_commercial_type_membershipId: string | undefined = party_commercial_type_membership.data?.items[0]?.id;
  const party_accounting_policy = await client.GET("/v1/companies/{company_id}/exports/party-accounting-policies", { params });
  const party_accounting_policyId: string | undefined = party_accounting_policy.data?.items[0]?.id;
  const party_credit_policy = await client.GET("/v1/companies/{company_id}/exports/party-credit-policies", { params });
  const party_credit_policyId: string | undefined = party_credit_policy.data?.items[0]?.id;
  const account_tax_profile = await client.GET("/v1/companies/{company_id}/exports/account-tax-profiles", { params });
  const account_tax_profileId: string | undefined = account_tax_profile.data?.items[0]?.id;
  const account_bank_profile = await client.GET("/v1/companies/{company_id}/exports/account-bank-profiles", { params });
  const account_bank_profileId: string | undefined = account_bank_profile.data?.items[0]?.id;
  const account_template_installation = await client.GET("/v1/companies/{company_id}/exports/template-installations", { params });
  const account_template_installationId: string | undefined = account_template_installation.data?.items[0]?.id;
  const account_template_binding = await client.GET("/v1/companies/{company_id}/exports/template-bindings", { params });
  const account_template_bindingId: string | undefined = account_template_binding.data?.items[0]?.id;
  const account_posting_mapping = await client.GET("/v1/companies/{company_id}/exports/posting-mappings", { params });
  const account_posting_mappingId: string | undefined = account_posting_mapping.data?.items[0]?.id;
  // @ts-expect-error Beneficiary secrets are absent from typed exports.
  party_bank_account.data?.items[0]?.account_number;
}
void [ledger, floatLimit, wrongDuty, aliasPolicy, aliasPolicyResult, exportEveryMaster];
