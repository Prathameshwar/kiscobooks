'use client';

import { useState } from 'react';
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardHeader,
  ConfirmDialog,
  DataTable,
  Disclosure,
  ErrorState,
  FormActions,
  Notice,
  PageHeader,
  PageNavigation,
  SectionHeader,
  Select,
  type Column,
} from '@janso/ui';
import { NewTemplateDialog } from '../(editor)/invoice-designer/NewTemplateDialog';
import {
  compareRules,
  isDefaultRule,
  isPublished,
  layoutInUse,
  ruleConditions,
  sameCriteria,
  useRoutingRules,
  useRoutingWrites,
  type RoutingRules,
} from '../lib/design-routing';
import { useDesignTemplates } from '../lib/design-templates';
import { MANAGE_VOUCHER_TYPES, kindLabel, kindSummary } from '../lib/voucher-kinds';

type Rule = RoutingRules['rules'][number];

/** The priority a default is written at: the usual 100, or the winning default's, so a newer rule wins the tie. */
const DEFAULT_PRIORITY = 100;

/**
 * One voucher kind's print: what it prints on now, and a way to make it its own.
 *
 * **Nobody has to do anything.** A voucher prints on the standard layout until a layout is set for
 * it, so this page opens on an answer — "Standard layout" — rather than an empty list asking for
 * setup. The one thing most people ever do here is **Customize layout**: it starts a new template
 * *and* makes it this kind's layout in the same step, so there is no routing to understand. Until
 * that template is published whatever printed before keeps printing — the service skips a rule whose
 * template has no published version — and the page says so rather than showing a custom layout that
 * is not yet in use. **Back to standard layout** undoes it.
 *
 * Templates, rules, priorities and conditions are still all here, but behind **Advanced**, because
 * they are the mechanism and not the thing a person came to do.
 *
 * **What is "in use" is what the service would resolve**, not what this company last wrote. An
 * ordinary document can only match a default rule, and the first by priority, then newer, wins —
 * *whoever owns it* — so a default set for the whole organisation can outrank this company's own, and
 * a rule on a draft is skipped in favour of the next. The card is read off `layoutInUse`, the same
 * function the cards page uses, so the two cannot disagree.
 *
 * **One default per company per kind.** The service allows one active rule per exact set of
 * voucher type, branch, currency and tax category *for a company*, whichever template it names, so a
 * second default is a 409 until the first is retired — and the check is not made when a retired rule
 * is switched back on, so *Reinstate* is withheld while an identical rule is in force. A default set
 * for the whole organisation does not collide with the company's own, and is somebody else's to change.
 *
 * Authority is read piece by piece, never as one gate: a reader sees the page without the buttons,
 * and a template author without routing access can still start a template. The service re-checks
 * every request against the actor's grants and the company.
 */
