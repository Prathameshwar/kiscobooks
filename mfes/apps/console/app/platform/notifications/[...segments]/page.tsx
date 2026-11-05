import { NotificationPage } from '../../../components/NotificationPage';
import type { NotificationQuery } from '../../../lib/notification-navigation';
export default async function Page({ params, searchParams }: { params: Promise<{ segments: string[] }>; searchParams?: Promise<NotificationQuery> }) {
  return NotificationPage({ owner: 'platform', route: (await params).segments, query: await searchParams });
}
