export interface paths {
    "/v1/activity": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Activity */
        get: operations["list_activity_v1_activity_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/audit-events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Audit Events */
        get: operations["list_audit_events_v1_audit_events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/audit-events/export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Export Audit Events */
        post: operations["export_audit_events_v1_audit_events_export_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/audit-events/security": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Security Events */
        get: operations["list_security_events_v1_audit_events_security_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/audit-events/{event_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Audit Event */
        get: operations["get_audit_event_v1_audit_events__event_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform-events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Listing */
        get: operations["listing_v1_platform_events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform-events/{event_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Detail */
        get: operations["detail_v1_platform_events__event_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * ActivityItem
         * @description The friendlier feed projection — "who did what to which entity" (§1).
         */
        ActivityItem: {
            /** Action */
            action: string;
            /** Actor Type */
            actor_type: string | null;
            /** Actor User Id */
            actor_user_id: string | null;
            /** Category */
            category: string;
            /** Company Id */
            company_id: string | null;
            /** Entity Id */
            entity_id: string | null;
            /** Entity Type */
            entity_type: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** On Behalf Of User Id */
            on_behalf_of_user_id: string | null;
            /** Source Service */
            source_service: string | null;
        };
        /** ActivityPage */
        ActivityPage: {
            /** Items */
            items: components["schemas"]["ActivityItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /**
         * AuditEventDetail
         * @description One event in full, including the before/after values and the chain proof.
         */
        AuditEventDetail: {
            /** Action */
            action: string;
            /** Actor Ip */
            actor_ip: string | null;
            /** Actor Type */
            actor_type: string | null;
            /** Actor User Agent */
            actor_user_agent: string | null;
            /** Actor User Id */
            actor_user_id: string | null;
            /** Api Client Id */
            api_client_id: string | null;
            /** Category */
            category: string;
            /** Changes */
            changes: {
                [key: string]: unknown;
            } | null;
            /** Company Id */
            company_id: string | null;
            /** Context */
            context: {
                [key: string]: unknown;
            } | null;
            /** Department Id */
            department_id: string | null;
            /** Entity Id */
            entity_id: string | null;
            /** Entity Type */
            entity_type: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Message Id
             * Format: uuid
             */
            message_id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** On Behalf Of User Id */
            on_behalf_of_user_id: string | null;
            /** Prev Hash */
            prev_hash: string | null;
            /** Reason */
            reason: string | null;
            /** Request Id */
            request_id: string | null;
            /** Row Hash */
            row_hash: string;
            /** Sequence */
            sequence: number;
            /** Source Service */
            source_service: string | null;
            /** Trace Id */
            trace_id: string | null;
        };
        /**
         * AuditEventItem
         * @description The lean audit-trail row.
         */
        AuditEventItem: {
            /** Action */
            action: string;
            /** Actor Type */
            actor_type: string | null;
            /** Actor User Id */
            actor_user_id: string | null;
            /** Category */
            category: string;
            /** Company Id */
            company_id: string | null;
            /** Department Id */
            department_id: string | null;
            /** Entity Id */
            entity_id: string | null;
            /** Entity Type */
            entity_type: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** On Behalf Of User Id */
            on_behalf_of_user_id: string | null;
            /** Sequence */
            sequence: number;
            /** Source Service */
            source_service: string | null;
            /** Trace Id */
            trace_id: string | null;
        };
        /** AuditEventPage */
        AuditEventPage: {
            /** Items */
            items: components["schemas"]["AuditEventItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /**
         * ExportResult
         * @description The result of an export — itself recorded as an ``access`` audit event (§5.3).
         *
         *     The rows are returned inline for v1 (bounded by ``limit``); wiring the signed,
         *     expiring download URL to object storage is the deployment hook (CLAUDE.md §5.14).
         */
        ExportResult: {
            /** Count */
            count: number;
            /** Events */
            events: components["schemas"]["AuditEventDetail"][];
            /**
             * Export Id
             * Format: uuid
             */
            export_id: string;
            /** Truncated */
            truncated: boolean;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** PageMeta */
        PageMeta: {
            /** Has More */
            has_more: boolean;
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_activity_v1_activity_get: {
        parameters: {
            query?: {
                company_id?: string | null;
                limit?: number;
                cursor?: string | null;
                sort?: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActivityPage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_audit_events_v1_audit_events_get: {
        parameters: {
            query?: {
                company_id?: string | null;
                entity_type?: string | null;
                entity_id?: string | null;
                action?: string | null;
                category?: string | null;
                occurred_from?: string | null;
                occurred_to?: string | null;
                limit?: number;
                cursor?: string | null;
                sort?: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditEventPage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    export_audit_events_v1_audit_events_export_post: {
        parameters: {
            query?: {
                company_id?: string | null;
                entity_type?: string | null;
                entity_id?: string | null;
                action?: string | null;
                category?: string | null;
                occurred_from?: string | null;
                occurred_to?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExportResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_security_events_v1_audit_events_security_get: {
        parameters: {
            query?: {
                company_id?: string | null;
                entity_type?: string | null;
                entity_id?: string | null;
                action?: string | null;
                occurred_from?: string | null;
                occurred_to?: string | null;
                limit?: number;
                cursor?: string | null;
                sort?: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditEventPage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_audit_event_v1_audit_events__event_id__get: {
        parameters: {
            query: {
                company_id?: string | null;
                /** @description The event's occurred_at (from the list item). Required so the lookup prunes to one monthly partition instead of scanning the largest table in the system. */
                occurred_at: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                event_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditEventDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    listing_v1_platform_events_get: {
        parameters: {
            query?: {
                entity_type?: string | null;
                entity_id?: string | null;
                category?: string | null;
                occurred_from?: string | null;
                occurred_to?: string | null;
                limit?: number;
                cursor?: string | null;
                sort?: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditEventPage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    detail_v1_platform_events__event_id__get: {
        parameters: {
            query: {
                occurred_at: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                event_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditEventDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
