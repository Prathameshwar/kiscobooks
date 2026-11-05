import type { BookDefinition } from './book-workspace';

export const inventoryReportCodes = ['STOCK_SUMMARY', 'ITEM_LEDGER', 'LOCATION_STOCK', 'STOCK_VALUATION', 'BATCH_SUMMARY', 'STOCK_EXPIRY', 'STOCK_REORDER', 'STOCK_AGEING', 'STOCK_MOVEMENT', 'STOCK_GROUP_SUMMARY'] as const;
export type InventoryReportCode = (typeof inventoryReportCodes)[number];
type InventoryDefinition = BookDefinition & { columns: readonly string[]; searchLabel?: string };
export const isInventoryReport = (code: string | undefined): code is InventoryReportCode => inventoryReportCodes.some(value => value === code);

export const inventoryWorkspaces: Record<InventoryReportCode, InventoryDefinition> = {
  STOCK_SUMMARY: {
    code:'STOCK_SUMMARY',title:'Stock Summary',overline:'Inventory position',resultNoun:'stock rows',
    lede:'Opening stock, stock movements and closing balances from a verified inventory snapshot.',
    focus:'Search the full result by item code or name',empty:'No stock items match the applied filters.',
    primaryFilters:['as_of','location_id','group_id','search'],
    columns:['item_name','unit','opening','inward','outward','quantity','carrying_value'],
  },
  ITEM_LEDGER: {
    code:'ITEM_LEDGER',title:'Item Stock Ledger',overline:'Item transaction history',resultNoun:'ledger rows',
    lede:'Trace an item’s opening balance, stock transactions and running quantity and value.',
    focus:'Select an item and period. Running balances stay separate by stock position.',
    empty:'No item stock entries match the selected period and scope.',
    primaryFilters:['item_id','date_from','as_of','location_id'],
    columns:['date','voucher_number','action','location_name','lot_code','unit','inward','outward','balance','value_balance'],
  },
  LOCATION_STOCK: {
    code:'LOCATION_STOCK',title:'Warehouse Stock',overline:'Stock by location',resultNoun:'warehouse stock rows',
    lede:'Find stock across warehouses, with opening, movement and closing balances by item.',
    focus:'Parent warehouse selections include their descendants once.',empty:'No warehouse stock matches the applied filters.',
    primaryFilters:['as_of','location_id','item_id','search'],
    columns:['location_name','item_name','unit','opening','inward','outward','quantity','carrying_value'],
  },
  STOCK_VALUATION: {
    code:'STOCK_VALUATION',title:'Stock Valuation',overline:'Inventory carrying value',resultNoun:'valuation rows',
    lede:'Review company-owned stock values, recorded costing evidence and available ledger reconciliation.',
    focus:'Values follow the recorded owner cost policy. Detail and control rows are separate evidence.',
    empty:'No company-owned stock matches the valuation selection.',primaryFilters:['as_of','location_id','item_id','search'],
    columns:['item_name','location_name','lot_code','unit','quantity','unit_cost','carrying_value','costing_method','row_kind'],
  },
  BATCH_SUMMARY: {
    code:'BATCH_SUMMARY',title:'Batch Summary',overline:'Batch and serial traceability',resultNoun:'batch rows',
    lede:'Review batch balances, manufacturing and expiry dates, with optional movement and serial history.',
    focus:'Current balances and history are distinct. History rows do not add to physical stock.',
    empty:'No tracked batches or serial positions match the applied filters.',primaryFilters:['as_of','item_id','lot_id','search'],
    columns:['item_name','lot_code','location_name','unit','quantity','manufacture_date','expiry_date','row_kind'],
  },
  STOCK_EXPIRY: {
    code:'STOCK_EXPIRY',title:'Stock Expiry',overline:'Expiry exceptions',resultNoun:'expiry rows',
    lede:'Identify expired and upcoming batches, and required expiry dates that are missing.',
    focus:'Expired or held stock remains physical stock. Eligibility follows the verified source policy.',
    empty:'No expired, upcoming or missing-expiry stock matches this selection.',primaryFilters:['as_of','days_ahead','location_id','search'],
    columns:['item_name','lot_code','location_name','unit','quantity','expiry_date','days_to_expiry','status','carrying_value'],
  },
  STOCK_REORDER: {
    code:'STOCK_REORDER',title:'Stock Reorder',overline:'Replenishment requirements',resultNoun:'reorder rows',
    lede:'Compare configured reorder and target levels with the explicitly selected stock quantity basis.',
    focus:'Company and warehouse stock bands can overlap. Evaluate each suggestion within its own scope.',
    empty:'No configured products need replenishment for this selection. Products without a stock band are excluded.',
    primaryFilters:['as_of','quantity_basis','location_id','search'],
    columns:['item_name','location_name','unit','projected_available','reorder_level','target_level','suggested_quantity','shortfall_after_order'],
  },
  STOCK_AGEING: {
    code:'STOCK_AGEING',title:'Stock Ageing',overline:'Age of remaining stock',resultNoun:'receipt cohorts',
    lede:'Review remaining stock by original receipt or manufacture age, including unknown or assumed dates.',
    focus:'Transfers preserve the original receipt date. Unknown history is not treated as new stock.',
    empty:'No remaining receipt cohorts match the applied filters.',primaryFilters:['as_of','age_basis','buckets','search'],
    columns:['item_name','location_name','lot_code','unit','quantity','origin_date','age_days','age_bucket','provenance'],
  },
  STOCK_MOVEMENT: {
    code:'STOCK_MOVEMENT',title:'Stock Movement',overline:'Period stock activity',resultNoun:'item movement rows',
    lede:'Review receipts, sales, consumption, returns and transfers, and identify nonmoving inventory.',
    focus:'Opening and turnover follow the selected From date. Transfers are separate from consumption.',
    empty:'No item activity matches the selected period and filters.',primaryFilters:['date_from','as_of','location_id','search'],
    columns:['item_name','unit','opening','inward','outward','quantity','receipts','sales','transfer_in','transfer_out','nonmoving'],
  },
  STOCK_GROUP_SUMMARY: {
    code:'STOCK_GROUP_SUMMARY',title:'Stock Group Summary',overline:'Stock by classification',resultNoun:'group stock rows',
    lede:'Review stock by item group, keeping units, ownership and custody separate.',
    focus:'Ancestor groups overlap their children. Group rows must not be added together.',
    empty:'No stock groups match the applied filters.',primaryFilters:['as_of','group_id','location_id','search'],searchLabel:'Search groups',
    columns:['group_name','unit','opening','inward','outward','quantity','carrying_value'],
  },
};

