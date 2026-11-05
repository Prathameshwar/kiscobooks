import type {
  AccountingField,
  AccountingResourceConfig,
} from './accounting-configuration-resources';
import {
  accountingLink,
  accountingResource,
  accountingUUID,
} from './accounting-configuration-resources';
export const accountingMasters = [
  'account-heads',
  'account-groups',
  'accounts',
  'parties',
  'party-commercial-types',
  'payment-terms',
  'withholding-sections',
  'withholding-rates',
  'exchange-rates',
  'charge-policies',
] as const;
export const accountingDescriptions: Record<string, string> = {
  'account-heads':
    'Review the installed chart headings used to classify account groups. Headings are maintained by the chart setup.',
  'account-groups':
    'Organise ledger accounts under the correct account head and optional parent group.',
  accounts:
    'Manage general, cash, bank, party and tax accounts, plus inventory and asset control ledgers. Complete required profiles before activation.',
  parties:
    'Manage shared customer and supplier identities, then add their roles, contacts and commercial defaults.',
  'party-commercial-types':
    'Define commercial classifications and assign them to parties through dated memberships.',
  'payment-terms':
    'Define payment conditions and their instalments for customer and supplier transactions.',
  'withholding-sections':
    'Maintain statutory withholding sections with verified official source evidence.',
  'withholding-rates':
    'Maintain exact, dated withholding rates by section and deductee type, supported by official evidence.',
  'exchange-rates':
    'Record exact currency quotes and submit them for independent review before use.',
  'charge-policies':
    'Define dated fixed charges or interest for party accounts, with calculation limits and tax treatment.',
};
export function accountingDescription(config: AccountingResourceConfig) {
  return (
    accountingDescriptions[config.resource] ??
    `Review and maintain ${config.title.toLowerCase()} for the current company.`
  );
}
export function accountingFieldSections(
  fields: AccountingField[],
  resource?: string,
) {
  const sections = [
    {
      title: 'Identity and references',
      keys: [
        'code',
        'name',
        'label',
        'legal_name',
        'kind',
        'party_id',
        'party_role',
        'account_id',
        'offset_account_id',
        'group_id',
        'head_id',
        'parent_id',
        'section_id',
        'deductee_type',
        'commercial_type_id',
        'payment_term_id',
      ],
    },
    {
      title: 'Dates and calculation',
      keys: [
        'valid_from',
        'valid_to',
        'accrual_start_date',
        'currency',
        'currency_mode',
        'rate',
        'rate_percent',
        'no_pan_rate_percent',
        'percentage',
        'method',
        'rate_period',
        'compound',
        'basis',
        'day_basis',
        'grace_days',
        'minimum',
        'cap',
        'charge_on_charge',
        'days',
      ],
    },
    {
      title: 'Evidence and tax treatment',
      keys: [
        'source_reference',
        'source_url',
        'source_sha256',
        'tax_treatment',
        'tax_reason',
        'description',
      ],
    },
  ];
  const grouped =
    resource === 'accounts'
      ? [
          {
            title: 'Account identity',
            keys: [
              'code',
              'name',
              'group_id',
              'kind',
              'party_role',
              'party_id',
            ],
          },
          {
            title: 'Currency and rounding',
            keys: [
              'currency_mode',
              'currency',
              'rounding_method',
              'rounding_limit',
            ],
          },
          {
            title: 'Posting controls',
            keys: ['posting_policy', 'inventory_affected', 'sort_order'],
          },
          { title: 'Description', keys: ['description'] },
        ]
      : resource === 'parties'
        ? [
            {
              title: 'Party identity',
              keys: [
                'code',
                'name',
                'legal_name',
                'party_type',
                'country_code',
              ],
            },
            { title: 'Notes', keys: ['notes'] },
          ]
        : sections;
  const assigned = new Set(grouped.flatMap((section) => section.keys));
  return [
    ...grouped.map((section) => ({
      title: section.title,
      fields: fields.filter((field) => section.keys.includes(field.key)),
    })),
    {
      title: 'Additional settings',
      fields: fields.filter((field) => !assigned.has(field.key)),
    },
  ].filter((section) =>
    section.fields.some(
      (field) => field.visible && (field.readable || field.control.write_only),
    ),
  );
}
export function accountingRelations(
  resource: string,
): { resource: string; filter: string }[] {
  return (
    (
      {
        'account-heads': [{ resource: 'account-groups', filter: 'head_id' }],
        'account-groups': [
          { resource: 'account-groups', filter: 'parent_id' },
          { resource: 'accounts', filter: 'group_id' },
        ],
        'withholding-sections': [
          { resource: 'withholding-rates', filter: 'section_id' },
        ],
      } as Record<string, { resource: string; filter: string }[]>
    )[resource] ?? []
  );
}

