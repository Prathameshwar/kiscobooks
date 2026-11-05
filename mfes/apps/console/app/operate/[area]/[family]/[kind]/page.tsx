import { notFound } from 'next/navigation';
import { OperateFrame } from '../../../../components/OperateFrame';
import { OperateVoucherList } from '../../../../components/OperateVoucherList';
import { listHref, operateArea, operateFamily } from '../../../../lib/operate-navigation';
import { kindFromSlug } from '../../../../lib/voucher-kinds';
import { isTypeId } from '../../../../lib/voucher-type-routes';

export default async function VoucherListPage({ params, searchParams }: { params: Promise<{ area: string; family: string; kind: string }>; searchParams?: Promise<{ type_id?: string | string[] }> }) {
  const segments = await params, typeId = (await searchParams)?.type_id;
  const area = operateArea(segments.area), family = area && operateFamily(area, segments.family), kind = kindFromSlug(segments.kind);
  if (!area || !family || !kind || !family.kinds.includes(kind) || typeId !== undefined && (typeof typeId !== 'string' || !isTypeId(typeId))) notFound();
  return OperateFrame({ href: listHref(area, family, kind), children: (company, permissions) => <OperateVoucherList key={company+kind+(typeId??'')} company={company} permissions={permissions} area={area} family={family} kind={kind} typeId={typeId} /> });
}
