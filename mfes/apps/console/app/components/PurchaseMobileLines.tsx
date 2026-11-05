'use client';

import { Button, Menu, useFormatters } from '@janso/ui';
import { purchaseLineAmounts } from '../lib/purchase-workspace';
import * as D from '../lib/fixed-decimal';
import type { PurchaseWorkspaceSectionProps } from './PurchaseWorkspaceHeader';

export function PurchaseMobileLines({ draft, dispatch, problems, disabled, onEdit }: PurchaseWorkspaceSectionProps & { onEdit: (key: string) => void }) {
  const { money, quantity } = useFormatters();
  return <div className="janso-entry-line-cards"><ul className="janso-entry-line-list" aria-label="Purchase line cards">
    {draft.lines.map((line, index) => {
      const amounts = purchaseLineAmounts(line), issue = problems.find(problem => problem.lineKey === line.key);
      return <li key={line.key} className="janso-entry-line-card" data-purchase-mobile-line={line.key}>
        <div className="janso-entry-line-card__head"><span className="janso-entry-workspace__caption">Line {index + 1} · {line.kind === 'ITEM' ? 'Item' : 'Account / service'}</span>
          {!disabled ? <Menu label={`Actions for line ${index + 1}`} items={[
            { id: 'duplicate', label: 'Duplicate line' }, { id: 'insert', label: 'Insert line below' },
            { id: 'up', label: 'Move up', disabledReason: index === 0 ? 'Already the first line' : undefined },
            { id: 'down', label: 'Move down', disabledReason: index === draft.lines.length - 1 ? 'Already the last line' : undefined },
            { id: 'remove', label: 'Remove line', destructive: true },
          ]} onSelect={action => action === 'up' || action === 'down' ? dispatch({ type: 'move', key: line.key, by: action === 'up' ? -1 : 1 }) : action === 'insert' ? dispatch({ type: 'add', after: line.key }) : dispatch({ type: action as 'duplicate' | 'remove', key: line.key })} /> : null}</div>
        <strong className="janso-entry-line-card__name">{line.label || 'Choose an item or expense account'}</strong>
        {line.kind === 'ITEM' ? <dl className="janso-entry-line-card__figures"><dt>Receipt qty</dt><dd>{quantity(line.received)} {line.unit}</dd><dt>Billed qty</dt><dd>{quantity(line.billed)} {line.unit}</dd><dt>Rate</dt><dd>{money(line.rate, { precision: 4 })}</dd></dl> : null}
        {amounts && amounts.discount > 0n ? <p className="janso-entry-workspace__caption">Line discount {money(D.format(amounts.discount))}</p> : null}
        <div className="janso-entry-line-card__total"><span>Line total before tax</span><strong>{amounts ? money(D.format(amounts.net)) : '—'}</strong></div>
        {issue ? <p className="janso-error">{issue.message}</p> : null}
        <Button type="button" variant="ghost" data-purchase-edit-line={line.key} onClick={() => onEdit(line.key)}>{disabled ? 'Review' : 'Edit'} line {index + 1}</Button>
      </li>;
    })}
    </ul>
    {!disabled ? <Button type="button" variant="ghost" onClick={() => dispatch({ type: 'add' })}>Add purchase line</Button> : null}
  </div>;
}
