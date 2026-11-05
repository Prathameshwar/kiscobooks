'use client';

import { useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  DataTable,
  ErrorState,
  FormActions,
  Notice,
  PageHeader,
  PageNavigation,
  SectionHeader,
  Select,
  TextField,
  type Column,
} from '@janso/ui';
import {
  ruleConditions,
  useRoutePreview,
  useRoutingRules,
  useRoutingWrites,
  type RuleDraft,
  type RoutingRules,
} from '../lib/design-routing';
import { useDesignTemplates } from '../lib/design-templates';
import { VOUCHER_KINDS, kindLabel } from '../lib/voucher-kinds';

type Rule = RoutingRules['rules'][number];

/**
 * Which layout each kind of document prints on.
 *
 * The missing half of the designer: a tenant could author a template and had no way to say
 * *when* it is used. The service has had this surface all along — create, list, amend, and the
 * same `POST /resolve` the renderer will call.
 *
 * Three things on one screen, in the order the question is actually asked: the rules in force,
 * a way to add one, and a way to check what a given document would resolve to. The check is not
 * decoration — a rule set that looks right and resolves to something else is the failure this
 * screen exists to prevent, and the only honest way to test it is to ask the thing that will be
 * asked.
 *
 * Laid out like every other console page (design-system §4.2–4.3): each of the three is a
 * `SectionHeader` over its content, directly in the page column, so the column owns the spacing.
 * A `Card` has no padding of its own — what sits inside one goes in a `CardBody`, and its
 * committing action in the `FormActions` footer.
 */
