import { redirect } from 'next/navigation';

/** Older dashboard links now open the native company party directory. */
export default async function CustomersPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = (await searchParams) ?? {};
  const params = new URLSearchParams({ role: 'CUSTOMER' });
  const search =
    typeof query.q === 'string'
      ? query.q
      : typeof query.name === 'string'
        ? query.name
        : '';
  if (
    search.trim().length >= 2 &&
    search.length <= 200 &&
    !/[\x00-\x1f\x7f]/.test(search)
  )
    params.set('q', search.trim());
  return redirect('/accounting/parties?' + params);
}
