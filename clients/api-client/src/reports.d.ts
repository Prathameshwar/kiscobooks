export interface paths {
    "/v1/companies/{company_id}/report-definitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Definitions */
        get: operations["definitions_v1_companies__company_id__report_definitions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/report-definitions/{code}/field-set": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Field Set */
        get: operations["field_set_v1_companies__company_id__report_definitions__code__field_set_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/report-generations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Generations */
        get: operations["generations_v1_companies__company_id__report_generations_get"];
        put?: never;
        /** Create Generation */
        post: operations["create_generation_v1_companies__company_id__report_generations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/report-generations/{identity}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Generation */
        get: operations["generation_v1_companies__company_id__report_generations__identity__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/report-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Report Runs */
        get: operations["report_runs_v1_companies__company_id__report_runs_get"];
        put?: never;
        /** Create Run */
        post: operations["create_run_v1_companies__company_id__report_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/report-runs/{identity}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Run */
        get: operations["run_v1_companies__company_id__report_runs__identity__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/report-runs/{identity}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download */
        get: operations["download_v1_companies__company_id__report_runs__identity__download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/report-runs/{identity}/rows": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rows */
        get: operations["rows_v1_companies__company_id__report_runs__identity__rows_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/gst-return-context": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Context */
        get: operations["context_v2_companies__company_id__gst_return_context_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/gstr1-context": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Context */
        get: operations["context_v2_companies__company_id__gstr1_context_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/overview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Overview */
        get: operations["overview_v2_companies__company_id__overview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-definitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Definitions */
        get: operations["definitions_v2_companies__company_id__report_definitions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-definitions/{code}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Definition */
        get: operations["definition_v2_companies__company_id__report_definitions__code__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-definitions/{code}/field-set": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Field Set */
        get: operations["field_set_v2_companies__company_id__report_definitions__code__field_set_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-definitions/{code}/validate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Validate Parameters */
        post: operations["validate_parameters_v2_companies__company_id__report_definitions__code__validate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-exports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Exports */
        get: operations["exports_v2_companies__company_id__report_exports_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-exports/{identity}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Status */
        get: operations["status_v2_companies__company_id__report_exports__identity__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-exports/{identity}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel */
        post: operations["cancel_v2_companies__company_id__report_exports__identity__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-exports/{identity}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download */
        get: operations["download_v2_companies__company_id__report_exports__identity__download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-exports/{identity}/download-token": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Token */
        get: operations["token_v2_companies__company_id__report_exports__identity__download_token_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-exports/{identity}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry */
        post: operations["retry_v2_companies__company_id__report_exports__identity__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-generations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Generations */
        get: operations["generations_v2_companies__company_id__report_generations_get"];
        put?: never;
        /** Create Generation */
        post: operations["create_generation_v2_companies__company_id__report_generations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-generations/{identity}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Generation */
        get: operations["read_generation_v2_companies__company_id__report_generations__identity__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-generations/{identity}/inventory": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Stock Source */
        get: operations["stock_source_v2_companies__company_id__report_generations__identity__inventory_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Runs */
        get: operations["runs_v2_companies__company_id__report_runs_get"];
        put?: never;
        /** Create Run */
        post: operations["create_run_v2_companies__company_id__report_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{identity}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Run */
        get: operations["run_v2_companies__company_id__report_runs__identity__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{identity}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel */
        post: operations["cancel_v2_companies__company_id__report_runs__identity__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{identity}/drilldowns": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Drilldown */
        post: operations["drilldown_v2_companies__company_id__report_runs__identity__drilldowns_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{identity}/exports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Export */
        post: operations["create_export_v2_companies__company_id__report_runs__identity__exports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{identity}/hierarchy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Hierarchy */
        get: operations["hierarchy_v2_companies__company_id__report_runs__identity__hierarchy_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{identity}/queries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Query Result */
        post: operations["query_result_v2_companies__company_id__report_runs__identity__queries_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{identity}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry */
        post: operations["retry_v2_companies__company_id__report_runs__identity__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{identity}/rows": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rows */
        get: operations["rows_v2_companies__company_id__report_runs__identity__rows_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{identity}/rows/{ordinal}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Row Detail */
        get: operations["row_detail_v2_companies__company_id__report_runs__identity__rows__ordinal__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{job_id}/gst-records": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Records */
        get: operations["records_v2_companies__company_id__report_runs__job_id__gst_records_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{job_id}/gst-review": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** History */
        get: operations["history_v2_companies__company_id__report_runs__job_id__gst_review_get"];
        put?: never;
        /** Review */
        post: operations["review_v2_companies__company_id__report_runs__job_id__gst_review_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{job_id}/gstr1-records": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Records */
        get: operations["records_v2_companies__company_id__report_runs__job_id__gstr1_records_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/report-runs/{job_id}/gstr1-review": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** History */
        get: operations["history_v2_companies__company_id__report_runs__job_id__gstr1_review_get"];
        put?: never;
        /** Review */
        post: operations["review_v2_companies__company_id__report_runs__job_id__gstr1_review_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v2/companies/{company_id}/source-readiness": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Readiness */
        get: operations["readiness_v2_companies__company_id__source_readiness_get"];
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
        /** ArtifactDownload */
        ArtifactDownload: {
            /** Byte Count */
            byte_count: number;
            /** Content Hash */
            content_hash: string;
            /**
             * Expires In
             * @default 120
             */
            expires_in?: number;
            /** Filename */
            filename: string;
            /** Token */
            token: string;
        };
        /** Column */
        Column: {
            /** Currency Key */
            currency_key?: string | null;
            /** Key */
            key: string;
            /**
             * Kind
             * @default TEXT
             * @enum {string}
             */
            kind?: "TEXT" | "IDENTIFIER" | "DATE" | "INTEGER" | "DECIMAL" | "MONEY" | "BOOLEAN";
            /** Metric */
            metric?: string | null;
            /**
             * Nullable
             * @default true
             */
            nullable?: boolean;
            /** Title */
            title: string;
        };
        /**
         * CompanyOverview
         * @description Covered posted activity and as-of positions over one verified owner cut.
         *
         *     ``top_expenses`` lists at most five ledgers with a positive net. ``other_expenses`` is the
         *     net of *every other* expense ledger, so it can be negative when one of them ends with a
         *     credit balance (purchase returns, say). It is never clamped:
         *     ``sum(top_expenses.amount) + other_expenses == totals.expenses`` exactly.
         */
        CompanyOverview: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Coverage Start
             * Format: date
             */
            coverage_start: string;
            /** Currency */
            currency: string;
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
            /** Earlier History Unavailable */
            earlier_history_unavailable: boolean;
            /**
             * Fiscal Year Id
             * Format: uuid
             */
            fiscal_year_id: string;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Other Expenses
             * @description Net of every expense ledger outside top_expenses; may be negative. sum(top_expenses) + other_expenses equals totals.expenses exactly.
             */
            other_expenses: string;
            payables: components["schemas"]["OverviewOpenItems"];
            /** Position */
            position: components["schemas"]["OverviewPosition"][];
            receivables: components["schemas"]["OverviewOpenItems"];
            /** Series */
            series: components["schemas"]["OverviewDay"][];
            /**
             * Snapshot Id
             * Format: uuid
             */
            snapshot_id: string;
            /**
             * Source Created At
             * Format: date-time
             */
            source_created_at: string;
            /** Top Expenses */
            top_expenses: components["schemas"]["OverviewLedger"][];
            totals: components["schemas"]["OverviewTotals"];
            /**
             * Year Start
             * Format: date
             */
            year_start: string;
        };
        /** Coverage */
        Coverage: {
            /**
             * As Of
             * Format: date
             */
            as_of: string;
            /** Captured At */
            captured_at?: string | null;
            /**
             * Classification Date
             * Format: date
             */
            classification_date: string;
            /**
             * Complete Company
             * @constant
             */
            complete_company: true;
            /** Currency */
            currency: string;
            /** Gl Complete */
            gl_complete: boolean;
            /** Group Count */
            group_count: number;
            /**
             * History Start
             * Format: date
             */
            history_start: string;
            /** Item Count */
            item_count: number;
            /**
             * Kind
             * @default COVERAGE
             * @constant
             */
            kind?: "COVERAGE";
            /** Location Count */
            location_count: number;
            /** Movement Count */
            movement_count: number;
            /** Movements Complete */
            movements_complete: boolean;
            /**
             * Native Stock Current
             * @default true
             */
            native_stock_current?: boolean;
            /** Orders Complete */
            orders_complete: boolean;
            /** Origins Complete */
            origins_complete: boolean;
            /** Policy Hash */
            policy_hash: string;
            /** Position Count */
            position_count: number;
            /** Reservations Complete */
            reservations_complete: boolean;
            /**
             * Serial History Complete
             * @default false
             */
            serial_history_complete?: boolean;
            /** Timezone */
            timezone: string;
            /** Valuation Complete */
            valuation_complete: boolean;
        };
        /** Definition */
        Definition: {
            /** Code */
            code: string;
            /**
             * Financial Statement
             * @default false
             */
            financial_statement?: boolean;
            /**
             * Formats
             * @default [
             *       "CSV"
             *     ]
             */
            formats?: "CSV"[];
            /** Rule Hash */
            rule_hash: string;
            /** Version */
            version: number;
        };
        /** DefinitionCatalog */
        DefinitionCatalog: {
            /** Items */
            items: components["schemas"]["DefinitionDetail"][];
        };
        /** DefinitionDetail */
        DefinitionDetail: {
            definition: components["schemas"]["ReportDefinition"];
            /** Execution Limits */
            execution_limits?: {
                [key: string]: number;
            };
            /**
             * Export Limits
             * @default []
             */
            export_limits?: components["schemas"]["ExportDefinition"][];
            /**
             * Formats
             * @default []
             */
            formats?: ("CSV" | "XLSX" | "HTML" | "PDF")[];
            /** Navigation */
            navigation?: {
                [key: string]: unknown;
            };
            /** Package Limits */
            package_limits?: {
                [key: string]: number;
            };
            /** Parameter Schema */
            parameter_schema: {
                [key: string]: unknown;
            };
            /**
             * Run Enabled
             * @default false
             */
            run_enabled?: boolean;
        };
        /** DefinitionFields */
        DefinitionFields: {
            /** Code */
            code: string;
            /** Execution Limits */
            execution_limits?: {
                [key: string]: number;
            };
            /** Export Limits */
            export_limits: components["schemas"]["ExportDefinition"][];
            /** Formats */
            formats: ("CSV" | "XLSX" | "HTML" | "PDF")[];
            /** Native */
            native: {
                [key: string]: unknown;
            };
            /** Navigation */
            navigation?: {
                [key: string]: unknown;
            };
            /** Package Limits */
            package_limits?: {
                [key: string]: number;
            };
            /** Version */
            version: number;
            /** Views */
            views: components["schemas"]["View"][];
        };
        /** DisplayConfiguration */
        DisplayConfiguration: {
            /** Amount Precision */
            amount_precision: number;
            /** Base Currency */
            base_currency: string;
            /** Company Label */
            company_label: string;
            /**
             * Currency Display
             * @enum {string}
             */
            currency_display: "symbol" | "code" | "none";
            /** Currency Symbol Override */
            currency_symbol_override?: string | null;
            /**
             * Currency Symbol Position
             * @enum {string}
             */
            currency_symbol_position: "prefix" | "suffix";
            /** Date Format */
            date_format: string;
            /** Datetime Format */
            datetime_format: string;
            /** Decimal Separator */
            decimal_separator: string;
            /**
             * Digit Grouping
             * @enum {string}
             */
            digit_grouping: "indian" | "western";
            /** Locale */
            locale: string;
            /**
             * Negative Format
             * @enum {string}
             */
            negative_format: "minus" | "parentheses";
            /** Quantity Precision */
            quantity_precision: number;
            rounding_mode: components["schemas"]["RoundingMode"];
            /** Thousands Separator */
            thousands_separator: string;
            /** Timezone */
            timezone: string;
            /**
             * Version
             * @default 1
             * @constant
             */
            version?: 1;
        };
        /** Drilldown */
        Drilldown: {
            /** Key */
            key: string;
            /** Target */
            target: string;
            /** Title */
            title: string;
            /**
             * Version
             * @default 1
             */
            version?: number;
        };
        /** DrilldownLink */
        DrilldownLink: {
            /**
             * Href
             * @default
             */
            href?: string;
            /** Key */
            key: string;
            /**
             * Method
             * @default POST
             * @enum {string}
             */
            method?: "GET" | "POST";
            /** Title */
            title: string;
            /** Token */
            token: string;
        };
        /** DrilldownOrigin */
        DrilldownOrigin: {
            /** Mapping */
            mapping: string;
            /** Ordinal */
            ordinal?: number | null;
            /** Parent Attempt */
            parent_attempt: number;
            /**
             * Parent Id
             * Format: uuid
             */
            parent_id: string;
        };
        /** DrilldownRequest */
        DrilldownRequest: {
            /** Token */
            token: string;
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
        /** ExportDefinition */
        ExportDefinition: {
            /** Exact Value Policy */
            exact_value_policy: string;
            /** Font Version */
            font_version: string;
            /**
             * Format
             * @enum {string}
             */
            format: "CSV" | "XLSX" | "HTML" | "PDF";
            /** Max Bytes */
            max_bytes: number;
            /** Max Cells */
            max_cells: number;
            /** Max Pages */
            max_pages?: number | null;
            /** Max Rows */
            max_rows: number;
            /** Media Type */
            media_type: string;
            /** Renderer Version */
            renderer_version: string;
            /** Template Version */
            template_version: string;
            /** Timeout Seconds */
            timeout_seconds: number;
        };
        /** ExportRequest */
        ExportRequest: {
            /**
             * Delivery
             * @default SINGLE
             * @enum {string}
             */
            delivery?: "SINGLE" | "PACKAGE";
            /**
             * Format
             * @enum {string}
             */
            format: "CSV" | "XLSX" | "HTML" | "PDF";
            /** Part Rows */
            part_rows?: number | null;
            trial_balance?: components["schemas"]["TrialPresentation"] | null;
            /**
             * View
             * @default default
             */
            view?: string;
        };
        /** FrameworkRunRequest */
        FrameworkRunRequest: {
            /** Code */
            code: string;
            /**
             * Execution
             * @default STANDARD
             * @enum {string}
             */
            execution?: "STANDARD" | "BULK";
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /** Parameters */
            parameters?: {
                [key: string]: unknown;
            };
            result_query?: components["schemas"]["ResultQuery"] | null;
            /** Version */
            version?: number | null;
            /**
             * View
             * @default default
             */
            view?: string;
        };
        /** GenerationDetail */
        GenerationDetail: {
            /** Applied Sequence */
            applied_sequence: number;
            /** Failure Code */
            failure_code: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Manifest */
            manifest: {
                [key: string]: unknown;
            } | null;
            /** Status */
            status: string;
            /** Target Sequence */
            target_sequence: number | null;
        };
        /** GenerationRequest */
        GenerationRequest: {
            /**
             * Owner
             * @default accounting
             * @constant
             */
            owner?: "accounting";
        };
        /** GstContext */
        GstContext: {
            /** Calculation Version */
            calculation_version: number;
            /** Can Capture */
            can_capture: boolean;
            /** Can Configure */
            can_configure: boolean;
            /** Can Prepare */
            can_prepare: boolean;
            /** Can Review */
            can_review: boolean;
            /** Registrations */
            registrations: {
                [key: string]: unknown;
            }[];
            /** Rule Version */
            rule_version: string;
        };
        /** GstReviewHistory */
        GstReviewHistory: {
            /** Items */
            items: components["schemas"]["GstReviewItem"][];
        };
        /** GstReviewItem */
        GstReviewItem: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Evidence Hash */
            evidence_hash: string;
            /** Filed Date */
            filed_date?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
            /** Reference */
            reference: string;
            /**
             * State
             * @enum {string}
             */
            state: "REVIEWED" | "EXTERNALLY_FILED";
        };
        /** GstReviewRequest */
        GstReviewRequest: {
            /** Evidence Hash */
            evidence_hash: string;
            /** Filed Date */
            filed_date?: string | null;
            /** Reference */
            reference: string;
            /**
             * State
             * @enum {string}
             */
            state: "REVIEWED" | "EXTERNALLY_FILED";
        };
        /**
         * Gstr1Context
         * @description Outward-return authority with the shared calculation-revision contract.
         */
        Gstr1Context: {
            /** Calculation Version */
            calculation_version: number;
            /** Can Capture */
            can_capture: boolean;
            /** Can Configure */
            can_configure: boolean;
            /** Can Prepare */
            can_prepare: boolean;
            /** Can Review */
            can_review: boolean;
            /** Registrations */
            registrations: {
                [key: string]: unknown;
            }[];
            /** Rule Version */
            rule_version: string;
        };
        /** JobDetail */
        JobDetail: {
            /** Attempt */
            attempt: number;
            /** Code */
            code: string;
            /** Completed Rows */
            completed_rows: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Delivery
             * @default SINGLE
             * @enum {string}
             */
            delivery?: "SINGLE" | "PACKAGE";
            display: components["schemas"]["DisplayConfiguration"] | null;
            /**
             * Execution
             * @default STANDARD
             * @enum {string}
             */
            execution?: "STANDARD" | "BULK";
            /** Failure Code */
            failure_code: string | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "RUN" | "EXPORT";
            origin: components["schemas"]["DrilldownOrigin"] | null;
            /** Parameters */
            parameters: {
                [key: string]: unknown;
            };
            /** Parent Id */
            parent_id: string | null;
            /** Result */
            result: {
                [key: string]: unknown;
            } | null;
            /**
             * Status
             * @enum {string}
             */
            status: "QUEUED" | "RUNNING" | "COMPLETE" | "FAILED" | "BLOCKED" | "CANCELLED";
            /** Title */
            title: string;
            /** Version */
            version: number;
            /**
             * View
             * @default default
             */
            view?: string;
            /** Views */
            views: components["schemas"]["View"][];
        };
        /** JobListItem */
        JobListItem: {
            /** Code */
            code: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Kind */
            kind: string;
            /** Status */
            status: string;
        };
        /** JobPage */
        JobPage: {
            /** Items */
            items: components["schemas"]["JobListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** ListItem */
        ListItem: {
            /** Applied Sequence */
            applied_sequence?: number | null;
            /** Generation Id */
            generation_id?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Status */
            status: string;
        };
        /**
         * OverviewBuckets
         * @description Bills by days past due at the period end; ``unknown`` has no due date.
         */
        OverviewBuckets: {
            /** Current */
            current: string;
            /** Days 1 30 */
            days_1_30: string;
            /** Days 31 60 */
            days_31_60: string;
            /** Days 61 90 */
            days_61_90: string;
            /** Days Over 90 */
            days_over_90: string;
            /** Unknown */
            unknown: string;
        };
        /** OverviewDay */
        OverviewDay: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Expenses */
            expenses: string;
            /** Income */
            income: string;
        };
        /**
         * OverviewLedger
         * @description An expense ledger whose net for the period is a positive amount (a debit balance).
         */
        OverviewLedger: {
            /**
             * Account Id
             * Format: uuid
             */
            account_id: string;
            /** Amount */
            amount: string;
            /** Name */
            name: string;
        };
        /**
         * OverviewOpenItems
         * @description One role's open bills: ``gross`` less ``advances`` is ``net``; ``overdue`` is gross.
         */
        OverviewOpenItems: {
            /** Advances */
            advances: string;
            buckets: components["schemas"]["OverviewBuckets"];
            /** Gross */
            gross: string;
            /** Net */
            net: string;
            /** Overdue */
            overdue: string;
            /** Parties */
            parties: components["schemas"]["OverviewParty"][];
        };
        /**
         * OverviewParty
         * @description One party, however many ledgers it holds: balances are summed across them.
         *
         *     ``name`` is the party's own name (a ledger's name only if the source carries none).
         *     ``outstanding`` is bills less unapplied credit; ``overdue`` is bills past due.
         */
        OverviewParty: {
            /** Name */
            name: string;
            /** Outstanding */
            outstanding: string;
            /** Overdue */
            overdue: string;
            /**
             * Party Id
             * Format: uuid
             */
            party_id: string;
        };
        /**
         * OverviewPosition
         * @description Closing cash plus bank balance at the end of one day.
         */
        OverviewPosition: {
            /** Cash And Bank */
            cash_and_bank: string;
            /**
             * Date
             * Format: date
             */
            date: string;
        };
        /** OverviewTotals */
        OverviewTotals: {
            /** Bank */
            bank: string;
            /** Cash */
            cash: string;
            /** Expenses */
            expenses: string;
            /** Income */
            income: string;
            /** Net Income */
            net_income: string;
            /** Net Payable */
            net_payable: string;
            /** Net Receivable */
            net_receivable: string;
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
        /** ParameterValidation */
        ParameterValidation: {
            /** Parameters */
            parameters?: {
                [key: string]: unknown;
            };
            /** Version */
            version?: number | null;
        };
        /** ReportDefinition */
        ReportDefinition: {
            /** Code */
            code: string;
            /** Datasets */
            datasets: string[];
            /** Description */
            description: string;
            /**
             * Drilldowns
             * @default []
             */
            drilldowns?: components["schemas"]["Drilldown"][];
            /**
             * Financial Statement
             * @default false
             */
            financial_statement?: boolean;
            /** Implementation Hash */
            implementation_hash: string;
            /** Metrics */
            metrics: string[];
            /** Parameter Schema Hash */
            parameter_schema_hash: string;
            /** Permissions */
            permissions: string[];
            /**
             * Resource Class
             * @default SHORT
             * @enum {string}
             */
            resource_class?: "SHORT" | "BULK";
            /** Title */
            title: string;
            /** Version */
            version: number;
            /** Views */
            views: components["schemas"]["View"][];
        };
        /** ResourcePage */
        ResourcePage: {
            /** Items */
            items: components["schemas"]["ListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** ResultPage */
        ResultPage: {
            /** Items */
            items: components["schemas"]["ResultRow"][];
            page: components["schemas"]["PageMeta"];
        };
        /** ResultQuery */
        ResultQuery: {
            /** Filters */
            filters?: {
                [key: string]: string;
            };
            /** Q */
            q?: string | null;
            /**
             * Sort
             * @default ordinal
             */
            sort?: string;
        };
        /** ResultRow */
        ResultRow: {
            /** Data */
            data: {
                [key: string]: unknown;
            };
            /**
             * Drilldowns
             * @default []
             */
            drilldowns?: components["schemas"]["DrilldownLink"][];
            /** Ordinal */
            ordinal: number;
            /** Source Ordinal */
            source_ordinal?: number | null;
        };
        /**
         * RoundingMode
         * @description ``company.rounding_mode`` values, mapped to Python rounding constants.
         * @enum {string}
         */
        RoundingMode: "half_up" | "half_even" | "down";
        /** RowItem */
        RowItem: {
            /** Data */
            data: {
                [key: string]: unknown;
            };
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Ordinal */
            ordinal: number;
        };
        /** RowPage */
        RowPage: {
            /** Items */
            items: components["schemas"]["RowItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** RunDetail */
        RunDetail: {
            /** Download Token */
            download_token?: string | null;
            /** Evidence */
            evidence: {
                [key: string]: unknown;
            } | null;
            /** Failure Code */
            failure_code: string | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Status */
            status: string;
        };
        /** RunRequest */
        RunRequest: {
            /** Account Id */
            account_id?: string | null;
            /**
             * Basis
             * @default BASE
             * @enum {string}
             */
            basis?: "BASE" | "TRANSACTION";
            /**
             * Code
             * @default SOURCE_RECONCILIATION
             * @enum {string}
             */
            code?: "SOURCE_RECONCILIATION" | "ACCOUNT_LEDGER" | "DAY_BOOK" | "TRIAL_BALANCE" | "PROFIT_LOSS" | "INCOME_EXPENSE" | "BALANCE_SHEET" | "BALANCE_CONTINUITY" | "ACCOUNT_SUMMARY" | "PARTY_LEDGER" | "OUTSTANDING_BILLS" | "ADVANCES" | "AGING" | "CASH_BOOK" | "BANK_BOOK" | "BANK_RECONCILIATION" | "BANK_RECONCILIATION_EVIDENCE" | "BANK_RECONCILIATION_WORKLIST" | "PAYMENT_REGISTER" | "RECEIPT_REGISTER" | "SALES_REGISTER" | "PURCHASE_REGISTER" | "INVOICE_COMPONENT_REGISTER" | "INVOICE_TAX_REGISTER" | "INVOICE_CREDIT_REGISTER" | "INVOICE_SETTLEMENT_REGISTER" | "INVOICE_GL_BRIDGE" | "TAX_GL_BRIDGE";
            /** Company Registration Id */
            company_registration_id?: string | null;
            /** Comparative From */
            comparative_from?: string | null;
            /** Comparative To */
            comparative_to?: string | null;
            /** Currency */
            currency?: string | null;
            /**
             * Date Basis
             * @default POSTING
             * @enum {string}
             */
            date_basis?: "POSTING" | "DOCUMENT" | "TAX_POINT";
            /** Date From */
            date_from?: string | null;
            /** Date To */
            date_to?: string | null;
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /**
             * Grain
             * @default DAY
             * @enum {string}
             */
            grain?: "DAY" | "MONTH";
            /** Group Id */
            group_id?: string | null;
            /** Invoice Id */
            invoice_id?: string | null;
            /** Journal Id */
            journal_id?: string | null;
            /** Party Id */
            party_id?: string | null;
            /** Role */
            role?: ("CUSTOMER" | "SUPPLIER") | null;
            /**
             * Search
             * @default
             */
            search?: string;
            /** Session Id */
            session_id?: string | null;
            /**
             * Show Zero
             * @default false
             */
            show_zero?: boolean;
            /** Statement Balance */
            statement_balance?: string | null;
            /** Tax Code */
            tax_code?: string | null;
            /** Tax Ledger Id */
            tax_ledger_id?: string | null;
            /** Tax Purpose */
            tax_purpose?: string | null;
        };
        /** SourceGenerationDetail */
        SourceGenerationDetail: {
            /** Applied Sequence */
            applied_sequence: number;
            /** Base Generation Id */
            base_generation_id: string | null;
            /** Failure Code */
            failure_code: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Manifest */
            manifest: {
                [key: string]: unknown;
            } | null;
            /**
             * Source Mode
             * @default VERSIONED
             * @constant
             */
            source_mode?: "VERSIONED";
            /** Status */
            status: string;
            /**
             * Strategy
             * @enum {string}
             */
            strategy: "FRESH" | "REFRESH" | "COMPACT";
            /** Target Sequence */
            target_sequence: number | null;
            /** Verified At */
            verified_at?: string | null;
        };
        /** SourceGenerationRequest */
        SourceGenerationRequest: {
            /** Base Generation Id */
            base_generation_id?: string | null;
            /**
             * Strategy
             * @default FRESH
             * @enum {string}
             */
            strategy?: "FRESH" | "REFRESH" | "COMPACT";
        };
        /** SourceReadiness */
        SourceReadiness: {
            /**
             * Business State
             * @default PREPARING
             * @enum {string}
             */
            business_state?: "PREPARING" | "OPENING_REQUIRED" | "BOOKS_NOT_STARTED" | "YEAR_REQUIRED" | "READY";
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Failure Code */
            failure_code?: string | null;
            /** Generation Id */
            generation_id?: string | null;
            /**
             * Inventory State
             * @default PREPARING
             * @enum {string}
             */
            inventory_state?: "PREPARING" | "READY" | "UPDATING";
            /** Owner Checked At */
            owner_checked_at?: string | null;
            /** Owner Sequence */
            owner_sequence?: number | null;
            /**
             * State
             * @enum {string}
             */
            state: "PREPARING" | "CURRENT" | "UPDATING" | "DELAYED" | "NEEDS_ACTION";
            /** Verified Sequence */
            verified_sequence?: number | null;
        };
        /** StockReference */
        StockReference: {
            /** Code */
            code: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
        };
        /** StockReferencePage */
        StockReferencePage: {
            coverage: components["schemas"]["Coverage"];
            /**
             * Generation Id
             * Format: uuid
             */
            generation_id: string;
            /** Items */
            items: components["schemas"]["StockReference"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** TrialHierarchyPage */
        TrialHierarchyPage: {
            /** Items */
            items: components["schemas"]["TrialHierarchyRow"][];
            page: components["schemas"]["PageMeta"];
            /** Periods */
            periods: ("CURRENT" | "COMPARATIVE")[];
            summary: components["schemas"]["TrialTotals"];
        };
        /** TrialHierarchyRow */
        TrialHierarchyRow: {
            data: components["schemas"]["TrialNode"];
            /**
             * Drilldowns
             * @default []
             */
            drilldowns?: components["schemas"]["DrilldownLink"][];
            /** Ordinal */
            ordinal: number;
        };
        /** TrialNode */
        TrialNode: {
            /** Account Count */
            account_count: number;
            /** Account Id */
            account_id?: string | null;
            /** Child Count */
            child_count: number;
            /** Closing Credit */
            closing_credit: string;
            /** Closing Debit */
            closing_debit: string;
            /** Code */
            code: string;
            /** Currency */
            currency: string;
            /** Depth */
            depth: number;
            /** Display Residual */
            display_residual?: {
                [key: string]: string;
            };
            /** Group Child Count */
            group_child_count: number;
            /** Group Id */
            group_id?: string | null;
            /**
             * Head Id
             * Format: uuid
             */
            head_id: string;
            /** Is Zero */
            is_zero: boolean;
            /** Name */
            name: string;
            /** Node Key */
            node_key: string;
            /** Opening Credit */
            opening_credit: string;
            /** Opening Debit */
            opening_debit: string;
            /** Parent Key */
            parent_key: string;
            /**
             * Period
             * @enum {string}
             */
            period: "CURRENT" | "COMPARATIVE";
            /** Period Credit */
            period_credit: string;
            /** Period Debit */
            period_debit: string;
            /**
             * Row Kind
             * @enum {string}
             */
            row_kind: "HEAD" | "GROUP" | "ACCOUNT";
        };
        /** TrialPresentation */
        TrialPresentation: {
            /** Collapsed */
            collapsed?: string[];
            /** Expanded */
            expanded?: string[];
            /**
             * Hierarchy
             * @default CURRENT
             * @enum {string}
             */
            hierarchy?: "CURRENT" | "ALL";
            /**
             * Level
             * @default GROUPS
             * @enum {string}
             */
            level?: "HEADS" | "GROUPS" | "ALL_GROUPS" | "LEDGERS";
            /**
             * Period
             * @default CURRENT
             * @enum {string}
             */
            period?: "CURRENT" | "COMPARATIVE";
            /**
             * Show Zero
             * @default true
             */
            show_zero?: boolean;
        };
        /** TrialTotals */
        TrialTotals: {
            /** Account Count */
            account_count: number;
            /** Closing Credit */
            closing_credit: string;
            /** Closing Debit */
            closing_debit: string;
            /** Closing Difference */
            closing_difference: string;
            /** Currency */
            currency: string;
            /** Display Residual */
            display_residual?: {
                [key: string]: string;
            };
            /** Opening Credit */
            opening_credit: string;
            /** Opening Debit */
            opening_debit: string;
            /** Opening Difference */
            opening_difference: string;
            /** Period Credit */
            period_credit: string;
            /** Period Debit */
            period_debit: string;
            /** Period Difference */
            period_difference: string;
        };
        /** ValidatedParameters */
        ValidatedParameters: {
            /** Code */
            code: string;
            /** Definition Identity */
            definition_identity: string;
            /** Parameter Hash */
            parameter_hash: string;
            /** Parameters */
            parameters: {
                [key: string]: unknown;
            };
            /** Version */
            version: number;
        };
        /** View */
        View: {
            /**
             * Calculation
             * @default detail
             */
            calculation?: string;
            /** Columns */
            columns: components["schemas"]["Column"][];
            /** Key */
            key: string;
            /**
             * Layout
             * @default REGISTER
             * @enum {string}
             */
            layout?: "REGISTER" | "STATEMENT" | "RECONCILIATION" | "SUMMARY";
            /**
             * Order
             * @default [
             *       "ordinal"
             *     ]
             */
            order?: string[];
            /**
             * Orientation
             * @default AUTO
             * @enum {string}
             */
            orientation?: "AUTO" | "PORTRAIT" | "LANDSCAPE";
            /** Title */
            title: string;
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
    definitions_v1_companies__company_id__report_definitions_get: {
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
                    "application/json": components["schemas"]["Definition"][];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    field_set_v1_companies__company_id__report_definitions__code__field_set_get: {
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
                code: string;
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    generations_v1_companies__company_id__report_generations_get: {
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_generation_v1_companies__company_id__report_generations_post: {
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
                "application/json": components["schemas"]["GenerationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GenerationDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    generation_v1_companies__company_id__report_generations__identity__get: {
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
                identity: string;
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
                    "application/json": components["schemas"]["GenerationDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    report_runs_v1_companies__company_id__report_runs_get: {
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_run_v1_companies__company_id__report_runs_post: {
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
                "application/json": components["schemas"]["RunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    run_v1_companies__company_id__report_runs__identity__get: {
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
                identity: string;
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
                    "application/json": components["schemas"]["RunDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    download_v1_companies__company_id__report_runs__identity__download_get: {
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
                identity: string;
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    rows_v1_companies__company_id__report_runs__identity__rows_get: {
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
                identity: string;
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
                    "application/json": components["schemas"]["RowPage"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    context_v2_companies__company_id__gst_return_context_get: {
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
                    "application/json": components["schemas"]["GstContext"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    context_v2_companies__company_id__gstr1_context_get: {
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
                    "application/json": components["schemas"]["Gstr1Context"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    overview_v2_companies__company_id__overview_get: {
        parameters: {
            query?: {
                generation_id?: string | null;
                fiscal_year_id?: string | null;
                date_from?: string | null;
                date_to?: string | null;
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
                    "application/json": components["schemas"]["CompanyOverview"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    definitions_v2_companies__company_id__report_definitions_get: {
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
                    "application/json": components["schemas"]["DefinitionCatalog"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    definition_v2_companies__company_id__report_definitions__code__get: {
        parameters: {
            query?: {
                version?: number | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                code: string;
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
                    "application/json": components["schemas"]["DefinitionDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    field_set_v2_companies__company_id__report_definitions__code__field_set_get: {
        parameters: {
            query?: {
                version?: number | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                code: string;
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
                    "application/json": components["schemas"]["DefinitionFields"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    validate_parameters_v2_companies__company_id__report_definitions__code__validate_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                code: string;
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ParameterValidation"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ValidatedParameters"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    exports_v2_companies__company_id__report_exports_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                code?: string | null;
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
                    "application/json": components["schemas"]["JobPage"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    status_v2_companies__company_id__report_exports__identity__get: {
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
                identity: string;
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
                    "application/json": components["schemas"]["JobDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    cancel_v2_companies__company_id__report_exports__identity__cancel_post: {
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
                identity: string;
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
                    "application/json": components["schemas"]["JobDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    download_v2_companies__company_id__report_exports__identity__download_get: {
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
                identity: string;
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    token_v2_companies__company_id__report_exports__identity__download_token_get: {
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
                identity: string;
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
                    "application/json": components["schemas"]["ArtifactDownload"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    retry_v2_companies__company_id__report_exports__identity__retry_post: {
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
                identity: string;
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
                    "application/json": components["schemas"]["JobDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    generations_v2_companies__company_id__report_generations_get: {
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_generation_v2_companies__company_id__report_generations_post: {
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
                "application/json": components["schemas"]["SourceGenerationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SourceGenerationDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    read_generation_v2_companies__company_id__report_generations__identity__get: {
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
                identity: string;
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
                    "application/json": components["schemas"]["SourceGenerationDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    stock_source_v2_companies__company_id__report_generations__identity__inventory_get: {
        parameters: {
            query?: {
                kind?: "ITEM" | "LOCATION" | "GROUP" | "LOT";
                q?: string;
                object_id?: string | null;
                item_id?: string | null;
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
                identity: string;
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
                    "application/json": components["schemas"]["StockReferencePage"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    runs_v2_companies__company_id__report_runs_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                code?: string | null;
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
                    "application/json": components["schemas"]["JobPage"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_run_v2_companies__company_id__report_runs_post: {
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
                "application/json": components["schemas"]["FrameworkRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    run_v2_companies__company_id__report_runs__identity__get: {
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
                identity: string;
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
                    "application/json": components["schemas"]["JobDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    cancel_v2_companies__company_id__report_runs__identity__cancel_post: {
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
                identity: string;
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
                    "application/json": components["schemas"]["JobDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    drilldown_v2_companies__company_id__report_runs__identity__drilldowns_post: {
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
                identity: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DrilldownRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    create_export_v2_companies__company_id__report_runs__identity__exports_post: {
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
                identity: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    hierarchy_v2_companies__company_id__report_runs__identity__hierarchy_get: {
        parameters: {
            query?: {
                parent?: string;
                period?: "CURRENT" | "COMPARATIVE";
                show_zero?: boolean;
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
                identity: string;
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
                    "application/json": components["schemas"]["TrialHierarchyPage"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    query_result_v2_companies__company_id__report_runs__identity__queries_post: {
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
                identity: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResultQuery"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    retry_v2_companies__company_id__report_runs__identity__retry_post: {
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
                identity: string;
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
                    "application/json": components["schemas"]["JobDetail"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    rows_v2_companies__company_id__report_runs__identity__rows_get: {
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
                identity: string;
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
                    "application/json": components["schemas"]["ResultPage"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    row_detail_v2_companies__company_id__report_runs__identity__rows__ordinal__get: {
        parameters: {
            query?: {
                token?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                "x-company-context"?: string | null;
                "x-company-signature"?: string | null;
            };
            path: {
                company_id: string;
                identity: string;
                ordinal: number;
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
                    "application/json": components["schemas"]["ResultRow"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    records_v2_companies__company_id__report_runs__job_id__gst_records_get: {
        parameters: {
            query?: {
                q?: string;
                category?: string;
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
                    "application/json": components["schemas"]["ResultPage"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    history_v2_companies__company_id__report_runs__job_id__gst_review_get: {
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
                    "application/json": components["schemas"]["GstReviewHistory"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    review_v2_companies__company_id__report_runs__job_id__gst_review_post: {
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
                "application/json": components["schemas"]["GstReviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GstReviewItem"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    records_v2_companies__company_id__report_runs__job_id__gstr1_records_get: {
        parameters: {
            query?: {
                q?: string;
                category?: string;
                view?: "STATUTORY" | "SOURCES";
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
                    "application/json": components["schemas"]["ResultPage"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    history_v2_companies__company_id__report_runs__job_id__gstr1_review_get: {
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
                    "application/json": components["schemas"]["GstReviewHistory"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    review_v2_companies__company_id__report_runs__job_id__gstr1_review_post: {
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
                "application/json": components["schemas"]["GstReviewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GstReviewItem"];
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
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    readiness_v2_companies__company_id__source_readiness_get: {
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
                    "application/json": components["schemas"]["SourceReadiness"];
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
            /** @description Internal Server Error */
            500: {
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
