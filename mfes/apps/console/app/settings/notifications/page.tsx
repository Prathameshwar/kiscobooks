import { NotificationPage } from '../../components/NotificationPage';
import type { NotificationQuery } from '../../lib/notification-navigation';
export default async function Page({ searchParams }: { searchParams?: Promise<NotificationQuery> }) {
  return NotificationPage({ owner: 'tenant', query: await searchParams });
}
