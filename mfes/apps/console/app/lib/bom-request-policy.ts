const uuid = '[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}';
const company = '^/v1/companies/' + uuid;
const isId = (value: string) => new RegExp('^' + uuid + '$', 'i').test(value);

/** Keep BOM definition authoring separate from production, inventory and cost execution. */
export function allowedBomRequest(
  method: string,
  path: string,
): boolean | undefined {
  const [route = '', query = ''] = path.split('?');
  if (
    !/\/(?:boms|bom-assignments)(?:\/|$)|\/entities\/catalog[.]bom(?:_draft|_revision|_component|_output|_assignment)?\/field-set$/i.test(
      route,
    )
  )
    return undefined;
  if (path.split('?').length > 2 || /[%\\#]/.test(route)) return false;
  const params = new URLSearchParams(query),
    keys = [...params.keys()];
  if (new Set(keys).size !== keys.length) return false;
  const list = (
    allowed: Record<string, (value: string) => boolean>,
    required: string[] = [],
  ) =>
    method === 'GET' &&
    required.every((key) => params.has(key)) &&
    keys.every((key) => allowed[key]?.(params.get(key)!) === true);
  const paging = {
    limit: (value: string) =>
      /^\d+$/.test(value) && +value >= 1 && +value <= 200,
    cursor: (value: string) => value.length > 0 && value.length <= 4096,
    sort: (value: string) => ['id', '-id'].includes(value),
  };
  const date = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value);
  if (
    new RegExp(
      company +
        '/entities/catalog[.]bom(?:_draft|_revision|_component|_output|_assignment)?/field-set$',
      'i',
    ).test(route)
  )
    return list({
      operation: (value) => ['create', 'update', 'publish'].includes(value),
    });
  if (new RegExp(company + '/boms/authoring-context$', 'i').test(route))
    return method === 'GET' && !keys.length;
  if (
    new RegExp(
      company +
        '/boms/options/references/(goods|units|routes|revisions)/' +
        uuid +
        '$',
      'i',
    ).test(route)
  )
    return method === 'GET' && !keys.length;
  const options = new RegExp(
    company + '/boms/options/(goods|units|routes|revisions)$',
    'i',
  ).exec(route);
  if (options)
    return list(
      {
        ...paging,
        value: isId,
        ...(options[1] === 'revisions' ? { bom_id: isId } : {}),
        ...(options[1] === 'units'
          ? { item_id: isId, as_of: date }
          : {
              q: (value: string) =>
                value.trim().length >= 2 && value.length <= 200,
            }),
      },
      options[1] === 'units' ? ['item_id', 'as_of'] : [],
    );
  const assignment = new RegExp(
    company + '/bom-assignments(?:/(' + uuid + '|resolve)(?:/(deactivate))?)?$',
    'i',
  ).exec(route);
  if (assignment) {
    if (assignment[1] === 'resolve')
      return (
        !assignment[2] &&
        list({ item_id: isId, warehouse_id: isId, as_of: date }, [
          'item_id',
          'as_of',
        ])
      );
    if (assignment[2]) return method === 'POST' && !keys.length;
    if (assignment[1]) return ['GET', 'PATCH'].includes(method) && !keys.length;
    return method === 'POST'
      ? !keys.length
      : list({
          ...paging,
          bom_id: isId,
          item_id: isId,
          warehouse_id: isId,
          is_active: (value) => ['true', 'false'].includes(value),
        });
  }
  const match = new RegExp(
    company +
      '/boms(?:/(' +
      uuid +
      ')(?:/(activate|deactivate|drafts|revisions)(?:/(' +
      uuid +
      ')(?:/(publish|retire|components|outputs|preview))?)?)?)?$',
    'i',
  ).exec(route);
  if (!match) return false;
  const [, object, collection, definition, child] = match;
  if (collection === 'activate' || collection === 'deactivate')
    return method === 'POST' && !keys.length && !definition;
  if (child === 'publish' || child === 'retire')
    return (
      method === 'POST' &&
      !keys.length &&
      (child === 'publish'
        ? collection === 'drafts'
        : collection === 'revisions')
    );
  if (child === 'preview') return method === 'POST' && !keys.length;
  if (child)
    return list({
      ...paging,
      sort: (value) =>
        ['id', '-id', 'sequence,id', '-sequence,id'].includes(value),
    });
  if (definition)
    return (
      (method === 'GET' || (method === 'PATCH' && collection === 'drafts')) &&
      !keys.length
    );
  if (collection)
    return method === 'POST'
      ? collection === 'drafts' && !keys.length
      : list({
          ...paging,
          status: (value) =>
            (collection === 'drafts'
              ? ['DRAFT', 'PUBLISHED']
              : ['PUBLISHED', 'RETIRED']
            ).includes(value),
        });
  if (object) return ['GET', 'PATCH'].includes(method) && !keys.length;
  return method === 'POST'
    ? !keys.length
    : list({
        ...paging,
        sort: (value) =>
          ['id', '-id', 'code', '-code', 'name', '-name'].includes(value),
        q: (value) => value.trim().length >= 2 && value.length <= 200,
        code: (value) => /^[A-Z0-9][A-Z0-9_.-]{0,29}$/.test(value),
        is_active: (value) => ['true', 'false'].includes(value),
      });
}