/** Use implemented, natively filtered directories and current-company target grants. */
export function accountingRelatedRowActions(
  resource: string,
  id: string,
  available: readonly string[],
  back: string,
) {
  if (!accountingUUID.test(id)) return [];
  const links = [...accountingRelations(resource)];
  if (resource === 'parties')
    links.push({ resource: 'accounts', filter: 'party_id' });
  if (resource === 'accounts')
    links.push({ resource: 'charge-policies', filter: 'account_id' });
  if (resource === 'payment-terms')
    links.push({ resource: 'payment-term-lines', filter: 'payment_term_id' });
  return links.flatMap((link) => {
    const config = accountingResource(link.resource);
    if (!config || !available.includes(link.resource)) return [];
    const label =
      link.filter === 'parent_id'
        ? 'child groups'
        : link.resource === 'accounts'
          ? 'ledger accounts'
          : config.title.toLowerCase();
    return [
      {
        id: 'related-' + link.resource + '-' + link.filter,
        label: 'View ' + label,
        href: accountingLink(
          '/accounting/' +
            link.resource +
            '?' +
            new URLSearchParams({ [link.filter]: id }),
          back,
        ),
      },
    ];
  });
}

/** Organise only the related resources already admitted by current-company grants. */
export function accountingRelationshipSections<
  T extends { config: AccountingResourceConfig },
>(resource: string, related: T[]) {
  const groups =
    resource === 'parties'
      ? [
          {
            title: 'Identity and roles',
            keys: ['party-roles', 'party-commercial-type-memberships'],
          },
          {
            title: 'Contacts and addresses',
            keys: [
              'party-addresses',
              'party-address-uses',
              'party-contacts',
              'party-contact-uses',
            ],
          },
          {
            title: 'Tax and identifiers',
            keys: [
              'party-identifiers',
              'party-tax-registrations',
              'party-registration-addresses',
              'party-withholding-profiles',
              'withholding-certificates',
            ],
          },
          {
            title: 'Banking and commercial policies',
            keys: [
              'party-bank-accounts',
              'party-accounting-policies',
              'party-credit-policies',
            ],
          },
        ]
      : resource === 'accounts'
        ? [
            {
              title: 'Aliases and references',
              keys: ['account-aliases', 'account-external-keys'],
            },
            {
              title: 'Bank and tax profiles',
              keys: [
                'account-bank-profiles',
                'account-tax-profiles',
                'account-tax-defaults',
              ],
            },
            {
              title: 'Posting and charges',
              keys: ['posting-mappings', 'charge-policies'],
            },
          ]
        : [];
  const assigned = new Set(groups.flatMap((group) => group.keys));
  return [
    ...groups.map((group) => ({
      title: group.title,
      items: related.filter((item) =>
        group.keys.includes(item.config.resource),
      ),
    })),
    {
      title: groups.length ? 'Other configuration' : 'Available configuration',
      items: related.filter((item) => !assigned.has(item.config.resource)),
    },
  ].filter((group) => group.items.length);
}
