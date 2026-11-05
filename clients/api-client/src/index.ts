import createClient, { type ClientOptions } from "openapi-fetch";
import type { paths as CatalogPaths } from "./catalog.js";
import type { paths as IdentityPaths } from "./identity.js";
import type { paths as AccountingPaths } from "./accounting.js";

import type { paths as AuditPaths } from "./audit.js";

export const createAuditClient = (options: ClientOptions) => createClient<AuditPaths>(options);
export const createCatalogClient = (options: ClientOptions) => createClient<CatalogPaths>(options);
export const createIdentityClient = (options: ClientOptions) => createClient<IdentityPaths>(options);
export const createAccountingClient = (options: ClientOptions) => createClient<AccountingPaths>(options);
export type { CatalogPaths, IdentityPaths, AccountingPaths, AuditPaths };

import type { paths as VouchersPaths } from "./vouchers.js";
export const createVouchersClient = (options: ClientOptions) => createClient<VouchersPaths>(options);
export type { VouchersPaths };

import type { paths as ReportsPaths } from "./reports.js";
export const createReportsClient = (options: ClientOptions) => createClient<ReportsPaths>(options);
export type { ReportsPaths };

import type { paths as NotificationPaths } from "./notification.js";
export const createNotificationClient = (options: ClientOptions) => createClient<NotificationPaths>(options);
export type { NotificationPaths };
