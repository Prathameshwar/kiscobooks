'use client';
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  type ReactNode,
} from 'react';
import type { components } from '@janso/api-client/catalog';
import type { Session } from '../session';
import { companyPermission } from '../lib/company-permissions';
import { masterRequest } from '../lib/catalog-master-api';
import { useServiceRead } from '../lib/service-resource';
import type { RequestFailure } from '../lib/service-call';

export type ProductMode = components['schemas']['ProductModeDetail'];
type ModeContext = {
  company: string;
  data: ProductMode | null;
  loading: boolean;
  failure: RequestFailure | null;
  refresh: () => void;
};
const Context = createContext<ModeContext | null>(null);
export const modeEvent = 'janso:product-mode-changed';
export function useProductMode() {
  return useContext(Context);
}
export function verifyProductMode(value: ProductMode, company: string) {
  if (
    !value ||
    value.company_id !== company ||
    typeof value.product_family_sku_enabled !== 'boolean' ||
    !Number.isSafeInteger(value.row_version) ||
    value.row_version < 0 ||
    !Number.isSafeInteger(value.policy_generation) ||
    value.policy_generation < 1
  )
    throw {
      status: 502,
      message:
        'Product settings could not be verified for this company. Please reload.',
    };
}
export function ProductModeProvider({
  session,
  children,
}: {
  session: Session;
  children: ReactNode;
}) {
  const company = session.company.id ?? '';
  const allowed =
    !!company &&
    companyPermission(session, 'product_configuration.read', company);
  const read = useServiceRead<ProductMode>(
    allowed
      ? `/v1/companies/${company}/product-configuration/authoring`
      : undefined,
    masterRequest,
    (value) => verifyProductMode(value, company),
  );
  // A previous company's response is never usable during the effect's reset render.
  const verified = useRef<ProductMode | null>(null);
  if (read.data?.company_id === company) verified.current = read.data;
  const data =
    allowed && verified.current?.company_id === company
      ? verified.current
      : null;
  const refreshRef = useRef(read.refresh);
  refreshRef.current = read.refresh;
  useEffect(() => {
    const update = () => refreshRef.current();
    window.addEventListener(modeEvent, update);
    const focus = () => refreshRef.current();
    window.addEventListener('focus', focus);
    return () => {
      window.removeEventListener(modeEvent, update);
      window.removeEventListener('focus', focus);
    };
  }, [company]);
  return (
    <Context.Provider
      value={{
        company,
        data,
        loading: allowed && ((!data && !read.failure) || read.loading),
        failure: allowed
          ? read.failure
          : {
              status: 403,
              message:
                'Product configuration read access is required to verify product structure.',
            },
        refresh: read.refresh,
      }}
    >
      {children}
    </Context.Provider>
  );
}
