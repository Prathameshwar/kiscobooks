export interface paths {
    "/internal/v1/print-layout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resolve Print Layout */
        post: operations["resolve_print_layout_internal_v1_print_layout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/assets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Company Assets
         * @description Assets this company may place on a layout.
         */
        get: operations["get_company_assets_v1_companies__company_id__assets_get"];
        put?: never;
        /**
         * Upload New Asset
         * @description Upload a brand asset's bytes to this service's own private disk.
         *
         *     The storage path is derived, never supplied; size, digest and (for PNG) pixel
         *     dimensions are measured from the decoded bytes, never taken from the request
         *     (designer plan P4/D3, 2026-11-03 — docs/invoice-design.md §9.2).
         */
        post: operations["upload_new_asset_v1_companies__company_id__assets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/assets/{asset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Asset Detail
         * @description One asset, including where this service stored it, and a fresh download token.
         */
        get: operations["get_asset_detail_v1_companies__company_id__assets__asset_id__get"];
        put?: never;
        post?: never;
        /**
         * Deactivate Company Asset
         * @description Withdraw an asset from new layouts. Published layouts keep rendering it.
         */
        delete: operations["deactivate_company_asset_v1_companies__company_id__assets__asset_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/assets/{asset_id}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download Asset
         * @description The asset's bytes, only against a signed, expiring, actor-bound token.
         *
         *     Current authorization is re-checked here, same as every other read — a token is
         *     never itself the authority, only a bounded convenience once authority is confirmed
         *     (CLAUDE.md §5.14).
         */
        get: operations["download_asset_v1_companies__company_id__assets__asset_id__download_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/assignments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Template Assignments
         * @description The routing rules in force, newest first.
         */
        get: operations["get_template_assignments_v1_companies__company_id__assignments_get"];
        put?: never;
        /**
         * Create Template Assignment
         * @description Route a voucher kind to a template. The template must be this company's.
         */
        post: operations["create_template_assignment_v1_companies__company_id__assignments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/assignments/{assignment_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Change Template Assignment
         * @description Re-prioritize or deactivate a rule. Its criteria are immutable.
         */
        patch: operations["change_template_assignment_v1_companies__company_id__assignments__assignment_id__patch"];
        trace?: never;
    };
    "/v1/companies/{company_id}/components": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Company Components
         * @description Reusable blocks visible to this company, without their contents.
         */
        get: operations["get_company_components_v1_companies__company_id__components_get"];
        put?: never;
        /**
         * Create New Component
         * @description Create a reusable block a layout can compose.
         */
        post: operations["create_new_component_v1_companies__company_id__components_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/components/{component_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Component Detail
         * @description One block, with its contents.
         */
        get: operations["get_component_detail_v1_companies__company_id__components__component_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Change Company Component
         * @description Edit or deactivate a block. Shipped blocks are read-only.
         */
        patch: operations["change_company_component_v1_companies__company_id__components__component_id__patch"];
        trace?: never;
    };
    "/v1/companies/{company_id}/renders": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Render History
         * @description What was printed, most recent first — optionally for one document.
         */
        get: operations["get_render_history_v1_companies__company_id__renders_get"];
        put?: never;
        /**
         * Record Render
         * @description Record that a document was printed, and from which template version.
         */
        post: operations["record_render_v1_companies__company_id__renders_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resolve Voucher Template
         * @description Which layout this document prints on, and which rule decided it.
         */
        post: operations["resolve_voucher_template_v1_companies__company_id__resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Company Templates
         * @description Templates this company may use: its own, and the tenant's shared designs.
         */
        get: operations["list_company_templates_v1_companies__company_id__templates_get"];
        put?: never;
        /**
         * Create New Template
         * @description Create a draft template, optionally with the first version of its canvas.
         */
        post: operations["create_new_template_v1_companies__company_id__templates_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/templates/{template_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Template Detail
         * @description One template, including its page geometry.
         */
        get: operations["get_template_detail_v1_companies__company_id__templates__template_id__get"];
        /**
         * Update Template Metadata
         * @description Change a template's name or page setup. Status is not writable here.
         */
        put: operations["update_template_metadata_v1_companies__company_id__templates__template_id__put"];
        post?: never;
        /**
         * Archive Company Template
         * @description Retire a template. The row stays — printed documents point at it.
         */
        delete: operations["archive_company_template_v1_companies__company_id__templates__template_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/templates/{template_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get All Template Versions
         * @description The template's revision history, without a layout tree per row.
         */
        get: operations["get_all_template_versions_v1_companies__company_id__templates__template_id__versions_get"];
        put?: never;
        /**
         * Save New Version
         * @description Append a canvas revision. Saving does not publish it.
         */
        post: operations["save_new_version_v1_companies__company_id__templates__template_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/templates/{template_id}/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Specific Version
         * @description One version of **this** template — a version id alone is never enough.
         */
        get: operations["get_specific_version_v1_companies__company_id__templates__template_id__versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/templates/{template_id}/versions/{version_id}/publish": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Publish Template Version
         * @description Make this version the layout every future document of this design prints on.
         */
        post: operations["publish_template_version_v1_companies__company_id__templates__template_id__versions__version_id__publish_post"];
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
        /** AssetDetail */
        AssetDetail: {
            /** Asset Name */
            asset_name: string;
            /** Asset Type */
            asset_type: string;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Content Digest */
            content_digest?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Created By */
            created_by?: string | null;
            /** Download Token */
            download_token?: string | null;
            /** File Name */
            file_name: string;
            /** File Size Bytes */
            file_size_bytes: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image Height Px */
            image_height_px?: number | null;
            /** Image Width Px */
            image_width_px?: number | null;
            /** Is Active */
            is_active: boolean;
            /** Mime Type */
            mime_type: string;
            /** Storage Backend */
            storage_backend: string;
            /** Storage Path */
            storage_path: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** AssetItem */
        AssetItem: {
            /** Asset Name */
            asset_name: string;
            /** Asset Type */
            asset_type: string;
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
            /** Download Token */
            download_token?: string | null;
            /** File Name */
            file_name: string;
            /** File Size Bytes */
            file_size_bytes: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image Height Px */
            image_height_px?: number | null;
            /** Image Width Px */
            image_width_px?: number | null;
            /** Is Active */
            is_active: boolean;
            /** Mime Type */
            mime_type: string;
        };
        /** AssetUpload */
        AssetUpload: {
            /** Asset Name */
            asset_name: string;
            /**
             * Asset Type
             * @enum {string}
             */
            asset_type: "LOGO" | "SIGNATURE" | "STAMP_SEAL" | "WATERMARK" | "HEADER_BANNER" | "FOOTER_BANNER" | "CUSTOM_FONT";
            /** Content Base64 */
            content_base64: string;
            /** File Name */
            file_name: string;
            /**
             * Is Tenant Wide
             * @default false
             */
            is_tenant_wide?: boolean;
            /** Mime Type */
            mime_type: string;
        };
        /** AssignmentCreate */
        AssignmentCreate: {
            /** Branch Id */
            branch_id?: string | null;
            /** Currency Code */
            currency_code?: string | null;
            /** Customer Tax Category */
            customer_tax_category?: string | null;
            /**
             * Priority
             * @default 100
             */
            priority?: number;
            /** Specific Version Id */
            specific_version_id?: string | null;
            /**
             * Template Id
             * Format: uuid
             */
            template_id: string;
            /** Voucher Kind */
            voucher_kind: string;
            /** Voucher Type Id */
            voucher_type_id?: string | null;
        };
        /** AssignmentItem */
        AssignmentItem: {
            /** Branch Id */
            branch_id?: string | null;
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
            /** Currency Code */
            currency_code?: string | null;
            /** Customer Tax Category */
            customer_tax_category?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Priority */
            priority: number;
            /** Specific Version Id */
            specific_version_id?: string | null;
            /**
             * Template Id
             * Format: uuid
             */
            template_id: string;
            /** Voucher Kind */
            voucher_kind: string;
            /** Voucher Type Id */
            voucher_type_id?: string | null;
        };
        /** AssignmentUpdate */
        AssignmentUpdate: {
            /** Is Active */
            is_active?: boolean | null;
            /** Priority */
            priority?: number | null;
        };
        /** CanvasElement */
        CanvasElement: {
            /** Asset Id */
            asset_id?: string | null;
            /** Binding Path */
            binding_path?: string | null;
            /** Content */
            content?: string | null;
            /** Height */
            height: number;
            /** Id */
            id: string;
            /** Image Fit */
            image_fit?: ("contain" | "cover" | "fill") | null;
            /** Label */
            label?: string | null;
            /** Show Value */
            show_value?: boolean | null;
            style?: components["schemas"]["CanvasStyle"];
            /** Symbology */
            symbology?: ("CODE128" | "EAN13" | "QR" | "DATAMATRIX") | null;
            /**
             * Type
             * @enum {string}
             */
            type: "TEXT" | "FIELD_BINDING" | "IMAGE" | "ITEM_TABLE" | "TAX_SUMMARY" | "QR_CODE" | "BARCODE" | "SHAPE" | "DIVIDER" | "SIGNATURE";
            /** Width */
            width: number;
            /** X */
            x: number;
            /** Y */
            y: number;
            /**
             * Z Index
             * @default 1
             */
            z_index?: number;
        };
        /**
         * CanvasElementV11
         * @description 1.0.0's element, plus the typed options the item table and totals block need.
         */
        CanvasElementV11: {
            /** Asset Id */
            asset_id?: string | null;
            /** Binding Path */
            binding_path?: string | null;
            /** Columns */
            columns?: components["schemas"]["ItemColumn"][] | null;
            /** Content */
            content?: string | null;
            /** Height */
            height: number;
            /** Id */
            id: string;
            /** Image Fit */
            image_fit?: ("contain" | "cover" | "fill") | null;
            /** Label */
            label?: string | null;
            row_options?: components["schemas"]["RowOptions"] | null;
            /** Show Cess */
            show_cess?: boolean | null;
            /** Show Value */
            show_value?: boolean | null;
            style?: components["schemas"]["CanvasStyle"];
            /** Symbology */
            symbology?: ("CODE128" | "EAN13" | "QR" | "DATAMATRIX") | null;
            /** Tax Grouping */
            tax_grouping?: ("by_rate" | "by_hsn" | "none") | null;
            /** Totals Rows */
            totals_rows?: ("subtotal" | "discount" | "taxable_value" | "cgst" | "sgst" | "igst" | "cess" | "round_off" | "grand_total" | "amount_in_words" | "outstanding_balance")[] | null;
            /**
             * Type
             * @enum {string}
             */
            type: "TEXT" | "FIELD_BINDING" | "IMAGE" | "ITEM_TABLE" | "ACCOUNT_TABLE" | "TAX_SUMMARY" | "TOTALS_BLOCK" | "QR_CODE" | "BARCODE" | "SHAPE" | "DIVIDER" | "SIGNATURE";
            /** Width */
            width: number;
            /** X */
            x: number;
            /** Y */
            y: number;
            /**
             * Z Index
             * @default 1
             */
            z_index?: number;
        };
        /** CanvasMargins */
        CanvasMargins: {
            /**
             * Bottom
             * @default 10
             */
            bottom?: number;
            /**
             * Left
             * @default 10
             */
            left?: number;
            /**
             * Right
             * @default 10
             */
            right?: number;
            /**
             * Top
             * @default 10
             */
            top?: number;
            /**
             * Unit
             * @default mm
             * @enum {string}
             */
            unit?: "mm" | "in" | "pt" | "px";
        };
        /** CanvasPage */
        CanvasPage: {
            /**
             * Grid Size
             * @default 5
             */
            grid_size?: number;
            /**
             * Grid Snap
             * @default true
             */
            grid_snap?: boolean;
            margins?: components["schemas"]["CanvasMargins"];
            /**
             * Orientation
             * @default portrait
             * @enum {string}
             */
            orientation?: "portrait" | "landscape";
            /**
             * Size
             * @default A4
             * @enum {string}
             */
            size?: "A4" | "LETTER" | "A5" | "THERMAL_80MM" | "THERMAL_58MM" | "CUSTOM";
        };
        /**
         * CanvasPageV11
         * @description Page *setup* — margins and the editor's grid.
         *
         *     **Paper size and orientation are deliberately absent.** They live on the template row
         *     (``paper_size``, ``page_orientation``, ``page_width_mm``, ``page_height_mm``), which is
         *     where they are ``DECIMAL(19,4)`` and where ``CUSTOM`` is validated to carry both
         *     dimensions. 1.0.0 restated size and orientation inside the tree as well — in the opposite
         *     case — which gave one document two answers to "what paper is this?" and nothing to
         *     resolve them with. One source of truth; see the decision log.
         */
        CanvasPageV11: {
            /**
             * Grid Snap
             * @default true
             */
            grid_snap?: boolean;
            /**
             * Grid Step Mm
             * @default 5
             */
            grid_step_mm?: number;
            margins?: components["schemas"]["CanvasMargins"];
        };
        /** CanvasSection */
        CanvasSection: {
            /** Component Code */
            component_code?: string | null;
            /** Elements */
            elements?: components["schemas"]["CanvasElement"][];
            /** Height */
            height?: number | null;
            /** Id */
            id: string;
            /** Title */
            title?: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "HEADER" | "BILLING_SHIPPING" | "ITEM_TABLE" | "TAX_SUMMARY" | "TOTALS" | "FOOTER" | "CUSTOM";
        };
        /**
         * CanvasSectionV11
         * @description 1.0.0's section, with the millimetre box the editor outlines and selects.
         */
        CanvasSectionV11: {
            /** Component Code */
            component_code?: string | null;
            /** Elements */
            elements?: components["schemas"]["CanvasElementV11"][];
            /**
             * Free Placement
             * @default false
             */
            free_placement?: boolean;
            /** Height */
            height: number;
            /** Id */
            id: string;
            /** Title */
            title?: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "HEADER" | "BILLING_SHIPPING" | "ITEM_TABLE" | "TAX_SUMMARY" | "TOTALS" | "FOOTER" | "CUSTOM";
            /** Width */
            width: number;
            /** X */
            x: number;
            /** Y */
            y: number;
        };
        /**
         * CanvasStyle
         * @description Typed styling. The renderer composes CSS from these; none of it is CSS itself.
         */
        CanvasStyle: {
            /** Background Color */
            background_color?: string | null;
            /** Border Color */
            border_color?: string | null;
            /** Border Style */
            border_style?: ("none" | "solid" | "dashed" | "dotted") | null;
            /** Border Width Mm */
            border_width_mm?: number | null;
            /** Color */
            color?: string | null;
            /** Font Size Pt */
            font_size_pt?: number | null;
            /** Font Style */
            font_style?: ("normal" | "italic") | null;
            /** Font Weight */
            font_weight?: ("normal" | "medium" | "semibold" | "bold") | null;
            /** Line Height */
            line_height?: number | null;
            /** Opacity */
            opacity?: number | null;
            /** Padding Mm */
            padding_mm?: number | null;
            /** Text Align */
            text_align?: ("left" | "center" | "right" | "justify") | null;
            /** Uppercase */
            uppercase?: boolean | null;
            /** Vertical Align */
            vertical_align?: ("top" | "middle" | "bottom") | null;
        };
        /** CanvasTheme */
        CanvasTheme: {
            /**
             * Font Family
             * @default Inter, sans-serif
             */
            font_family?: string;
            /**
             * Font Size Pt
             * @default 9
             */
            font_size_pt?: number;
            /**
             * Primary Color
             * @default #1E40AF
             */
            primary_color?: string;
            /** Secondary Color */
            secondary_color?: string | null;
        };
        /**
         * CanvasV10
         * @description The ``1.0.0`` root layout tree — **frozen**.
         *
         *     Not kept for politeness. A version row stores this tree verbatim and a
         *     ``layout_digest`` over those exact bytes (docs/invoice-design.md §4.3), so a reprint of a
         *     published document verifies against them. Widening this model would make every stored
         *     1.0.0 layout re-validate against a different shape, and *normalising* one on read would
         *     change its digest and silently invalidate the evidence. New capability goes in a new
         *     schema version beside this one; nothing here moves again.
         */
        CanvasV10: {
            page?: components["schemas"]["CanvasPage"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            schema_version: "1.0.0";
            /** Sections */
            sections?: components["schemas"]["CanvasSection"][];
            theme?: components["schemas"]["CanvasTheme"];
        };
        /**
         * CanvasV11
         * @description The ``1.1.0`` root layout tree.
         */
        CanvasV11: {
            page?: components["schemas"]["CanvasPageV11"];
            print_options?: components["schemas"]["PrintOptions"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            schema_version: "1.1.0";
            /** Sections */
            sections?: components["schemas"]["CanvasSectionV11"][];
            theme?: components["schemas"]["CanvasTheme"];
        };
        /** ComponentCreate */
        ComponentCreate: {
            /** Code */
            code: string;
            /**
             * Component Category
             * @enum {string}
             */
            component_category: "HEADER" | "BANK_DETAILS" | "TERMS_CONDITIONS" | "SIGNATORY" | "TAX_SUMMARY" | "FOOTER";
            /** Content Definition */
            content_definition: {
                [key: string]: string | boolean | number;
            };
            /** Description */
            description?: string | null;
            /**
             * Is Tenant Wide
             * @default false
             */
            is_tenant_wide?: boolean;
            /** Name */
            name: string;
        };
        /** ComponentDetail */
        ComponentDetail: {
            /** Code */
            code: string;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Component Category */
            component_category: string;
            /** Content Definition */
            content_definition: {
                [key: string]: string | boolean | number;
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Created By */
            created_by?: string | null;
            /** Description */
            description?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Is System */
            is_system: boolean;
            /** Name */
            name: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** ComponentItem */
        ComponentItem: {
            /** Code */
            code: string;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Component Category */
            component_category: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Is System */
            is_system: boolean;
            /** Name */
            name: string;
        };
        /** ComponentUpdate */
        ComponentUpdate: {
            /** Content Definition */
            content_definition?: {
                [key: string]: string | boolean | number;
            } | null;
            /** Description */
            description?: string | null;
            /** Is Active */
            is_active?: boolean | null;
            /** Name */
            name?: string | null;
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
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** ItemColumn */
        ItemColumn: {
            /** Align */
            align?: ("left" | "center" | "right") | null;
            /**
             * Key
             * @enum {string}
             */
            key: "serial_no" | "description" | "hsn_sac" | "batch" | "expiry" | "quantity" | "unit" | "rate" | "mrp" | "discount" | "taxable_value" | "cgst_rate" | "cgst_amount" | "sgst_rate" | "sgst_amount" | "igst_rate" | "igst_amount" | "cess" | "amount" | "account";
            /** Label */
            label?: string | null;
            /**
             * Show
             * @default true
             */
            show?: boolean;
            /** Width Mm */
            width_mm: number;
        };
        /** PageMeta */
        PageMeta: {
            /**
             * Has More
             * @default false
             */
            has_more?: boolean;
            /** Next Cursor */
            next_cursor?: string | null;
        };
        /** Page[AssetItem] */
        Page_AssetItem_: {
            /** Items */
            items: components["schemas"]["AssetItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[AssignmentItem] */
        Page_AssignmentItem_: {
            /** Items */
            items: components["schemas"]["AssignmentItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[ComponentItem] */
        Page_ComponentItem_: {
            /** Items */
            items: components["schemas"]["ComponentItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[SnapshotItem] */
        Page_SnapshotItem_: {
            /** Items */
            items: components["schemas"]["SnapshotItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[TemplateItem] */
        Page_TemplateItem_: {
            /** Items */
            items: components["schemas"]["TemplateItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[VersionItem] */
        Page_VersionItem_: {
            /** Items */
            items: components["schemas"]["VersionItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** PrintLayout */
        PrintLayout: {
            /** Assignment Rule Id */
            assignment_rule_id?: string | null;
            /** Layout Definition */
            layout_definition?: {
                [key: string]: unknown;
            } | null;
            /** Layout Digest */
            layout_digest: string;
            /** Name */
            name: string;
            /** Page Height Mm */
            page_height_mm?: string | null;
            /**
             * Page Orientation
             * @default PORTRAIT
             */
            page_orientation?: string;
            /** Page Width Mm */
            page_width_mm?: string | null;
            /**
             * Paper Size
             * @default A4
             */
            paper_size?: string;
            /**
             * Source
             * @enum {string}
             */
            source: "BUILTIN" | "CUSTOM";
            /** Template Id */
            template_id?: string | null;
            /** Version */
            version: string;
            /** Version Id */
            version_id?: string | null;
        };
        /**
         * PrintOptions
         * @description How many copies print, and what each is marked as.
         */
        PrintOptions: {
            /** Copies */
            copies?: ("ORIGINAL_FOR_RECIPIENT" | "DUPLICATE_FOR_TRANSPORTER" | "TRIPLICATE_FOR_SUPPLIER" | "EXTRA_COPY")[];
            /** Copy Mark Position */
            copy_mark_position?: ("top-right" | "top-center" | "watermark") | null;
            /**
             * Pre Printed Stationery
             * @default false
             */
            pre_printed_stationery?: boolean;
        };
        /** PrintResolve */
        PrintResolve: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Currency Code */
            currency_code: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /**
             * Voucher Kind
             * @constant
             */
            voucher_kind: "PURCHASE";
            /**
             * Voucher Type Id
             * Format: uuid
             */
            voucher_type_id: string;
        };
        /** ResolveTemplateRequest */
        ResolveTemplateRequest: {
            /** Branch Id */
            branch_id?: string | null;
            /** Currency Code */
            currency_code?: string | null;
            /** Customer Tax Category */
            customer_tax_category?: string | null;
            /** Voucher Kind */
            voucher_kind: string;
            /** Voucher Type Id */
            voucher_type_id?: string | null;
        };
        /**
         * ResolveTemplateResponse
         * @description The resolved layout, and the rule that chose it.
         *
         *     ``assignment_rule_id`` is ``None`` when no rule matched and the company's single
         *     published template was used instead — which is the difference between "configured"
         *     and "defaulted", and an operator needs to see it.
         */
        ResolveTemplateResponse: {
            /** Assignment Rule Id */
            assignment_rule_id?: string | null;
            /** Layout Definition */
            layout_definition: components["schemas"]["CanvasV10"] | components["schemas"]["CanvasV11"];
            /** Layout Digest */
            layout_digest: string;
            /** Template Code */
            template_code: string;
            /**
             * Template Id
             * Format: uuid
             */
            template_id: string;
            /** Template Name */
            template_name: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
            /** Version Number */
            version_number: number;
        };
        /**
         * RowOptions
         * @description How the body rows of an item table are drawn.
         */
        RowOptions: {
            /** Blank Rows */
            blank_rows?: number | null;
            /** Description Under Item */
            description_under_item?: boolean | null;
            /** Repeat Header */
            repeat_header?: boolean | null;
            /** Zebra */
            zebra?: boolean | null;
        };
        /** SnapshotDetail */
        SnapshotDetail: {
            /** Checksum Sha256 */
            checksum_sha256?: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** File Size Bytes */
            file_size_bytes?: number | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Output Format */
            output_format: string;
            /** Render Channel */
            render_channel: string;
            /** Render Duration Ms */
            render_duration_ms?: number | null;
            /**
             * Rendered At
             * Format: date-time
             */
            rendered_at: string;
            /** Rendered By */
            rendered_by?: string | null;
            /** Storage Path */
            storage_path?: string | null;
            /**
             * Template Id
             * Format: uuid
             */
            template_id: string;
            /**
             * Template Version Id
             * Format: uuid
             */
            template_version_id: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /**
             * Voucher Id
             * Format: uuid
             */
            voucher_id: string;
            /** Voucher Revision Id */
            voucher_revision_id?: string | null;
        };
        /** SnapshotItem */
        SnapshotItem: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Output Format */
            output_format: string;
            /** Render Channel */
            render_channel: string;
            /**
             * Rendered At
             * Format: date-time
             */
            rendered_at: string;
            /** Rendered By */
            rendered_by?: string | null;
            /**
             * Template Id
             * Format: uuid
             */
            template_id: string;
            /**
             * Template Version Id
             * Format: uuid
             */
            template_version_id: string;
            /**
             * Voucher Id
             * Format: uuid
             */
            voucher_id: string;
            /** Voucher Revision Id */
            voucher_revision_id?: string | null;
        };
        /** SnapshotRecordRequest */
        SnapshotRecordRequest: {
            /** Checksum Sha256 */
            checksum_sha256?: string | null;
            /** File Size Bytes */
            file_size_bytes?: number | null;
            /**
             * Output Format
             * @default PDF
             * @enum {string}
             */
            output_format?: "PDF" | "HTML" | "ZPL" | "ESC_POS" | "PNG";
            /**
             * Render Channel
             * @enum {string}
             */
            render_channel: "PRINT" | "PDF_DOWNLOAD" | "EMAIL" | "WHATSAPP" | "CLIENT_PORTAL";
            /** Render Duration Ms */
            render_duration_ms?: number | null;
            /**
             * Template Id
             * Format: uuid
             */
            template_id: string;
            /**
             * Template Version Id
             * Format: uuid
             */
            template_version_id: string;
            /**
             * Voucher Id
             * Format: uuid
             */
            voucher_id: string;
            /** Voucher Revision Id */
            voucher_revision_id?: string | null;
        };
        /** TemplateCreate */
        TemplateCreate: {
            /** Code */
            code: string;
            /** Description */
            description?: string | null;
            /** Initial Canvas */
            initial_canvas?: (components["schemas"]["CanvasV10"] | components["schemas"]["CanvasV11"]) | null;
            /**
             * Is Tenant Wide
             * @default false
             */
            is_tenant_wide?: boolean;
            /** Line Profile */
            line_profile?: ("ITEMS" | "ACCOUNTS" | "MIXED") | null;
            /** Name */
            name: string;
            /** Page Height Mm */
            page_height_mm?: number | string | null;
            /**
             * Page Orientation
             * @default PORTRAIT
             * @enum {string}
             */
            page_orientation?: "PORTRAIT" | "LANDSCAPE";
            /** Page Width Mm */
            page_width_mm?: number | string | null;
            /**
             * Paper Size
             * @default A4
             * @enum {string}
             */
            paper_size?: "A4" | "LETTER" | "A5" | "THERMAL_80MM" | "THERMAL_58MM" | "CUSTOM";
            /**
             * Unit Of Measure
             * @default mm
             * @enum {string}
             */
            unit_of_measure?: "mm" | "in" | "pt" | "px";
            /** Voucher Kind */
            voucher_kind?: string | null;
        };
        /**
         * TemplateCreated
         * @description What creation returns: the template, and the version it created, if any.
         *
         *     A created template is ``DRAFT`` with no live version, so ``current_version_id`` is
         *     null — the designer needs the id of the draft version it just saved, and making the
         *     client list versions to find it would be a worse contract.
         */
        TemplateCreated: {
            /** Code */
            code: string;
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
            /** Created By */
            created_by?: string | null;
            /** Current Version Id */
            current_version_id?: string | null;
            /** Description */
            description?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Initial Version Id */
            initial_version_id?: string | null;
            /** Is System */
            is_system: boolean;
            /** Line Profile */
            line_profile?: string | null;
            /** Name */
            name: string;
            /** Page Height Mm */
            page_height_mm?: string | null;
            /** Page Orientation */
            page_orientation: string;
            /** Page Width Mm */
            page_width_mm?: string | null;
            /** Paper Size */
            paper_size: string;
            /** Status */
            status: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Unit Of Measure */
            unit_of_measure: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Updated By */
            updated_by?: string | null;
            /** Voucher Kind */
            voucher_kind?: string | null;
        };
        /** TemplateDetail */
        TemplateDetail: {
            /** Code */
            code: string;
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
            /** Created By */
            created_by?: string | null;
            /** Current Version Id */
            current_version_id?: string | null;
            /** Description */
            description?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is System */
            is_system: boolean;
            /** Line Profile */
            line_profile?: string | null;
            /** Name */
            name: string;
            /** Page Height Mm */
            page_height_mm?: string | null;
            /** Page Orientation */
            page_orientation: string;
            /** Page Width Mm */
            page_width_mm?: string | null;
            /** Paper Size */
            paper_size: string;
            /** Status */
            status: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Unit Of Measure */
            unit_of_measure: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Updated By */
            updated_by?: string | null;
            /** Voucher Kind */
            voucher_kind?: string | null;
        };
        /**
         * TemplateItem
         * @description The lean list projection — no page geometry, no audit columns.
         */
        TemplateItem: {
            /** Code */
            code: string;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Current Version Id */
            current_version_id?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is System */
            is_system: boolean;
            /** Line Profile */
            line_profile?: string | null;
            /** Name */
            name: string;
            /** Page Orientation */
            page_orientation: string;
            /** Paper Size */
            paper_size: string;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Voucher Kind */
            voucher_kind?: string | null;
        };
        /** TemplateUpdate */
        TemplateUpdate: {
            /** Description */
            description?: string | null;
            /** Line Profile */
            line_profile?: ("ITEMS" | "ACCOUNTS" | "MIXED") | null;
            /** Name */
            name?: string | null;
            /** Page Height Mm */
            page_height_mm?: number | string | null;
            /** Page Orientation */
            page_orientation?: ("PORTRAIT" | "LANDSCAPE") | null;
            /** Page Width Mm */
            page_width_mm?: number | string | null;
            /** Paper Size */
            paper_size?: ("A4" | "LETTER" | "A5" | "THERMAL_80MM" | "THERMAL_58MM" | "CUSTOM") | null;
            /** Unit Of Measure */
            unit_of_measure?: ("mm" | "in" | "pt" | "px") | null;
            /** Voucher Kind */
            voucher_kind?: string | null;
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
        /** VersionCreate */
        VersionCreate: {
            /** Change Summary */
            change_summary?: string | null;
            /** Layout Definition */
            layout_definition: components["schemas"]["CanvasV10"] | components["schemas"]["CanvasV11"];
        };
        /** VersionDetail */
        VersionDetail: {
            /** Change Summary */
            change_summary?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Created By */
            created_by?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Layout Definition */
            layout_definition: components["schemas"]["CanvasV10"] | components["schemas"]["CanvasV11"];
            /** Layout Digest */
            layout_digest: string;
            /** Published At */
            published_at?: string | null;
            /** Published By */
            published_by?: string | null;
            /** Schema Version */
            schema_version: string;
            /**
             * Template Id
             * Format: uuid
             */
            template_id: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Version Number */
            version_number: number;
        };
        /**
         * VersionItem
         * @description Lean list projection: the history, without every layout tree in it.
         */
        VersionItem: {
            /** Change Summary */
            change_summary?: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Created By */
            created_by?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Layout Digest */
            layout_digest: string;
            /** Published At */
            published_at?: string | null;
            /** Schema Version */
            schema_version: string;
            /**
             * Template Id
             * Format: uuid
             */
            template_id: string;
            /** Version Number */
            version_number: number;
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
    resolve_print_layout_internal_v1_print_layout_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PrintResolve"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrintLayout"];
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
    get_company_assets_v1_companies__company_id__assets_get: {
        parameters: {
            query?: {
                asset_type?: string | null;
                include_inactive?: boolean;
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
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
                    "application/json": components["schemas"]["Page_AssetItem_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    upload_new_asset_v1_companies__company_id__assets_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssetUpload"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssetDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    get_asset_detail_v1_companies__company_id__assets__asset_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
                asset_id: string;
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
                    "application/json": components["schemas"]["AssetDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    deactivate_company_asset_v1_companies__company_id__assets__asset_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
                asset_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    download_asset_v1_companies__company_id__assets__asset_id__download_get: {
        parameters: {
            query: {
                token: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
                asset_id: string;
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
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    get_template_assignments_v1_companies__company_id__assignments_get: {
        parameters: {
            query?: {
                voucher_kind?: string | null;
                include_inactive?: boolean;
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
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
                    "application/json": components["schemas"]["Page_AssignmentItem_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    create_template_assignment_v1_companies__company_id__assignments_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssignmentCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssignmentItem"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    change_template_assignment_v1_companies__company_id__assignments__assignment_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
                assignment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssignmentUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssignmentItem"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    get_company_components_v1_companies__company_id__components_get: {
        parameters: {
            query?: {
                category?: string | null;
                include_inactive?: boolean;
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
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
                    "application/json": components["schemas"]["Page_ComponentItem_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    create_new_component_v1_companies__company_id__components_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ComponentCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComponentDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    get_component_detail_v1_companies__company_id__components__component_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
                component_id: string;
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
                    "application/json": components["schemas"]["ComponentDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    change_company_component_v1_companies__company_id__components__component_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
                component_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ComponentUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComponentDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    get_render_history_v1_companies__company_id__renders_get: {
        parameters: {
            query?: {
                voucher_id?: string | null;
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
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
                    "application/json": components["schemas"]["Page_SnapshotItem_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    record_render_v1_companies__company_id__renders_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SnapshotRecordRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    resolve_voucher_template_v1_companies__company_id__resolve_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResolveTemplateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResolveTemplateResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    list_company_templates_v1_companies__company_id__templates_get: {
        parameters: {
            query?: {
                status?: string | null;
                voucher_kind?: string | null;
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
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
                    "application/json": components["schemas"]["Page_TemplateItem_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    create_new_template_v1_companies__company_id__templates_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
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
                    "application/json": components["schemas"]["TemplateCreated"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    get_template_detail_v1_companies__company_id__templates__template_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
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
                    "application/json": components["schemas"]["TemplateDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    update_template_metadata_v1_companies__company_id__templates__template_id__put: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
                template_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TemplateUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TemplateDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    archive_company_template_v1_companies__company_id__templates__template_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
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
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    get_all_template_versions_v1_companies__company_id__templates__template_id__versions_get: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
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
                    "application/json": components["schemas"]["Page_VersionItem_"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    save_new_version_v1_companies__company_id__templates__template_id__versions_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
                template_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    get_specific_version_v1_companies__company_id__templates__template_id__versions__version_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
                template_id: string;
                version_id: string;
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
                    "application/json": components["schemas"]["VersionDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
    publish_template_version_v1_companies__company_id__templates__template_id__versions__version_id__publish_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
            };
            path: {
                company_id: string;
                template_id: string;
                version_id: string;
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
                    "application/json": components["schemas"]["TemplateDetail"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
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
            /** @description Request Entity Too Large */
            413: {
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
