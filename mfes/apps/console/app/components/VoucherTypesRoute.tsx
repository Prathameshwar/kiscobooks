import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { companyPermission } from '../lib/company-permissions';
import { TYPES_ROOT, isTypeId } from '../lib/voucher-type-routes';
import { ConsoleShell } from './ConsoleShell';
import { NoCompany } from './NoCompany';
import { VoucherTypeDetail } from './VoucherTypeDetail';
import { VoucherTypeDirectory } from './VoucherTypeDirectory';
import { VoucherTypeEditor } from './VoucherTypeEditor';
import { VoucherTypeRulesEditor } from './VoucherTypeRulesEditor';

type Query = Record<string, string | string[] | undefined>;

/** A query value that is a single string, and nothing else. */
const one = (value: string | string[] | undefined) => (typeof value === 'string' ? value : undefined);

/**
 * `/masters/voucher-types`, by the segments after it:
 *
 *  - none — the list
 *  - `new` (optionally `?from=<type id>`) — start a type, or a copy of one
 *  - `<id>` — one type; `<id>/edit` — change its entry rules
 *
 * Anything else is a 404: an id that is not a UUID, a third segment, or `edit` on `new`. Opening a
 * page needs `vouchers.read` for the company; creating, copying and editing also need
 * `vouchers.type.manage`. Presentation only — the service authorizes every call again, against the
 * actor's grants and the object's own company.
 */
export async function VoucherTypesRoute({ record, query }: { record: string[]; query: Query }) {
  // Ids are lower case on the wire and a response is compared with the id asked for, so an upper-case URL is lowered here
  // (the catalog masters do the same) instead of reaching a page that would call the right answer a mismatch.
  const [first, second] = record.map((segment, index) => (index === 0 ? segment.toLowerCase() : segment));
  const creating = first === 'new' && record.length === 1;
  const detail = !!first && first !== 'new' && record.length === 1 && isTypeId(first);
  const editing = !!first && first !== 'new' && second === 'edit' && record.length === 2 && isTypeId(first);
  if (record.length && !creating && !detail && !editing) notFound();

  // A copy names its source by id, once. Anything else in that slot — a repeat, or text — is not a source, and a form
  // that quietly ignored it would start a type from scratch while the address said otherwise.
  const raw = query.from;
  if (creating && raw !== undefined && (typeof raw !== 'string' || !isTypeId(raw))) notFound();
  const from = typeof raw === 'string' ? raw.toLowerCase() : undefined;

  const { session, context } = await pageContext();
  const company = session.company.id;
  const read = !!company && companyPermission(session, 'vouchers.read', company);
  const manage = !!company && companyPermission(session, 'vouchers.type.manage', company);
  const writing = creating || editing;

  return (
    <Providers session={session}>
      <ConsoleShell session={session} context={context} activeHref={TYPES_ROOT}>
        {!company ? (
          <NoCompany
            action="manage voucher types for"
            context={context}
            canCreate={companyPermission(session, 'company.create')}
          />
        ) : !read ? (
          <ErrorState status={403} detail="Voucher read access is required for this company." />
        ) : writing && !manage ? (
          <ErrorState status={403} detail="The voucher type manage permission is required for this company." />
        ) : creating ? (
          <VoucherTypeEditor key={company + (from ?? '')} company={company} from={from} />
        ) : editing ? (
          <VoucherTypeRulesEditor key={company + first} company={company} id={first!} />
        ) : detail ? (
          <VoucherTypeDetail key={company + first} company={company} id={first!} canManage={manage} saved={one(query.saved)} />
        ) : (
          <VoucherTypeDirectory key={company} company={company} canManage={manage} />
        )}
      </ConsoleShell>
    </Providers>
  );
}
