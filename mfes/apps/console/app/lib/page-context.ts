import { getCompanyContext, getCompanyList, type CompanyContext } from './company-context';
import { getSession, type Session } from '../session';

export type PageContext = { session: Session; context: CompanyContext };

/**
 * What every console page resolves, once, in its Server Component.
 *
 * Both halves are request-scoped and are passed down as props — never imported from module
 * scope by a client component, where one binding lives for the whole server process and would
 * be shared across tenants (see `session.ts`).
 *
 * The two reads run **together**: the company list needs nothing from the session now that
 * Identity resolves the open company itself, and the session no longer needs the list to finish
 * its own chain. The fiscal context still follows, because which year contains today depends on
 * the company's timezone.
 */
export async function pageContext(): Promise<PageContext> {
  const [session, list] = await Promise.all([getSession(), getCompanyList()]);
  return { session, context: await getCompanyContext(session, list) };
}
