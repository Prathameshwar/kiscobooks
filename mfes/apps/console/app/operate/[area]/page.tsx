import { notFound } from 'next/navigation';
import { OperateFrame } from '../../components/OperateFrame';
import { OperateLanding } from '../../components/OperateLanding';
import { areaHref, operateArea } from '../../lib/operate-navigation';

export default async function OperateAreaPage({ params }: { params: Promise<{ area: string }> }) {
  const area = operateArea((await params).area);
  if (!area) notFound();
  return OperateFrame({ href: areaHref(area), children: () => <OperateLanding area={area} /> });
}