export function inventoryColumnVisible(code: string, key: string): boolean | undefined {
  return isInventoryReport(code) ? inventoryWorkspaces[code].columns.includes(key) : undefined;
}

export const inventorySummaryFields: Partial<Record<InventoryReportCode, readonly [string,string,string][]>> = {
  ITEM_LEDGER:[['item_count','Stock items','Distinct items'],['owned_value','Owned closing value','Recorded carrying value'],['entry_count','Stock transactions','Opening balances excluded'],['row_count','Report rows','Full selection']],
  LOCATION_STOCK:[['item_count','Stock items','Distinct items'],['owned_value','Owned stock value','Recorded carrying value'],['location_count','Warehouses','Distinct locations'],['row_count','Stock rows','Full selection']],
  STOCK_VALUATION:[['owned_value','Owned stock value','Position balances only'],['balance_count','Stock positions','GL and cost details excluded'],['detail_count','Cost details','Separate residual cost evidence'],['control_count','Control accounts','Verified reconciliation rows when available']],
  BATCH_SUMMARY:[['item_count','Tracked items','Distinct items'],['batch_count','Batches','Distinct lots'],['balance_count','Stock positions','Current physical balances'],['history_count','History entries','Excluded from physical totals']],
  STOCK_EXPIRY:[['expired_count','Expired positions','Physical stock needing attention'],['near_expiry_count','Near-expiry positions','Within the selected days'],['unknown_expiry_count','Missing expiry dates','Required expiry is unknown'],['owned_value','Owned exposure value','Recorded costs of selected exceptions']],
  STOCK_REORDER:[['configured_count','Configured stock bands','Selected product and warehouse scopes'],['shortage_count','Below reorder level','Selected quantity basis'],['limited_count','Order limits reached','Target remains unmet after this order'],['quantity_basis','Quantity basis','Orders follow the chosen coverage']],
  STOCK_AGEING:[['item_count','Stock items','Distinct items'],['cohort_count','Receipt cohorts','Remaining quantities only'],['unknown_count','Unknown age','Missing original receipt or manufacture date'],['assumed_count','Assumed history','Kept separate from known provenance']],
  STOCK_MOVEMENT:[['item_count','Stock items','Distinct items'],['nonmoving_count','Nonmoving stock rows','Genuine sale or consumption history'],['unknown_count','Unknown inactivity','Retained history is insufficient'],['owned_value','Owned closing value','Recorded cost at the cutoff']],
  STOCK_GROUP_SUMMARY:[['group_count','Stock groups','Ungrouped stock included when present'],['item_count','Stock items','Distinct items across selected groups'],['owned_value','Owned stock value','Each physical position counted once'],['row_count','Group rows','Parent and child rows can overlap']],
};

export const inventoryParameterLabels: Record<string,string> = {
  days_ahead:'Expiry within (days)',include_expired:'Include expired stock',include_history:'Include movement history',serial:'Serial number',include_cost_details:'Include cost details',age_basis:'Age from',buckets:'Age bands (days)',nonmoving_days:'Nonmoving threshold (days)',only_nonmoving:'Only nonmoving stock',only_shortages:'Only below reorder level',include_orders:'Include open orders',quantity_basis:'Stock quantity basis',owner:'Stock ownership',include_inactive:'Include inactive items',
};

export function inventoryCoverageHint(code:string, coverage:{movements_complete?:boolean;valuation_complete?:boolean;origins_complete?:boolean;reservations_complete?:boolean;serial_history_complete?:boolean;orders_complete?:boolean}|null, filters:Record<string,string>):string|undefined {
  if (!coverage) return;
  if (['ITEM_LEDGER','STOCK_MOVEMENT'].includes(code)&&coverage.movements_complete===false) return 'This snapshot has incomplete stock movement history. Refresh stock data after the history is verified.';
  if (code==='STOCK_VALUATION'&&coverage.valuation_complete===false) return 'Complete stock costs are unavailable in this snapshot. Refresh stock data after the costs are verified.';
  if (code==='STOCK_AGEING'&&coverage.origins_complete===false) return 'Remaining receipt origins are unavailable in this snapshot. Refresh stock data to prepare stock ageing.';
  if (code==='BATCH_SUMMARY'&&filters.include_history==='true'&&filters.serial&&coverage.serial_history_complete===false) return 'This snapshot cannot certify complete serial history. Choose a newer verified snapshot.';
  if (code==='STOCK_REORDER'&&filters.quantity_basis!=='ELIGIBLE'&&coverage.reservations_complete===false) return 'Available stock needs verified reservations. Choose Eligible stock to evaluate replenishment before reservations.';
  if (code==='STOCK_REORDER'&&filters.include_orders==='true'&&coverage.orders_complete===false) return 'Open order supply and demand are unavailable in this snapshot. Turn off Include open orders.';
}