export function VoucherPrintKind({
  company,
  kind,
  canManageTemplates,
  canReadRouting,
  canManageRouting,
  returnTo,
}: {
  company: string;
  /** The `VOUCHER_KINDS` code, already validated against the vocabulary by the page. */
  kind: string;
  /** `design.template.manage` — starting a new template. */
  canManageTemplates: boolean;
  /** `design.assignment.read` — knowing which layout is in use, and the table of rules. */
  canReadRouting: boolean;
  /** `design.assignment.manage` — making a template this kind's layout, and going back to standard. */
  canManageRouting: boolean;
  returnTo?: string;
}) {
  const label = kindLabel(kind);
  const lower = label.toLowerCase();
  const {
    templates,
    hasMore: moreTemplates,
    loading: loadingTemplates,
    failure: templatesFailure,
    refresh: refreshTemplates,
  } = useDesignTemplates(company);
  const routing = useRoutingRules(canReadRouting ? company : undefined, kind);
  const writes = useRoutingWrites(company);
  const [creating, setCreating] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [templateId, setTemplateId] = useState('');

  const failure = templatesFailure ?? routing.failure;
  if (failure) {
    if (failure.status === 403) {
      return (
        <div className="janso-page">
          <ErrorState status={403} detail={failure.message} />
        </div>
      );
    }
    // A failed *re-read* after a write that went through also lands here, so the message must not claim
    // nothing changed, and there has to be a way to ask again.
    return (
      <div className="janso-page">
        <Notice tone="danger">
          {failure.message}{' '}
          <Button
            variant="ghost"
            onClick={() => {
              routing.refresh();
              refreshTemplates();
            }}
          >
            Try again
          </Button>
        </Notice>
      </div>
    );
  }

  const byId = new Map(templates.map((template) => [template.id, template]));
  const nameOf = (rule: Rule) => byId.get(rule.template_id)?.name ?? 'Unknown template';
  // Two rules on one template (a default and a currency rule is common) must not share a name.
  const ruleName = (rule: Rule) => (isDefaultRule(rule) ? nameOf(rule) : `${nameOf(rule)}, ${ruleConditions(rule)}`);
  // In force first, then in the order the service resolves them.
  const rules = [...routing.rules].sort(
    (left, right) => Number(right.is_active) - Number(left.is_active) || compareRules(left, right),
  );
  const loading = routing.loading || loadingTemplates;

  const { winner, without, special } = layoutInUse(rules, byId, company);
  const winnerLayout = winner ? byId.get(winner.template_id) : undefined;
  const ownWins = !!winner && winner.company_id === company;
  // This company's own default, in whatever state its template is in. Only one can be in force; the
  // first by resolution order is the one the page speaks of.
  const own = rules.find((rule) => rule.is_active && isDefaultRule(rule) && rule.company_id === company);
  const ownLayout = own ? byId.get(own.template_id) : undefined;
  const ownLive = isPublished(ownLayout);
  // What `Back to standard layout` ends: the rule actually deciding, or else the company's draft.
  const target = ownWins ? winner : own;
  const printsNow = winnerLayout ? winnerLayout.name : 'the standard layout';
  const priority = String(Math.max(DEFAULT_PRIORITY, winner?.priority ?? 0));
  // Purchase has a standard canvas to start from (plan R4); the other kinds do not yet.
  const opensOn = kind === 'PURCHASE' ? 'on a copy of the standard layout' : 'on an empty page';

  // Only a published template can be chosen as the layout from the advanced list.
  // A design made for another kind cannot be routed here; the service refuses it too.
  const routable = templates.filter((template) => isPublished(template) && (!template.voucher_kind || template.voucher_kind === kind));
  // Derived, never stored on its own: a choice that has left the list must not stay armed behind a
  // select that shows its placeholder.
  const chosen = routable.some((template) => template.id === templateId) ? templateId : '';
  // Either list running past its page means "no layout of its own" or "this template exists" may be
  // read off an incomplete answer, so nothing is claimed.
  const incomplete = routing.hasMore || moreTemplates;
  const canRoute = canManageRouting && canReadRouting;

  /**
   * Whether this actor may flip this rule from here: they hold the grant and the rule is this
   * company's own (a tenant-wide rule needs a tenant-level grant the console cannot tell the actor
   * has). Retiring is always safe. *Reinstating* also needs a template this page can see — an archived
   * template's rules were retired *because* it was archived — and no identical rule already in force,
   * which the service would have refused to write but does not check when a rule is switched back on.
   */
  const mayToggle = (rule: Rule) =>
    canManageRouting &&
    rule.company_id === company &&
    (rule.is_active ||
      (byId.has(rule.template_id) &&
        !rules.some((other) => other.is_active && other.id !== rule.id && sameCriteria(other, rule))));

  /** The kind's default rule: no conditions. */
  const routeTo = (id: string) =>
    writes.create({ voucherKind: kind, templateId: id, priority, currencyCode: '', customerTaxCategory: '' });

  async function makeLayout(template: { id: string }): Promise<string | null> {
    if (await routeTo(template.id)) return null;
    // The page may have been stale — a default may already exist — and a new template now does.
    routing.refresh();
    refreshTemplates();
    return `It could not be made the layout for ${lower}. Open it, publish it, then choose it under Advanced on this page.`;
  }

  async function routeTemplate(): Promise<void> {
    if (!chosen) return;
    if (await routeTo(chosen)) {
      setTemplateId('');
      routing.refresh();
    }
  }

  async function backToStandard(): Promise<void> {
    if (!target) return;
    if (await writes.setActive(target.id, false)) {
      setLeaving(false);
      routing.refresh();
    }
  }

  const columns: Column<Rule>[] = [
    {
      key: 'template',
      header: 'Template',
      type: 'link',
      locked: true,
      value: nameOf,
      href: (rule) => (byId.has(rule.template_id) ? `/invoice-designer/${rule.template_id}` : null),
    },
    {
      key: 'code',
      header: 'Code',
      type: 'code',
      value: (rule) => byId.get(rule.template_id)?.code,
    },
    { key: 'conditions', header: 'Conditions', value: ruleConditions },
    { key: 'priority', header: 'Priority', align: 'end' },
    {
      key: 'state',
      header: 'State',
      type: 'status',
      value: (rule) => (rule.is_active ? 'active' : 'retired'),
      label: (code) => (code === 'active' ? 'Active' : 'Retired'),
      tone: (code) => (code === 'active' ? 'success' : 'neutral'),
    },
    ...(canManageRouting
      ? [
          {
            key: 'action',
            header: 'Action',
            hideHeader: true,
            type: 'custom',
            align: 'end',
            render: (rule) =>
              mayToggle(rule) ? (
                <Button
                  variant="ghost"
                  disabled={writes.pending}
                  aria-label={`${rule.is_active ? 'Retire' : 'Reinstate'} ${ruleName(rule)}`}
                  onClick={() => {
                    // A write left uncertain by a server error would otherwise swallow this one in silence.
                    writes.clear();
                    void writes.setActive(rule.id, !rule.is_active).then((ok) => {
                      if (ok) routing.refresh();
                    });
                  }}
                >
                  {rule.is_active ? 'Retire' : 'Reinstate'}
                </Button>
              ) : null,
          } satisfies Column<Rule>,
        ]
      : []),
  ];

  const customize = canManageTemplates ? (
    <Button
      onClick={() => {
        writes.clear();
        setCreating(true);
      }}
    >
      {canRoute ? 'Customize layout' : 'New template'}
    </Button>
  ) : null;
  const goBackLabel =
    own && ownLayout && !ownLive ? 'Stop customizing' : without ? 'Remove this company’s layout' : 'Back to standard layout';
  const goBack =
    target && mayToggle(target) ? (
      <Button
        variant="ghost"
        onClick={() => {
          writes.clear();
          setLeaving(true);
        }}
      >
        {goBackLabel}
      </Button>
    ) : null;
  /** Only an author of the company's own, non-shipped template may change it; anyone else may look. */
  const designLink = (template: (typeof templates)[number] | undefined, editVerb: string) => {
    if (!template) return null;
    const mayEdit = canManageTemplates && template.company_id === company && !template.is_system;
    return (
      <a className="janso-btn janso-btn--primary" href={`/invoice-designer/${template.id}`}>
        {mayEdit ? editVerb : 'View design'}
      </a>
    );
  };

  const specialNote = special ? ' Documents that match a rule under Advanced print on that rule’s layout instead.' : '';
  const ownNote = !own
    ? ''
    : !ownLayout
      ? ' This company has a layout of its own, but its template cannot be shown here.'
      : ownLive
        ? ` This company’s own layout, ${ownLayout.name}, is not used while the organisation’s takes precedence.`
        : ` This company’s own layout, ${ownLayout.name}, is still a draft.`;

  /** The answer to "what does this print on?", in the one place it is asked. */
  const inUse =
    winner && ownWins ? (
      <Card>
        <CardHeader
          title={winnerLayout!.name}
          subtitle={`Every ${lower} document prints on this layout unless another rule under Advanced applies.`}
          badge={<Badge tone="success">Custom layout</Badge>}
        />
        <FormActions>
          {goBack}
          {designLink(winnerLayout, 'Edit design')}
        </FormActions>
      </Card>
    ) : winner ? (
      <Card>
        <CardHeader
          title={winnerLayout!.name}
          subtitle={
            `Every ${lower} document prints on this layout, which is set for your whole organisation.` +
            (own ? ownNote : canRoute ? ' Customize it to give this company its own.' : '')
          }
          badge={<Badge tone="info">Organisation layout</Badge>}
        />
        <FormActions>
          {own ? goBack : customize}
          {own ? designLink(ownLayout, 'Continue designing') : null}
        </FormActions>
      </Card>
    ) : own && ownLayout ? (
      <Card>
        <CardHeader
          title="Standard layout"
          subtitle={`${ownLayout.name} is still a draft. ${label} documents keep printing on the standard layout until it is published.${specialNote}`}
          badge={<Badge tone="warn">Draft in progress</Badge>}
        />
        <FormActions>
          {goBack}
          {designLink(ownLayout, 'Continue designing')}
        </FormActions>
      </Card>
    ) : own ? (
      <Card>
        <CardHeader
          title="Custom layout"
          subtitle="This company has a layout of its own for this voucher, but its template cannot be shown here."
          badge={<Badge tone="success">Custom layout</Badge>}
        />
        {goBack ? <FormActions>{goBack}</FormActions> : null}
      </Card>
    ) : (
      <Card>
        <CardHeader
          title="Standard layout"
          subtitle={
            `Every ${lower} document prints on the standard layout.` +
            (canRoute ? ' Customize it to add your logo or change the arrangement — there is nothing to set up otherwise.' : '') +
            specialNote
          }
          badge={<Badge>Built in</Badge>}
        />
        {customize ? <FormActions>{customize}</FormActions> : null}
      </Card>
    );

  return (
    <div className="janso-page">
      <PageNavigation
        back={{ href: returnTo ?? '/documents/vouchers', label: returnTo ? 'voucher workflow' : 'voucher print' }}
        breadcrumbs={[
          { label: 'Print templates', href: '/invoice-designer' },
          { label: 'Voucher print', href: '/documents/vouchers' },
          { label },
        ]}
      />
      <PageHeader
        title={`${label} print`}
        lede={`${kindSummary(kind)}. It prints on the standard layout unless a layout has been set for it.`}
        actions={
          <>
            {/* Without read access the layout in use is unknown, so there is no Customize to offer —
                but a template author can still start a template. */}
            {canManageTemplates && !canReadRouting ? (
              <Button
                onClick={() => {
                  writes.clear();
                  setCreating(true);
                }}
              >
                New template
              </Button>
            ) : null}
            <a className="janso-btn janso-btn--ghost" href={MANAGE_VOUCHER_TYPES}>
              Manage voucher type
            </a>
          </>
        }
      />
      {canManageTemplates ? (
        <NewTemplateDialog
          company={company}
          kind={kind}
          open={creating}
          onClose={() => setCreating(false)}
          title={canRoute ? 'Customize layout' : 'New template'}
          note={
            canRoute
              ? `It opens in the designer ${opensOn}. Once you publish it, it becomes the layout for ${lower}; until then ${lower} documents keep printing on ${printsNow}.`
              : `It opens in the designer ${opensOn}. A template is used for ${lower} once someone with routing access chooses it.`
          }
          onCreated={canRoute ? makeLayout : undefined}
        />
      ) : null}
      {target && mayToggle(target) ? (
        <ConfirmDialog
          open={leaving}
          title={without ? `Stop using ${nameOf(target)} for ${lower}?` : `Go back to the standard layout for ${lower}?`}
          confirmLabel={goBackLabel}
          busy={writes.pending}
          error={writes.failure}
          onConfirm={() => void backToStandard()}
          onCancel={() => {
            if (writes.pending) return;
            writes.clear();
            setLeaving(false);
          }}
        >
          {nameOf(target)} stops being used for {lower}
          {without
            ? `, which then print on ${byId.get(without.template_id)?.name ?? 'the organisation’s layout'}, set for your whole organisation.`
            : ', which print on the standard layout again.'}{' '}
          The template is kept in Print templates, and you can use it again later.
        </ConfirmDialog>
      ) : null}

      {canReadRouting ? (
        <>
          <SectionHeader title="Layout in use" />
          {loading ? (
            <p role="status">Checking which layout {lower} prints on…</p>
          ) : incomplete ? (
            <Notice tone="warning">
              This company has more rules or templates than fit on one page, so which layout {lower} prints on
              cannot be told from here. Use{' '}
              <a className="janso-link" href="/documents/routing">
                Document routing
              </a>
              .
            </Notice>
          ) : (
            inUse
          )}
          {/* One place for a failed write, whichever control made it — retiring a rule has no form to sit in.
              Not behind a dialog that is already saying it. */}
          {writes.failure && !leaving && !creating ? <Notice tone="danger">{writes.failure}</Notice> : null}

          <Disclosure summary="Advanced: other templates and rules">
            <div className="janso-flow">
              {canRoute && !loading && !incomplete ? (
                own ? (
                  <Notice>
                    To use a different template for {lower}, {without ? 'remove this company’s layout' : 'go back to the standard layout'}{' '}
                    first, then choose it here.
                  </Notice>
                ) : routable.length === 0 ? (
                  <Notice>
                    No published template to choose from yet. Customize the layout, or publish a template in the
                    designer, and it can be chosen here.
                  </Notice>
                ) : (
                  <>
                    <SectionHeader
                      title="Use an existing template"
                      description={
                        <>
                          Every {lower} document prints on it unless another rule applies. For a currency or tax-category
                          condition, use{' '}
                          <a className="janso-link" href="/documents/routing">
                            Document routing
                          </a>
                          .
                        </>
                      }
                    />
                    <Card>
                      <CardBody>
                        <div className="janso-form-grid console-routing-fields">
                          <Select
                            label="Template"
                            value={chosen}
                            options={[
                              { value: '', label: 'Choose a published template' },
                              ...routable.map((template) => ({ value: template.id, label: template.name })),
                            ]}
                            // A refusal of Customize's rule is not about this select, which nobody touched.
                            error={chosen ? writes.fields?.template_id : undefined}
                            onChange={(value) => {
                              writes.clear();
                              setTemplateId(value);
                            }}
                          />
                        </div>
                      </CardBody>
                      <FormActions>
                        <Button
                          disabled={!chosen || writes.pending}
                          loading={writes.pending}
                          onClick={() => void routeTemplate()}
                        >
                          Use for {lower}
                        </Button>
                      </FormActions>
                    </Card>
                  </>
                )
              ) : null}
              <SectionHeader
                title={`Rules for ${lower}`}
                description="The rule with the highest priority wins; among equals, the one with more conditions, then the newer. Retired rules are kept and shown."
              />
              <DataTable
                caption={`Layout rules for ${lower}`}
                columns={columns}
                rows={rules}
                rowId={(rule) => rule.id}
                rowLabel={ruleName}
                loading={loading}
                emptyTitle={`No rules for ${lower}`}
                emptyBody={`${label} documents print on the standard layout.`}
              />
            </div>
          </Disclosure>
        </>
      ) : (
        <Notice>Routing read access is required to see which layout {lower} prints on.</Notice>
      )}
    </div>
  );
}
