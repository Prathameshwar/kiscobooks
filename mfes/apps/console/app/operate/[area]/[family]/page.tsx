import { notFound } from 'next/navigation';
import { OperateFrame } from '../../../components/OperateFrame';
import { OperateFamilyPage } from '../../../components/OperateFamily';
import { familyHref, operateArea, operateFamily } from '../../../lib/operate-navigation';

export default async function FamilyPage({ params }: { params: Promise<{ area: string; family: string }> }) {
  const segments = await params;
  const area = operateArea(segments.area);
  const family = area && operateFamily(area, segments.family);
  if (!area || !family) notFound();
  return OperateFrame({ href: familyHref(area, family), children: (company, permissions) => <OperateFamilyPage key={company} company={company} area={area} family={family} canPrint={permissions.includes('design.template.read')} canManageTypes={permissions.includes('vouchers.type.manage')} /> });
}