export function DocumentRouting({
  company,
  canManage,
}: {
  company: string;
  /** `design.assignment.manage`. Without it this is a read-only list. */
  canManage: boolean;
}) {
  const { rules, loading, failure, refresh } = useRoutingRules(company);
  const { templates } = useDesignTemplates(company);
  const writes = useRoutingWrites(company);
  const preview = useRoutePreview(company);

  const [draft, setDraft] = useState<RuleDraft>({
    voucherKind: 'SALES',
    templateId: '',
    priority: '100',
    currencyCode: '',
    customerTaxCategory: '',
  });
  const [probe, setProbe] = useState({
    voucherKind: 'SALES',
    currencyCode: '',
    customerTaxCategory: '',
  });

  // Only a published template can be routed to: an assignment pointing at a draft resolves to
  // nothing, which is a rule that silently does not work.
  const routable = templates.filter((template) => template.current_version_id);
  const nameOf = (id: string) =>
    templates.find((template) => template.id === id)?.name ?? 'Unknown template';

  async function addRule(): Promise<void> {
    if (!draft.templateId) return;
    if (await writes.create(draft)) {
      setDraft({ ...draft, currencyCode: '', customerTaxCategory: '' });
      refresh();
    }
  }

  if (failure) {
    return (
      <div className="janso-page">
        <ErrorState status={failure.status === 403 ? 403 : 500} detail={failure.message} />
      </div>
    );
  }

  const columns: Column<Rule>[] = [
    { key: 'voucher_kind', header: 'Document', value: (rule) => kindLabel(rule.voucher_kind) },
    { key: 'template_id', header: 'Template', value: (rule) => nameOf(rule.template_id) },
    {
      key: 'conditions',
      header: 'Conditions',
      value: ruleConditions,
    },
    { key: 'priority', header: 'Priority', align: 'end' },
    {
      key: 'state',
      header: 'State',
      type: 'status',
      value: (rule) => (rule.is_active ? 'active' : 'retired'),
      label: (code) => (code === 'active' ? 'Active' : 'Retired'),
      tone: (code) => (code === 'active' ? 'success' : 'neutral'),
    },
    ...(canManage
      ? [
          {
            key: 'action',
            header: 'Action',
            hideHeader: true,
            type: 'custom',
            align: 'end',
            render: (rule) => (
              <Button
                variant="ghost"
                disabled={writes.pending}
                onClick={() =>
                  void writes.setActive(rule.id, !rule.is_active).then((ok) => {
                    if (ok) refresh();
                  })
                }
              >
                {rule.is_active ? 'Retire' : 'Reinstate'}
              </Button>
            ),
          } satisfies Column<Rule>,
        ]
      : []),
  ];

  return (
    <div className="janso-page">
      <PageNavigation
        back={{ href: '/invoice-designer', label: 'print templates' }}
        breadcrumbs={[
          { label: 'Print templates', href: '/invoice-designer' },
          { label: 'Routing' },
        ]}
      />
      <PageHeader
        title="Document routing"
        lede="Most companies never need this: every voucher already prints on the standard layout, and Voucher print gives one a layout of its own in a click. Use routing for the rare case of a different layout by currency or customer tax category. The rule with the highest priority wins; among equals, the one with more conditions, then the newer."
      />

      <SectionHeader
        title="Rules in force"
        description="Retired rules are kept and shown, so “why is it still printing the old design?” is answerable here."
      />
      <DataTable
        caption="Routing rules"
        columns={columns}
        rows={rules}
        rowId={(rule) => rule.id}
        rowLabel={(rule) => kindLabel(rule.voucher_kind)}
        loading={loading}
        emptyTitle="No routing rules yet"
        emptyBody="Without one, a document prints on the standard layout."
      />

      {canManage ? (
        <>
          <SectionHeader
            title="Add a rule"
            description="Leave a condition blank to match anything. A blank rule for a document kind is the default for that kind."
          />
          {routable.length === 0 ? (
            <>
              {writes.failure ? <Notice tone="danger">{writes.failure}</Notice> : null}
              <Notice tone="warning">
                Nothing to route to yet — a rule may only point at a template with a published
                version, because one pointing at a draft resolves to nothing.
              </Notice>
            </>
          ) : (
            <Card>
              <CardBody>
                <div className="janso-flow">
                  <div className="janso-form-grid console-routing-fields">
                    <Select
                      label="Document kind"
                      value={draft.voucherKind}
                      options={VOUCHER_KINDS}
                      onChange={(voucherKind) => setDraft({ ...draft, voucherKind })}
                    />
                    <Select
                      label="Template"
                      value={draft.templateId}
                      options={[
                        { value: '', label: 'Choose a published template' },
                        ...routable.map((template) => ({
                          value: template.id,
                          label: template.name,
                        })),
                      ]}
                      error={writes.fields?.template_id}
                      onChange={(templateId) => setDraft({ ...draft, templateId })}
                    />
                    <TextField
                      label="Priority"
                      hint="1–1000. Higher wins when two rules match."
                      value={draft.priority}
                      inputMode="numeric"
                      error={writes.fields?.priority}
                      onChange={(event) => setDraft({ ...draft, priority: event.target.value })}
                    />
                    <TextField
                      label="Currency (optional)"
                      hint="Three letters, e.g. INR."
                      value={draft.currencyCode}
                      maxLength={3}
                      error={writes.fields?.currency_code}
                      onChange={(event) => setDraft({ ...draft, currencyCode: event.target.value })}
                    />
                    <TextField
                      label="Customer tax category (optional)"
                      value={draft.customerTaxCategory}
                      maxLength={32}
                      error={writes.fields?.customer_tax_category}
                      onChange={(event) =>
                        setDraft({ ...draft, customerTaxCategory: event.target.value })
                      }
                    />
                  </div>
                  {writes.failure ? <Notice tone="danger">{writes.failure}</Notice> : null}
                </div>
              </CardBody>
              <FormActions>
                <Button
                  disabled={!draft.templateId || writes.pending}
                  loading={writes.pending}
                  onClick={() => void addRule()}
                >
                  Add rule
                </Button>
              </FormActions>
            </Card>
          )}
        </>
      ) : null}

      <SectionHeader
        title="Check a document"
        description="Asks the service the same question the renderer will ask, so a rule set that looks right but resolves wrong is caught here."
      />
      <Card>
        <CardBody>
          <div className="janso-flow">
            <div className="janso-form-grid console-routing-fields">
              <Select
                label="Document kind"
                value={probe.voucherKind}
                options={VOUCHER_KINDS}
                onChange={(voucherKind) => setProbe({ ...probe, voucherKind })}
              />
              <TextField
                label="Document currency"
                hint="Leave blank to ask about a document that names none."
                value={probe.currencyCode}
                maxLength={3}
                onChange={(event) => setProbe({ ...probe, currencyCode: event.target.value })}
              />
              <TextField
                label="Document tax category"
                value={probe.customerTaxCategory}
                maxLength={32}
                onChange={(event) =>
                  setProbe({ ...probe, customerTaxCategory: event.target.value })
                }
              />
            </div>
            {preview.failure ? <Notice tone="danger">{preview.failure}</Notice> : null}
            {preview.result ? (
              <Notice tone={preview.result.assignment_rule_id ? 'success' : 'warning'}>
                {/* Configured or defaulted is the distinction an operator needs: a null rule id
                  * means nothing matched and the most recently published template was used. */}
                {preview.result.assignment_rule_id
                  ? `A matching rule routes this to ${preview.result.template_name} (${preview.result.template_code}), version ${preview.result.version_number}.`
                  : `No rule matched. This falls back to ${preview.result.template_name} (${preview.result.template_code}), version ${preview.result.version_number} — the company’s most recently published template.`}
              </Notice>
            ) : null}
          </div>
        </CardBody>
        <FormActions>
          <Button variant="ghost" loading={preview.pending} onClick={() => void preview.run(probe)}>
            Resolve
          </Button>
        </FormActions>
      </Card>
    </div>
  );
}
