export interface paths {
    "/internal/v1/sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Apply Sources */
        post: operations["apply_sources_internal_v1_sources_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/checkout-counters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Counter */
        post: operations["create_counter_v1_companies__company_id__checkout_counters_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/checkout-counters/{counter_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Counter Detail */
        get: operations["counter_detail_v1_companies__company_id__checkout_counters__counter_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/checkout-counters/{counter_id}/operators": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Assign Operator */
        post: operations["assign_operator_v1_companies__company_id__checkout_counters__counter_id__operators_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/checkout-counters/{counter_id}/operators/{user_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Operator Status */
        put: operations["set_operator_status_v1_companies__company_id__checkout_counters__counter_id__operators__user_id__status_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/checkout-counters/{counter_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Counter Status */
        put: operations["set_counter_status_v1_companies__company_id__checkout_counters__counter_id__status_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/counter-outlets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Outlet */
        post: operations["create_outlet_v1_companies__company_id__counter_outlets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/counter-outlets/{outlet_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Outlet Detail */
        get: operations["outlet_detail_v1_companies__company_id__counter_outlets__outlet_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/counter-outlets/{outlet_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Outlet Status */
        put: operations["set_outlet_status_v1_companies__company_id__counter_outlets__outlet_id__status_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/counter-sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Open Session */
        post: operations["open_session_v1_companies__company_id__counter_sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/counter-sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Session Detail */
        get: operations["session_detail_v1_companies__company_id__counter_sessions__session_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/counter-sessions/{session_id}/cash-events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Record Cash Movement */
        post: operations["record_cash_movement_v1_companies__company_id__counter_sessions__session_id__cash_events_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/counter-sessions/{session_id}/close": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Close Session */
        post: operations["close_session_v1_companies__company_id__counter_sessions__session_id__close_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/day-book/query": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Activity */
        post: operations["activity_v1_companies__company_id__day_book_query_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/day-book/types/{type_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Type Revisions */
        get: operations["type_revisions_v1_companies__company_id__day_book_types__type_id__revisions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/print-capabilities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Print Capabilities
         * @description What each kind's printer prints from a designed layout; the designer blocks the rest.
         */
        get: operations["print_capabilities_v1_companies__company_id__print_capabilities_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/stock-opening-imports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Listing */
        get: operations["listing_v1_companies__company_id__stock_opening_imports_get"];
        put?: never;
        /** Stage */
        post: operations["stage_v1_companies__company_id__stock_opening_imports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/stock-opening-imports/template": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Template */
        get: operations["template_v1_companies__company_id__stock_opening_imports_template_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/stock-opening-imports/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Detail */
        get: operations["detail_v1_companies__company_id__stock_opening_imports__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/stock-opening-imports/{job_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel */
        post: operations["cancel_v1_companies__company_id__stock_opening_imports__job_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/stock-opening-imports/{job_id}/commit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Commit */
        post: operations["commit_v1_companies__company_id__stock_opening_imports__job_id__commit_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/stock-opening-imports/{job_id}/report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Report */
        get: operations["report_v1_companies__company_id__stock_opening_imports__job_id__report_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/stock-opening-imports/{job_id}/report-ticket": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ticket */
        get: operations["ticket_v1_companies__company_id__stock_opening_imports__job_id__report_ticket_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/stock-opening-imports/{job_id}/validate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Validate */
        post: operations["validate_v1_companies__company_id__stock_opening_imports__job_id__validate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-artifacts/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Artifact Status */
        get: operations["artifact_status_v1_companies__company_id__voucher_artifacts__artifact_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-artifacts/{artifact_id}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download */
        get: operations["download_v1_companies__company_id__voucher_artifacts__artifact_id__download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-capabilities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Capabilities */
        get: operations["capabilities_v1_companies__company_id__voucher_capabilities_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-configuration-bindings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Company Bind */
        post: operations["company_bind_v1_companies__company_id__voucher_configuration_bindings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-configuration-bindings/{object_id}/close": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Close Binding */
        post: operations["close_binding_v1_companies__company_id__voucher_configuration_bindings__object_id__close_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-configurations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Configuration */
        post: operations["create_configuration_v1_companies__company_id__voucher_configurations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-configurations/{object_id}/publish": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Publish Configuration */
        post: operations["publish_configuration_v1_companies__company_id__voucher_configurations__object_id__publish_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-configurations/{object_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revise Configuration */
        post: operations["revise_configuration_v1_companies__company_id__voucher_configurations__object_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-export": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Export */
        get: operations["export_v1_companies__company_id__voucher_export_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-field-adoptions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Adoptions */
        get: operations["adoptions_v1_companies__company_id__voucher_field_adoptions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-field-adoptions/{object_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Adoption Detail */
        get: operations["adoption_detail_v1_companies__company_id__voucher_field_adoptions__object_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-field-adoptions/{object_id}/apply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Apply Adoption */
        post: operations["apply_adoption_v1_companies__company_id__voucher_field_adoptions__object_id__apply_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-field-adoptions/{object_id}/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Adoption */
        post: operations["preview_adoption_v1_companies__company_id__voucher_field_adoptions__object_id__preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-import-template-snapshots": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Template */
        post: operations["create_voucher_import_template_snapshot"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-import-template-snapshots/{template_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Template Snapshot */
        get: operations["get_voucher_import_template_snapshot"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-import-templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Template */
        get: operations["download_voucher_import_template"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Jobs */
        get: operations["list_voucher_imports"];
        put?: never;
        /** Stage */
        post: operations["stage_voucher_import"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Job */
        get: operations["get_voucher_import"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/attempts/{attempt_id}/results": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Results */
        get: operations["list_voucher_import_attempt_results"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel */
        post: operations["cancel_voucher_import"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/commit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Commit */
        post: operations["commit_voucher_import"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Download */
        post: operations["download_voucher_import_data"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/download-ticket": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ticket */
        post: operations["create_voucher_import_download_ticket"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/history/{kind}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** History */
        get: operations["list_voucher_import_history"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/report": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Report */
        get: operations["download_voucher_import_report"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/report-ticket": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Report Ticket */
        get: operations["get_voucher_import_report_ticket"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry */
        post: operations["retry_voucher_import"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revision */
        post: operations["revise_voucher_import"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/run": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Run
         * @description Advance a validating or committing job by one bounded step.
         *
         *     Naturally idempotent: rows move forward once and every draft has its own
         *     per-voucher idempotency key and unique effect, so a repeat creates nothing.
         */
        post: operations["run_voucher_import"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/validate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Validate */
        post: operations["validate_voucher_import"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/vouchers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Vouchers */
        get: operations["list_voucher_import_vouchers"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-imports/{job_id}/vouchers/{import_key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Voucher */
        get: operations["get_voucher_import_voucher"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-kinds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Kinds */
        get: operations["kinds_v1_companies__company_id__voucher_kinds_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-operations/{operation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Operation Detail */
        get: operations["operation_detail_v1_companies__company_id__voucher_operations__operation_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-operations/{operation_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Execution */
        post: operations["cancel_execution_v1_companies__company_id__voucher_operations__operation_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-operations/{operation_id}/recover": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Recover Operation */
        post: operations["recover_operation_v1_companies__company_id__voucher_operations__operation_id__recover_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-print-jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Print Status */
        get: operations["print_status_v1_companies__company_id__voucher_print_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-print-jobs/{job_id}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Print Download */
        get: operations["print_download_v1_companies__company_id__voucher_print_jobs__job_id__download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-series": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Series */
        post: operations["create_series_v1_companies__company_id__voucher_series_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Template */
        post: operations["create_template_v1_companies__company_id__voucher_templates_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-type-defaults/bootstrap": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Bootstrap */
        post: operations["bootstrap_v1_companies__company_id__voucher_type_defaults_bootstrap_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Type */
        post: operations["create_type_v1_companies__company_id__voucher_types_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-types/{object_id}/classes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Class */
        post: operations["create_class_v1_companies__company_id__voucher_types__object_id__classes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-types/{object_id}/configuration-bindings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Type Bind */
        post: operations["type_bind_v1_companies__company_id__voucher_types__object_id__configuration_bindings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-types/{object_id}/effective-configuration": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Effective Configuration */
        get: operations["effective_configuration_v1_companies__company_id__voucher_types__object_id__effective_configuration_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-types/{object_id}/field-set": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Field Set */
        get: operations["field_set_v1_companies__company_id__voucher_types__object_id__field_set_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/voucher-types/{object_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revise Type */
        post: operations["revise_type_v1_companies__company_id__voucher_types__object_id__revisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Voucher */
        post: operations["create_voucher_v1_companies__company_id__vouchers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/duplicate-bills": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Duplicate Bills
         * @description Other live Purchase bills from this supplier with this bill number, in the fiscal year.
         *
         *     Give the supplier ``party_id``, the payable ledger ``party_account_id``, or both; a bill
         *     matches on either. Matching ignores case, runs of whitespace, dash variants, invisible
         *     characters and punctuation around the number. A cancelled, rejected or reversed bill is not a
         *     match, and neither is the voucher named in ``exclude_voucher_id``. At most five rows;
         *     ``truncated`` is true when the search stopped at its ceiling before reading every bill.
         */
        get: operations["duplicate_bills_v1_companies__company_id__vouchers_duplicate_bills_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{object_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Voucher Detail */
        get: operations["voucher_detail_v1_companies__company_id__vouchers__object_id__get"];
        /** Edit Voucher */
        put: operations["edit_voucher_v1_companies__company_id__vouchers__object_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{object_id}/field-set": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Voucher Field Set
         * @description Pinned custom-field definitions for a saved revision, plus its edit view.
         *
         *     Everything is filtered by current read policy. `native`, `custom`, `configuration` and `layouts`
         *     are the type's field-set for this voucher's dates, so a client can edit what it reopened.
         */
        get: operations["voucher_field_set_v1_companies__company_id__vouchers__object_id__field_set_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{object_id}/invoice-acceptance": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Accept Invoice */
        post: operations["accept_invoice_v1_companies__company_id__vouchers__object_id__invoice_acceptance_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{object_id}/invoice-preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Preview Invoice */
        post: operations["preview_invoice_v1_companies__company_id__vouchers__object_id__invoice_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{object_id}/issue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Issue Voucher */
        post: operations["issue_voucher_v1_companies__company_id__vouchers__object_id__issue_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{object_id}/post": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Voucher */
        post: operations["post_voucher_v1_companies__company_id__vouchers__object_id__post_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{object_id}/reverse": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reverse Voucher */
        post: operations["reverse_voucher_v1_companies__company_id__vouchers__object_id__reverse_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{object_id}/revisions/{revision_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Voucher Revision */
        get: operations["voucher_revision_v1_companies__company_id__vouchers__object_id__revisions__revision_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{object_id}/share": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Share Voucher */
        post: operations["share_voucher_v1_companies__company_id__vouchers__object_id__share_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{object_id}/{action}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Voucher Action */
        post: operations["voucher_action_v1_companies__company_id__vouchers__object_id___action__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{voucher_id}/artifacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Artifact */
        post: operations["create_artifact_v1_companies__company_id__vouchers__voucher_id__artifacts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{voucher_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** History */
        get: operations["history_v1_companies__company_id__vouchers__voucher_id__history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{voucher_id}/print-jobs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Print Job */
        post: operations["create_print_job_v1_companies__company_id__vouchers__voucher_id__print_jobs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{voucher_id}/supporting-files": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Listing */
        get: operations["listing_v1_companies__company_id__vouchers__voucher_id__supporting_files_get"];
        put?: never;
        /** Upload */
        post: operations["upload_v1_companies__company_id__vouchers__voucher_id__supporting_files_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/vouchers/{voucher_id}/supporting-files/{file_id}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download */
        get: operations["download_v1_companies__company_id__vouchers__voucher_id__supporting_files__file_id__download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/{resource}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Resource */
        get: operations["list_resource_v1_companies__company_id___resource__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/{resource}/{object_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Resource Detail */
        get: operations["resource_detail_v1_companies__company_id___resource___object_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/{resource}/{object_id}/retire": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retire */
        post: operations["retire_v1_companies__company_id___resource___object_id__retire_post"];
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
        /** AccountEntry */
        "AccountEntry-Input": {
            /**
             * Account Id
             * Format: uuid
             */
            account_id: string;
            /** Amount */
            amount: string;
            /** Bill Reference */
            bill_reference?: string | null;
            /** Currency */
            currency: string;
            /**
             * Description
             * @default
             */
            description?: string;
            /** Due Date */
            due_date?: string | null;
            /**
             * Exchange Rate
             * @default 1
             */
            exchange_rate?: string;
            /**
             * Line Key
             * Format: uuid
             */
            line_key: string;
            /**
             * Purpose
             * @default PRINCIPAL
             * @enum {string}
             */
            purpose?: "PRINCIPAL" | "DISCOUNT" | "FEE" | "ROUNDING";
            /**
             * Side
             * @enum {string}
             */
            side: "DEBIT" | "CREDIT";
            /** Source Version */
            source_version: number;
            /**
             * Tracking
             * @default NONE
             * @enum {string}
             */
            tracking?: "NONE" | "NEW_REF" | "ON_ACCOUNT" | "ADVANCE";
        };
        /** AccountEntry */
        "AccountEntry-Output": {
            /**
             * Account Id
             * Format: uuid
             */
            account_id: string;
            /** Amount */
            amount: string;
            /** Bill Reference */
            bill_reference?: string | null;
            /** Currency */
            currency: string;
            /**
             * Description
             * @default
             */
            description?: string;
            /** Due Date */
            due_date?: string | null;
            /**
             * Exchange Rate
             * @default 1.00000000
             */
            exchange_rate?: string;
            /**
             * Line Key
             * Format: uuid
             */
            line_key: string;
            /**
             * Purpose
             * @default PRINCIPAL
             * @enum {string}
             */
            purpose?: "PRINCIPAL" | "DISCOUNT" | "FEE" | "ROUNDING";
            /**
             * Side
             * @enum {string}
             */
            side: "DEBIT" | "CREDIT";
            /** Source Version */
            source_version: number;
            /**
             * Tracking
             * @default NONE
             * @enum {string}
             */
            tracking?: "NONE" | "NEW_REF" | "ON_ACCOUNT" | "ADVANCE";
        };
        /** ArtifactCreate */
        ArtifactCreate: {
            /** Expected Version */
            expected_version: number;
            /**
             * Reason
             * @default
             */
            reason?: string;
            /** Template Revision Id */
            template_revision_id?: string | null;
        };
        /** AssignmentDetail */
        AssignmentDetail: {
            /** Line Key */
            line_key?: string | null;
            /** Override Reason */
            override_reason?: string | null;
            /**
             * Principal Id
             * Format: uuid
             */
            principal_id: string;
            /**
             * Role
             * @enum {string}
             */
            role: "SELLER" | "BROKER" | "COLLECTOR" | "RETURN_HANDLER" | "PAYMENT_HANDLER";
            /**
             * Share
             * @default 100
             */
            share?: string;
            /** Source Code */
            source_code?: string | null;
            /** Source Name */
            source_name?: string | null;
            /** Source Revision Id */
            source_revision_id?: string | null;
            /** Source Version */
            source_version: number;
        };
        /** AssignmentInput */
        AssignmentInput: {
            /** Line Key */
            line_key?: string | null;
            /** Override Reason */
            override_reason?: string | null;
            /**
             * Principal Id
             * Format: uuid
             */
            principal_id: string;
            /**
             * Role
             * @enum {string}
             */
            role: "SELLER" | "BROKER" | "COLLECTOR" | "RETURN_HANDLER" | "PAYMENT_HANDLER";
            /**
             * Share
             * @default 100
             */
            share?: string;
            /** Source Revision Id */
            source_revision_id?: string | null;
            /** Source Version */
            source_version: number;
        };
        /** AttachmentInput */
        AttachmentInput: {
            /** Content Hash */
            content_hash: string;
            /**
             * Media Type
             * @enum {string}
             */
            media_type: "application/pdf" | "image/png" | "image/jpeg" | "text/plain";
            /** Object Key */
            object_key: string;
            /** Size Bytes */
            size_bytes: number;
        };
        /** AttemptItem */
        AttemptItem: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Outcome */
            outcome: string;
            /**
             * Phase
             * @enum {string}
             */
            phase: "VALIDATE" | "COMMIT";
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
        };
        /** AttemptResultPage */
        AttemptResultPage: {
            /** Items */
            items: components["schemas"]["ImportVoucherDetail"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** BillAllocation */
        "BillAllocation-Input": {
            /**
             * Allocation Key
             * Format: uuid
             */
            allocation_key: string;
            /** Amount */
            amount: string;
            credit: components["schemas"]["BillTarget"];
            /** Currency */
            currency: string;
            debt: components["schemas"]["BillTarget"];
            /** Fx Account Id */
            fx_account_id?: string | null;
        };
        /** BillAllocation */
        "BillAllocation-Output": {
            /**
             * Allocation Key
             * Format: uuid
             */
            allocation_key: string;
            /** Amount */
            amount: string;
            credit: components["schemas"]["BillTarget"];
            /** Currency */
            currency: string;
            debt: components["schemas"]["BillTarget"];
            /** Fx Account Id */
            fx_account_id?: string | null;
        };
        /** BillTarget */
        BillTarget: {
            /** Item Id */
            item_id?: string | null;
            /** Line Key */
            line_key?: string | null;
        };
        /** BindingCreate */
        BindingCreate: {
            /**
             * Configuration Revision Id
             * Format: uuid
             */
            configuration_revision_id: string;
            /** Expected Version */
            expected_version: number;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to?: string | null;
        };
        /** CashMovement */
        CashMovement: {
            /** Amount */
            amount: string;
            /**
             * Direction
             * @enum {string}
             */
            direction: "IN" | "OUT";
            /**
             * Event Key
             * Format: uuid
             */
            event_key: string;
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
            /**
             * Source Revision Id
             * Format: uuid
             */
            source_revision_id: string;
            /**
             * Source Voucher Id
             * Format: uuid
             */
            source_voucher_id: string;
        };
        /** Choice */
        Choice: {
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /** Label */
            label: string;
            /** Value */
            value: string;
        };
        /** ClassCreate */
        ClassCreate: {
            /** Code */
            code: string;
            /** Expected Version */
            expected_version: number;
            /** Name */
            name: string;
            policy?: components["schemas"]["Policy"];
        };
        /** CloseBinding */
        CloseBinding: {
            /** Expected Version */
            expected_version: number;
            /**
             * Reason
             * @default
             */
            reason?: string;
            /**
             * Valid To
             * Format: date
             */
            valid_to: string;
        };
        /**
         * CommercialAttributionConfiguration
         * @description Typed, default-off capture settings; no commission posting authority.
         */
        CommercialAttributionConfiguration: {
            /**
             * Allow Line Assignments
             * @default false
             */
            allow_line_assignments?: boolean;
            /**
             * Broker
             * @default OFF
             * @enum {string}
             */
            broker?: "OFF" | "OPTIONAL" | "REQUIRED";
            /**
             * Collector
             * @default OFF
             * @enum {string}
             */
            collector?: "OFF" | "OPTIONAL" | "REQUIRED";
            /**
             * Max Participants
             * @default 1
             */
            max_participants?: number;
            /**
             * Payment Handler
             * @default OFF
             * @enum {string}
             */
            payment_handler?: "OFF" | "OPTIONAL" | "REQUIRED";
            /**
             * Return Handler
             * @default OFF
             * @enum {string}
             */
            return_handler?: "OFF" | "OPTIONAL" | "REQUIRED";
            /**
             * Seller
             * @default OFF
             * @enum {string}
             */
            seller?: "OFF" | "OPTIONAL" | "REQUIRED";
        };
        /** ComponentAllocation */
        ComponentAllocation: {
            /** Amount */
            amount: string;
            /**
             * Component Key
             * Format: uuid
             */
            component_key: string;
            /**
             * Line Key
             * Format: uuid
             */
            line_key: string;
            /**
             * Purpose
             * @enum {string}
             */
            purpose: "COMMERCIAL" | "TAX_BASE" | "STOCK_COST";
        };
        /** ComponentCalculation */
        ComponentCalculation: {
            /** Amount */
            amount: string;
            /** Basis Amount */
            basis_amount: string;
            /** Basis Quantity */
            basis_quantity: string | null;
            /** Input Amount */
            input_amount: string;
            /**
             * Key
             * Format: uuid
             */
            key: string;
        };
        /** ConfigurationCreate */
        ConfigurationCreate: {
            /** Code */
            code: string;
            /**
             * Family
             * @default COMMON
             * @enum {string}
             */
            family?: "COMMON" | "SALES" | "PURCHASE";
            /** Name */
            name: string;
            policy?: components["schemas"]["Policy"];
        };
        /** CountCapture */
        CountCapture: {
            /** Expected Revision */
            expected_revision: number;
            /**
             * Observation Id
             * Format: uuid
             */
            observation_id: string;
        };
        /** CounterConfiguration */
        CounterConfiguration: {
            /**
             * Mode
             * @default OFF
             * @enum {string}
             */
            mode?: "OFF" | "OPTIONAL" | "REQUIRED";
            /**
             * Session Required
             * @default false
             */
            session_required?: boolean;
        };
        /** CounterCreate */
        CounterCreate: {
            /** Code */
            code: string;
            /** Name */
            name: string;
            /**
             * Outlet Id
             * Format: uuid
             */
            outlet_id: string;
        };
        /** CounterInput */
        CounterInput: {
            /**
             * Counter Id
             * Format: uuid
             */
            counter_id: string;
            /** Session Id */
            session_id?: string | null;
        };
        /** CounterMasterDetail */
        CounterMasterDetail: {
            /** Code */
            code: string;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Outlet Id */
            outlet_id?: string | null;
            /** Row Version */
            row_version: number;
            /** Status */
            status: string;
        };
        /** CounterOperatorDetail */
        CounterOperatorDetail: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Counter Id
             * Format: uuid
             */
            counter_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Row Version */
            row_version: number;
            /** Status */
            status: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** CounterSessionDetail */
        CounterSessionDetail: {
            /** Closed By */
            closed_by: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Counted Cash */
            counted_cash: string | null;
            /**
             * Counter Id
             * Format: uuid
             */
            counter_id: string;
            /** Currency */
            currency: string;
            /** Expected Cash */
            expected_cash: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Opened By
             * Format: uuid
             */
            opened_by: string;
            /** Opening Cash */
            opening_cash: string;
            /** Row Version */
            row_version: number;
            /**
             * Status
             * @enum {string}
             */
            status: "OPEN" | "CLOSED";
            /** Variance */
            variance: string | null;
        };
        /** CustomDefinition */
        CustomDefinition: {
            /**
             * Choices
             * @default []
             */
            choices?: components["schemas"]["Choice"][];
            /**
             * Data Type
             * @enum {string}
             */
            data_type: "text" | "long_text" | "integer" | "decimal" | "boolean" | "date" | "datetime" | "currency_amount" | "select" | "multi_select" | "dynamic_select" | "auto_number";
            /** Default Value */
            default_value?: unknown;
            /** Depends On Key */
            depends_on_key?: string | null;
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /**
             * Is Immutable After Create
             * @default false
             */
            is_immutable_after_create?: boolean;
            /**
             * Is Searchable
             * @default false
             */
            is_searchable?: boolean;
            /** Key */
            key: string;
            /** Option Source Key */
            option_source_key?: string | null;
            sequence_config?: components["schemas"]["SequenceRules"] | null;
            validation?: components["schemas"]["ValidationRules"];
            /** Visibility */
            visibility?: {
                [key: string]: unknown;
            } | null;
        };
        /** DayBookCondition */
        DayBookCondition: {
            /**
             * Field
             * @enum {string}
             */
            field: "number" | "narration" | "kind";
            /**
             * Operator
             * @default contains
             * @enum {string}
             */
            operator?: "contains" | "equals" | "not_contains";
            /** Value */
            value: string;
        };
        /** DayBookDocument */
        DayBookDocument: {
            /** Currency */
            currency: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Kind */
            kind: string;
            /** Narration */
            narration: string;
            /** Number */
            number: string | null;
            /** Particulars */
            particulars: string;
            /** Profile */
            profile: string;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Status */
            status: string;
            /** Type Code */
            type_code: string;
            /**
             * Type Id
             * Format: uuid
             */
            type_id: string;
            /** Type Name */
            type_name: string;
            /**
             * Voucher Id
             * Format: uuid
             */
            voucher_id: string;
        };
        /** DayBookPage */
        DayBookPage: {
            /** Items */
            items: components["schemas"]["DayBookDocument"][];
            /**
             * Observed At
             * Format: date-time
             */
            observed_at: string;
            page: components["schemas"]["PageMeta"];
            /**
             * Scope
             * @default LIVE_DOCUMENTS
             * @constant
             */
            scope?: "LIVE_DOCUMENTS";
            summary: components["schemas"]["DayBookSummary"] | null;
        };
        /** DayBookQuery */
        DayBookQuery: {
            /** Conditions */
            conditions?: components["schemas"]["DayBookCondition"][];
            /** Currency */
            currency?: string | null;
            /** Cursor */
            cursor?: string | null;
            /**
             * Date From
             * Format: date
             */
            date_from: string;
            /**
             * Date To
             * Format: date
             */
            date_to: string;
            /**
             * Include Summary
             * @default false
             */
            include_summary?: boolean;
            /** Kinds */
            kinds?: string[];
            /**
             * Limit
             * @default 50
             */
            limit?: number;
            /**
             * Match
             * @default ALL
             * @enum {string}
             */
            match?: "ALL" | "ANY";
            /** Party Id */
            party_id?: string | null;
            /**
             * Q
             * @default
             */
            q?: string;
            /**
             * Sort
             * @default date
             * @enum {string}
             */
            sort?: "date" | "-date" | "number";
            /** Status */
            status?: string | null;
            /** Type Id */
            type_id?: string | null;
        };
        /** DayBookSummary */
        DayBookSummary: {
            /** By Kind */
            by_kind: {
                [key: string]: number;
            };
            /** By Status */
            by_status: {
                [key: string]: number;
            };
            /** Voucher Count */
            voucher_count: number;
        };
        /** DayBookTypeRevisions */
        DayBookTypeRevisions: {
            /** Revision Ids */
            revision_ids: string[];
            /**
             * Type Id
             * Format: uuid
             */
            type_id: string;
        };
        /** DefaultsCreate */
        DefaultsCreate: {
            /** Expected Features */
            expected_features?: ("inventory" | "bom_definitions" | "approval_workflow" | "multi_currency")[] | null;
        };
        /** DefaultsResult */
        DefaultsResult: {
            /** Catalogue Version */
            catalogue_version: string;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Created Count */
            created_count: number;
            /** Features */
            features: ("inventory" | "bom_definitions" | "approval_workflow" | "multi_currency")[];
            /** Preserved Count */
            preserved_count: number;
            /** Review Count */
            review_count: number;
            /**
             * Status
             * @enum {string}
             */
            status: "READY" | "NEEDS_REVIEW";
            /** Updated Count */
            updated_count: number;
        };
        /** DefinitionFact */
        DefinitionFact: {
            definition: components["schemas"]["CustomDefinition"];
            /**
             * Entity Type
             * @enum {string}
             */
            entity_type: "vouchers.voucher" | "vouchers.voucher_item";
            presentation?: components["schemas"]["Presentation"];
            /** Source Version */
            source_version: number;
        };
        /** DownloadTicket */
        DownloadTicket: {
            /**
             * Expires In
             * @default 300
             */
            expires_in?: number;
            /** Token */
            token: string;
        };
        /** DuplicateBill */
        DuplicateBill: {
            /** Bill Reference */
            bill_reference: string;
            /**
             * Document Date
             * Format: date
             */
            document_date: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Revision Number */
            revision_number: number;
            /** Status */
            status: string;
        };
        /**
         * DuplicateBillList
         * @description At most five rows, most recent first. Not a growing list, so no cursor.
         *
         *     ``truncated`` is true when the candidate walk hit its hard ceiling before reading every bill
         *     of the supplier or ledger in the fiscal year: an older duplicate may exist that was not seen.
         */
        DuplicateBillList: {
            /** Items */
            items: components["schemas"]["DuplicateBill"][];
            /**
             * Truncated
             * @default false
             */
            truncated?: boolean;
        };
        /** ErrorBody */
        ErrorBody: {
            /** Code */
            code: string;
            /** Feature */
            feature?: string | null;
            /** Fields */
            fields?: {
                [key: string]: string;
            } | null;
            /** Message */
            message: string;
            /** Trace Id */
            trace_id?: string | null;
        };
        /** ErrorEnvelope */
        ErrorEnvelope: {
            error: components["schemas"]["ErrorBody"];
        };
        /** FulfillmentTermsInput */
        FulfillmentTermsInput: {
            /**
             * Delivery Terms
             * @default
             */
            delivery_terms?: string;
            /** Destination Reference */
            destination_reference?: string | null;
            /**
             * Payment Terms
             * @default
             */
            payment_terms?: string;
            /**
             * Purpose
             * @enum {string}
             */
            purpose: "PROCURE" | "INTERNAL_ISSUE" | "SALE" | "PURCHASE" | "QUOTE";
            /** Required By */
            required_by?: string | null;
            /** Valid Until */
            valid_until?: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HistoryPage */
        HistoryPage: {
            /** Items */
            items: (components["schemas"]["RevisionItem"] | components["schemas"]["AttemptItem"])[];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** ImportCommit */
        ImportCommit: {
            /**
             * Exclude Keys
             * @default []
             */
            exclude_keys?: string[];
            /** Expected Version */
            expected_version: number;
            /**
             * On Error
             * @default STOP
             * @enum {string}
             */
            on_error?: "STOP" | "CONTINUE_INDEPENDENT";
            /** Selection Digest */
            selection_digest: string;
        };
        /** ImportDownload */
        ImportDownload: {
            /** Attempt Id */
            attempt_id?: string | null;
            /**
             * Format
             * @default CSV
             * @enum {string}
             */
            format?: "CSV" | "TSV" | "XLSX" | "JSON";
            /**
             * Kind
             * @default RESULT
             * @enum {string}
             */
            kind?: "SOURCE" | "NORMALIZED" | "CORRECTION" | "RESULT";
            /** Revision */
            revision?: number | null;
        };
        /** ImportDownloadRequest */
        ImportDownloadRequest: {
            /** Attempt Id */
            attempt_id?: string | null;
            /**
             * Format
             * @default CSV
             * @enum {string}
             */
            format?: "CSV" | "TSV" | "XLSX" | "JSON";
            /**
             * Kind
             * @default RESULT
             * @enum {string}
             */
            kind?: "SOURCE" | "NORMALIZED" | "CORRECTION" | "RESULT";
            /** Revision */
            revision?: number | null;
            /** Token */
            token: string;
        };
        /** ImportIssue */
        ImportIssue: {
            /** Code */
            code: string;
            /** Column */
            column: string | null;
            /** Layer */
            layer: string;
            /** Message */
            message: string;
            /** Row */
            row: number;
            /**
             * Severity
             * @default error
             * @enum {string}
             */
            severity?: "error" | "warning";
            /** Sheet */
            sheet: string;
        };
        /** ImportJobDetail */
        ImportJobDetail: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Created Count */
            created_count: number;
            /**
             * Duplicate Rule
             * @enum {string}
             */
            duplicate_rule: "DATE_NUMBER_PARTY" | "DATE_NUMBER" | "DATE_NUMBER_ACCOUNT";
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Failed Count */
            failed_count: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Sha256 */
            input_sha256: string;
            /** Invalid Count */
            invalid_count: number;
            /** Kind */
            kind: string;
            /**
             * On Error
             * @enum {string}
             */
            on_error: "STOP" | "CONTINUE_INDEPENDENT";
            /** Own */
            own: boolean;
            /** Revision */
            revision: number;
            /** Row Version */
            row_version: number;
            /** Selection Digest */
            selection_digest: string | null;
            /**
             * Source Format
             * @enum {string}
             */
            source_format: "CSV" | "TSV" | "XLSX" | "JSON";
            /**
             * State
             * @enum {string}
             */
            state: "STAGED" | "VALIDATING" | "READY" | "COMMITTING" | "SUCCEEDED" | "PARTIAL" | "FAILED" | "CANCELLED" | "EXPIRED";
            /**
             * Type Id
             * Format: uuid
             */
            type_id: string;
            /**
             * Type Revision Id
             * Format: uuid
             */
            type_revision_id: string;
            /** Valid Count */
            valid_count: number;
            /** Voucher Count */
            voucher_count: number;
            /** Warning Count */
            warning_count: number;
        };
        /** ImportJobListItem */
        ImportJobListItem: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Created Count */
            created_count: number;
            /** Failed Count */
            failed_count: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Invalid Count */
            invalid_count: number;
            /** Kind */
            kind: string;
            /** Own */
            own: boolean;
            /** Row Version */
            row_version: number;
            /**
             * Source Format
             * @enum {string}
             */
            source_format: "CSV" | "TSV" | "XLSX" | "JSON";
            /**
             * State
             * @enum {string}
             */
            state: "STAGED" | "VALIDATING" | "READY" | "COMMITTING" | "SUCCEEDED" | "PARTIAL" | "FAILED" | "CANCELLED" | "EXPIRED";
            /** Valid Count */
            valid_count: number;
            /** Voucher Count */
            voucher_count: number;
            /** Warning Count */
            warning_count: number;
        };
        /** ImportJobPage */
        ImportJobPage: {
            /** Items */
            items: components["schemas"]["ImportJobListItem"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** ImportListItem */
        ImportListItem: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Row Version */
            row_version: number;
            /** Source Key */
            source_key: string;
            /** State */
            state: string;
        };
        /** ImportRevisionInput */
        ImportRevisionInput: {
            /** Content Base64 */
            content_base64?: string | null;
            /** Document */
            document?: {
                [key: string]: unknown;
            } | null;
            /**
             * Duplicate Rule
             * @default DATE_NUMBER_PARTY
             * @enum {string}
             */
            duplicate_rule?: "DATE_NUMBER_PARTY" | "DATE_NUMBER" | "DATE_NUMBER_ACCOUNT";
            /** Expected Version */
            expected_version: number;
            /**
             * Format
             * @enum {string}
             */
            format: "CSV" | "TSV" | "XLSX" | "JSON";
            /** Template Id */
            template_id?: string | null;
            /**
             * Voucher Type Id
             * Format: uuid
             */
            voucher_type_id: string;
        };
        /** ImportStage */
        ImportStage: {
            /** Content Base64 */
            content_base64?: string | null;
            /** Document */
            document?: {
                [key: string]: unknown;
            } | null;
            /**
             * Duplicate Rule
             * @default DATE_NUMBER_PARTY
             * @enum {string}
             */
            duplicate_rule?: "DATE_NUMBER_PARTY" | "DATE_NUMBER" | "DATE_NUMBER_ACCOUNT";
            /**
             * Format
             * @enum {string}
             */
            format: "CSV" | "TSV" | "XLSX" | "JSON";
            /** Template Id */
            template_id?: string | null;
            /**
             * Voucher Type Id
             * Format: uuid
             */
            voucher_type_id: string;
        };
        /** ImportVersion */
        ImportVersion: {
            /** Expected Version */
            expected_version: number;
        };
        /** ImportVoucherDetail */
        ImportVoucherDetail: {
            /** Computed Payable */
            computed_payable: string | null;
            /** Computed Tax Total */
            computed_tax_total: string | null;
            /** Currency */
            currency: string | null;
            /** Declared Total */
            declared_total: string | null;
            /** Error Count */
            error_count: number;
            /** Errors */
            errors: components["schemas"]["ImportIssue"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Import Key */
            import_key: string;
            /** Ordinal */
            ordinal: number;
            /** Row Version */
            row_version: number;
            /** Source Input */
            source_input?: {
                [key: string]: unknown;
            } | null;
            /** Source Rows */
            source_rows: [
                string,
                number
            ][];
            /**
             * State
             * @enum {string}
             */
            state: "STAGED" | "VALID" | "WARNING" | "INVALID" | "BLOCKED" | "CREATED" | "FAILED" | "NOT_SELECTED";
            /** Supplier Difference */
            supplier_difference: string | null;
            /** Voucher Id */
            voucher_id: string | null;
        };
        /** ImportVoucherListItem */
        ImportVoucherListItem: {
            /** Computed Payable */
            computed_payable: string | null;
            /** Currency */
            currency: string | null;
            /** Declared Total */
            declared_total: string | null;
            /** Error Count */
            error_count: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Import Key */
            import_key: string;
            /** Ordinal */
            ordinal: number;
            /** Row Version */
            row_version: number;
            /**
             * State
             * @enum {string}
             */
            state: "STAGED" | "VALID" | "WARNING" | "INVALID" | "BLOCKED" | "CREATED" | "FAILED" | "NOT_SELECTED";
            /** Supplier Difference */
            supplier_difference: string | null;
            /** Voucher Id */
            voucher_id: string | null;
        };
        /** ImportVoucherPage */
        ImportVoucherPage: {
            /** Items */
            items: components["schemas"]["ImportVoucherListItem"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** InvoiceAcceptance */
        InvoiceAcceptance: {
            /** Calculation Hash */
            calculation_hash: string;
            /** Expected Version */
            expected_version: number;
        };
        /** InvoiceCalculationDetail */
        InvoiceCalculationDetail: {
            /** Allocations */
            allocations: components["schemas"]["ComponentAllocation"][];
            /** Calculation Hash */
            calculation_hash: string;
            /**
             * Calculation Version
             * @default 1
             * @constant
             */
            calculation_version?: 1;
            /** Charged Tax Total */
            charged_tax_total: string;
            /** Commercial Total */
            commercial_total: string;
            /** Components */
            components: components["schemas"]["ComponentCalculation"][];
            /** Currency */
            currency: string;
            /** Lines */
            lines: components["schemas"]["SupplyCalculation"][];
            /** Payable */
            payable: string;
            /** Rounding */
            rounding: string;
            /** Supplier Difference */
            supplier_difference?: string | null;
            /** Tax Evidence */
            tax_evidence: {
                [key: string]: unknown;
            }[];
            /** Tax Total */
            tax_total: string;
        };
        /** InvoiceComponent */
        InvoiceComponent: {
            /** Account Id */
            account_id?: string | null;
            /** Account Version */
            account_version?: number | null;
            /**
             * Allocation Basis
             * @default VALUE
             * @enum {string}
             */
            allocation_basis?: "VALUE" | "QUANTITY";
            /**
             * Amount Basis
             * @default NET_EXCL_TAX
             * @enum {string}
             */
            amount_basis?: "NET_EXCL_TAX" | "GROSS_INCL_TAX";
            /**
             * Commercial Treatment
             * @default COUNTERPARTY
             * @enum {string}
             */
            commercial_treatment?: "COUNTERPARTY" | "THIRD_PARTY_COST";
            /**
             * Component Key
             * Format: uuid
             */
            component_key: string;
            /**
             * Cost Allocation Basis
             * @default VALUE
             * @enum {string}
             */
            cost_allocation_basis?: "VALUE" | "QUANTITY";
            /**
             * Cost Targets
             * @default []
             */
            cost_targets?: string[];
            /**
             * Denominator
             * @default 1
             */
            denominator?: string;
            /**
             * Dependencies
             * @default []
             */
            dependencies?: string[];
            /**
             * Effect
             * @enum {string}
             */
            effect: "ADD" | "DEDUCT";
            /**
             * Input Kind
             * @enum {string}
             */
            input_kind: "FIXED" | "PERCENT" | "PER_QUANTITY";
            /**
             * Purpose
             * @enum {string}
             */
            purpose: "DISCOUNT" | "FREIGHT" | "PACKING" | "INSURANCE" | "HANDLING" | "OTHER_CHARGE";
            /** Quantity Basis */
            quantity_basis?: ("ACTUAL" | "BILLED" | "ACCEPTED" | "RETURNED" | "MEASURED") | null;
            /**
             * Return Treatment
             * @default PROPORTIONAL
             * @enum {string}
             */
            return_treatment?: "PROPORTIONAL" | "NONRETURNABLE";
            /**
             * Scope
             * @enum {string}
             */
            scope: "LINE" | "SELECTED_LINES" | "INVOICE";
            /** Source Evidence */
            source_evidence: string;
            /** Targets */
            targets: string[];
            /** Tax Allocation Basis */
            tax_allocation_basis?: ("VALUE" | "QUANTITY") | null;
            /**
             * Tax Targets
             * @default []
             */
            tax_targets?: string[];
            /**
             * Tax Treatment
             * @default ASSESSABLE
             * @enum {string}
             */
            tax_treatment?: "ASSESSABLE" | "NO_CHANGE";
            /** Unit Id */
            unit_id?: string | null;
            /** Value */
            value: string;
        };
        /** InvoiceInput */
        "InvoiceInput-Input": {
            /** Accepted Calculation Hash */
            accepted_calculation_hash?: string | null;
            /**
             * Allocations
             * @default []
             */
            allocations?: components["schemas"]["BillAllocation-Input"][];
            /** Bill Reference */
            bill_reference: string;
            /**
             * Components
             * @default []
             */
            components?: components["schemas"]["InvoiceComponent"][];
            /**
             * Due Date
             * Format: date
             */
            due_date: string;
            /**
             * Exchange Rate
             * @default 1
             */
            exchange_rate?: string;
            /**
             * Party Account Id
             * Format: uuid
             */
            party_account_id: string;
            /** Party Account Version */
            party_account_version: number;
            /**
             * Party Line Key
             * Format: uuid
             */
            party_line_key: string;
            /** Payable Total */
            payable_total?: string | null;
            /** Rounding Account Id */
            rounding_account_id?: string | null;
            /** Rounding Account Version */
            rounding_account_version?: number | null;
            /** Rounding Increment */
            rounding_increment?: string | null;
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version?: 1;
            /** Source Invoice Id */
            source_invoice_id?: string | null;
            /** Supplier Declared Total */
            supplier_declared_total?: string | null;
            /** Supplier Difference Reason */
            supplier_difference_reason?: string | null;
            /** Supplies */
            supplies: components["schemas"]["InvoiceSupply"][];
            tax: components["schemas"]["InvoiceTaxContext"];
            /**
             * Tenders
             * @default []
             */
            tenders?: components["schemas"]["InvoiceSettlement"][];
        };
        "InvoiceInput-Output": {
            [key: string]: unknown;
        };
        /** InvoicePolicy */
        InvoicePolicy: {
            /**
             * Allowed Component Inputs
             * @default [
             *       "FIXED",
             *       "PERCENT",
             *       "PER_QUANTITY"
             *     ]
             */
            allowed_component_inputs?: ("FIXED" | "PERCENT" | "PER_QUANTITY")[];
            /**
             * Allowed Price Bases
             * @default [
             *       "GROSS_INCL_TAX",
             *       "NET_EXCL_TAX"
             *     ]
             */
            allowed_price_bases?: ("NET_EXCL_TAX" | "GROSS_INCL_TAX")[];
            /**
             * Allowed Scopes
             * @default [
             *       "INVOICE",
             *       "LINE",
             *       "SELECTED_LINES"
             *     ]
             */
            allowed_scopes?: ("LINE" | "SELECTED_LINES" | "INVOICE")[];
            /**
             * Allowed Supply Kinds
             * @default [
             *       "ACCOUNT",
             *       "GOODS",
             *       "SERVICE"
             *     ]
             */
            allowed_supply_kinds?: ("GOODS" | "SERVICE" | "ACCOUNT")[];
            /**
             * Charges Allowed
             * @default false
             */
            charges_allowed?: boolean;
            /**
             * Deal Manual Stacking Allowed
             * @default false
             */
            deal_manual_stacking_allowed?: boolean;
            /**
             * Discount Amount Bases
             * @default [
             *       "GROSS_INCL_TAX",
             *       "NET_EXCL_TAX"
             *     ]
             */
            discount_amount_bases?: ("NET_EXCL_TAX" | "GROSS_INCL_TAX")[];
            /**
             * Discount Compounding Allowed
             * @default true
             */
            discount_compounding_allowed?: boolean;
            /**
             * Discount Input Kinds
             * @default [
             *       "FIXED",
             *       "PERCENT",
             *       "PER_QUANTITY"
             *     ]
             */
            discount_input_kinds?: ("FIXED" | "PERCENT" | "PER_QUANTITY")[];
            /**
             * Independent Tax Allocation Allowed
             * @default false
             */
            independent_tax_allocation_allowed?: boolean;
            /**
             * Manual Discounts Allowed
             * @default false
             */
            manual_discounts_allowed?: boolean;
            /**
             * Manual Free Allowed
             * @default false
             */
            manual_free_allowed?: boolean;
            /**
             * Max Allocations
             * @default 4000
             */
            max_allocations?: number;
            /**
             * Max Components
             * @default 200
             */
            max_components?: number;
            /** Max Discount Amount */
            max_discount_amount?: string | null;
            /**
             * Max Discount Components
             * @default 200
             */
            max_discount_components?: number;
            /**
             * Max Discount Pct
             * @default 100
             */
            max_discount_pct?: string;
            /**
             * Purchase Supply Natures
             * @default [
             *       "ASSET",
             *       "EXPENSE"
             *     ]
             */
            purchase_supply_natures?: ("EXPENSE" | "ASSET")[];
            /**
             * Sales Advance Adjustments Allowed
             * @default true
             */
            sales_advance_adjustments_allowed?: boolean;
            /**
             * Sales Charge Purposes
             * @default [
             *       "FREIGHT",
             *       "HANDLING",
             *       "INSURANCE",
             *       "OTHER_CHARGE",
             *       "PACKING"
             *     ]
             */
            sales_charge_purposes?: ("FREIGHT" | "PACKING" | "INSURANCE" | "HANDLING" | "OTHER_CHARGE")[];
            /**
             * Sales Charge Scopes
             * @default [
             *       "INVOICE",
             *       "LINE",
             *       "SELECTED_LINES"
             *     ]
             */
            sales_charge_scopes?: ("LINE" | "SELECTED_LINES" | "INVOICE")[];
            /**
             * Sales Credit Allowed
             * @default true
             */
            sales_credit_allowed?: boolean;
            /**
             * Sales Discount Scopes
             * @default [
             *       "INVOICE",
             *       "LINE",
             *       "SELECTED_LINES"
             *     ]
             */
            sales_discount_scopes?: ("LINE" | "SELECTED_LINES" | "INVOICE")[];
            /**
             * Sales Invoice Rounding Allowed
             * @default true
             */
            sales_invoice_rounding_allowed?: boolean;
            /** Sales Party Account Ids */
            sales_party_account_ids?: string[] | null;
            /**
             * Sales Split Tenders Allowed
             * @default true
             */
            sales_split_tenders_allowed?: boolean;
            /** Sales Supply Account Ids */
            sales_supply_account_ids?: string[] | null;
            /**
             * Sales Supply Natures
             * @default [
             *       "INCOME"
             *     ]
             */
            sales_supply_natures?: ("INCOME" | "ASSET")[];
            /**
             * Sales Tax Profiles
             * @default [
             *       "INDIA_DOMESTIC_SERVICE",
             *       "INDIA_DOMESTIC_SERVICE_RCM",
             *       "UNTAXED_ACCOUNT"
             *     ]
             */
            sales_tax_profiles?: ("INDIA_DOMESTIC_SERVICE" | "INDIA_DOMESTIC_SERVICE_RCM" | "UNTAXED_ACCOUNT")[];
            /**
             * Sales Tender Modes
             * @default [
             *       "BANK_TRANSFER",
             *       "CARD",
             *       "CASH",
             *       "CHEQUE",
             *       "IMPS",
             *       "NEFT",
             *       "RTGS",
             *       "UPI"
             *     ]
             */
            sales_tender_modes?: ("CASH" | "CHEQUE" | "NEFT" | "RTGS" | "IMPS" | "UPI" | "CARD" | "BANK_TRANSFER")[];
            /**
             * Same Item Deals Allowed
             * @default false
             */
            same_item_deals_allowed?: boolean;
            /**
             * Supplier Difference Limit
             * @default 0
             */
            supplier_difference_limit?: string;
        };
        /** InvoiceQuantity */
        InvoiceQuantity: {
            /**
             * Basis
             * @enum {string}
             */
            basis: "ACTUAL" | "BILLED" | "ACCEPTED" | "RETURNED" | "MEASURED";
            /** Quantity */
            quantity: string;
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
        };
        /** InvoiceSettlement */
        InvoiceSettlement: {
            /**
             * Account Id
             * Format: uuid
             */
            account_id: string;
            /** Account Version */
            account_version: number;
            tender: components["schemas"]["Tender-Input"];
        };
        /** InvoiceSupply */
        InvoiceSupply: {
            /**
             * Account Id
             * Format: uuid
             */
            account_id: string;
            /** Account Version */
            account_version: number;
            /** Amount */
            amount: string;
            /** Description */
            description: string;
            /**
             * Free Purpose
             * @default NONE
             * @enum {string}
             */
            free_purpose?: "NONE" | "MANUAL_PAID_BUNDLE" | "SCHEME_PAID_BUNDLE" | "GIFT" | "SAMPLE";
            /** Free Reason */
            free_reason?: string | null;
            /** Input Credit */
            input_credit?: ("ELIGIBLE" | "INELIGIBLE") | null;
            /** Input Credit Reason */
            input_credit_reason?: string | null;
            /** Item Line Key */
            item_line_key?: string | null;
            /**
             * Line Key
             * Format: uuid
             */
            line_key: string;
            /**
             * Price Basis
             * @default NET_EXCL_TAX
             * @enum {string}
             */
            price_basis?: "NET_EXCL_TAX" | "GROSS_INCL_TAX";
            /**
             * Price Denominator
             * @default 1
             */
            price_denominator?: string;
            /** Promotion Revision Id */
            promotion_revision_id?: string | null;
            /** Promotion Version */
            promotion_version?: number | null;
            /**
             * Quantities
             * @default []
             */
            quantities?: components["schemas"]["InvoiceQuantity"][];
            /**
             * Supply Kind
             * @enum {string}
             */
            supply_kind: "ACCOUNT" | "SERVICE" | "GOODS";
            tax?: components["schemas"]["InvoiceTaxContext"] | null;
            /** Unit Price */
            unit_price?: string | null;
        };
        /** InvoiceTaxContext */
        InvoiceTaxContext: {
            /** Company Registration Id */
            company_registration_id?: string | null;
            /**
             * Date Contract Version
             * @default 2
             * @constant
             */
            date_contract_version?: 2;
            /** Party Registration Id */
            party_registration_id?: string | null;
            /** Payment Date */
            payment_date?: string | null;
            /** Place Of Supply */
            place_of_supply?: string | null;
            /**
             * Profile
             * @enum {string}
             */
            profile: "INDIA_DOMESTIC_SERVICE" | "INDIA_DOMESTIC_SERVICE_RCM" | "INDIA_DOMESTIC_GOODS" | "UNTAXED_ACCOUNT";
            /** Service Completion Date */
            service_completion_date?: string | null;
            /** Supplier Invoice Date */
            supplier_invoice_date?: string | null;
            /** Supplier Invoice Number */
            supplier_invoice_number?: string | null;
            /** Withholding Section Id */
            withholding_section_id?: string | null;
        };
        /** IssueRequest */
        IssueRequest: {
            /** Expected Version */
            expected_version: number;
            /** Manual Number */
            manual_number?: string | null;
            /**
             * Reason
             * @default
             */
            reason?: string;
            /** Requested Sequence */
            requested_sequence?: number | null;
            /** Series Id */
            series_id?: string | null;
        };
        /** ItemInput */
        ItemInput: {
            /** Actual Quantity */
            actual_quantity: string;
            /** Billed Quantity */
            billed_quantity: string;
            /** Custom Fields */
            custom_fields?: {
                [key: string]: unknown;
            };
            /**
             * Item Id
             * Format: uuid
             */
            item_id: string;
            /** Item Version */
            item_version: number;
            /** Planned Quantity */
            planned_quantity?: string | null;
            /**
             * Unit Id
             * Format: uuid
             */
            unit_id: string;
        };
        /**
         * JobProcessConfiguration
         * @description Immutable direction and restrictive preparation choices for job work.
         */
        JobProcessConfiguration: {
            /**
             * Allowed Consumption Modes
             * @default [
             *       "SEPARATE"
             *     ]
             */
            allowed_consumption_modes?: ("SEPARATE" | "COMBINED")[];
            /**
             * Bom Required
             * @default false
             */
            bom_required?: boolean;
            /**
             * Order Required
             * @default false
             */
            order_required?: boolean;
            /** Role */
            role?: ("PRINCIPAL" | "WORKER") | null;
        };
        /**
         * LayoutPreview
         * @description One saved design version to print this bill on once, to check it (designer plan R4).
         */
        LayoutPreview: {
            /**
             * Template Id
             * Format: uuid
             */
            template_id: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /** LineInput */
        LineInput: {
            /**
             * Description
             * @default
             */
            description?: string;
            item: components["schemas"]["ItemInput"];
            /**
             * Line Key
             * Format: uuid
             */
            line_key: string;
            /**
             * Line Kind
             * @default ITEM
             * @constant
             */
            line_kind?: "ITEM";
        };
        /** LinkInput */
        LinkInput: {
            /**
             * Purpose
             * @default REFERENCE
             * @constant
             */
            purpose?: "REFERENCE";
            /**
             * Source Revision Id
             * Format: uuid
             */
            source_revision_id: string;
            /**
             * Source Voucher Id
             * Format: uuid
             */
            source_voucher_id: string;
        };
        /**
         * ManufacturingConfiguration
         * @description Definition-stage limits; these fields never authorize physical production.
         */
        ManufacturingConfiguration: {
            /**
             * Allowed Output Roles
             * @default [
             *       "BY_PRODUCT",
             *       "CO_PRODUCT",
             *       "PRIMARY",
             *       "SCRAP"
             *     ]
             */
            allowed_output_roles?: ("PRIMARY" | "CO_PRODUCT" | "BY_PRODUCT" | "SCRAP")[];
            /**
             * Bom Required
             * @default true
             */
            bom_required?: boolean;
            /**
             * Manual Variance Allowed
             * @default false
             */
            manual_variance_allowed?: boolean;
            /**
             * Max Input Lines
             * @default 200
             */
            max_input_lines?: number;
            /**
             * Max Output Lines
             * @default 20
             */
            max_output_lines?: number;
            /**
             * Partial Runs Allowed
             * @default false
             */
            partial_runs_allowed?: boolean;
        };
        /** MasterFact */
        MasterFact: {
            /**
             * Entity Type
             * @enum {string}
             */
            entity_type: "company" | "item" | "item_transaction_policy" | "item_unit_revision" | "unit" | "item_regulatory_classification" | "party" | "party_drug_licence" | "broker_party" | "account" | "fiscal_period" | "salesperson";
            /** Facts */
            facts?: {
                [key: string]: string | number | boolean | null;
            };
            /**
             * Source Id
             * Format: uuid
             */
            source_id: string;
            /** Source Version */
            source_version: number;
            /**
             * Status
             * @enum {string}
             */
            status: "ACTIVE" | "RETIRED";
        };
        /** MasterStatusUpdate */
        MasterStatusUpdate: {
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ACTIVE" | "INACTIVE";
        };
        /**
         * MoneyConfiguration
         * @description V2 voucher-facing restrictions on the existing owner-validated money input.
         */
        MoneyConfiguration: {
            /**
             * Allowed Purposes
             * @default [
             *       "ADVANCE",
             *       "BILL_ADJUSTMENT",
             *       "GENERAL",
             *       "REFUND",
             *       "SETTLEMENT",
             *       "TRANSFER"
             *     ]
             */
            allowed_purposes?: ("GENERAL" | "TRANSFER" | "SETTLEMENT" | "ADVANCE" | "REFUND" | "BILL_ADJUSTMENT")[];
            /**
             * Allowed Tender Modes
             * @default [
             *       "BANK_TRANSFER",
             *       "CARD",
             *       "CASH",
             *       "CHEQUE",
             *       "IMPS",
             *       "NEFT",
             *       "RTGS",
             *       "UPI"
             *     ]
             */
            allowed_tender_modes?: ("CASH" | "CHEQUE" | "NEFT" | "RTGS" | "IMPS" | "UPI" | "CARD" | "BANK_TRANSFER")[];
            /**
             * Max Tenders
             * @default 200
             */
            max_tenders?: number;
        };
        /** MoneyInput */
        "MoneyInput-Input": {
            /**
             * Accounts
             * @default []
             */
            accounts?: components["schemas"]["AccountEntry-Input"][];
            /**
             * Allocations
             * @default []
             */
            allocations?: components["schemas"]["BillAllocation-Input"][];
            /**
             * Purpose
             * @default GENERAL
             * @enum {string}
             */
            purpose?: "GENERAL" | "TRANSFER" | "SETTLEMENT" | "ADVANCE" | "REFUND" | "BILL_ADJUSTMENT";
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version?: 1;
            /**
             * Tenders
             * @default []
             */
            tenders?: components["schemas"]["Tender-Input"][];
        };
        /** MoneyInput */
        "MoneyInput-Output": {
            /**
             * Accounts
             * @default []
             */
            accounts?: components["schemas"]["AccountEntry-Output"][];
            /**
             * Allocations
             * @default []
             */
            allocations?: components["schemas"]["BillAllocation-Output"][];
            /**
             * Purpose
             * @default GENERAL
             * @enum {string}
             */
            purpose?: "GENERAL" | "TRANSFER" | "SETTLEMENT" | "ADVANCE" | "REFUND" | "BILL_ADJUSTMENT";
            /**
             * Schema Version
             * @default 1
             * @constant
             */
            schema_version?: 1;
            /**
             * Tenders
             * @default []
             */
            tenders?: components["schemas"]["Tender-Output"][];
        };
        /**
         * MoneyPolicy
         * @description Controls can narrow compiled capabilities; dimensions and tax are later contracts.
         */
        MoneyPolicy: {
            /**
             * Allocations Allowed
             * @default true
             */
            allocations_allowed?: boolean;
            /** Allowed Account Ids */
            allowed_account_ids?: string[] | null;
            /**
             * Allowed Account Kinds
             * @default [
             *       "BANK",
             *       "CASH",
             *       "GENERAL",
             *       "PARTY"
             *     ]
             */
            allowed_account_kinds?: ("GENERAL" | "CASH" | "BANK" | "PARTY")[];
            /**
             * Allowed Payment Modes
             * @default [
             *       "BANK_TRANSFER",
             *       "CARD",
             *       "CASH",
             *       "CHEQUE",
             *       "IMPS",
             *       "NEFT",
             *       "RTGS",
             *       "UPI"
             *     ]
             */
            allowed_payment_modes?: ("CASH" | "CHEQUE" | "NEFT" | "RTGS" | "IMPS" | "UPI" | "CARD" | "BANK_TRANSFER")[];
            /**
             * Allowed Recognition
             * @default [
             *       "BOOK_DATE",
             *       "MATURITY_DATE"
             *     ]
             */
            allowed_recognition?: ("BOOK_DATE" | "MATURITY_DATE")[];
            /**
             * Allowed Tracking
             * @default [
             *       "ADVANCE",
             *       "NEW_REF",
             *       "NONE",
             *       "ON_ACCOUNT"
             *     ]
             */
            allowed_tracking?: ("NONE" | "NEW_REF" | "ON_ACCOUNT" | "ADVANCE")[];
            /**
             * Foreign Currency Allowed
             * @default false
             */
            foreign_currency_allowed?: boolean;
            /**
             * Journal Cash Bank Allowed
             * @default false
             */
            journal_cash_bank_allowed?: boolean;
            /**
             * Max Account Entries
             * @default 200
             */
            max_account_entries?: number;
            /**
             * Settlement Adjustments Allowed
             * @default false
             */
            settlement_adjustments_allowed?: boolean;
            /**
             * Split Tenders Allowed
             * @default true
             */
            split_tenders_allowed?: boolean;
        };
        /**
         * NotificationConfiguration
         * @description Opt-in external voucher messages; delivery remains Notification-owned.
         */
        NotificationConfiguration: {
            /**
             * Automatic Events
             * @default []
             */
            automatic_events?: ("ISSUED" | "ACCEPTED" | "POSTED")[];
            /**
             * Channels
             * @default []
             */
            channels?: ("email" | "sms" | "whatsapp")[];
            /**
             * Enabled
             * @default false
             */
            enabled?: boolean;
            /**
             * Manual Share Allowed
             * @default false
             */
            manual_share_allowed?: boolean;
        };
        /** OpeningCapture */
        "OpeningCapture-Input": {
            /**
             * Cohort Order
             * @default 1
             */
            cohort_order?: number;
            /**
             * Cost Mode
             * @enum {string}
             */
            cost_mode: "RATE" | "VALUE";
            /** Entered Quantity */
            entered_quantity: string;
            /**
             * Entered Unit Id
             * Format: uuid
             */
            entered_unit_id: string;
            /** History Known */
            history_known: boolean;
            /** Measured Base Quantity */
            measured_base_quantity?: string | null;
            /**
             * Priced Quantity
             * @default 1
             */
            priced_quantity?: string;
            /** Received On */
            received_on?: string | null;
            /** Source Key */
            source_key: string;
            /** Unit Cost */
            unit_cost?: string | null;
            /**
             * Unit Revision Id
             * Format: uuid
             */
            unit_revision_id: string;
        };
        /** OpeningCapture */
        "OpeningCapture-Output": {
            /**
             * Cohort Order
             * @default 1
             */
            cohort_order?: number;
            /**
             * Cost Mode
             * @enum {string}
             */
            cost_mode: "RATE" | "VALUE";
            /** Entered Quantity */
            entered_quantity: string;
            /**
             * Entered Unit Id
             * Format: uuid
             */
            entered_unit_id: string;
            /** History Known */
            history_known: boolean;
            /** Measured Base Quantity */
            measured_base_quantity?: string | null;
            /**
             * Priced Quantity
             * @default 1.0000
             */
            priced_quantity?: string;
            /** Received On */
            received_on?: string | null;
            /** Source Key */
            source_key: string;
            /** Unit Cost */
            unit_cost?: string | null;
            /**
             * Unit Revision Id
             * Format: uuid
             */
            unit_revision_id: string;
        };
        /** OpeningImportCommit */
        OpeningImportCommit: {
            /** Expected Version */
            expected_version: number;
            /** Review Hash */
            review_hash: string;
        };
        /** OpeningImportDetail */
        OpeningImportDetail: {
            /** Chunk Count */
            chunk_count: number;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Created Chunks */
            created_chunks: number;
            /**
             * Effect Kind
             * @default DRAFT_ONLY
             * @constant
             */
            effect_kind?: "DRAFT_ONLY";
            /** Effects */
            effects: {
                [key: string]: unknown;
            }[];
            /** Errors */
            errors: {
                [key: string]: unknown;
            }[];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Hash */
            input_hash: string;
            /**
             * Posting Required
             * @default true
             */
            posting_required?: boolean;
            /** Review Hash */
            review_hash: string | null;
            /** Row Version */
            row_version: number;
            /** Source Key */
            source_key: string;
            /** State */
            state: string;
            /** Validated Chunks */
            validated_chunks: number;
        };
        /** OpeningImportDocument */
        OpeningImportDocument: {
            /** Vouchers */
            vouchers: components["schemas"]["VoucherInput"][];
        };
        /** OpeningImportStage */
        OpeningImportStage: {
            /** Content Base64 */
            content_base64?: string | null;
            document?: components["schemas"]["OpeningImportDocument"] | null;
            /**
             * Format
             * @default JSON
             * @enum {string}
             */
            format?: "JSON" | "CSV" | "TSV" | "XLSX";
            /** Source Key */
            source_key: string;
        };
        /** OpeningImportVersion */
        OpeningImportVersion: {
            /** Expected Version */
            expected_version: number;
        };
        /** OperationDetail */
        OperationDetail: {
            /** Attempt Count */
            attempt_count: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Purpose */
            purpose: string;
            /** Rejection Code */
            rejection_code?: string | null;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Row Version */
            row_version: number;
            /** Status */
            status: string;
            /**
             * Voucher Id
             * Format: uuid
             */
            voucher_id: string;
        };
        /** OperatorCreate */
        OperatorCreate: {
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** OperatorStatusUpdate */
        OperatorStatusUpdate: {
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ACTIVE" | "INACTIVE";
        };
        /**
         * OrderPolicy
         * @description Bounded capture controls for existing non-posting order/quote/indent profiles.
         */
        OrderPolicy: {
            /**
             * Allowed Purposes
             * @default [
             *       "INTERNAL_ISSUE",
             *       "PROCURE",
             *       "PURCHASE",
             *       "QUOTE",
             *       "SALE"
             *     ]
             */
            allowed_purposes?: ("PROCURE" | "INTERNAL_ISSUE" | "SALE" | "PURCHASE" | "QUOTE")[];
            /**
             * Delivery Terms Required
             * @default false
             */
            delivery_terms_required?: boolean;
            /** Max Required By Days */
            max_required_by_days?: number | null;
            /** Max Validity Days */
            max_validity_days?: number | null;
            /**
             * Payment Terms Required
             * @default false
             */
            payment_terms_required?: boolean;
        };
        /** OutletCreate */
        OutletCreate: {
            /** Code */
            code: string;
            /** Name */
            name: string;
        };
        /** PageMeta */
        PageMeta: {
            /** Has More */
            has_more: boolean;
            /** Limit */
            limit: number;
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** Page[ImportListItem] */
        Page_ImportListItem_: {
            /** Items */
            items: components["schemas"]["ImportListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** PartyInput */
        PartyInput: {
            /**
             * Party Id
             * Format: uuid
             */
            party_id: string;
            /**
             * Role
             * @enum {string}
             */
            role: "CUSTOMER" | "SUPPLIER" | "CONSIGNEE" | "PRINCIPAL" | "WORKER" | "CARRIER" | "OTHER";
            /** Source Version */
            source_version: number;
        };
        /** Policy */
        Policy: {
            /**
             * Allowed Modes
             * @default [
             *       "ACCOUNTS",
             *       "ITEMS",
             *       "MIXED"
             *     ]
             */
            allowed_modes?: ("ACCOUNTS" | "ITEMS" | "MIXED")[];
            /**
             * Allowed Party Roles
             * @default [
             *       "CARRIER",
             *       "CONSIGNEE",
             *       "CUSTOMER",
             *       "OTHER",
             *       "PRINCIPAL",
             *       "SUPPLIER",
             *       "WORKER"
             *     ]
             */
            allowed_party_roles?: ("CUSTOMER" | "SUPPLIER" | "CONSIGNEE" | "PRINCIPAL" | "WORKER" | "CARRIER" | "OTHER")[];
            /** Allowed Series Ids */
            allowed_series_ids?: string[] | null;
            /** Allowed Template Revision Ids */
            allowed_template_revision_ids?: string[] | null;
            /**
             * Approval Required
             * @default true
             */
            approval_required?: boolean;
            /**
             * Backdate Days
             * @default 3650
             */
            backdate_days?: number;
            commercial_attribution?: components["schemas"]["CommercialAttributionConfiguration"] | null;
            counter?: components["schemas"]["CounterConfiguration"] | null;
            /**
             * Default Mode
             * @default ACCOUNTS
             * @enum {string}
             */
            default_mode?: "ACCOUNTS" | "ITEMS" | "MIXED";
            /**
             * Default Narration
             * @default
             */
            default_narration?: string;
            /** Default Series Id */
            default_series_id?: string | null;
            /** Default Template Revision Id */
            default_template_revision_id?: string | null;
            financial?: components["schemas"]["MoneyPolicy"] | null;
            /**
             * Forbidden Sections
             * @default []
             */
            forbidden_sections?: ("ITEMS" | "PARTIES" | "REFERENCES" | "ATTACHMENTS" | "ACCOUNTS" | "CHARGES" | "TAX" | "TENDERS" | "BILL_ALLOCATIONS")[];
            /**
             * Future Days
             * @default 365
             */
            future_days?: number;
            /** Header Field Keys */
            header_field_keys?: string[] | null;
            invoice?: components["schemas"]["InvoicePolicy"] | null;
            /** Item Field Keys */
            item_field_keys?: string[] | null;
            job_process?: components["schemas"]["JobProcessConfiguration"] | null;
            /**
             * Line Description Required
             * @default false
             */
            line_description_required?: boolean;
            manufacturing?: components["schemas"]["ManufacturingConfiguration"] | null;
            /**
             * Max Lines
             * @default 200
             */
            max_lines?: number;
            /**
             * Max Parties
             * @default 20
             */
            max_parties?: number;
            money?: components["schemas"]["MoneyConfiguration"] | null;
            /**
             * Narration Required
             * @default false
             */
            narration_required?: boolean;
            notification?: components["schemas"]["NotificationConfiguration"] | null;
            order?: components["schemas"]["OrderPolicy"] | null;
            purchase_calculation?: components["schemas"]["PurchaseCalculationPolicy"] | null;
            /**
             * Required Header Fields
             * @default []
             */
            required_header_fields?: string[];
            /**
             * Required Item Fields
             * @default []
             */
            required_item_fields?: string[];
            /**
             * Required Sections
             * @default []
             */
            required_sections?: ("ITEMS" | "PARTIES" | "REFERENCES" | "ATTACHMENTS" | "ACCOUNTS" | "CHARGES" | "TAX" | "TENDERS" | "BILL_ALLOCATIONS")[];
            sales_workflow?: components["schemas"]["SalesWorkflowConfiguration"] | null;
            /**
             * Schema Version
             * @default 1
             * @enum {integer}
             */
            schema_version?: 1 | 2;
            /**
             * Self Approval Allowed
             * @default false
             */
            self_approval_allowed?: boolean;
            stock?: components["schemas"]["StockPolicy"] | null;
            /**
             * Supplier Reference Required
             * @default false
             */
            supplier_reference_required?: boolean;
        };
        /** PostingOperation */
        PostingOperation: {
            /**
             * Execution Id
             * Format: uuid
             */
            execution_id: string;
            /**
             * Operation Id
             * Format: uuid
             */
            operation_id: string;
            /** Row Version */
            row_version: number;
            /** Status */
            status: string;
            /**
             * Voucher Id
             * Format: uuid
             */
            voucher_id: string;
        };
        /** Presentation */
        Presentation: {
            /** Help Text */
            help_text?: string | null;
            /**
             * Label
             * @default
             */
            label?: string;
        };
        /** PrintCreate */
        PrintCreate: {
            /** Expected Version */
            expected_version: number;
            layout_preview?: components["schemas"]["LayoutPreview"] | null;
            /**
             * Reason
             * @default
             */
            reason?: string;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
        };
        /** PrintJobDetail */
        PrintJobDetail: {
            /** Attempt */
            attempt: number;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Content Hash */
            content_hash?: string | null;
            /** Document Status */
            document_status: string;
            /** Download Token */
            download_token?: string | null;
            /** Failure Code */
            failure_code?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Layout Name */
            layout_name: string;
            /** Layout Version */
            layout_version: string;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Revision Number */
            revision_number: number;
            /** Size Bytes */
            size_bytes?: number | null;
            /**
             * Status
             * @enum {string}
             */
            status: "PENDING" | "RUNNING" | "READY" | "FAILED";
            /**
             * Voucher Id
             * Format: uuid
             */
            voucher_id: string;
        };
        /** PurchaseCalculationPolicy */
        PurchaseCalculationPolicy: {
            /** Default Preset */
            default_preset?: string | null;
            /**
             * Presets
             * @default []
             */
            presets?: components["schemas"]["PurchaseCalculationPreset"][];
        };
        /** PurchaseCalculationPreset */
        PurchaseCalculationPreset: {
            /** Key */
            key: string;
            /** Name */
            name: string;
            /**
             * Steps
             * @default []
             */
            steps?: components["schemas"]["PurchaseCalculationStep"][];
        };
        /** PurchaseCalculationStep */
        PurchaseCalculationStep: {
            /**
             * Amount Basis
             * @default NET_EXCL_TAX
             * @enum {string}
             */
            amount_basis?: "NET_EXCL_TAX" | "GROSS_INCL_TAX";
            /**
             * Basis Recipe
             * @default AFTER_DISCOUNTS
             * @enum {string}
             */
            basis_recipe?: "ORIGINAL" | "AFTER_DISCOUNTS" | "AFTER_STEPS";
            /**
             * Dependencies
             * @default []
             */
            dependencies?: string[];
            /**
             * Input Kind
             * @default PERCENT
             * @enum {string}
             */
            input_kind?: "FIXED" | "PERCENT";
            /** Key */
            key: string;
            /** Name */
            name: string;
            /**
             * Purpose
             * @enum {string}
             */
            purpose: "DISCOUNT" | "FREIGHT" | "PACKING" | "INSURANCE" | "HANDLING" | "OTHER_CHARGE";
            /**
             * Scope
             * @default INVOICE
             * @enum {string}
             */
            scope?: "INVOICE" | "SELECTED_LINES";
            /**
             * Tax Treatment
             * @default ASSESSABLE
             * @enum {string}
             */
            tax_treatment?: "ASSESSABLE" | "NO_CHANGE";
            /**
             * Value
             * @default 0
             */
            value?: string;
        };
        /** QuantityCapture */
        "QuantityCapture-Input": {
            /** Entered Quantity */
            entered_quantity: string;
            /**
             * Entered Unit Id
             * Format: uuid
             */
            entered_unit_id: string;
            /** Measured Base Quantity */
            measured_base_quantity?: string | null;
            /**
             * Unit Revision Id
             * Format: uuid
             */
            unit_revision_id: string;
        };
        /** QuantityCapture */
        "QuantityCapture-Output": {
            /** Entered Quantity */
            entered_quantity: string;
            /**
             * Entered Unit Id
             * Format: uuid
             */
            entered_unit_id: string;
            /** Measured Base Quantity */
            measured_base_quantity?: string | null;
            /**
             * Unit Revision Id
             * Format: uuid
             */
            unit_revision_id: string;
        };
        /** ReferenceInput */
        ReferenceInput: {
            /**
             * Purpose
             * @enum {string}
             */
            purpose: "SUPPLIER_INVOICE" | "CUSTOMER_ORDER" | "EXTERNAL" | "CHALLAN";
            /** Reference */
            reference: string;
            /** Reference Date */
            reference_date?: string | null;
        };
        /** ReportTicket */
        ReportTicket: {
            /** Download Path */
            download_path: string;
            /** Expires In */
            expires_in: number;
        };
        /** ResourceDetail */
        ResourceDetail: {
            /** Amount */
            amount?: string | null;
            /** Code */
            code?: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Currency */
            currency?: string | null;
            /** Current Revision */
            current_revision?: number | null;
            /** Derived From Revision Id */
            derived_from_revision_id?: string | null;
            /** Document Date */
            document_date?: string | null;
            /** Family */
            family?: string | null;
            /** Fields */
            fields?: string[] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Issue Number */
            issue_number?: string | null;
            /** Kind */
            kind?: string | null;
            /** Name */
            name?: string | null;
            /** Outlet Id */
            outlet_id?: string | null;
            /** Padding */
            padding?: number | null;
            /** Party Account Id */
            party_account_id?: string | null;
            /** Policy */
            policy?: {
                [key: string]: unknown;
            } | null;
            /** Prefix */
            prefix?: string | null;
            /** Profile */
            profile?: string | null;
            /** Ref Number */
            ref_number?: string | null;
            /** Revision Id */
            revision_id?: string | null;
            /** Revision Number */
            revision_number?: number | null;
            /** Row Version */
            row_version: number;
            /** Status */
            status?: string | null;
            /** Title */
            title?: string | null;
            /** Type Code */
            type_code?: string | null;
            /** Type Id */
            type_id?: string | null;
            /** Type Revision Id */
            type_revision_id?: string | null;
        };
        /** ResourceItem */
        ResourceItem: {
            /** Amount */
            amount?: string | null;
            /** Code */
            code?: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Currency */
            currency?: string | null;
            /** Current Revision */
            current_revision?: number | null;
            /** Document Date */
            document_date?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Issue Number */
            issue_number?: string | null;
            /** Kind */
            kind?: string | null;
            /** Name */
            name?: string | null;
            /** Outlet Id */
            outlet_id?: string | null;
            /** Party Account Id */
            party_account_id?: string | null;
            /** Profile */
            profile?: string | null;
            /** Ref Number */
            ref_number?: string | null;
            /** Revision Number */
            revision_number?: number | null;
            /** Row Version */
            row_version: number;
            /** Status */
            status?: string | null;
            /** Type Code */
            type_code?: string | null;
            /** Type Id */
            type_id?: string | null;
        };
        /** ResourcePage */
        ResourcePage: {
            /** Items */
            items: components["schemas"]["ResourceItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** ReverseRequest */
        ReverseRequest: {
            /** Expected Version */
            expected_version: number;
            /**
             * Posting Date
             * Format: date
             */
            posting_date: string;
            /** Reason */
            reason: string;
        };
        /** RevisionItem */
        RevisionItem: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Revision */
            revision: number;
            /**
             * Source Format
             * @enum {string}
             */
            source_format: "CSV" | "TSV" | "XLSX" | "JSON";
            /** Source Sha256 */
            source_sha256: string;
        };
        /**
         * SalesWorkflowConfiguration
         * @description Sales invoice terms and customer-order evidence, without posting effects.
         */
        SalesWorkflowConfiguration: {
            /**
             * Customer Order Reference Required
             * @default false
             */
            customer_order_reference_required?: boolean;
            /** Max Due Days */
            max_due_days?: number | null;
        };
        /** SequenceRules */
        SequenceRules: {
            /**
             * Padding
             * @default 1
             */
            padding?: number;
            /**
             * Prefix
             * @default
             */
            prefix?: string;
            /**
             * Reset
             * @default never
             * @enum {string}
             */
            reset?: "never" | "calendar_year" | "month" | "fiscal_year";
            /**
             * Start
             * @default 1
             */
            start?: number;
        };
        /** SeriesCreate */
        SeriesCreate: {
            /** Code */
            code: string;
            /**
             * Include Year
             * @default true
             */
            include_year?: boolean;
            /**
             * Numbering Mode
             * @default AUTOMATIC
             * @enum {string}
             */
            numbering_mode?: "AUTOMATIC" | "AUTOMATIC_WITH_OVERRIDE" | "MANUAL";
            /**
             * Padding
             * @default 6
             */
            padding?: number;
            /**
             * Prefix
             * @default
             */
            prefix?: string;
            /**
             * Reset Policy
             * @default FINANCIAL_YEAR
             * @enum {string}
             */
            reset_policy?: "FINANCIAL_YEAR" | "NEVER";
            /**
             * Start Value
             * @default 1
             */
            start_value?: number;
            /**
             * Suffix
             * @default
             */
            suffix?: string;
        };
        /** SessionClose */
        SessionClose: {
            /** Counted Cash */
            counted_cash: string;
            /** Expected Version */
            expected_version: number;
            /** Reason */
            reason?: string | null;
        };
        /** SessionOpen */
        SessionOpen: {
            /**
             * Counter Id
             * Format: uuid
             */
            counter_id: string;
            /** Currency */
            currency: string;
            /** Opening Cash */
            opening_cash: string;
        };
        /** ShareRequest */
        ShareRequest: {
            /**
             * Channel
             * @enum {string}
             */
            channel: "email" | "sms" | "whatsapp";
            /** Expected Version */
            expected_version: number;
            /**
             * Party Id
             * Format: uuid
             */
            party_id: string;
        };
        /** ShareResult */
        ShareResult: {
            /**
             * Message Id
             * Format: uuid
             */
            message_id: string;
            /**
             * Status
             * @default queued
             * @constant
             */
            status?: "queued";
            /**
             * Voucher Id
             * Format: uuid
             */
            voucher_id: string;
        };
        /** SourceBundle */
        SourceBundle: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Definitions
             * @default []
             */
            definitions?: components["schemas"]["DefinitionFact"][];
            /**
             * Masters
             * @default []
             */
            masters?: components["schemas"]["MasterFact"][];
            /**
             * Message Id
             * Format: uuid
             */
            message_id: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
        };
        /** StockInput */
        "StockInput-Input": {
            /**
             * Action
             * @enum {string}
             */
            action: "OPENING" | "RECEIPT" | "DISPATCH" | "TRANSFER" | "TRANSFER_DISPATCH" | "TRANSFER_RECEIPT" | "CUSTOMER_RETURN" | "SUPPLIER_RETURN" | "COUNT" | "PURCHASE_INVOICE";
            /** Currency */
            currency: string;
            /** Lines */
            lines: components["schemas"]["StockLine-Input"][];
            /** Opening Control Id */
            opening_control_id?: string | null;
            /** Opening Mode */
            opening_mode?: ("COMBINED" | "LINKED_GL") | null;
            /** Reason */
            reason: string;
            /**
             * Stock Date
             * Format: date
             */
            stock_date: string;
            /**
             * Version
             * @default 1
             * @constant
             */
            version?: 1;
        };
        /** StockInput */
        "StockInput-Output": {
            /**
             * Action
             * @enum {string}
             */
            action: "OPENING" | "RECEIPT" | "DISPATCH" | "TRANSFER" | "TRANSFER_DISPATCH" | "TRANSFER_RECEIPT" | "CUSTOMER_RETURN" | "SUPPLIER_RETURN" | "COUNT" | "PURCHASE_INVOICE";
            /** Currency */
            currency: string;
            /** Lines */
            lines: components["schemas"]["StockLine-Output"][];
            /** Opening Control Id */
            opening_control_id?: string | null;
            /** Opening Mode */
            opening_mode?: ("COMBINED" | "LINKED_GL") | null;
            /** Reason */
            reason: string;
            /**
             * Stock Date
             * Format: date
             */
            stock_date: string;
            /**
             * Version
             * @default 1
             * @constant
             */
            version?: 1;
        };
        /** StockLine */
        "StockLine-Input": {
            /** Bin Id */
            bin_id?: string | null;
            count?: components["schemas"]["CountCapture"] | null;
            /** Destination Bin Id */
            destination_bin_id?: string | null;
            /** Destination Warehouse Id */
            destination_warehouse_id?: string | null;
            /**
             * Item Id
             * Format: uuid
             */
            item_id: string;
            /**
             * Line Id
             * Format: uuid
             */
            line_id: string;
            /** Lot Id */
            lot_id?: string | null;
            opening?: components["schemas"]["OpeningCapture-Input"] | null;
            /** Opening Journal Line Id */
            opening_journal_line_id?: string | null;
            /** Quantity */
            quantity: string;
            quantity_entry?: components["schemas"]["QuantityCapture-Input"] | null;
            /** Received Value */
            received_value?: string | null;
            /** Source Movement Id */
            source_movement_id?: string | null;
            /**
             * Unit Ids
             * @default []
             */
            unit_ids?: string[];
            /**
             * Warehouse Id
             * Format: uuid
             */
            warehouse_id: string;
            /** Zero Value Reason */
            zero_value_reason?: string | null;
        };
        /** StockLine */
        "StockLine-Output": {
            /** Bin Id */
            bin_id?: string | null;
            count?: components["schemas"]["CountCapture"] | null;
            /** Destination Bin Id */
            destination_bin_id?: string | null;
            /** Destination Warehouse Id */
            destination_warehouse_id?: string | null;
            /**
             * Item Id
             * Format: uuid
             */
            item_id: string;
            /**
             * Line Id
             * Format: uuid
             */
            line_id: string;
            /** Lot Id */
            lot_id?: string | null;
            opening?: components["schemas"]["OpeningCapture-Output"] | null;
            /** Opening Journal Line Id */
            opening_journal_line_id?: string | null;
            /** Quantity */
            quantity: string;
            quantity_entry?: components["schemas"]["QuantityCapture-Output"] | null;
            /** Received Value */
            received_value?: string | null;
            /** Source Movement Id */
            source_movement_id?: string | null;
            /**
             * Unit Ids
             * @default []
             */
            unit_ids?: string[];
            /**
             * Warehouse Id
             * Format: uuid
             */
            warehouse_id: string;
            /** Zero Value Reason */
            zero_value_reason?: string | null;
        };
        /** StockPolicy */
        StockPolicy: {
            /**
             * Allow Zero Value Receipts
             * @default false
             */
            allow_zero_value_receipts?: boolean;
            /**
             * Opening Gl Mode
             * @default EITHER
             * @enum {string}
             */
            opening_gl_mode?: "COMBINED" | "LINKED_GL" | "EITHER";
        };
        /** SupplyCalculation */
        SupplyCalculation: {
            /** Commercial */
            commercial: string;
            /** Entered */
            entered: string;
            /**
             * Key
             * Format: uuid
             */
            key: string;
            /** Payable */
            payable: string;
            /** Price Rounding */
            price_rounding: string;
            /** Stock Cost */
            stock_cost?: string | null;
            /** Taxable */
            taxable: string;
            /** Taxes */
            taxes: components["schemas"]["TaxCalculation"][];
        };
        /** SupportingFileDetail */
        SupportingFileDetail: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Content Hash */
            content_hash: string;
            /** Download Token */
            download_token?: string | null;
            /** Filename */
            filename: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Media Type
             * @enum {string}
             */
            media_type: "application/pdf" | "image/png" | "image/jpeg" | "text/plain";
            /** Object Key */
            object_key: string;
            /** Size Bytes */
            size_bytes: number;
            /**
             * Voucher Id
             * Format: uuid
             */
            voucher_id: string;
        };
        /** SupportingFileUpload */
        SupportingFileUpload: {
            /** Content Base64 */
            content_base64: string;
            /** Expected Version */
            expected_version: number;
            /** Filename */
            filename: string;
            /**
             * Media Type
             * @enum {string}
             */
            media_type: "application/pdf" | "image/png" | "image/jpeg" | "text/plain";
            /**
             * Reason
             * @default
             */
            reason?: string;
        };
        /** TaxCalculation */
        TaxCalculation: {
            /** Amount */
            amount: string;
            /** Basis */
            basis: string;
            /**
             * Code
             * @enum {string}
             */
            code: "CGST" | "SGST" | "UTGST" | "IGST" | "CESS";
            /** Key */
            key: string;
            /** Supplier Charged */
            supplier_charged: boolean;
        };
        /** TemplateCreate */
        TemplateCreate: {
            /** Code */
            code: string;
            /**
             * Fields
             * @default [
             *       "document_date",
             *       "currency",
             *       "narration",
             *       "lines"
             *     ]
             */
            fields?: ("document_date" | "currency" | "narration" | "lines" | "parties" | "references" | "custom_fields" | "fulfillment_terms")[];
            /** Title */
            title: string;
        };
        /** TemplateSnapshotDetail */
        TemplateSnapshotDetail: {
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Fingerprint */
            fingerprint: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Snapshot */
            snapshot: {
                [key: string]: unknown;
            };
        };
        /** TemplateSnapshotInput */
        TemplateSnapshotInput: {
            /** Class Id */
            class_id?: string | null;
            /**
             * Document Date
             * Format: date
             */
            document_date: string;
            /**
             * Posting Date
             * Format: date
             */
            posting_date: string;
            /**
             * Voucher Type Id
             * Format: uuid
             */
            voucher_type_id: string;
        };
        /** Tender */
        "Tender-Input": {
            /** Amount */
            amount: string;
            /** Currency */
            currency: string;
            /** Instrument Date */
            instrument_date?: string | null;
            /**
             * Line Key
             * Format: uuid
             */
            line_key: string;
            /**
             * Mode
             * @enum {string}
             */
            mode: "CASH" | "CHEQUE" | "NEFT" | "RTGS" | "IMPS" | "UPI" | "CARD" | "BANK_TRANSFER";
            /**
             * Recognition
             * @default BOOK_DATE
             * @enum {string}
             */
            recognition?: "BOOK_DATE" | "MATURITY_DATE";
            /** Reference */
            reference?: string | null;
            /**
             * Tender Key
             * Format: uuid
             */
            tender_key: string;
        };
        /** Tender */
        "Tender-Output": {
            /** Amount */
            amount: string;
            /** Currency */
            currency: string;
            /** Instrument Date */
            instrument_date?: string | null;
            /**
             * Line Key
             * Format: uuid
             */
            line_key: string;
            /**
             * Mode
             * @enum {string}
             */
            mode: "CASH" | "CHEQUE" | "NEFT" | "RTGS" | "IMPS" | "UPI" | "CARD" | "BANK_TRANSFER";
            /**
             * Recognition
             * @default BOOK_DATE
             * @enum {string}
             */
            recognition?: "BOOK_DATE" | "MATURITY_DATE";
            /** Reference */
            reference?: string | null;
            /**
             * Tender Key
             * Format: uuid
             */
            tender_key: string;
        };
        /** TypeCreate */
        TypeCreate: {
            /** Code */
            code: string;
            /** Derived From Revision Id */
            derived_from_revision_id?: string | null;
            /** Kind */
            kind: string;
            /** Name */
            name: string;
            policy?: components["schemas"]["Policy"];
            /**
             * Profile
             * @default STANDARD
             */
            profile?: string;
        };
        /** TypeRevise */
        TypeRevise: {
            /** Expected Version */
            expected_version: number;
            policy: components["schemas"]["Policy"];
            /**
             * Reason
             * @default
             */
            reason?: string;
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
        /** ValidationRules */
        ValidationRules: {
            /**
             * Case Sensitive
             * @default true
             */
            case_sensitive?: boolean;
            /**
             * Decimal Places
             * @default 4
             */
            decimal_places?: number;
            /** Max */
            max?: number | string | null;
            /**
             * Max Length
             * @default 4096
             */
            max_length?: number;
            /** Min */
            min?: number | string | null;
            /**
             * Min Length
             * @default 0
             */
            min_length?: number;
            /** Regex */
            regex?: string | null;
            /** Regex Message */
            regex_message?: string | null;
            /**
             * Required
             * @default false
             */
            required?: boolean;
            /**
             * Unique Within
             * @default none
             * @enum {string}
             */
            unique_within?: "none" | "company" | "tenant";
        };
        /** Version */
        Version: {
            /** Expected Version */
            expected_version: number;
            /**
             * Reason
             * @default
             */
            reason?: string;
        };
        /**
         * VoucherActionRequest
         * @description The body of submit, approve, reject, cancel, accept, decline and expire.
         */
        VoucherActionRequest: {
            /**
             * Acknowledge Duplicate Bill
             * @default false
             */
            acknowledge_duplicate_bill?: boolean;
            /** Expected Version */
            expected_version: number;
            /**
             * Reason
             * @default
             */
            reason?: string;
        };
        /** VoucherDetail */
        VoucherDetail: {
            /** Assignments */
            assignments?: components["schemas"]["AssignmentDetail"][] | null;
            /** Attachments */
            attachments?: {
                [key: string]: unknown;
            }[] | null;
            /** Cashier Id */
            cashier_id?: string | null;
            /** Class Id */
            class_id?: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Configuration Hash */
            configuration_hash?: string | null;
            /** Content Hash */
            content_hash?: string | null;
            counter?: components["schemas"]["CounterInput"] | null;
            /** Credit Terms Date */
            credit_terms_date?: string | null;
            /** Currency */
            currency?: string | null;
            /** Custom Fields */
            custom_fields?: {
                [key: string]: unknown;
            } | null;
            /** Document Date */
            document_date?: string | null;
            financial?: components["schemas"]["MoneyInput-Output"] | null;
            /** Fiscal Start Date */
            fiscal_start_date?: string | null;
            fulfillment_terms?: components["schemas"]["FulfillmentTermsInput"] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            invoice?: components["schemas"]["InvoiceInput-Output"] | null;
            /** Issue Number */
            issue_number?: string | null;
            /** Kind */
            kind?: string | null;
            /** Lines */
            lines?: {
                [key: string]: unknown;
            }[] | null;
            /** Links */
            links?: {
                [key: string]: unknown;
            }[] | null;
            /** Mode */
            mode?: string | null;
            /** Narration */
            narration?: string | null;
            /** Parties */
            parties?: {
                [key: string]: unknown;
            }[] | null;
            /** Posting Date */
            posting_date?: string | null;
            /** Profile */
            profile?: string | null;
            /** References */
            references?: {
                [key: string]: unknown;
            }[] | null;
            /**
             * Revision Id
             * Format: uuid
             */
            revision_id: string;
            /** Revision Number */
            revision_number: number;
            /** Row Version */
            row_version: number;
            /** Status */
            status: string;
            /** Statutory Date */
            statutory_date?: string | null;
            stock?: components["schemas"]["StockInput-Output"] | null;
            /** Stock Date */
            stock_date?: string | null;
            /**
             * Type Revision Id
             * Format: uuid
             */
            type_revision_id: string;
        };
        /** VoucherEdit */
        VoucherEdit: {
            content: components["schemas"]["VoucherInput"];
            /** Expected Version */
            expected_version: number;
            /**
             * Reason
             * @default
             */
            reason?: string;
        };
        /** VoucherInput */
        VoucherInput: {
            /**
             * Assignments
             * @default []
             */
            assignments?: components["schemas"]["AssignmentInput"][];
            /**
             * Attachments
             * @default []
             */
            attachments?: components["schemas"]["AttachmentInput"][];
            /** Class Id */
            class_id?: string | null;
            counter?: components["schemas"]["CounterInput"] | null;
            /** Credit Terms Date */
            credit_terms_date?: string | null;
            /** Currency */
            currency: string;
            /** Custom Fields */
            custom_fields?: {
                [key: string]: unknown;
            };
            /**
             * Document Date
             * Format: date
             */
            document_date: string;
            financial?: components["schemas"]["MoneyInput-Input"] | null;
            fulfillment_terms?: components["schemas"]["FulfillmentTermsInput"] | null;
            invoice?: components["schemas"]["InvoiceInput-Input"] | null;
            /**
             * Lines
             * @default []
             */
            lines?: components["schemas"]["LineInput"][];
            /**
             * Links
             * @default []
             */
            links?: components["schemas"]["LinkInput"][];
            /**
             * Mode
             * @default ACCOUNTS
             * @enum {string}
             */
            mode?: "ACCOUNTS" | "ITEMS" | "MIXED";
            /**
             * Narration
             * @default
             */
            narration?: string;
            /**
             * Parties
             * @default []
             */
            parties?: components["schemas"]["PartyInput"][];
            /** Posting Date */
            posting_date?: string | null;
            /**
             * References
             * @default []
             */
            references?: components["schemas"]["ReferenceInput"][];
            /** Statutory Date */
            statutory_date?: string | null;
            stock?: components["schemas"]["StockInput-Input"] | null;
            /** Stock Date */
            stock_date?: string | null;
            /**
             * Type Revision Id
             * Format: uuid
             */
            type_revision_id: string;
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
    apply_sources_internal_v1_sources_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SourceBundle"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
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
    create_counter_v1_companies__company_id__checkout_counters_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CounterCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CounterMasterDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    counter_detail_v1_companies__company_id__checkout_counters__counter_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                counter_id: string;
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
                    "application/json": components["schemas"]["CounterMasterDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    assign_operator_v1_companies__company_id__checkout_counters__counter_id__operators_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                counter_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OperatorCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CounterOperatorDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    set_operator_status_v1_companies__company_id__checkout_counters__counter_id__operators__user_id__status_put: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                counter_id: string;
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OperatorStatusUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CounterOperatorDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    set_counter_status_v1_companies__company_id__checkout_counters__counter_id__status_put: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                counter_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MasterStatusUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CounterMasterDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_outlet_v1_companies__company_id__counter_outlets_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OutletCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CounterMasterDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    outlet_detail_v1_companies__company_id__counter_outlets__outlet_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                outlet_id: string;
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
                    "application/json": components["schemas"]["CounterMasterDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    set_outlet_status_v1_companies__company_id__counter_outlets__outlet_id__status_put: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                outlet_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MasterStatusUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CounterMasterDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    open_session_v1_companies__company_id__counter_sessions_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SessionOpen"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CounterSessionDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    session_detail_v1_companies__company_id__counter_sessions__session_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                session_id: string;
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
                    "application/json": components["schemas"]["CounterSessionDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    record_cash_movement_v1_companies__company_id__counter_sessions__session_id__cash_events_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CashMovement"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CounterSessionDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    close_session_v1_companies__company_id__counter_sessions__session_id__close_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                session_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SessionClose"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CounterSessionDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    activity_v1_companies__company_id__day_book_query_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DayBookQuery"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DayBookPage"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    type_revisions_v1_companies__company_id__day_book_types__type_id__revisions_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                type_id: string;
                company_id: string;
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
                    "application/json": components["schemas"]["DayBookTypeRevisions"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    print_capabilities_v1_companies__company_id__print_capabilities_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    listing_v1_companies__company_id__stock_opening_imports_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                q?: string | null;
                sort?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
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
                    "application/json": components["schemas"]["Page_ImportListItem_"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    stage_v1_companies__company_id__stock_opening_imports_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpeningImportStage"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpeningImportDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    template_v1_companies__company_id__stock_opening_imports_template_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    detail_v1_companies__company_id__stock_opening_imports__job_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
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
                    "application/json": components["schemas"]["OpeningImportDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    cancel_v1_companies__company_id__stock_opening_imports__job_id__cancel_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpeningImportVersion"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpeningImportDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    commit_v1_companies__company_id__stock_opening_imports__job_id__commit_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpeningImportCommit"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpeningImportDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    report_v1_companies__company_id__stock_opening_imports__job_id__report_get: {
        parameters: {
            query: {
                token: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
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
                content?: never;
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    ticket_v1_companies__company_id__stock_opening_imports__job_id__report_ticket_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    validate_v1_companies__company_id__stock_opening_imports__job_id__validate_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpeningImportVersion"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpeningImportDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    artifact_status_v1_companies__company_id__voucher_artifacts__artifact_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                artifact_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    download_v1_companies__company_id__voucher_artifacts__artifact_id__download_get: {
        parameters: {
            query: {
                token: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                artifact_id: string;
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
                    "application/json": unknown;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    capabilities_v1_companies__company_id__voucher_capabilities_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    company_bind_v1_companies__company_id__voucher_configuration_bindings_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BindingCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    close_binding_v1_companies__company_id__voucher_configuration_bindings__object_id__close_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CloseBinding"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_configuration_v1_companies__company_id__voucher_configurations_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConfigurationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResourceDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    publish_configuration_v1_companies__company_id__voucher_configurations__object_id__publish_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Version"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResourceDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    revise_configuration_v1_companies__company_id__voucher_configurations__object_id__revisions_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TypeRevise"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResourceDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    export_v1_companies__company_id__voucher_export_get: {
        parameters: {
            query?: {
                q?: string | null;
                sort?: "id" | "-id" | "document_date" | "-document_date";
                limit?: number;
                cursor?: string | null;
                status?: string | null;
                code?: string | null;
                type_id?: string | null;
                party_id?: string | null;
                item_id?: string | null;
                kind?: string | null;
                document_from?: string | null;
                document_to?: string | null;
                issue_number?: string | null;
                custom_entity?: "vouchers.voucher" | "vouchers.voucher_item";
                type_revision_id?: string | null;
                parent_id?: string | null;
                outlet_id?: string | null;
                assignment_role?: ("SELLER" | "BROKER" | "COLLECTOR" | "RETURN_HANDLER" | "PAYMENT_HANDLER") | null;
                assignment_principal_id?: string | null;
                counter_id?: string | null;
                custom_key?: string | null;
                custom_value?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    adoptions_v1_companies__company_id__voucher_field_adoptions_get: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    adoption_detail_v1_companies__company_id__voucher_field_adoptions__object_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    apply_adoption_v1_companies__company_id__voucher_field_adoptions__object_id__apply_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Version"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    preview_adoption_v1_companies__company_id__voucher_field_adoptions__object_id__preview_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Version"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_voucher_import_template_snapshot: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TemplateSnapshotInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TemplateSnapshotDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_voucher_import_template_snapshot: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                template_id: string;
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
                    "application/json": components["schemas"]["TemplateSnapshotDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    download_voucher_import_template: {
        parameters: {
            query: {
                voucher_type_id: string;
                format?: "CSV" | "TSV" | "XLSX" | "JSON";
                document_date?: string | null;
                posting_date?: string | null;
                class_id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
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
                    "application/json": unknown;
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": string;
                    "text/csv": string;
                    "text/tab-separated-values": string;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_voucher_imports: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                state?: ("STAGED" | "VALIDATING" | "READY" | "COMMITTING" | "SUCCEEDED" | "PARTIAL" | "FAILED" | "CANCELLED" | "EXPIRED") | null;
                mine?: boolean;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
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
                    "application/json": components["schemas"]["ImportJobPage"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    stage_voucher_import: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportStage"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportJobDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_voucher_import: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
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
                    "application/json": components["schemas"]["ImportJobDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_voucher_import_attempt_results: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
                attempt_id: string;
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
                    "application/json": components["schemas"]["AttemptResultPage"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    cancel_voucher_import: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportVersion"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportJobDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    commit_voucher_import: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportCommit"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportJobDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    download_voucher_import_data: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportDownloadRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": string;
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": string;
                    "text/csv": string;
                    "text/tab-separated-values": string;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_voucher_import_download_ticket: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportDownload"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DownloadTicket"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_voucher_import_history: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
                kind: "attempts" | "revisions";
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
                    "application/json": components["schemas"]["HistoryPage"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    download_voucher_import_report: {
        parameters: {
            query: {
                format?: "CSV" | "TSV" | "XLSX";
                token: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
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
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": string;
                    "text/csv": string;
                    "text/tab-separated-values": string;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_voucher_import_report_ticket: {
        parameters: {
            query?: {
                format?: "CSV" | "TSV" | "XLSX";
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
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
                    "application/json": components["schemas"]["ReportTicket"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    retry_voucher_import: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportVersion"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportJobDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    revise_voucher_import: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportRevisionInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportJobDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    run_voucher_import: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
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
                    "application/json": components["schemas"]["ImportJobDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    validate_voucher_import: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ImportVersion"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportJobDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_voucher_import_vouchers: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                state?: ("STAGED" | "VALID" | "WARNING" | "INVALID" | "BLOCKED" | "CREATED" | "FAILED" | "NOT_SELECTED") | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
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
                    "application/json": components["schemas"]["ImportVoucherPage"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    get_voucher_import_voucher: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
                import_key: string;
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
                    "application/json": components["schemas"]["ImportVoucherDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    kinds_v1_companies__company_id__voucher_kinds_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    operation_detail_v1_companies__company_id__voucher_operations__operation_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                operation_id: string;
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
                    "application/json": components["schemas"]["OperationDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    cancel_execution_v1_companies__company_id__voucher_operations__operation_id__cancel_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                operation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Version"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    recover_operation_v1_companies__company_id__voucher_operations__operation_id__recover_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                operation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Version"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    print_status_v1_companies__company_id__voucher_print_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
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
                    "application/json": components["schemas"]["PrintJobDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    print_download_v1_companies__company_id__voucher_print_jobs__job_id__download_get: {
        parameters: {
            query: {
                token: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                job_id: string;
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
                    "application/pdf": unknown;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_series_v1_companies__company_id__voucher_series_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SeriesCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResourceDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_template_v1_companies__company_id__voucher_templates_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TemplateCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResourceDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    bootstrap_v1_companies__company_id__voucher_type_defaults_bootstrap_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DefaultsCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DefaultsResult"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_type_v1_companies__company_id__voucher_types_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TypeCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResourceDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_class_v1_companies__company_id__voucher_types__object_id__classes_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ClassCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResourceDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    type_bind_v1_companies__company_id__voucher_types__object_id__configuration_bindings_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BindingCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    effective_configuration_v1_companies__company_id__voucher_types__object_id__effective_configuration_get: {
        parameters: {
            query: {
                date: string;
                class_id?: string | null;
                posting_date?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    field_set_v1_companies__company_id__voucher_types__object_id__field_set_get: {
        parameters: {
            query: {
                date: string;
                class_id?: string | null;
                posting_date?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    revise_type_v1_companies__company_id__voucher_types__object_id__revisions_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TypeRevise"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResourceDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_voucher_v1_companies__company_id__vouchers_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VoucherInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VoucherDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    duplicate_bills_v1_companies__company_id__vouchers_duplicate_bills_get: {
        parameters: {
            query: {
                party_id?: string | null;
                party_account_id?: string | null;
                bill_reference: string;
                document_date: string;
                exclude_voucher_id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
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
                    "application/json": components["schemas"]["DuplicateBillList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    voucher_detail_v1_companies__company_id__vouchers__object_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
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
                    "application/json": components["schemas"]["VoucherDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    edit_voucher_v1_companies__company_id__vouchers__object_id__put: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VoucherEdit"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VoucherDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    voucher_field_set_v1_companies__company_id__vouchers__object_id__field_set_get: {
        parameters: {
            query?: {
                revision_id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    accept_invoice_v1_companies__company_id__vouchers__object_id__invoice_acceptance_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InvoiceAcceptance"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VoucherDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    preview_invoice_v1_companies__company_id__vouchers__object_id__invoice_preview_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Version"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InvoiceCalculationDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    issue_voucher_v1_companies__company_id__vouchers__object_id__issue_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IssueRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VoucherDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    post_voucher_v1_companies__company_id__vouchers__object_id__post_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Version"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostingOperation"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    reverse_voucher_v1_companies__company_id__vouchers__object_id__reverse_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReverseRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostingOperation"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    voucher_revision_v1_companies__company_id__vouchers__object_id__revisions__revision_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
                revision_id: string;
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
                    "application/json": components["schemas"]["VoucherDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    share_voucher_v1_companies__company_id__vouchers__object_id__share_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ShareRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ShareResult"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    voucher_action_v1_companies__company_id__vouchers__object_id___action__post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
                action: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VoucherActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VoucherDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_artifact_v1_companies__company_id__vouchers__voucher_id__artifacts_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                voucher_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ArtifactCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    history_v1_companies__company_id__vouchers__voucher_id__history_get: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                voucher_id: string;
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
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_print_job_v1_companies__company_id__vouchers__voucher_id__print_jobs_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                voucher_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PrintCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrintJobDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    listing_v1_companies__company_id__vouchers__voucher_id__supporting_files_get: {
        parameters: {
            query?: {
                revision_id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                voucher_id: string;
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
                    "application/json": components["schemas"]["SupportingFileDetail"][];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    upload_v1_companies__company_id__vouchers__voucher_id__supporting_files_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                voucher_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SupportingFileUpload"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupportingFileDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    download_v1_companies__company_id__vouchers__voucher_id__supporting_files__file_id__download_get: {
        parameters: {
            query: {
                token: string;
                revision_id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                voucher_id: string;
                file_id: string;
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
                content?: never;
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    list_resource_v1_companies__company_id___resource__get: {
        parameters: {
            query?: {
                q?: string | null;
                sort?: "id" | "-id" | "document_date" | "-document_date";
                limit?: number;
                cursor?: string | null;
                status?: string | null;
                code?: string | null;
                type_id?: string | null;
                party_id?: string | null;
                item_id?: string | null;
                kind?: string | null;
                document_from?: string | null;
                document_to?: string | null;
                issue_number?: string | null;
                custom_entity?: "vouchers.voucher" | "vouchers.voucher_item";
                type_revision_id?: string | null;
                parent_id?: string | null;
                outlet_id?: string | null;
                assignment_role?: ("SELLER" | "BROKER" | "COLLECTOR" | "RETURN_HANDLER" | "PAYMENT_HANDLER") | null;
                assignment_principal_id?: string | null;
                counter_id?: string | null;
                custom_key?: string | null;
                custom_value?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                resource: string;
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
                    "application/json": components["schemas"]["ResourcePage"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    resource_detail_v1_companies__company_id___resource___object_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                resource: string;
                object_id: string;
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
                    "application/json": components["schemas"]["ResourceDetail"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    retire_v1_companies__company_id___resource___object_id__retire_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                resource: "voucher-types" | "voucher-configurations" | "voucher-series" | "voucher-templates";
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Version"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Too Many Requests */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
}
