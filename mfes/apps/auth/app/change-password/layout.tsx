import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { Notice } from '@janso/ui';

/** A self-service screen; native credential changes still require provider authentication. */
export default async function ChangePasswordLayout({children}: {children:React.ReactNode}) {
  const auth=process.env.NEXTAUTH_URL,secret=process.env.NEXTAUTH_SECRET;
  if (!auth || !secret) return <Notice tone="danger">Password change is temporarily unavailable. Please try again.</Notice>;
  const token=await getToken({req:new NextRequest(auth,{headers:await headers()}),secret,secureCookie:auth.startsWith('https://')});
  if (!token || typeof token.accessToken !== 'string' || !token.accessToken || typeof token.accessTokenExpires !== 'number' || !Number.isFinite(token.accessTokenExpires) || token.accessTokenExpires<=Date.now()+10000) redirect('/login?reauth=1');
  return children;
}
