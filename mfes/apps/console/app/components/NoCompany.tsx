import { EmptyState, StoreIcon } from '@janso/ui';
import type { CompanyContext } from '../lib/company-context';

/**
 * What a company-scoped screen shows when no company is open.
 *
 * One component for every such screen, because the *reason* differs and a bare "Select a
 * company" tells the reader nothing about which of these they are in:
 *
 *  - nothing has been created yet, and they may create it
 *  - nothing has been created yet, and they may not
 *  - companies exist but their role cannot read them (`company.read` is a real permission the
 *    seeded clerk and controller roles do not hold — docs/roles-permissions.md §4)
 *
 * The switcher in the rail is the way out of the first case; an administrator is the way out of
 * the others. Saying which is the whole point.
 */
export function NoCompany({ action, context, canCreate }: { action: string; context: CompanyContext; canCreate: boolean }) {
  return (
    <EmptyState
      icon={<StoreIcon size={20} />}
      title={`No company is open, so there is nothing to ${action} yet`}
      body={context.companiesNote ?? 'Choose a company from the switcher at the top of the menu.'}
      action={
        canCreate ? (
          // An anchor, not a `Button`: this is a destination, and a button that navigates is
          // not reachable the way a link is (no middle-click, no "open in new tab").
          <a className="janso-btn janso-btn--primary" href="/companies/new">
            Create a company
          </a>
        ) : (
          <a className="janso-link" href="/companies">
            See the companies you can open
          </a>
        )
      }
    />
  );
}
