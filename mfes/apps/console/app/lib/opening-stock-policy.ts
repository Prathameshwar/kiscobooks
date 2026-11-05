import { trackingId } from './stock-tracking-resources';

/** Only the opening owners, fixed company paths and typed query parameters. */
export function allowedOpeningRequest(
  service: string,
  method: string,
  path: string,
): boolean {
  if (
    !path.startsWith('/') ||
    path.startsWith('//') ||
    path.includes('#') ||
    path.includes('\\') ||
    /[%\\#\x00-\x1f\x7f]/.test(path.split('?')[0]!) ||
    path.split('?').length > 2
  )
    return false;
  const url = new URL(path, 'https://opening.invalid'),
    id = trackingId.source.slice(1, -1);
  if (
    url.pathname !== path.split('?')[0] ||
    new Set(url.searchParams.keys()).size !== [...url.searchParams].length ||
    [...url.searchParams.values()].some((value) =>
      /[\x00-\x1f\x7f]/.test(value),
    )
  )
    return false;
  const base = `/v1/companies/${id}`,
    query = url.searchParams;
  const list = (filters: string[] = []) =>
    method === 'GET' &&
    [...query].every(([key, value]) => {
      if (key === 'limit') return /^[1-9]\d{0,2}$/.test(value) && +value <= 200;
      if (key === 'sort') return ['id', '-id'].includes(value);
      if (key === 'cursor') return value.length > 0 && value.length <= 4096;
      if (key === 'include_reversed')
        return filters.includes(key) && ['true', 'false'].includes(value);
      if (key === 'as_of')
        return filters.includes(key) && /^\d{4}-\d\d-\d\d$/.test(value);
      return filters.includes(key) && trackingId.test(value);
    });
  const download = () =>
    method === 'GET' &&
    query.size === 1 &&
    !!query.get('token') &&
    query.get('token')!.length <= 4096;
  if (service === 'accounting') {
    const root = `${base}/stock/openings`;
    if (new RegExp(`^${root}$`, 'i').test(url.pathname))
      return method === 'POST' && !query.size;
    if (
      new RegExp(`^${root}/(?:readiness|capabilities)$`, 'i').test(url.pathname)
    )
      return method === 'GET' && !query.size;
    if (
      new RegExp(`^${root}/(?:calculate|confirm-zero|adopt)$`, 'i').test(
        url.pathname,
      )
    )
      return method === 'POST' && !query.size;
    if (new RegExp(`^${root}/${id}/cohorts$`, 'i').test(url.pathname))
      return list(['item_id', 'warehouse_id', 'include_reversed']);
    if (new RegExp(`^${root}/${id}/revisions$`, 'i').test(url.pathname))
      return list();
    if (new RegExp(`^${root}/${id}/export$`, 'i').test(url.pathname))
      return download();
    if (
      new RegExp(
        `^${root}/${id}(?:/(?:manifest|reconciliation|accounting-preview|export-ticket|revisions/${id}))?$`,
        'i',
      ).test(url.pathname)
    )
      return method === 'GET' && !query.size;
    return (
      new RegExp(`^${root}/${id}/(?:replace|reopen|finalize)$`, 'i').test(
        url.pathname,
      ) &&
      method === 'POST' &&
      !query.size
    );
  }
  if (service === 'catalog') {
    if (new RegExp(`^${base}/items/${id}/unit-bindings(?:/${id})?$`, 'i').test(url.pathname))
      return list();
    return new RegExp(`^${base}/item-unit-bindings/${id}/revisions(?:/${id})?$`, 'i')
      .test(url.pathname) && list(['as_of']);
  }
  if (service !== 'vouchers') return false;
  const root = `${base}/stock-opening-imports`;
  if (new RegExp(`^${root}$`, 'i').test(url.pathname))
    return method === 'POST' ? !query.size : list();
  if (new RegExp(`^${root}/template$`, 'i').test(url.pathname))
    return method === 'GET' && !query.size;
  if (new RegExp(`^${root}/${id}/report$`, 'i').test(url.pathname))
    return download();
  if (new RegExp(`^${root}/${id}(?:/report-ticket)?$`, 'i').test(url.pathname))
    return method === 'GET' && !query.size;
  return (
    new RegExp(`^${root}/${id}/(?:validate|commit|cancel)$`, 'i').test(
      url.pathname,
    ) &&
    method === 'POST' &&
    !query.size
  );
}
