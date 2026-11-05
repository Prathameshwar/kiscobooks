'use client';

import type { ReactNode } from 'react';
import {
  ActionCard,
  Button,
  DocumentIcon,
  Notice,
  PageHeader,
  PageNavigation,
  ReceiptIcon,
  SectionHeader,
  StockIcon,
} from '@janso/ui';
import { layoutInUse, useRoutingRules } from '../lib/design-routing';
import { useDesignTemplates } from '../lib/design-templates';
import {
  MANAGE_VOUCHER_TYPES,
  VOUCHER_KIND_GROUPS,
  kindLabel,
  kindSlug,
  kindSummary,
  type VoucherKindGroup,
} from '../lib/voucher-kinds';

const GROUP_ICONS: Record<string, ReactNode> = {
  accounting: <ReceiptIcon />,
  inventory: <StockIcon />,
  orders: <DocumentIcon />,
  general: <DocumentIcon />,
};

/**
 * Voucher print — a card for every kind of voucher, and the way into designing what it prints.
 *
 * The designer answers "what could a document look like" and routing answers "which one is used";
 * neither starts from the thing a person actually has in mind, which is *a sales invoice* or *a
 * receipt*. This page does: pick the voucher, and the next page is that voucher's print — its
 * templates, a way to design another, and the voucher type it belongs to.
 *
 * **Nothing here needs setting up.** Every voucher prints on the standard layout, so a card
 * without a custom layout says "Standard layout" and is not a gap to fill. What a card says is read
 * by `layoutInUse` — the same function the voucher's own page asks — so the two cannot disagree:
 * "Custom layout" when a default rule in force names a *published* template (a retired rule routes
 * nothing and a draft is skipped when a document resolves), and "Custom for some documents" when
 * only rules for particular cases (a currency, a tax category) are in force.
 *
 * The chip is a courtesy and never a gate: a reader without routing access still gets every
 * card, just without it, and it is withheld, with a note saying so, rather than guessed when
 * either list is longer than one page.
 */
export function VoucherPrintHub({
  company,
  canManage,
  canReadRouting,
}: {
  company: string;
  /** `design.template.manage` — only changes the verb on each card; the card still opens. */
  canManage: boolean;
  /** `design.assignment.read` — without it there is no chip, because there are no rules to read. */
  canReadRouting: boolean;
}) {
  const routing = useRoutingRules(canReadRouting ? company : undefined);
  const designs = useDesignTemplates(canReadRouting ? company : undefined);
  const failure = routing.failure ?? designs.failure;
  const known =
    canReadRouting && !routing.loading && !designs.loading && !failure && !routing.hasMore && !designs.hasMore;

  const templates = new Map(designs.templates.map((template) => [template.id, template]));

  const statusOf = (kind: string) => {
    if (!known) return undefined;
    const { winner, special } = layoutInUse(
      routing.rules.filter((rule) => rule.voucher_kind === kind),
      templates,
      company,
    );
    if (winner) return { label: 'Custom layout', tone: 'success' as const };
    return special ? { label: 'Custom for some documents', tone: 'info' as const } : { label: 'Standard layout' };
  };

  const section = (group: VoucherKindGroup) => (
    <section key={group.key} className="janso-flow" aria-label={group.title}>
      <SectionHeader title={group.title} description={group.description} />
      <div className="janso-action-card-grid">
        {group.kinds.map((kind) => (
          <ActionCard
            key={kind}
            title={kindLabel(kind)}
            description={`${kindSummary(kind)}.`}
            icon={GROUP_ICONS[group.key]}
            href={`/documents/vouchers/${kindSlug(kind)}`}
            actionLabel={canManage ? 'Design print' : 'View print'}
            status={statusOf(kind)}
          />
        ))}
      </div>
    </section>
  );

  return (
    <div className="janso-page">
      <PageNavigation
        back={{ href: '/invoice-designer', label: 'print templates' }}
        breadcrumbs={[
          { label: 'Print templates', href: '/invoice-designer' },
          { label: 'Voucher print' },
        ]}
      />
      <PageHeader
        title="Voucher print"
        lede="Vouchers print on the standard layout until a layout is set for them. Choose one to give it a layout of your own."
        actions={
          <>
            <a className="janso-btn janso-btn--ghost" href={MANAGE_VOUCHER_TYPES}>
              Manage voucher types
            </a>
          </>
        }
      />
      {canReadRouting && failure && failure.status !== 403 ? (
        <Notice tone="warning">
          Which vouchers have a custom layout could not be loaded, but every voucher type still opens.{' '}
          <Button
            variant="ghost"
            onClick={() => {
              routing.refresh();
              designs.refresh();
            }}
          >
            Retry
          </Button>
        </Notice>
      ) : canReadRouting && (routing.hasMore || designs.hasMore) && !failure ? (
        <Notice>
          Which vouchers have a custom layout is hidden because this company has more rules or templates than fit
          on one page. Every voucher type still opens.
        </Notice>
      ) : null}
      {VOUCHER_KIND_GROUPS.map(section)}
    </div>
  );
}
