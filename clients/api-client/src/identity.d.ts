export interface paths {
    "/internal/v1/catalog-enrollments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** List Enrollments */
        post: operations["list_catalog_enrollments"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/reference-changes/{service}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Changes */
        get: operations["changes_internal_v1_reference_changes__service__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/reference-changes/{service}/ack": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Acknowledge */
        post: operations["acknowledge_internal_v1_reference_changes__service__ack_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/report-authority/{tenant_id}/{company_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Report Authority */
        post: operations["report_authority_internal_v1_report_authority__tenant_id___company_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/report-enrollments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Enrollments */
        post: operations["enrollments_internal_v1_report_enrollments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/tenants/{tenant_id}/companies/{company_id}/catalog-authorizations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Authorize */
        post: operations["authorize_catalog_job_actor"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/tenants/{tenant_id}/companies/{company_id}/catalog-snapshots": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start Snapshot */
        post: operations["create_catalog_source_snapshot"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/tenants/{tenant_id}/companies/{company_id}/catalog-snapshots/{snapshot_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Snapshot */
        get: operations["get_catalog_source_snapshot"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/tenants/{tenant_id}/companies/{company_id}/catalog-snapshots/{snapshot_id}/pages/{page_number}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Page */
        get: operations["get_catalog_source_snapshot_page"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/tenants/{tenant_id}/companies/{company_id}/posting/configuration": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Configuration */
        get: operations["configuration_internal_v1_tenants__tenant_id__companies__company_id__posting_configuration_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/tenants/{tenant_id}/companies/{company_id}/posting/reservations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reserve */
        post: operations["reserve_internal_v1_tenants__tenant_id__companies__company_id__posting_reservations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/tenants/{tenant_id}/companies/{company_id}/posting/reservations/{operation_id}/{outcome}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Terminal */
        post: operations["terminal_internal_v1_tenants__tenant_id__companies__company_id__posting_reservations__operation_id___outcome__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/tenants/{tenant_id}/companies/{company_id}/stock-posting/reservations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reserve */
        post: operations["reserve_internal_v1_tenants__tenant_id__companies__company_id__stock_posting_reservations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/tenants/{tenant_id}/companies/{company_id}/stock-posting/reservations/{operation_id}/{outcome}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Terminal */
        post: operations["terminal_internal_v1_tenants__tenant_id__companies__company_id__stock_posting_reservations__operation_id___outcome__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/voucher-enrollments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Enrollments */
        post: operations["enrollments_internal_v1_voucher_enrollments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/api-tokens/{token_id}/revoke": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revoke Token */
        post: operations["revoke_token_v1_api_tokens__token_id__revoke_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Companies */
        get: operations["list_companies_v1_companies_get"];
        put?: never;
        /** Create Company */
        post: operations["create_company_v1_companies_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company */
        get: operations["get_company_v1_companies__company_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Company */
        patch: operations["update_company_v1_companies__company_id__patch"];
        trace?: never;
    };
    "/v1/companies/{company_id}/addresses": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Addresses */
        get: operations["list_addresses_v1_companies__company_id__addresses_get"];
        put?: never;
        /** Add Address */
        post: operations["add_address_v1_companies__company_id__addresses_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/bank-accounts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Banks */
        get: operations["banks_v1_companies__company_id__bank_accounts_get"];
        put?: never;
        /** Create Bank */
        post: operations["create_bank_v1_companies__company_id__bank_accounts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/bank-accounts/{bank_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Bank */
        get: operations["get_bank_v1_companies__company_id__bank_accounts__bank_id__get"];
        /** Update Bank */
        put: operations["update_bank_v1_companies__company_id__bank_accounts__bank_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/bank-accounts/{bank_id}/lifecycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Bank Lifecycle */
        post: operations["bank_lifecycle_v1_companies__company_id__bank_accounts__bank_id__lifecycle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/bank-accounts/{bank_id}/reveal": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reveal Bank */
        post: operations["reveal_bank_v1_companies__company_id__bank_accounts__bank_id__reveal_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/bank-encryption/rotate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Rotate Encryption */
        post: operations["rotate_encryption_v1_companies__company_id__bank_encryption_rotate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/contacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Contacts */
        get: operations["contacts_v1_companies__company_id__contacts_get"];
        put?: never;
        /** Create Contact */
        post: operations["create_contact_v1_companies__company_id__contacts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/contacts/{contact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Contact */
        get: operations["get_contact_v1_companies__company_id__contacts__contact_id__get"];
        /** Update Contact */
        put: operations["update_contact_v1_companies__company_id__contacts__contact_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/contacts/{contact_id}/lifecycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Contact Lifecycle */
        post: operations["contact_lifecycle_v1_companies__company_id__contacts__contact_id__lifecycle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/departments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Departments */
        get: operations["list_departments_v1_companies__company_id__departments_get"];
        put?: never;
        /** Create Department */
        post: operations["create_department_v1_companies__company_id__departments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/departments/field-set": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Department Fields */
        get: operations["department_fields_v1_companies__company_id__departments_field_set_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/departments/{department_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Department */
        get: operations["get_department_v1_companies__company_id__departments__department_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Department */
        patch: operations["update_department_v1_companies__company_id__departments__department_id__patch"];
        trace?: never;
    };
    "/v1/companies/{company_id}/departments/{department_id}/lifecycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Department Lifecycle */
        post: operations["department_lifecycle_v1_companies__company_id__departments__department_id__lifecycle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/departments/{department_id}/reparent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reparent Department */
        post: operations["reparent_department_v1_companies__company_id__departments__department_id__reparent_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/display-config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Display Config
         * @description How this company's amounts and dates are written. Not a company detail.
         *
         *     Readable by ``company.read`` **or** by anyone who may work in this company
         *     (``session_context.may_work_in``). A clerk who raises invoices here has to render its
         *     figures the way the company states them — ``12,34,567.89`` and ``dd-MM-yyyy``, from
         *     config and never from the browser's locale (CLAUDE.md §4). Refusing them these
         *     sixteen formatting values would not protect anything: it would make the console fall
         *     back to a different format for the same company, which is how two people read one
         *     invoice differently.
         */
        get: operations["get_display_config_v1_companies__company_id__display_config_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Documents */
        get: operations["documents_v1_companies__company_id__documents_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/documents/reconcile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reconcile */
        post: operations["reconcile_v1_companies__company_id__documents_reconcile_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/documents/{document_id}/download": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Download */
        post: operations["download_v1_companies__company_id__documents__document_id__download_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/documents/{document_id}/finalize": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Finalize */
        post: operations["finalize_v1_companies__company_id__documents__document_id__finalize_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/documents/{document_id}/lifecycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Lifecycle */
        post: operations["lifecycle_v1_companies__company_id__documents__document_id__lifecycle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/documents/{document_id}/upload": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Upload */
        put: operations["upload_v1_companies__company_id__documents__document_id__upload_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/features": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Features */
        get: operations["list_features_v1_companies__company_id__features_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/features/{feature_key}/disable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Disable Feature */
        post: operations["disable_feature_v1_companies__company_id__features__feature_key__disable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/features/{feature_key}/enable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Enable Feature */
        post: operations["enable_feature_v1_companies__company_id__features__feature_key__enable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/gst-filing-preferences": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read */
        get: operations["read_v1_companies__company_id__gst_filing_preferences_get"];
        put?: never;
        /** Create */
        post: operations["create_v1_companies__company_id__gst_filing_preferences_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/gst-filing-preferences/{object_id}": {
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
        /** Close */
        patch: operations["close_v1_companies__company_id__gst_filing_preferences__object_id__patch"];
        trace?: never;
    };
    "/v1/companies/{company_id}/gst-outward-profile-setup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Setup */
        get: operations["setup_v1_companies__company_id__gst_outward_profile_setup_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/gst-outward-profiles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read */
        get: operations["read_v1_companies__company_id__gst_outward_profiles_get"];
        put?: never;
        /** Create */
        post: operations["create_v1_companies__company_id__gst_outward_profiles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/gst-outward-profiles/{object_id}": {
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
        /** Close */
        patch: operations["close_v1_companies__company_id__gst_outward_profiles__object_id__patch"];
        trace?: never;
    };
    "/v1/companies/{company_id}/gst-registration-setup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Registration Setup */
        get: operations["registration_setup_v1_companies__company_id__gst_registration_setup_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/licences": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Licences */
        get: operations["list_licences_v1_companies__company_id__licences_get"];
        put?: never;
        /** Add Licence */
        post: operations["add_licence_v1_companies__company_id__licences_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/lifecycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Company Lifecycle */
        post: operations["company_lifecycle_v1_companies__company_id__lifecycle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/memberships": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Memberships */
        get: operations["list_memberships_v1_companies__company_id__memberships_get"];
        put?: never;
        /** Create Membership */
        post: operations["create_membership_v1_companies__company_id__memberships_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/salespeople": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Salespeople */
        get: operations["list_salespeople_v1_companies__company_id__salespeople_get"];
        put?: never;
        /** Create Salesperson */
        post: operations["create_salesperson_v1_companies__company_id__salespeople_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/salespeople/{salesperson_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Salesperson */
        get: operations["get_salesperson_v1_companies__company_id__salespeople__salesperson_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Salesperson */
        patch: operations["update_salesperson_v1_companies__company_id__salespeople__salesperson_id__patch"];
        trace?: never;
    };
    "/v1/companies/{company_id}/setup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read */
        get: operations["read_v1_companies__company_id__setup_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/setup-readiness": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Setup Readiness
         * @description Identity-owned setup facts; downstream execution readiness belongs to its owner.
         */
        get: operations["setup_readiness_v1_companies__company_id__setup_readiness_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/setup/enroll-reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Enroll Existing Reports
         * @description Audited adoption preserves existing books, openings, periods and report history.
         */
        post: operations["enroll_existing_reports_v1_companies__company_id__setup_enroll_reports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/setup/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry */
        post: operations["retry_v1_companies__company_id__setup_retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/statutory-ids": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Statutory Ids */
        get: operations["list_statutory_ids_v1_companies__company_id__statutory_ids_get"];
        put?: never;
        /** Add Statutory Id */
        post: operations["add_statutory_id_v1_companies__company_id__statutory_ids_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/step-up/challenge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Challenge */
        post: operations["challenge_v1_companies__company_id__step_up_challenge_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/step-up/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Complete */
        post: operations["complete_v1_companies__company_id__step_up_complete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/tax-registrations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Tax Registrations */
        get: operations["list_tax_registrations_v1_companies__company_id__tax_registrations_get"];
        put?: never;
        /** Add Tax Registration */
        post: operations["add_tax_registration_v1_companies__company_id__tax_registrations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/tax-registrations/{registration_id}": {
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
        /** Amend Tax Registration */
        patch: operations["amend_tax_registration_v1_companies__company_id__tax_registrations__registration_id__patch"];
        trace?: never;
    };
    "/v1/companies/{company_id}/transaction-currencies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Currencies */
        get: operations["list_currencies_v1_companies__company_id__transaction_currencies_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/transaction-currencies/{currency_code}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Currency */
        put: operations["set_currency_v1_companies__company_id__transaction_currencies__currency_code__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Company Users */
        get: operations["list_company_users_v1_companies__company_id__users_get"];
        put?: never;
        /** Invite Company User */
        post: operations["invite_company_user_v1_companies__company_id__users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Company User */
        get: operations["get_company_user_v1_companies__company_id__users__user_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/companies/{company_id}/visibility": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Set Visibility
         * @description Change a company's visibility — a display preference, but the change itself is a
         *     ``security`` audit event (invariant 17, company.md §6). Never removes audit rows or
         *     hides data from an authorized reader; it only keeps the company out of switchers.
         */
        post: operations["set_visibility_v1_companies__company_id__visibility_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/company-classifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Company Classifications */
        get: operations["list_company_classifications_v1_company_classifications_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/company-features": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Feature Catalogue
         * @description What a company may be given — the code catalogue, not any company's state.
         *
         *     A company's own flags are ``GET /companies/{id}/features``. This is the catalogue
         *     itself: no tenant data, no company, no database, so no object scope applies and the
         *     same answer serves every caller in the installation.
         */
        get: operations["list_feature_catalogue_v1_company_features_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/company-setup-commands/{key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Creation Receipt */
        get: operations["creation_receipt_v1_company_setup_commands__key__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/custom-field-definitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Definitions */
        get: operations["list_definitions_v1_custom_field_definitions_get"];
        put?: never;
        /** Create Definition */
        post: operations["create_definition_v1_custom_field_definitions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/custom-field-definitions/{definition_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Definition */
        get: operations["get_definition_v1_custom_field_definitions__definition_id__get"];
        /** Update Definition */
        put: operations["update_definition_v1_custom_field_definitions__definition_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/custom-field-definitions/{definition_id}/rebuild": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Rebuild Definition */
        post: operations["rebuild_definition_v1_custom_field_definitions__definition_id__rebuild_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/entities/{entity_type}/custom-field-contract": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Product Field Contract */
        get: operations["product_field_contract_v1_entities__entity_type__custom_field_contract_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/entities/{entity_type}/field-config": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Layouts */
        get: operations["layouts_v1_entities__entity_type__field_config_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/entities/{entity_type}/field-config/{field_key}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Configure Field */
        put: operations["configure_field_v1_entities__entity_type__field_config__field_key__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/entities/{entity_type}/field-set": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Field Set */
        get: operations["get_field_set_v1_entities__entity_type__field_set_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/field-policies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Policies */
        get: operations["policies_v1_field_policies_get"];
        put?: never;
        /** Create Policy */
        post: operations["create_policy_v1_field_policies_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/field-policies/{policy_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Update Policy */
        put: operations["update_policy_v1_field_policies__policy_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/invitations/{invitation_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel Invitation */
        post: operations["cancel_invitation_v1_invitations__invitation_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/memberships/{membership_id}/end": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** End Membership */
        post: operations["end_membership_v1_memberships__membership_id__end_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/memberships/{membership_id}/make-primary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Make Primary */
        post: operations["make_primary_v1_memberships__membership_id__make_primary_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/onboarding/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Status */
        get: operations["status_v1_onboarding_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/onboarding/tenant": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Workspace */
        post: operations["create_workspace_v1_onboarding_tenant_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/permissions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Permissions
         * @description The fixed permission catalogue a client builds its role-composition form from.
         */
        get: operations["list_permissions_v1_permissions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/access/role": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Role */
        get: operations["role_v1_platform_access_role_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/access/tenants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tenants */
        get: operations["tenants_v1_platform_access_tenants_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/access/tenants/{tenant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tenant */
        get: operations["tenant_v1_platform_access_tenants__tenant_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/access/tenants/{tenant_id}/administrators": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Administrators */
        get: operations["administrators_v1_platform_access_tenants__tenant_id__administrators_get"];
        put?: never;
        /** Invite */
        post: operations["invite_v1_platform_access_tenants__tenant_id__administrators_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/access/tenants/{tenant_id}/administrators/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Administrator */
        get: operations["administrator_v1_platform_access_tenants__tenant_id__administrators__user_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/access/tenants/{tenant_id}/administrators/{user_id}/commands": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Change */
        post: operations["change_v1_platform_access_tenants__tenant_id__administrators__user_id__commands_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/access/tenants/{tenant_id}/administrators/{user_id}/password-recovery": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Password Recovery */
        post: operations["password_recovery_v1_platform_access_tenants__tenant_id__administrators__user_id__password_recovery_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/accounts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Accounts */
        get: operations["accounts_v1_platform_accounts_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/accounts/options": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Account Options */
        get: operations["account_options_v1_platform_accounts_options_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/accounts/pending-registration": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Pending Registration */
        get: operations["pending_registration_v1_platform_accounts_pending_registration_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/accounts/sync": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Sync Accounts */
        post: operations["sync_accounts_v1_platform_accounts_sync_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/accounts/{account_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Account */
        get: operations["account_v1_platform_accounts__account_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/accounts/{account_id}/reconcile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reconcile Account */
        post: operations["reconcile_account_v1_platform_accounts__account_id__reconcile_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/accounts/{account_id}/review": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Review */
        post: operations["review_v1_platform_accounts__account_id__review_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/details": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Platform Details */
        get: operations["platform_details_v1_platform_details_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Platform Details */
        patch: operations["update_platform_details_v1_platform_details_patch"];
        trace?: never;
    };
    "/v1/platform/pricing": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Prices */
        get: operations["list_prices_v1_platform_pricing_get"];
        put?: never;
        /** Create Price */
        post: operations["create_price_v1_platform_pricing_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/pricing/{price_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Price */
        get: operations["get_price_v1_platform_pricing__price_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Price */
        patch: operations["update_price_v1_platform_pricing__price_id__patch"];
        trace?: never;
    };
    "/v1/platform/pricing/{price_id}/revisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Revisions */
        get: operations["revisions_v1_platform_pricing__price_id__revisions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/pricing/{price_id}/{action}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Lifecycle */
        post: operations["lifecycle_v1_platform_pricing__price_id___action__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/references/options": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Options */
        get: operations["options_v1_platform_references_options_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/references/timezones": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Timezone Listing
         * @description Read-only pinned IANA catalogue; administrators cannot edit timezone rules.
         */
        get: operations["timezone_listing_v1_platform_references_timezones_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/references/{kind}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Listing */
        get: operations["listing_v1_platform_references__kind__get"];
        put?: never;
        /** Create */
        post: operations["create_v1_platform_references__kind__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/references/{kind}/{code}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get */
        get: operations["get_v1_platform_references__kind___code__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Edit */
        patch: operations["edit_v1_platform_references__kind___code__patch"];
        trace?: never;
    };
    "/v1/platform/references/{kind}/{code}/{action}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Lifecycle */
        post: operations["lifecycle_v1_platform_references__kind___code___action__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/system-roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Preview */
        get: operations["preview_v1_platform_system_roles_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/system-roles/reconcile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reconcile */
        post: operations["reconcile_v1_platform_system_roles_reconcile_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/tenant-administrators/available": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Available Administrator */
        get: operations["available_administrator_v1_platform_tenant_administrators_available_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/tenant-options": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tenant Options */
        get: operations["tenant_options_v1_platform_tenant_options_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/tenants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tenants */
        get: operations["tenants_v1_platform_tenants_get"];
        put?: never;
        /** Provision */
        post: operations["provision_v1_platform_tenants_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/tenants/{tenant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tenant Detail */
        get: operations["tenant_detail_v1_platform_tenants__tenant_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Platform Tenant */
        patch: operations["update_platform_tenant_v1_platform_tenants__tenant_id__patch"];
        trace?: never;
    };
    "/v1/platform/tenants/{tenant_id}/administrator-invitation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Administrator Invitation */
        get: operations["administrator_invitation_v1_platform_tenants__tenant_id__administrator_invitation_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/tenants/{tenant_id}/impersonation-sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Start */
        post: operations["start_v1_platform_tenants__tenant_id__impersonation_sessions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/tenants/{tenant_id}/impersonation-sessions/{session_id}/end": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** End */
        post: operations["end_v1_platform_tenants__tenant_id__impersonation_sessions__session_id__end_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/platform/tenants/{tenant_id}/lifecycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Tenant Lifecycle */
        post: operations["tenant_lifecycle_v1_platform_tenants__tenant_id__lifecycle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/reference/countries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Countries
         * @description Active ISO countries; jurisdiction_supported identifies company setup support.
         */
        get: operations["countries_v1_reference_countries_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/reference/countries/{country_code}/licence-types": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Licence Types
         * @description Supported licence kinds; validity requirements describe platform validation.
         */
        get: operations["licence_types_v1_reference_countries__country_code__licence_types_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/reference/countries/{country_code}/states": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * States
         * @description Active subdivisions of one active country, ordered by code.
         */
        get: operations["states_v1_reference_countries__country_code__states_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/reference/currencies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Currencies
         * @description Active currencies for base and optional reporting currency selection.
         */
        get: operations["currencies_v1_reference_currencies_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/reference/timezones": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Timezones
         * @description Bounded active IANA choices for company and warehouse forms.
         */
        get: operations["timezones_v1_reference_timezones_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/registration/invitation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Invitation */
        get: operations["invitation_v1_registration_invitation_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/registration/options": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Options */
        get: operations["options_v1_registration_options_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/role-assignments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Assignments */
        get: operations["list_assignments_v1_role_assignments_get"];
        put?: never;
        /** Assign Role */
        post: operations["assign_role_v1_role_assignments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/role-assignments/check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Check Assignment */
        post: operations["check_assignment_v1_role_assignments_check_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/role-assignments/{assignment_id}/regrant": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Regrant Assignment */
        post: operations["regrant_assignment_v1_role_assignments__assignment_id__regrant_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/role-assignments/{assignment_id}/revoke": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revoke Assignment */
        post: operations["revoke_assignment_v1_role_assignments__assignment_id__revoke_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Roles */
        get: operations["list_roles_v1_roles_get"];
        put?: never;
        /** Create Role */
        post: operations["create_role_v1_roles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/roles/{role_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Role */
        get: operations["get_role_v1_roles__role_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Role */
        patch: operations["update_role_v1_roles__role_id__patch"];
        trace?: never;
    };
    "/v1/roles/{role_id}/clone": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Clone Role
         * @description Clone any role (system or tenant) into an editable tenant role. Cloning grants
         *     the source's permissions into the copy, so the actor must hold them (guard 1).
         */
        post: operations["clone_role_v1_roles__role_id__clone_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/roles/{role_id}/lifecycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Role Lifecycle */
        post: operations["role_lifecycle_v1_roles__role_id__lifecycle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Current Session */
        get: operations["current_session_v1_session_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/session/api-tokens": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Tokens */
        get: operations["tokens_v1_session_api_tokens_get"];
        put?: never;
        /** Issue Token */
        post: operations["issue_token_v1_session_api_tokens_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/session/companies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Session Companies
         * @description The companies this actor may work in — an authenticated self-read, no permission.
         *
         *     Not a second company list. ``GET /v1/companies`` answers "describe the companies I
         *     may read" and requires ``company.read``; this answers "where may I work", which a
         *     clerk has to be able to ask about their own access (docs/company-context-ui-todo.md
         *     D2). Rows come from the actor's own grants, so there is nothing here they could not
         *     already reach, and the projection carries four fields rather than a company's details.
         */
        get: operations["list_session_companies_v1_session_companies_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/session/password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Change Own Password */
        post: operations["change_own_password_v1_session_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/session/preferences": {
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
        /** Update Preferences */
        patch: operations["update_preferences_v1_session_preferences_patch"];
        trace?: never;
    };
    "/v1/session/revoke": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revoke Own Sessions */
        post: operations["revoke_own_sessions_v1_session_revoke_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/setup/administrator": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Administrator */
        get: operations["administrator_v1_setup_administrator_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/setup/checks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Checks */
        get: operations["checks_v1_setup_checks_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/setup/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Complete */
        post: operations["complete_v1_setup_complete_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/setup/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Status */
        get: operations["status_v1_setup_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/tenant": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Tenant */
        get: operations["get_tenant_v1_tenant_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Tenant */
        patch: operations["update_tenant_v1_tenant_patch"];
        trace?: never;
    };
    "/v1/tenants/{tenant_id}/invitations/{invitation_id}/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Accept Invitation */
        post: operations["accept_invitation_v1_tenants__tenant_id__invitations__invitation_id__accept_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/user-groups": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Groups */
        get: operations["list_groups_v1_user_groups_get"];
        put?: never;
        /** Create Group */
        post: operations["create_group_v1_user_groups_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/user-groups/field-set": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Group Fields */
        get: operations["group_fields_v1_user_groups_field_set_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/user-groups/{group_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Group */
        get: operations["get_group_v1_user_groups__group_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Group */
        patch: operations["update_group_v1_user_groups__group_id__patch"];
        trace?: never;
    };
    "/v1/user-groups/{group_id}/lifecycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Group Lifecycle */
        post: operations["group_lifecycle_v1_user_groups__group_id__lifecycle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/user-groups/{group_id}/members": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Group Members */
        get: operations["list_group_members_v1_user_groups__group_id__members_get"];
        put?: never;
        /** Add Group Member */
        post: operations["add_group_member_v1_user_groups__group_id__members_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/user-groups/{group_id}/members/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove Member */
        delete: operations["remove_member_v1_user_groups__group_id__members__user_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Users */
        get: operations["list_users_v1_users_get"];
        put?: never;
        /** Invite User */
        post: operations["invite_user_v1_users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get User */
        get: operations["get_user_v1_users__user_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update User */
        patch: operations["update_user_v1_users__user_id__patch"];
        trace?: never;
    };
    "/v1/users/{user_id}/deactivate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Deactivate User */
        post: operations["deactivate_user_v1_users__user_id__deactivate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/users/{user_id}/identities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Identities */
        get: operations["list_identities_v1_users__user_id__identities_get"];
        put?: never;
        /** Link Identity */
        post: operations["link_identity_v1_users__user_id__identities_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/users/{user_id}/identities/{identity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Unlink Identity */
        delete: operations["unlink_identity_v1_users__user_id__identities__identity_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/users/{user_id}/invitations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Invitations */
        get: operations["list_invitations_v1_users__user_id__invitations_get"];
        put?: never;
        /** Resend Invitation */
        post: operations["resend_invitation_v1_users__user_id__invitations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/users/{user_id}/lifecycle": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** User Lifecycle */
        post: operations["user_lifecycle_v1_users__user_id__lifecycle_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/users/{user_id}/notification-preferences": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Preferences */
        get: operations["preferences_v1_users__user_id__notification_preferences_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/users/{user_id}/notification-preferences/{event_key}/{channel}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Preference */
        put: operations["set_preference_v1_users__user_id__notification_preferences__event_key___channel__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/users/{user_id}/password-recovery": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Issue Recovery Link */
        post: operations["issue_recovery_link_v1_users__user_id__password_recovery_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/v1/users/{user_id}/revoke-sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revoke User Sessions */
        post: operations["revoke_user_sessions_v1_users__user_id__revoke_sessions_post"];
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
        /** AccountCommand */
        AccountCommand: {
            /** Action */
            action: string;
            /**
             * Actor Id
             * Format: uuid
             */
            actor_id: string;
            /** Attested */
            attested: boolean;
            /** Completed At */
            completed_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Error Code */
            error_code: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Reason */
            reason: string;
            /** Status */
            status: string;
            /** Workspace Name */
            workspace_name: string | null;
        };
        /** AccountDecision */
        AccountDecision: {
            /**
             * Action
             * @enum {string}
             */
            action: "approve" | "reject" | "reopen";
            /**
             * Attested
             * @default false
             */
            attested?: boolean;
            /** Reason */
            reason: string;
            /** Version */
            version: number;
            /** Workspace Name */
            workspace_name?: string | null;
        };
        /** AccountHandoff */
        AccountHandoff: {
            /** Invitation Url */
            invitation_url?: string | null;
            /**
             * Notification Status
             * @enum {string}
             */
            notification_status: "queued" | "manual";
            /** Sign In Url */
            sign_in_url: string;
            /** Username */
            username: string;
        };
        /** AccountReconciliation */
        AccountReconciliation: {
            /** Reason */
            reason: string;
            /** Version */
            version: number;
        };
        /** AccountReviewDetail */
        AccountReviewDetail: {
            /** Country Code */
            country_code: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Email */
            email: string;
            handoff?: components["schemas"]["AccountHandoff"] | null;
            /** History */
            history: components["schemas"]["AccountCommand"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Needs Attention */
            needs_attention: boolean;
            /** Provider Active */
            provider_active: boolean;
            /** Provider Verified */
            provider_verified: boolean;
            /** State Code */
            state_code: string;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Username */
            username: string;
            /** Version */
            version: number;
            /** Workspace Name */
            workspace_name: string | null;
        };
        /** AccountReviewItem */
        AccountReviewItem: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Email */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Needs Attention */
            needs_attention: boolean;
            /** Status */
            status: string;
            /** Username */
            username: string;
        };
        /** AccountSyncResult */
        AccountSyncResult: {
            /** Imported */
            imported: number;
            /** Next Page */
            next_page: number | null;
        };
        /** ActorAuthorizationProof */
        ActorAuthorizationProof: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Contract
             * @default identity.company_actor_authorization.v1
             */
            contract?: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /**
             * Generated At
             * Format: date-time
             */
            generated_at: string;
            /** Permissions */
            permissions: string[];
            /**
             * Request Id
             * Format: uuid
             */
            request_id: string;
            /** Source Version */
            source_version: number;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** AddressCreate */
        AddressCreate: {
            /** City */
            city: string;
            /** Country Code */
            country_code: string;
            /**
             * Is Primary
             * @default false
             */
            is_primary?: boolean;
            /** Label */
            label?: string | null;
            /** Line1 */
            line1: string;
            /** Line2 */
            line2?: string | null;
            /** Postal Code */
            postal_code: string;
            /** State Code */
            state_code: string;
            /** Type */
            type: string;
        };
        /** AddressItem */
        AddressItem: {
            /** City */
            city: string;
            /** Country Code */
            country_code: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Is Primary */
            is_primary: boolean;
            /** Label */
            label: string | null;
            /** Line1 */
            line1: string;
            /** Line2 */
            line2: string | null;
            /** Postal Code */
            postal_code: string;
            /** State Code */
            state_code: string;
            /** Type */
            type: string;
        };
        /** AdministratorAvailability */
        AdministratorAvailability: {
            available: components["schemas"]["AvailableAdministrator"] | null;
        };
        /** AdministratorCommand */
        AdministratorCommand: {
            /**
             * Action
             * @enum {string}
             */
            action: "edit" | "suspend" | "restore" | "revoke" | "resend_invitation";
            /** Display Name */
            display_name?: string | null;
            /**
             * Expected Assignment Updated At
             * Format: date-time
             */
            expected_assignment_updated_at: string;
            /**
             * Expected Updated At
             * Format: date-time
             */
            expected_updated_at: string;
            /** Reason */
            reason: string;
        };
        /** AdministratorInvite */
        AdministratorInvite: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /** Reason */
            reason: string;
        };
        /** AdministratorListItem */
        AdministratorListItem: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** AdministratorReceipt */
        AdministratorReceipt: {
            /**
             * Administrator Id
             * Format: uuid
             */
            administrator_id: string;
            /** Assignment Active */
            assignment_active: boolean;
            /**
             * Assignment Id
             * Format: uuid
             */
            assignment_id: string;
            /**
             * Assignment Updated At
             * Format: date-time
             */
            assignment_updated_at: string;
            /** Invitation Expires At */
            invitation_expires_at?: string | null;
            /** Invitation Id */
            invitation_id?: string | null;
            /** Invitation Url */
            invitation_url?: string | null;
            /** Status */
            status: string;
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
        /** AdministratorRecoveryLink */
        AdministratorRecoveryLink: {
            /**
             * Administrator Id
             * Format: uuid
             */
            administrator_id: string;
            /**
             * Delivery
             * @enum {string}
             */
            delivery: "link" | "email";
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Recovery Url */
            recovery_url?: string | null;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
        };
        /** AdministratorRecoveryRequest */
        AdministratorRecoveryRequest: {
            /**
             * Delivery
             * @enum {string}
             */
            delivery: "link" | "email";
            /**
             * Expected Assignment Updated At
             * Format: date-time
             */
            expected_assignment_updated_at: string;
            /**
             * Expected Updated At
             * Format: date-time
             */
            expected_updated_at: string;
            /** Reason */
            reason: string;
        };
        /** AdministratorTenant */
        AdministratorTenant: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Status */
            status: string;
        };
        /** AssignmentCheck */
        AssignmentCheck: {
            /**
             * Allowed
             * @default true
             * @constant
             */
            allowed?: true;
        };
        /** AssignmentCreate */
        AssignmentCreate: {
            /** Grant Reason */
            grant_reason?: string | null;
            /**
             * Role Id
             * Format: uuid
             */
            role_id: string;
            /** Scope Id */
            scope_id?: string | null;
            /**
             * Scope Type
             * @enum {string}
             */
            scope_type: "tenant" | "company" | "department";
            /**
             * Subject Id
             * Format: uuid
             */
            subject_id: string;
            /**
             * Subject Type
             * @enum {string}
             */
            subject_type: "user" | "user_group";
            /** Valid From */
            valid_from?: string | null;
            /** Valid To */
            valid_to?: string | null;
        };
        /** AssignmentItem */
        AssignmentItem: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Grant Reason */
            grant_reason: string | null;
            /** Granted By */
            granted_by: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /**
             * Role Id
             * Format: uuid
             */
            role_id: string;
            /** Role Name */
            role_name?: string | null;
            /** Scope Id */
            scope_id: string | null;
            /** Scope Label */
            scope_label?: string | null;
            /** Scope Type */
            scope_type: string;
            /**
             * Subject Id
             * Format: uuid
             */
            subject_id: string;
            /** Subject Label */
            subject_label?: string | null;
            /** Subject Type */
            subject_type: string;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to: string | null;
        };
        /** AssignmentPage */
        AssignmentPage: {
            /** Items */
            items: components["schemas"]["AssignmentItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** AssignmentRegrant */
        AssignmentRegrant: {
            /** Reason */
            reason: string;
            /** Valid From */
            valid_from?: string | null;
            /** Valid To */
            valid_to?: string | null;
        };
        /** AvailableAdministrator */
        AvailableAdministrator: {
            /** Email */
            email: string;
            /** Name */
            name: string;
            /** Username */
            username: string;
        };
        /** BankItem */
        BankItem: {
            /** Account Last4 */
            account_last4: string | null;
            /** Account Name */
            account_name: string;
            /** Bank Name */
            bank_name: string;
            /** Branch */
            branch?: string | null;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Currency Code */
            currency_code: string;
            /** Iban Last4 */
            iban_last4: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Ifsc */
            ifsc?: string | null;
            /** Is Active */
            is_active: boolean;
            /**
             * Is Primary
             * @default false
             */
            is_primary?: boolean;
            /** Label */
            label: string;
            /** Swift */
            swift?: string | null;
        };
        /** BankReveal */
        BankReveal: {
            /** Account Number */
            account_number: string | null;
            /** Iban */
            iban: string | null;
        };
        /** BankWrite */
        BankWrite: {
            /** Account Name */
            account_name: string;
            /** Account Number */
            account_number?: string | null;
            /** Bank Name */
            bank_name: string;
            /** Branch */
            branch?: string | null;
            /** Currency Code */
            currency_code: string;
            /** Iban */
            iban?: string | null;
            /** Ifsc */
            ifsc?: string | null;
            /**
             * Is Primary
             * @default false
             */
            is_primary?: boolean;
            /** Label */
            label: string;
            /** Swift */
            swift?: string | null;
        };
        /** Challenge */
        Challenge: {
            /** Auth Url */
            auth_url: string;
            /**
             * Challenge Id
             * Format: uuid
             */
            challenge_id: string;
            /** Expires In Seconds */
            expires_in_seconds: number;
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
        /** ClassificationChoice */
        ClassificationChoice: {
            /** Code */
            code: string;
            /** Label */
            label: string;
            /** Sort Order */
            sort_order: number;
        };
        /** CompanyClassifications */
        CompanyClassifications: {
            /** Business Categories */
            business_categories: components["schemas"]["ClassificationChoice"][];
            /** Business Roles */
            business_roles: components["schemas"]["ClassificationChoice"][];
            /** Store Formats */
            store_formats: components["schemas"]["ClassificationChoice"][];
        };
        /** CompanyCreate */
        CompanyCreate: {
            /** Amount Precision */
            amount_precision: number;
            /** Backdated Posting Limit Days */
            backdated_posting_limit_days?: number | null;
            /** Base Currency */
            base_currency: string;
            /**
             * Books Begin Date
             * Format: date
             */
            books_begin_date: string;
            /** Brand Color */
            brand_color?: string | null;
            /** Business Category Code */
            business_category_code?: string | null;
            /** Business Nature */
            business_nature?: string | null;
            /** Business Roles */
            business_roles?: string[];
            /** Cash Receipt Limit */
            cash_receipt_limit?: number | string | null;
            /** Code */
            code: string;
            /** Country Code */
            country_code: string;
            /** Credit Limit Default */
            credit_limit_default?: number | string | null;
            /** Currency Symbol Override */
            currency_symbol_override?: string | null;
            /** Currency Symbol Position */
            currency_symbol_position: string;
            /** Custom Fields */
            custom_fields?: {
                [key: string]: unknown;
            };
            /** Date Format */
            date_format: string;
            /** Datetime Format */
            datetime_format: string;
            /** Decimal Separator */
            decimal_separator: string;
            /** Declaration Text */
            declaration_text?: string | null;
            /** Default Payment Terms Days */
            default_payment_terms_days: number;
            /** Default Tax System */
            default_tax_system: string;
            /** Digit Grouping */
            digit_grouping: string;
            /** Display Name */
            display_name: string;
            /** Entity Type */
            entity_type: string;
            /** Fiscal Year Start Day */
            fiscal_year_start_day: number;
            /** Fiscal Year Start Month */
            fiscal_year_start_month: number;
            /** Incorporation Date */
            incorporation_date?: string | null;
            /** Industry Code */
            industry_code?: string | null;
            initial_tax_registration?: components["schemas"]["InitialTaxRegistration"] | null;
            /** Jurisdiction Text */
            jurisdiction_text?: string | null;
            /** Legal Name */
            legal_name: string;
            /** Locale */
            locale: string;
            /** Logo Url */
            logo_url?: string | null;
            /** Negative Format */
            negative_format: string;
            /** Parent Company Id */
            parent_company_id?: string | null;
            /** Quantity Precision */
            quantity_precision: number;
            /**
             * Reporting Currency
             * @description Reporting currency; null uses base currency. Does not enable FX billing.
             */
            reporting_currency?: string | null;
            /**
             * Requires Step Up
             * @default false
             */
            requires_step_up?: boolean;
            /** Rounding Mode */
            rounding_mode: string;
            setup?: components["schemas"]["CompanySetupOptions"];
            /**
             * Show Amount In Words
             * @default false
             */
            show_amount_in_words?: boolean;
            /** Signatory Designation */
            signatory_designation?: string | null;
            /** Signatory Name */
            signatory_name?: string | null;
            /** Signature Url */
            signature_url?: string | null;
            /** State Code */
            state_code: string;
            /** Store Format Code */
            store_format_code?: string | null;
            /** Tax Treatment Default */
            tax_treatment_default: string;
            /** Terms And Conditions */
            terms_and_conditions?: string | null;
            /**
             * Thousands Separator
             * @default
             */
            thousands_separator?: string;
            /** Timezone */
            timezone: string;
            /** Trade Name */
            trade_name?: string | null;
            /**
             * Visibility
             * @default listed
             */
            visibility?: string;
        };
        /** CompanyCurrenciesView */
        CompanyCurrenciesView: {
            /** Allowances */
            allowances: components["schemas"]["CurrencyAllowanceView"][];
            /** Base Currency */
            base_currency: string;
        };
        /** CompanyDetail */
        CompanyDetail: {
            /** Amount Precision */
            amount_precision?: number;
            /** Backdated Posting Limit Days */
            backdated_posting_limit_days?: number | null;
            /** Base Currency */
            base_currency?: string;
            /**
             * Books Begin Date
             * Format: date
             */
            books_begin_date?: string;
            /** Brand Color */
            brand_color?: string | null;
            /** Business Category Code */
            business_category_code?: string | null;
            /** Business Nature */
            business_nature?: string | null;
            /** Business Roles */
            business_roles?: string[];
            /** Cash Receipt Limit */
            cash_receipt_limit?: string | null;
            /** Code */
            code?: string;
            /** Country Code */
            country_code?: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Credit Limit Default */
            credit_limit_default?: string | null;
            /** Currency Symbol Override */
            currency_symbol_override?: string | null;
            /** Currency Symbol Position */
            currency_symbol_position?: string;
            /** Custom Fields */
            custom_fields?: {
                [key: string]: unknown;
            } | null;
            /** Date Format */
            date_format?: string;
            /** Datetime Format */
            datetime_format?: string;
            /** Decimal Separator */
            decimal_separator?: string;
            /** Declaration Text */
            declaration_text?: string | null;
            /** Default Payment Terms Days */
            default_payment_terms_days?: number;
            /** Default Tax System */
            default_tax_system?: string;
            /** Digit Grouping */
            digit_grouping?: string;
            /** Display Name */
            display_name?: string;
            /** Dsc Thumbprint */
            dsc_thumbprint: string | null;
            /** Entity Type */
            entity_type?: string;
            /** First Posted At */
            first_posted_at: string | null;
            /** Fiscal Year Start Day */
            fiscal_year_start_day?: number;
            /** Fiscal Year Start Month */
            fiscal_year_start_month?: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Incorporation Date */
            incorporation_date?: string | null;
            /** Industry Code */
            industry_code?: string | null;
            /** Jurisdiction Text */
            jurisdiction_text?: string | null;
            /** Legal Name */
            legal_name?: string;
            /** Locale */
            locale?: string;
            /** Logo Url */
            logo_url?: string | null;
            /** Negative Format */
            negative_format?: string;
            /** Parent Company Id */
            parent_company_id: string | null;
            /** Quantity Precision */
            quantity_precision?: number;
            /** Reporting Currency */
            reporting_currency?: string | null;
            /** Requires Step Up */
            requires_step_up?: boolean;
            /** Rounding Mode */
            rounding_mode?: string;
            /** Show Amount In Words */
            show_amount_in_words?: boolean;
            /** Signatory Designation */
            signatory_designation?: string | null;
            /** Signatory Name */
            signatory_name?: string | null;
            /** Signature Url */
            signature_url?: string | null;
            /** State Code */
            state_code?: string;
            /** Status */
            status: string;
            /** Store Format Code */
            store_format_code?: string | null;
            /** Tax Treatment Default */
            tax_treatment_default?: string;
            /** Terms And Conditions */
            terms_and_conditions?: string | null;
            /** Thousands Separator */
            thousands_separator?: string;
            /** Timezone */
            timezone?: string;
            /** Trade Name */
            trade_name?: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Visibility */
            visibility?: string;
        };
        /** CompanyLifecycle */
        CompanyLifecycle: {
            /** Reason */
            reason: string;
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "suspended" | "closed";
        };
        /** CompanyListItem */
        CompanyListItem: {
            /** Base Currency */
            base_currency?: string;
            /** Code */
            code?: string;
            /** Country Code */
            country_code?: string;
            /** Display Name */
            display_name?: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Legal Name */
            legal_name?: string;
            /** Requires Step Up */
            requires_step_up?: boolean;
            /** State Code */
            state_code?: string;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Visibility */
            visibility?: string;
        };
        /** CompanyPage */
        CompanyPage: {
            /** Items */
            items: components["schemas"]["CompanyListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /**
         * CompanyServiceScope
         * @description Explicit tenant/company grant; authenticated services have no implicit scope.
         */
        CompanyServiceScope: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
        };
        /** CompanySetupOptions */
        CompanySetupOptions: {
            /** Features */
            features?: string[];
            /**
             * Opening Choice
             * @default DECIDE_LATER
             * @enum {string}
             */
            opening_choice?: "ZERO_CONFIRMED" | "IMPORT_EXISTING" | "DECIDE_LATER";
            /** Opening Reason */
            opening_reason?: string | null;
        };
        /** CompanySetupReadiness */
        CompanySetupReadiness: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Company Status */
            company_status: string;
            /**
             * Company Updated At
             * Format: date-time
             */
            company_updated_at: string;
            /** Features */
            features: components["schemas"]["SetupFeature"][];
            /** First Posted At */
            first_posted_at: string | null;
            /** Frozen Company Fields */
            frozen_company_fields: string[];
            /**
             * Scope
             * @default IDENTITY_ONLY
             * @constant
             */
            scope?: "IDENTITY_ONLY";
        };
        /** CompanySetupStatus */
        CompanySetupStatus: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Failure Code */
            failure_code: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Opening Choice */
            opening_choice: string;
            /** Status */
            status: string;
            /** Steps */
            steps: components["schemas"]["SetupStepView"][];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** CompanyState */
        CompanyState: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Status */
            status: string;
        };
        /** CompanyUpdate */
        CompanyUpdate: {
            /** Amount Precision */
            amount_precision?: number;
            /** Backdated Posting Limit Days */
            backdated_posting_limit_days?: number | null;
            /** Base Currency */
            base_currency?: string;
            /**
             * Books Begin Date
             * Format: date
             */
            books_begin_date?: string;
            /** Brand Color */
            brand_color?: string | null;
            /** Business Category Code */
            business_category_code?: string | null;
            /** Business Nature */
            business_nature?: string | null;
            /** Business Roles */
            business_roles?: string[];
            /** Cash Receipt Limit */
            cash_receipt_limit?: number | string | null;
            /** Code */
            code?: string;
            /** Country Code */
            country_code?: string;
            /** Credit Limit Default */
            credit_limit_default?: number | string | null;
            /** Currency Symbol Override */
            currency_symbol_override?: string | null;
            /** Currency Symbol Position */
            currency_symbol_position?: string;
            /** Custom Fields */
            custom_fields?: {
                [key: string]: unknown;
            } | null;
            /** Date Format */
            date_format?: string;
            /** Datetime Format */
            datetime_format?: string;
            /** Decimal Separator */
            decimal_separator?: string;
            /** Declaration Text */
            declaration_text?: string | null;
            /** Default Payment Terms Days */
            default_payment_terms_days?: number;
            /** Default Tax System */
            default_tax_system?: string;
            /** Digit Grouping */
            digit_grouping?: string;
            /** Display Name */
            display_name?: string;
            /** Entity Type */
            entity_type?: string;
            /**
             * Expected Updated At
             * @description Optional optimistic concurrency precondition; never stored.
             */
            expected_updated_at?: string | null;
            /** Fiscal Year Start Day */
            fiscal_year_start_day?: number;
            /** Fiscal Year Start Month */
            fiscal_year_start_month?: number;
            /** Incorporation Date */
            incorporation_date?: string | null;
            /** Industry Code */
            industry_code?: string | null;
            /** Jurisdiction Text */
            jurisdiction_text?: string | null;
            /** Legal Name */
            legal_name?: string;
            /** Locale */
            locale?: string;
            /** Logo Url */
            logo_url?: string | null;
            /** Negative Format */
            negative_format?: string;
            /** Quantity Precision */
            quantity_precision?: number;
            /**
             * Reporting Currency
             * @description Reporting currency; null uses base currency. Does not enable FX billing.
             */
            reporting_currency?: string | null;
            /** Rounding Mode */
            rounding_mode?: string;
            /** Show Amount In Words */
            show_amount_in_words?: boolean;
            /** Signatory Designation */
            signatory_designation?: string | null;
            /** Signatory Name */
            signatory_name?: string | null;
            /** Signature Url */
            signature_url?: string | null;
            /** State Code */
            state_code?: string;
            /** Store Format Code */
            store_format_code?: string | null;
            /** Tax Treatment Default */
            tax_treatment_default?: string;
            /** Terms And Conditions */
            terms_and_conditions?: string | null;
            /** Thousands Separator */
            thousands_separator?: string;
            /** Timezone */
            timezone?: string;
            /** Trade Name */
            trade_name?: string | null;
        };
        /**
         * CompanyUserInvite
         * @description Only a new tenant person; company and account classification are fixed by the route.
         */
        CompanyUserInvite: {
            /** Display Name */
            display_name?: string | null;
            /** Email */
            email: string;
            /** First Name */
            first_name: string;
            /** Last Name */
            last_name?: string | null;
        };
        /** Complete */
        Complete: {
            /**
             * Challenge Id
             * Format: uuid
             */
            challenge_id: string;
        };
        /** ContactCreate */
        ContactCreate: {
            /** Designation */
            designation?: string | null;
            /** Email */
            email?: string | null;
            /**
             * Is Primary
             * @default false
             */
            is_primary?: boolean;
            /** Name */
            name: string;
            /** Phone */
            phone?: string | null;
            /** Phone Country Code */
            phone_country_code?: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "primary" | "finance" | "support" | "statutory";
        };
        /** ContactItem */
        ContactItem: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Designation */
            designation?: string | null;
            /** Email */
            email?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /**
             * Is Primary
             * @default false
             */
            is_primary?: boolean;
            /** Name */
            name: string;
            /** Phone */
            phone?: string | null;
            /** Phone Country Code */
            phone_country_code?: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "primary" | "finance" | "support" | "statutory";
        };
        /**
         * ContactUpdate
         * @description Replacement of editable contact fields; lifecycle is a separate action.
         */
        ContactUpdate: {
            /** Designation */
            designation?: string | null;
            /** Email */
            email?: string | null;
            /**
             * Is Primary
             * @default false
             */
            is_primary?: boolean;
            /** Name */
            name: string;
            /** Phone */
            phone?: string | null;
            /** Phone Country Code */
            phone_country_code?: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "primary" | "finance" | "support" | "statutory";
        };
        /** CountryChoice */
        CountryChoice: {
            /** Code */
            code: string;
            /** Default Currency Code */
            default_currency_code: string;
            /** Default Features */
            default_features: string[];
            /** Jurisdiction Supported */
            jurisdiction_supported: boolean;
            /** Name */
            name: string;
            setup_defaults: components["schemas"]["CountrySetupDefaults"];
            /** Subdivision Label */
            subdivision_label: string;
            /** Tax Registration Options */
            tax_registration_options?: components["schemas"]["TaxRegistrationChoice"][];
            /** Tax Systems */
            tax_systems: string[];
        };
        /** CountryData */
        CountryData: {
            /** Code */
            code: string;
            /** Default Currency Code */
            default_currency_code: string;
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /** Iso3 */
            iso3: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "country";
            /** Name */
            name: string;
            /** Numeric Code */
            numeric_code: string;
            /** Official Name */
            official_name: string;
            /** Phone Prefix */
            phone_prefix: string;
            /** Subdivision Label */
            subdivision_label: string;
        };
        /**
         * CountrySetupDefaults
         * @description A starting point for a new company in this country, never a decision.
         *
         *     ``POST /v1/companies`` still requires every one of these explicitly. Served here so
         *     that a setup form does not carry its own table of jurisdiction conventions
         *     (``identity.domain.company_defaults``).
         */
        CountrySetupDefaults: {
            /** Amount Precision */
            amount_precision: number;
            /** Currency Symbol Position */
            currency_symbol_position: string;
            /** Date Format */
            date_format: string;
            /** Datetime Format */
            datetime_format: string;
            /** Decimal Separator */
            decimal_separator: string;
            /** Default Payment Terms Days */
            default_payment_terms_days: number;
            /** Digit Grouping */
            digit_grouping: string;
            /** Fiscal Year Start Day */
            fiscal_year_start_day: number;
            /** Fiscal Year Start Month */
            fiscal_year_start_month: number;
            /** Locale */
            locale: string;
            /** Negative Format */
            negative_format: string;
            /** Quantity Precision */
            quantity_precision: number;
            /** Rounding Mode */
            rounding_mode: string;
            /** Tax Treatment Default */
            tax_treatment_default: string;
            /** Thousands Separator */
            thousands_separator: string;
            /** Timezone */
            timezone: string;
        };
        /** CreationReceipt */
        CreationReceipt: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
        };
        /** CurrencyAllowanceView */
        CurrencyAllowanceView: {
            /** Currency Code */
            currency_code: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Row Version */
            row_version: number;
        };
        /** CurrencyAllowanceWrite */
        CurrencyAllowanceWrite: {
            /** Expected Version */
            expected_version?: number | null;
            /** Is Active */
            is_active: boolean;
        };
        /** CurrencyChoice */
        CurrencyChoice: {
            /** Code */
            code: string;
            /** Minor Unit */
            minor_unit: number;
            /** Name */
            name: string;
            /** Symbol */
            symbol: string;
        };
        /** CurrencyData */
        CurrencyData: {
            /** Code */
            code: string;
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "currency";
            /** Major Unit Name */
            major_unit_name: string;
            /** Minor Unit */
            minor_unit: number;
            /** Minor Unit Name */
            minor_unit_name?: string | null;
            /** Minor Unit Name Plural */
            minor_unit_name_plural?: string | null;
            /** Name */
            name: string;
            /** Numeric Code */
            numeric_code: string;
            /** Symbol */
            symbol: string;
        };
        /** CustomDefinition */
        "CustomDefinition-Input": {
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
            validation?: components["schemas"]["ValidationRules-Input"];
            /** Visibility */
            visibility?: {
                [key: string]: unknown;
            } | null;
        };
        /** CustomDefinition */
        "CustomDefinition-Output": {
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
            validation?: components["schemas"]["ValidationRules-Output"];
            /** Visibility */
            visibility?: {
                [key: string]: unknown;
            } | null;
        };
        /** DeactivateRequest */
        DeactivateRequest: {
            /** Reason */
            reason?: string | null;
        };
        /** DefinitionItem */
        DefinitionItem: {
            /** Company Id */
            company_id?: string | null;
            definition: components["schemas"]["CustomDefinition-Output"];
            /** Digest */
            digest: string;
            /** Display Group */
            display_group?: string | null;
            /**
             * Display Order
             * @default 0
             */
            display_order?: number;
            /**
             * Entity Type
             * @default identity.company
             * @enum {string}
             */
            entity_type?: "identity.company" | "catalog.product_family" | "catalog.item" | "vouchers.voucher" | "vouchers.voucher_item";
            /** Expected Digest */
            expected_digest?: string | null;
            /** Help Text */
            help_text?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Label */
            label: string;
            /** Placeholder */
            placeholder?: string | null;
            /**
             * Requires Adoption
             * @default false
             */
            requires_adoption?: boolean;
            /** Requires Feature */
            requires_feature?: string | null;
        };
        /** DefinitionListItem */
        DefinitionListItem: {
            /** Data Type */
            data_type: string;
            /** Entity Type */
            entity_type: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Is Searchable */
            is_searchable: boolean;
            /** Key */
            key: string;
            /** Label */
            label: string;
        };
        /** DefinitionWrite */
        DefinitionWrite: {
            /** Company Id */
            company_id?: string | null;
            definition: components["schemas"]["CustomDefinition-Input"];
            /** Display Group */
            display_group?: string | null;
            /**
             * Display Order
             * @default 0
             */
            display_order?: number;
            /**
             * Entity Type
             * @default identity.company
             * @enum {string}
             */
            entity_type?: "identity.company" | "catalog.product_family" | "catalog.item" | "vouchers.voucher" | "vouchers.voucher_item";
            /** Expected Digest */
            expected_digest?: string | null;
            /** Help Text */
            help_text?: string | null;
            /** Label */
            label: string;
            /** Placeholder */
            placeholder?: string | null;
            /** Requires Feature */
            requires_feature?: string | null;
        };
        /** DepartmentCreate */
        DepartmentCreate: {
            /** Code */
            code: string;
            /** Cost Centre Code */
            cost_centre_code?: string | null;
            /** Head User Id */
            head_user_id?: string | null;
            /** Name */
            name: string;
            /** Parent Id */
            parent_id?: string | null;
        };
        /** DepartmentItem */
        DepartmentItem: {
            /** Code */
            code: string;
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Cost Centre Code */
            cost_centre_code: string | null;
            /** Head User Id */
            head_user_id: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Name */
            name: string;
            /** Parent Id */
            parent_id: string | null;
            /** Path */
            path: string;
        };
        /** DepartmentListItem */
        DepartmentListItem: {
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
            /** Is Active */
            is_active: boolean;
            /** Name */
            name: string;
            /** Parent Id */
            parent_id: string | null;
            /** Path */
            path: string;
        };
        /** DepartmentPage */
        DepartmentPage: {
            /** Items */
            items: components["schemas"]["DepartmentListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** DepartmentReparent */
        DepartmentReparent: {
            /** Parent Id */
            parent_id?: string | null;
        };
        /** DepartmentUpdate */
        DepartmentUpdate: {
            /** Code */
            code?: string;
            /** Cost Centre Code */
            cost_centre_code?: string | null;
            /** Head User Id */
            head_user_id?: string | null;
            /** Name */
            name?: string;
        };
        /** DisplayConfig */
        DisplayConfig: {
            /** Amount Precision */
            amount_precision?: number;
            /** Base Currency */
            base_currency?: string;
            /**
             * Currency Display
             * @default symbol
             */
            currency_display?: string;
            /** Currency Symbol Override */
            currency_symbol_override?: string | null;
            /** Currency Symbol Position */
            currency_symbol_position?: string;
            /** Date Format */
            date_format?: string;
            /** Datetime Format */
            datetime_format?: string;
            /** Decimal Separator */
            decimal_separator?: string;
            /** Digit Grouping */
            digit_grouping?: string;
            /** Locale */
            locale?: string;
            /** Negative Format */
            negative_format?: string;
            /** Quantity Precision */
            quantity_precision?: number;
            /** Rounding Mode */
            rounding_mode?: string;
            /** Show Amount In Words */
            show_amount_in_words?: boolean;
            /** Thousands Separator */
            thousands_separator?: string;
            /** Timezone */
            timezone?: string;
        };
        /** DocumentItem */
        DocumentItem: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Content Type */
            content_type: string | null;
            /** Expires On */
            expires_on: string | null;
            /** File Size Bytes */
            file_size_bytes: number | null;
            /** Finalized At */
            finalized_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Issued On */
            issued_on: string | null;
            /** Storage State */
            storage_state: string;
            /** Title */
            title: string;
            /** Type */
            type: string;
        };
        /** DocumentLink */
        DocumentLink: {
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Headers */
            headers?: {
                [key: string]: string;
            };
            /**
             * Method
             * @enum {string}
             */
            method: "PUT" | "GET";
            /** Url */
            url: string;
        };
        /** DocumentWrite */
        DocumentWrite: {
            /** Content Sha256 */
            content_sha256: string;
            /**
             * Content Type
             * @enum {string}
             */
            content_type: "application/pdf" | "image/png" | "image/jpeg";
            /** Expires On */
            expires_on?: string | null;
            /** File Size Bytes */
            file_size_bytes: number;
            /** Issued On */
            issued_on?: string | null;
            /** Title */
            title: string;
            /** Type */
            type: string;
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
        /**
         * FeatureActionRequest
         * @description Optional reason recorded on the audit event; an empty body is allowed.
         */
        FeatureActionRequest: {
            /** Expected Updated At */
            expected_updated_at?: string | null;
            /** Reason */
            reason?: string | null;
        };
        /** FeatureCatalogue */
        FeatureCatalogue: {
            /** Items */
            items: components["schemas"]["FeatureCatalogueItem"][];
        };
        /**
         * FeatureCatalogueItem
         * @description One capability a company may be given, as a setup form needs it.
         *
         *     The graph is ``billing_platform.features`` and the wording
         *     ``identity.domain.company_features``; this is the two of them joined for a client, so
         *     no client has to keep its own list of what the platform can do.
         */
        FeatureCatalogueItem: {
            /** Description */
            description: string;
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Locks */
            locks: boolean;
            /** Requires */
            requires: string[];
            /** Tax Systems */
            tax_systems: string[];
        };
        /** FeatureList */
        FeatureList: {
            /** Enabled */
            enabled: string[];
            /** Features */
            features: components["schemas"]["FeatureView"][];
        };
        /** FeatureView */
        FeatureView: {
            /** Feature Key */
            feature_key: string;
            /** Is Enabled */
            is_enabled: boolean;
            /** Locked */
            locked: boolean;
            /** Locked At */
            locked_at: string | null;
        };
        /** FieldDescriptor */
        FieldDescriptor: {
            /** Choices */
            choices?: {
                [key: string]: unknown;
            }[] | null;
            custom?: components["schemas"]["CustomDefinition-Output"] | null;
            /** Data Type */
            data_type?: string | null;
            /** Default Value */
            default_value?: unknown;
            /** Group */
            group: string;
            /** Help Text */
            help_text?: string | null;
            /** Hideable */
            hideable: boolean;
            /**
             * Is Visible
             * @default true
             */
            is_visible?: boolean;
            /** Key */
            key: string;
            /** Label */
            label?: string | null;
            /** Order */
            order: number;
            /** Placeholder */
            placeholder?: string | null;
            /** Renameable */
            renameable: boolean;
            /** Required */
            required: boolean;
            /** Requires Feature */
            requires_feature: string | null;
            /**
             * Source
             * @default native
             */
            source?: string;
            /** Validation */
            validation?: {
                [key: string]: unknown;
            } | null;
            /**
             * Writable
             * @default true
             */
            writable?: boolean;
        };
        /**
         * FieldSet
         * @description Merged native/custom field set for an entity (docs/identity-schema.md §6.2).
         *
         *     Includes layout and effective policy/permission/lifecycle write hints. The API
         *     independently enforces every mutation; presentation visibility is not authorization.
         */
        FieldSet: {
            /** Entity Type */
            entity_type: string;
            /** Fields */
            fields: components["schemas"]["FieldDescriptor"][];
            /** Model Name */
            model_name: string;
        };
        /** GroupMemberAdd */
        GroupMemberAdd: {
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** GroupMemberItem */
        GroupMemberItem: {
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
            /**
             * User Group Id
             * Format: uuid
             */
            user_group_id: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** GroupMemberListItem */
        GroupMemberListItem: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Display Name */
            display_name?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * User Group Id
             * Format: uuid
             */
            user_group_id: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** GroupUpdate */
        GroupUpdate: {
            /** Description */
            description?: string | null;
            /** Name */
            name?: string;
        };
        /** GstFilingClose */
        GstFilingClose: {
            /**
             * Valid To
             * Format: date
             */
            valid_to: string;
        };
        /** GstFilingCreate */
        GstFilingCreate: {
            /**
             * Frequency
             * @enum {string}
             */
            frequency: "MONTHLY" | "QRMP";
            /**
             * Registration Id
             * Format: uuid
             */
            registration_id: string;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to?: string | null;
        };
        /** GstFilingItem */
        GstFilingItem: {
            /**
             * Frequency
             * @enum {string}
             */
            frequency: "MONTHLY" | "QRMP";
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Registration Id
             * Format: uuid
             */
            registration_id: string;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to?: string | null;
        };
        /** GstOutwardProfileClose */
        GstOutwardProfileClose: {
            /**
             * Valid To
             * Format: date
             */
            valid_to: string;
        };
        /** GstOutwardProfileCreate */
        GstOutwardProfileCreate: {
            /** Annual Turnover */
            annual_turnover: string;
            /**
             * Currency
             * @default INR
             * @constant
             */
            currency?: "INR";
            /** Evidence Hash */
            evidence_hash: string;
            /** Reference */
            reference: string;
            /**
             * Registration Id
             * Format: uuid
             */
            registration_id: string;
            /** Rule 14A */
            rule_14a: boolean;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to?: string | null;
        };
        /** GstOutwardProfileItem */
        GstOutwardProfileItem: {
            /** Annual Turnover */
            annual_turnover: string;
            /**
             * Currency
             * @default INR
             * @constant
             */
            currency?: "INR";
            /** Evidence Hash */
            evidence_hash: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Reference */
            reference: string;
            /**
             * Registration Id
             * Format: uuid
             */
            registration_id: string;
            /** Rule 14A */
            rule_14a: boolean;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to?: string | null;
        };
        /** GstOutwardProfileSetup */
        GstOutwardProfileSetup: {
            /** Can Manage */
            can_manage: boolean;
            /** Create Schema */
            create_schema: {
                [key: string]: unknown;
            };
        };
        /** GstRegistrationSetup */
        GstRegistrationSetup: {
            /** Can Manage */
            can_manage: boolean;
            /** Country Code */
            country_code: string;
            /** Create Schema */
            create_schema: {
                [key: string]: unknown;
            };
            /** Default Tax System */
            default_tax_system: string;
            /** Regimes */
            regimes: {
                [key: string]: string;
            };
            /** States */
            states: components["schemas"]["identity__schemas__reference__StateChoice"][];
        };
        /**
         * InitialTaxRegistration
         * @description One optional registration for the new company's selected jurisdiction.
         */
        InitialTaxRegistration: {
            /** Number */
            number: string;
            /** Regime */
            regime: string;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
        };
        /** InvitationAvailability */
        InvitationAvailability: {
            /** Available */
            available: boolean;
        };
        /** InvitationItem */
        InvitationItem: {
            /** Accepted At */
            accepted_at: string | null;
            /** Cancelled At */
            cancelled_at: string | null;
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
            /** Status */
            status: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** LanguageData */
        LanguageData: {
            /** Code */
            code: string;
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /** Iso3 */
            iso3: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "language";
            /** Name */
            name: string;
            /** Native Name */
            native_name?: string | null;
        };
        /** LayoutItem */
        LayoutItem: {
            /** Display Group */
            display_group?: string | null;
            /** Display Order */
            display_order?: number | null;
            /** Entity Type */
            entity_type: string;
            /** Field Key */
            field_key: string;
            /** Field Source */
            field_source: string;
            /** Help Text Override */
            help_text_override?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Required */
            is_required?: boolean | null;
            /** Is Visible */
            is_visible?: boolean | null;
            /** Label Override */
            label_override?: string | null;
        };
        /** LayoutWrite */
        LayoutWrite: {
            /** Display Group */
            display_group?: string | null;
            /** Display Order */
            display_order?: number | null;
            /** Help Text Override */
            help_text_override?: string | null;
            /** Is Required */
            is_required?: boolean | null;
            /** Is Visible */
            is_visible?: boolean | null;
            /** Label Override */
            label_override?: string | null;
        };
        /** LicenceCreate */
        LicenceCreate: {
            /** Document Url */
            document_url?: string | null;
            /**
             * Is Primary
             * @default false
             */
            is_primary?: boolean;
            /** Issued On */
            issued_on?: string | null;
            /** Issuing Authority */
            issuing_authority?: string | null;
            /** Kind */
            kind: string;
            /** Number */
            number: string;
            /** Premises Address Id */
            premises_address_id?: string | null;
            /** Renewal Reminder Days */
            renewal_reminder_days?: number | null;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to?: string | null;
        };
        /** LicenceItem */
        LicenceItem: {
            /** Document Url */
            document_url: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Primary */
            is_primary: boolean;
            /** Issued On */
            issued_on: string | null;
            /** Issuing Authority */
            issuing_authority: string | null;
            /** Kind */
            kind: string;
            /** Number */
            number: string;
            /** Premises Address Id */
            premises_address_id: string | null;
            /** Renewal Reminder Days */
            renewal_reminder_days: number | null;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to: string | null;
        };
        /** LicenceTypeChoice */
        LicenceTypeChoice: {
            /** Kind */
            kind: string;
            /** Label */
            label: string;
            /** Prints On Invoice */
            prints_on_invoice: boolean;
            /** Valid To Required */
            valid_to_required: boolean;
        };
        /** MembershipCreate */
        MembershipCreate: {
            /** Department Id */
            department_id?: string | null;
            /**
             * Is Primary
             * @default false
             */
            is_primary?: boolean;
            /** Started On */
            started_on?: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** MembershipEnd */
        MembershipEnd: {
            /** Ended On */
            ended_on?: string | null;
            /** Reason */
            reason: string;
        };
        /** MembershipItem */
        MembershipItem: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Department Id */
            department_id: string | null;
            /** Ended On */
            ended_on: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Is Primary */
            is_primary: boolean;
            /** Started On */
            started_on: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** OnboardingStatus */
        OnboardingStatus: {
            /** Email Verified */
            email_verified: boolean;
            /** Linked */
            linked: boolean;
            options?: components["schemas"]["TenantChoices"] | null;
            /** Tenant Id */
            tenant_id?: string | null;
        };
        /**
         * PageMeta
         * @description The cursor envelope returned alongside every list ``items`` array.
         *
         *     No total by default (api-conventions §list): an unconditional exact count on a
         *     growing table is the query that quietly gets expensive.
         */
        PageMeta: {
            /** Has More */
            has_more: boolean;
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** Page[AccountReviewItem] */
        Page_AccountReviewItem_: {
            /** Items */
            items: components["schemas"]["AccountReviewItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[AddressItem] */
        Page_AddressItem_: {
            /** Items */
            items: components["schemas"]["AddressItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[AdministratorListItem] */
        Page_AdministratorListItem_: {
            /** Items */
            items: components["schemas"]["AdministratorListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[AdministratorTenant] */
        Page_AdministratorTenant_: {
            /** Items */
            items: components["schemas"]["AdministratorTenant"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[BankItem] */
        Page_BankItem_: {
            /** Items */
            items: components["schemas"]["BankItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[ContactItem] */
        Page_ContactItem_: {
            /** Items */
            items: components["schemas"]["ContactItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[DefinitionListItem] */
        Page_DefinitionListItem_: {
            /** Items */
            items: components["schemas"]["DefinitionListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[DocumentItem] */
        Page_DocumentItem_: {
            /** Items */
            items: components["schemas"]["DocumentItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[GroupMemberListItem] */
        Page_GroupMemberListItem_: {
            /** Items */
            items: components["schemas"]["GroupMemberListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[GstFilingItem] */
        Page_GstFilingItem_: {
            /** Items */
            items: components["schemas"]["GstFilingItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[GstOutwardProfileItem] */
        Page_GstOutwardProfileItem_: {
            /** Items */
            items: components["schemas"]["GstOutwardProfileItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[InvitationItem] */
        Page_InvitationItem_: {
            /** Items */
            items: components["schemas"]["InvitationItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[LayoutItem] */
        Page_LayoutItem_: {
            /** Items */
            items: components["schemas"]["LayoutItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[LicenceItem] */
        Page_LicenceItem_: {
            /** Items */
            items: components["schemas"]["LicenceItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[MembershipItem] */
        Page_MembershipItem_: {
            /** Items */
            items: components["schemas"]["MembershipItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[PlatformPriceItem] */
        Page_PlatformPriceItem_: {
            /** Items */
            items: components["schemas"]["PlatformPriceItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[PlatformPriceRevisionItem] */
        Page_PlatformPriceRevisionItem_: {
            /** Items */
            items: components["schemas"]["PlatformPriceRevisionItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[PlatformTenantItem] */
        Page_PlatformTenantItem_: {
            /** Items */
            items: components["schemas"]["PlatformTenantItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[PolicyItem] */
        Page_PolicyItem_: {
            /** Items */
            items: components["schemas"]["PolicyItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[PreferenceItem] */
        Page_PreferenceItem_: {
            /** Items */
            items: components["schemas"]["PreferenceItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[ReferenceItem] */
        Page_ReferenceItem_: {
            /** Items */
            items: components["schemas"]["ReferenceItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[StatutoryIdItem] */
        Page_StatutoryIdItem_: {
            /** Items */
            items: components["schemas"]["StatutoryIdItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[TaxRegistrationItem] */
        Page_TaxRegistrationItem_: {
            /** Items */
            items: components["schemas"]["TaxRegistrationItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[TimezoneChoice] */
        Page_TimezoneChoice_: {
            /** Items */
            items: components["schemas"]["TimezoneChoice"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[TokenItem] */
        Page_TokenItem_: {
            /** Items */
            items: components["schemas"]["TokenItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[UserGroupListItem] */
        Page_UserGroupListItem_: {
            /** Items */
            items: components["schemas"]["UserGroupListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** Page[UserIdentityItem] */
        Page_UserIdentityItem_: {
            /** Items */
            items: components["schemas"]["UserIdentityItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** PasswordChange */
        PasswordChange: {
            /** Current Password */
            current_password: string;
            /** New Password */
            new_password: string;
        };
        /** PendingRegistration */
        PendingRegistration: {
            /** Email */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Workspace Name */
            workspace_name: string | null;
        };
        /** PendingRegistrationResult */
        PendingRegistrationResult: {
            match: components["schemas"]["PendingRegistration"] | null;
        };
        /** PermissionCatalogue */
        PermissionCatalogue: {
            /** Permissions */
            permissions: string[];
        };
        /** PlatformAdministrator */
        PlatformAdministrator: {
            /** Assignment Active */
            assignment_active: boolean;
            /**
             * Assignment Id
             * Format: uuid
             */
            assignment_id: string;
            /**
             * Assignment Updated At
             * Format: date-time
             */
            assignment_updated_at: string;
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Active Administrator */
            last_active_administrator: boolean;
            /** Recovery Deliveries */
            recovery_deliveries?: ("link" | "email")[];
            /** Status */
            status: string;
            tenant: components["schemas"]["AdministratorTenant"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to: string | null;
        };
        /** PlatformAdministratorRole */
        PlatformAdministratorRole: {
            /** Description */
            description: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Is System
             * @default true
             * @constant
             */
            is_system?: true;
            /**
             * Key
             * @default tenant_admin
             * @constant
             */
            key?: "tenant_admin";
            /** Name */
            name: string;
            /** Permissions */
            permissions: string[];
            /**
             * Scope Hint
             * @default tenant
             * @constant
             */
            scope_hint?: "tenant";
        };
        /** PlatformDetails */
        PlatformDetails: {
            /** Name */
            name: string;
            /** Public Url */
            public_url: string;
        };
        /** PlatformInvitation */
        PlatformInvitation: {
            /**
             * Administrator Id
             * Format: uuid
             */
            administrator_id: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /**
             * Invitation Id
             * Format: uuid
             */
            invitation_id: string;
            /** Url */
            url: string;
        };
        /** PlatformPriceDetail */
        PlatformPriceDetail: {
            /**
             * Category
             * @enum {string}
             */
            category: "platform" | "whatsapp" | "sms" | "email" | "llm" | "document";
            /** Code */
            code: string;
            /** Deleted At */
            deleted_at: string | null;
            /**
             * Description
             * @default
             */
            description?: string;
            /**
             * Fx Inr Per Usd
             * @default 94.8228
             */
            fx_inr_per_usd?: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /**
             * Model
             * @default
             */
            model?: string;
            /** Monthly Fee */
            monthly_fee: string;
            /** Name */
            name: string;
            /**
             * Output Unit Price
             * @default 0
             */
            output_unit_price?: string;
            /** Prices */
            prices: components["schemas"]["PriceCurrency"][];
            /**
             * Provider
             * @default
             */
            provider?: string;
            /**
             * Tax Percent
             * @default 18
             */
            tax_percent?: string;
            /**
             * Term Months
             * @enum {integer}
             */
            term_months: 1 | 12 | 36;
            /**
             * Unit
             * @enum {string}
             */
            unit: "none" | "messages" | "segments" | "emails" | "tokens" | "pages";
            /**
             * Unit Price
             * @default 0
             */
            unit_price?: string;
            /** Version */
            version: number;
        };
        /** PlatformPriceInput */
        PlatformPriceInput: {
            /**
             * Category
             * @enum {string}
             */
            category: "platform" | "whatsapp" | "sms" | "email" | "llm" | "document";
            /** Code */
            code: string;
            /**
             * Description
             * @default
             */
            description?: string;
            /**
             * Fx Inr Per Usd
             * @default 94.8228
             */
            fx_inr_per_usd?: number | string;
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /**
             * Model
             * @default
             */
            model?: string;
            /** Monthly Fee */
            monthly_fee: number | string;
            /** Name */
            name: string;
            /**
             * Output Unit Price
             * @default 0
             */
            output_unit_price?: number | string;
            /**
             * Provider
             * @default
             */
            provider?: string;
            /**
             * Tax Percent
             * @default 18
             */
            tax_percent?: number | string;
            /**
             * Term Months
             * @enum {integer}
             */
            term_months: 1 | 12 | 36;
            /**
             * Unit
             * @enum {string}
             */
            unit: "none" | "messages" | "segments" | "emails" | "tokens" | "pages";
            /**
             * Unit Price
             * @default 0
             */
            unit_price?: number | string;
        };
        /** PlatformPriceItem */
        PlatformPriceItem: {
            /**
             * Category
             * @enum {string}
             */
            category: "platform" | "whatsapp" | "sms" | "email" | "llm" | "document";
            /** Code */
            code: string;
            /** Deleted At */
            deleted_at: string | null;
            /** Fx Inr Per Usd */
            fx_inr_per_usd: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Monthly Fee */
            monthly_fee: string;
            /** Name */
            name: string;
            /** Output Unit Price */
            output_unit_price: string;
            /** Term Months */
            term_months: number;
            /**
             * Unit
             * @enum {string}
             */
            unit: "none" | "messages" | "segments" | "emails" | "tokens" | "pages";
            /** Unit Price */
            unit_price: string;
            /** Usd Monthly Fee */
            readonly usd_monthly_fee: string;
            /** Usd Unit Price */
            readonly usd_unit_price: string;
            /** Version */
            version: number;
        };
        /** PlatformPriceLifecycle */
        PlatformPriceLifecycle: {
            /** Expected Version */
            expected_version: number;
        };
        /** PlatformPriceRevisionItem */
        PlatformPriceRevisionItem: {
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
            snapshot: components["schemas"]["PlatformPriceDetail"];
            /** Version */
            version: number;
        };
        /** PlatformPriceUpdate */
        PlatformPriceUpdate: {
            /**
             * Category
             * @enum {string}
             */
            category: "platform" | "whatsapp" | "sms" | "email" | "llm" | "document";
            /** Code */
            code: string;
            /**
             * Description
             * @default
             */
            description?: string;
            /** Expected Version */
            expected_version: number;
            /**
             * Fx Inr Per Usd
             * @default 94.8228
             */
            fx_inr_per_usd?: number | string;
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /**
             * Model
             * @default
             */
            model?: string;
            /** Monthly Fee */
            monthly_fee: number | string;
            /** Name */
            name: string;
            /**
             * Output Unit Price
             * @default 0
             */
            output_unit_price?: number | string;
            /**
             * Provider
             * @default
             */
            provider?: string;
            /**
             * Tax Percent
             * @default 18
             */
            tax_percent?: number | string;
            /**
             * Term Months
             * @enum {integer}
             */
            term_months: 1 | 12 | 36;
            /**
             * Unit
             * @enum {string}
             */
            unit: "none" | "messages" | "segments" | "emails" | "tokens" | "pages";
            /**
             * Unit Price
             * @default 0
             */
            unit_price?: number | string;
        };
        /** PlatformTenantCreated */
        PlatformTenantCreated: {
            /**
             * Administrator Mode
             * @enum {string}
             */
            administrator_mode: "new" | "existing";
            /** Administrator Password */
            administrator_password?: string | null;
            /** Administrator Username */
            administrator_username: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Default Country Code */
            default_country_code: string;
            /** Default Currency Code */
            default_currency_code: string;
            /** Default Locale */
            default_locale: string;
            /** Default State Code */
            default_state_code: string | null;
            /** Default Timezone */
            default_timezone: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /**
             * Notification Status
             * @default manual
             * @enum {string}
             */
            notification_status?: "queued" | "manual";
            /** Plan Id */
            plan_id: string | null;
            /** Primary Contact Email */
            primary_contact_email: string;
            /** Sign In Url */
            sign_in_url: string;
            /** Slug */
            slug: string;
            /** Status */
            status: string;
            /** Trial Ends On */
            trial_ends_on: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** PlatformTenantDetail */
        PlatformTenantDetail: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Default Country Code */
            default_country_code: string;
            /** Default Currency Code */
            default_currency_code: string;
            /** Default Locale */
            default_locale: string;
            /** Default State Code */
            default_state_code: string | null;
            /** Default Timezone */
            default_timezone: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Plan Id */
            plan_id: string | null;
            /** Primary Contact Email */
            primary_contact_email: string;
            /** Slug */
            slug: string;
            /** Status */
            status: string;
            /** Suspended At */
            suspended_at: string | null;
            /** Suspended Reason */
            suspended_reason: string | null;
            /** Trial Ends On */
            trial_ends_on: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** PlatformTenantItem */
        PlatformTenantItem: {
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
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** PlatformTenantProvision */
        PlatformTenantProvision: {
            /** Administrator Email */
            administrator_email: string;
            /**
             * Administrator Mode
             * @default new
             * @enum {string}
             */
            administrator_mode?: "new" | "existing";
            /** Administrator Name */
            administrator_name: string;
            /** Administrator Password */
            administrator_password?: string | null;
            /** Country Code */
            country_code: string;
            /** Currency Code */
            currency_code?: string | null;
            /** Locale */
            locale?: string | null;
            /** Name */
            name: string;
            /**
             * Recipient Confirmed
             * @default false
             */
            recipient_confirmed?: boolean;
            /** State Code */
            state_code?: string | null;
            /** Timezone */
            timezone?: string | null;
        };
        /** PolicyItem */
        PolicyItem: {
            /**
             * Access
             * @enum {string}
             */
            access: "read" | "write";
            /** Condition */
            condition?: {
                [key: string]: unknown;
            } | null;
            /**
             * Effect
             * @enum {string}
             */
            effect: "deny" | "allow";
            /**
             * Entity Type
             * @default identity.company
             * @enum {string}
             */
            entity_type?: "identity.company" | "accounting.account" | "accounting.account_alias" | "accounting.account_bank_profile" | "accounting.account_external_key" | "accounting.account_group" | "accounting.account_group_alias" | "accounting.account_group_closure" | "accounting.account_head" | "accounting.account_posting_mapping" | "accounting.account_tax_default" | "accounting.account_tax_profile" | "accounting.account_template_binding" | "accounting.account_template_installation" | "accounting.accounting_setup" | "accounting.allocation" | "accounting.bank_adjustment_proposal" | "accounting.bank_instrument" | "accounting.bank_instrument_event" | "accounting.bank_match_event" | "accounting.bank_opening_item" | "accounting.bank_reconciliation_policy" | "accounting.bank_reconciliation_session" | "accounting.bank_statement_entry" | "accounting.bank_statement_import" | "accounting.bank_statement_mapping" | "accounting.charge_assessment" | "accounting.charge_policy" | "accounting.charge_tax_snapshot" | "accounting.credit_override" | "accounting.credit_reservation" | "accounting.financial_setup" | "accounting.fiscal_period" | "accounting.fiscal_transition" | "accounting.fiscal_year" | "accounting.invoice_allocation_fact" | "accounting.invoice_component_fact" | "accounting.invoice_credit_action" | "accounting.invoice_credit_event" | "accounting.invoice_posting_line" | "accounting.invoice_record" | "accounting.invoice_supply_fact" | "accounting.invoice_tax_component" | "accounting.journal" | "accounting.journal_line" | "accounting.journal_tax" | "accounting.open_item" | "accounting.opening_batch" | "accounting.party" | "accounting.party_accounting_policy" | "accounting.party_address" | "accounting.party_address_use" | "accounting.party_bank_account" | "accounting.party_commercial_type" | "accounting.party_commercial_type_membership" | "accounting.party_contact" | "accounting.party_contact_use" | "accounting.party_credit_policy" | "accounting.party_drug_licence" | "accounting.party_identifier" | "accounting.party_registration_address" | "accounting.party_role" | "accounting.party_tax_registration" | "accounting.party_withholding_profile" | "accounting.payment_term" | "accounting.payment_term_line" | "accounting.source_document" | "accounting.stock_account_policy" | "accounting.stock_cost_pool" | "accounting.stock_lot" | "accounting.stock_movement" | "accounting.stock_position" | "accounting.stock_posting" | "accounting.stock_unit" | "accounting.withholding_certificate" | "accounting.withholding_rate" | "accounting.withholding_section" | "catalog.company_product_authoring_configuration" | "catalog.item" | "catalog.product_family" | "vouchers.voucher" | "vouchers.voucher_item" | "vouchers.configuration";
            /** Field Key */
            field_key: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /** Reason */
            reason: string;
            /** Scope Id */
            scope_id?: string | null;
            /**
             * Scope Type
             * @default tenant
             * @enum {string}
             */
            scope_type?: "tenant" | "company";
            /**
             * Subject Id
             * Format: uuid
             */
            subject_id: string;
            /**
             * Subject Type
             * @enum {string}
             */
            subject_type: "user" | "user_group" | "role";
        };
        /** PolicyWrite */
        PolicyWrite: {
            /**
             * Access
             * @enum {string}
             */
            access: "read" | "write";
            /** Condition */
            condition?: {
                [key: string]: unknown;
            } | null;
            /**
             * Effect
             * @enum {string}
             */
            effect: "deny" | "allow";
            /**
             * Entity Type
             * @default identity.company
             * @enum {string}
             */
            entity_type?: "identity.company" | "accounting.account" | "accounting.account_alias" | "accounting.account_bank_profile" | "accounting.account_external_key" | "accounting.account_group" | "accounting.account_group_alias" | "accounting.account_group_closure" | "accounting.account_head" | "accounting.account_posting_mapping" | "accounting.account_tax_default" | "accounting.account_tax_profile" | "accounting.account_template_binding" | "accounting.account_template_installation" | "accounting.accounting_setup" | "accounting.allocation" | "accounting.bank_adjustment_proposal" | "accounting.bank_instrument" | "accounting.bank_instrument_event" | "accounting.bank_match_event" | "accounting.bank_opening_item" | "accounting.bank_reconciliation_policy" | "accounting.bank_reconciliation_session" | "accounting.bank_statement_entry" | "accounting.bank_statement_import" | "accounting.bank_statement_mapping" | "accounting.charge_assessment" | "accounting.charge_policy" | "accounting.charge_tax_snapshot" | "accounting.credit_override" | "accounting.credit_reservation" | "accounting.financial_setup" | "accounting.fiscal_period" | "accounting.fiscal_transition" | "accounting.fiscal_year" | "accounting.invoice_allocation_fact" | "accounting.invoice_component_fact" | "accounting.invoice_credit_action" | "accounting.invoice_credit_event" | "accounting.invoice_posting_line" | "accounting.invoice_record" | "accounting.invoice_supply_fact" | "accounting.invoice_tax_component" | "accounting.journal" | "accounting.journal_line" | "accounting.journal_tax" | "accounting.open_item" | "accounting.opening_batch" | "accounting.party" | "accounting.party_accounting_policy" | "accounting.party_address" | "accounting.party_address_use" | "accounting.party_bank_account" | "accounting.party_commercial_type" | "accounting.party_commercial_type_membership" | "accounting.party_contact" | "accounting.party_contact_use" | "accounting.party_credit_policy" | "accounting.party_drug_licence" | "accounting.party_identifier" | "accounting.party_registration_address" | "accounting.party_role" | "accounting.party_tax_registration" | "accounting.party_withholding_profile" | "accounting.payment_term" | "accounting.payment_term_line" | "accounting.source_document" | "accounting.stock_account_policy" | "accounting.stock_cost_pool" | "accounting.stock_lot" | "accounting.stock_movement" | "accounting.stock_position" | "accounting.stock_posting" | "accounting.stock_unit" | "accounting.withholding_certificate" | "accounting.withholding_rate" | "accounting.withholding_section" | "catalog.company_product_authoring_configuration" | "catalog.item" | "catalog.product_family" | "vouchers.voucher" | "vouchers.voucher_item" | "vouchers.configuration";
            /** Field Key */
            field_key: string;
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /** Reason */
            reason: string;
            /** Scope Id */
            scope_id?: string | null;
            /**
             * Scope Type
             * @default tenant
             * @enum {string}
             */
            scope_type?: "tenant" | "company";
            /**
             * Subject Id
             * Format: uuid
             */
            subject_id: string;
            /**
             * Subject Type
             * @enum {string}
             */
            subject_type: "user" | "user_group" | "role";
        };
        /** PostingConfiguration */
        PostingConfiguration: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Configuration Hash */
            configuration_hash: string;
            /** Enabled Features */
            enabled_features: string[];
            /** Settings */
            settings: {
                [key: string]: unknown;
            };
        };
        /** PostingReceipt */
        PostingReceipt: {
            /** Configuration Hash */
            configuration_hash: string;
            /** Confirmed At */
            confirmed_at: string | null;
            /** Features */
            features: string[];
            /**
             * Operation Id
             * Format: uuid
             */
            operation_id: string;
            /**
             * Reservation Id
             * Format: uuid
             */
            reservation_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "pending" | "confirmed" | "aborted";
        };
        /** PreferenceItem */
        PreferenceItem: {
            /** Channel */
            channel: string;
            /** Event Key */
            event_key: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Enabled */
            is_enabled: boolean;
            /** Source Version */
            source_version: number;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** PreferenceUpdate */
        PreferenceUpdate: {
            /** Currency Display */
            currency_display?: ("symbol" | "code" | "none") | null;
            /** Date Format */
            date_format?: string | null;
            /** Datetime Format */
            datetime_format?: string | null;
            /** Default Company Id */
            default_company_id?: string | null;
            /** Digit Grouping */
            digit_grouping?: ("indian" | "western" | "none") | null;
            /** Landing Page */
            landing_page?: string | null;
            /** Locale */
            locale?: string | null;
            /** Theme */
            theme?: ("light" | "dark" | "system") | null;
            /** Timezone */
            timezone?: string | null;
        };
        /** PreferenceWrite */
        PreferenceWrite: {
            /** Is Enabled */
            is_enabled: boolean;
        };
        /** PriceCurrency */
        PriceCurrency: {
            /**
             * Currency
             * @enum {string}
             */
            currency: "INR" | "USD";
            /** Monthly Fee */
            monthly_fee: string;
            /** Output Unit Price */
            output_unit_price: string;
            /** Term Net */
            term_net: string;
            /** Term Tax */
            term_tax: string;
            /** Term Total */
            term_total: string;
            /** Unit Price */
            unit_price: string;
        };
        /** Proof */
        Proof: {
            /** Expires In Seconds */
            expires_in_seconds: number;
            /** Proof */
            proof: string;
        };
        /** ReasonRequest */
        ReasonRequest: {
            /** Reason */
            reason: string;
        };
        /** RebuildRequest */
        RebuildRequest: {
            /** After */
            after?: string | null;
            /**
             * Apply Defaults
             * @default false
             */
            apply_defaults?: boolean;
            /** Definition Hash */
            definition_hash?: string | null;
            /**
             * Limit
             * @default 50
             */
            limit?: number;
        };
        /** RebuildResult */
        RebuildResult: {
            /** Definition Hash */
            definition_hash: string;
            /** Next After */
            next_after: string | null;
            /** Processed */
            processed: number;
        };
        /** ReconcileResult */
        ReconcileResult: {
            /** Expired */
            expired: number;
        };
        /** RecoveryLink */
        RecoveryLink: {
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Recovery Url */
            recovery_url: string;
        };
        /** ReferenceDetail */
        ReferenceDetail: {
            /** Code */
            code: string;
            /** Data */
            data: components["schemas"]["CountryData"] | components["schemas"]["StateData"] | components["schemas"]["CurrencyData"] | components["schemas"]["LanguageData"];
            /** Display Code */
            readonly display_code: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Name */
            name: string;
            /** Parent Code */
            parent_code: string | null;
            /** Protected Fields */
            protected_fields: string[];
            /** Source */
            source: string;
            /** Sync Ready */
            sync_ready: boolean;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
        };
        /** ReferenceItem */
        ReferenceItem: {
            /** Code */
            code: string;
            /** Display Code */
            readonly display_code: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Name */
            name: string;
            /** Parent Code */
            parent_code: string | null;
            /** Source */
            source: string;
            /** Version */
            version: number;
        };
        /** ReferenceLifecycle */
        ReferenceLifecycle: {
            /** Reason */
            reason: string;
            /** Version */
            version: number;
        };
        /** ReferenceOption */
        ReferenceOption: {
            /** Code */
            code: string;
            /** Name */
            name: string;
        };
        /** ReferenceOptions */
        ReferenceOptions: {
            /** Countries */
            countries: components["schemas"]["ReferenceOption"][];
            /** Currencies */
            currencies: components["schemas"]["ReferenceOption"][];
        };
        /** ReferenceUpdate */
        ReferenceUpdate: {
            /** Data */
            data: components["schemas"]["CountryData"] | components["schemas"]["StateData"] | components["schemas"]["CurrencyData"] | components["schemas"]["LanguageData"];
            /** Version */
            version: number;
        };
        /** RegistrationChoices */
        RegistrationChoices: {
            /** Countries */
            countries: components["schemas"]["TenantChoice"][];
            /** States */
            states: components["schemas"]["identity__services__tenant_choices__StateChoice"][];
        };
        /** ReportAuthority */
        ReportAuthority: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /**
             * Contract
             * @default identity.company_actor_authorization.v1
             */
            contract?: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /**
             * Generated At
             * Format: date-time
             */
            generated_at: string;
            /** Permissions */
            permissions: string[];
            /** Read Allowed */
            read_allowed: boolean;
            /**
             * Request Id
             * Format: uuid
             */
            request_id: string;
            /** Source Version */
            source_version: number;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** ReportEnrollmentStatus */
        ReportEnrollmentStatus: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Enrolled */
            enrolled: boolean;
        };
        /** RevokeRequest */
        RevokeRequest: {
            /** Reason */
            reason?: string | null;
        };
        /** RoleClone */
        RoleClone: {
            /** Key */
            key: string;
            /** Name */
            name?: string | null;
        };
        /**
         * RoleComposed
         * @description A role plus any separation-of-duties pairs the composition holds both halves of.
         *
         *     Returned (not rejected) for a tenant role: a small business may legitimately need
         *     one person to both raise and approve (docs/roles-permissions.md §1.4). The client
         *     surfaces the warning; the pairs are also recorded as an ``admin`` audit event.
         */
        RoleComposed: {
            role: components["schemas"]["RoleDetail"];
            /** Separation Of Duties Warnings */
            separation_of_duties_warnings: string[][];
        };
        /** RoleCreate */
        RoleCreate: {
            /** Description */
            description?: string | null;
            /** Key */
            key: string;
            /** Name */
            name: string;
            /** Permissions */
            permissions: string[];
            /** Scope Hint */
            scope_hint?: string | null;
        };
        /** RoleDetail */
        RoleDetail: {
            /** Cloned From Role Id */
            cloned_from_role_id: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Is System */
            is_system: boolean;
            /** Key */
            key: string;
            /** Name */
            name: string;
            /** Permissions */
            permissions: string[];
            /** Scope Hint */
            scope_hint: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** RoleListItem */
        RoleListItem: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Is System */
            is_system: boolean;
            /** Key */
            key: string;
            /** Name */
            name: string;
            /** Scope Hint */
            scope_hint: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** RolePage */
        RolePage: {
            /** Items */
            items: components["schemas"]["RoleListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** RoleSeedChange */
        RoleSeedChange: {
            /** Added */
            added: string[];
            /**
             * Deactivate
             * @default false
             */
            deactivate?: boolean;
            /** Key */
            key: string;
            /** Metadata Changed */
            metadata_changed: boolean;
            /** Removed */
            removed: string[];
        };
        /** RoleSeedCommand */
        RoleSeedCommand: {
            /** Expected Catalogue Digest */
            expected_catalogue_digest: string;
            /** Expected Current Digest */
            expected_current_digest: string;
            /** Reason */
            reason: string;
        };
        /** RoleSeedPlan */
        RoleSeedPlan: {
            /** Catalogue Digest */
            catalogue_digest: string;
            /** Changes */
            changes: components["schemas"]["RoleSeedChange"][];
            /** Current Digest */
            current_digest: string;
        };
        /** RoleSeedResult */
        RoleSeedResult: {
            /** Added Grants */
            added_grants: number;
            /** Catalogue Digest */
            catalogue_digest: string;
            /** Changed */
            changed: boolean;
            /** Current Digest */
            current_digest: string;
            /** Deactivated Roles */
            deactivated_roles: number;
            /** Inserted Roles */
            inserted_roles: number;
            /** Removed Grants */
            removed_grants: number;
            /** Updated Roles */
            updated_roles: number;
        };
        /** RoleUpdate */
        RoleUpdate: {
            /** Description */
            description?: string | null;
            /** Name */
            name?: string;
            /** Permissions */
            permissions?: string[];
            /** Scope Hint */
            scope_hint?: string | null;
        };
        /** SalespersonCreate */
        SalespersonCreate: {
            /** Code */
            code: string;
            /** Name */
            name: string;
            /** User Id */
            user_id?: string | null;
        };
        /** SalespersonItem */
        SalespersonItem: {
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
            /** Is Active */
            is_active: boolean;
            /** Name */
            name: string;
            /** Row Version */
            row_version: number;
            /** User Id */
            user_id: string | null;
        };
        /** SalespersonPage */
        SalespersonPage: {
            /** Items */
            items: components["schemas"]["SalespersonItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** SalespersonUpdate */
        SalespersonUpdate: {
            /** Expected Version */
            expected_version: number;
            /** Is Active */
            is_active?: boolean | null;
            /** Name */
            name?: string | null;
            /** User Id */
            user_id?: string | null;
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
        /** SessionCompany */
        SessionCompany: {
            /** Code */
            code?: string | null;
            /** Display Name */
            display_name?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Status */
            status?: string | null;
        };
        /**
         * SessionCompanyChoice
         * @description One switcher row from the actor's own authority — not a company read.
         *
         *     Deliberately four fields. This is the one company list an actor without
         *     ``company.read`` can see (docs/company-context-ui-todo.md D2), so it carries what it
         *     takes to *choose* a company and nothing that describes one: no legal name, no
         *     jurisdiction, no statutory identifier, no currency. Field-policy read denies still
         *     apply on top, which is why the two text fields are not required in the schema.
         */
        SessionCompanyChoice: {
            /** Code */
            code?: string;
            /** Display Name */
            display_name?: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Default */
            is_default: boolean;
            /** Requires Step Up */
            requires_step_up?: boolean;
        };
        /** SessionCompanyPage */
        SessionCompanyPage: {
            /** Items */
            items: components["schemas"]["SessionCompanyChoice"][];
            page: components["schemas"]["PageMeta"];
        };
        /** SessionDetail */
        SessionDetail: {
            company: components["schemas"]["SessionCompany"] | null;
            /** Grants */
            grants: components["schemas"]["SessionGrant"][];
            /** Permissions */
            permissions: string[];
            /** Selected Company Id */
            selected_company_id?: string | null;
            /**
             * Selected Source
             * @enum {string}
             */
            selected_source: "explicit" | "default" | "membership" | "first" | "none";
            /**
             * Step Up Required
             * @default false
             */
            step_up_required?: boolean;
            tenant: components["schemas"]["SessionTenant"];
            user: components["schemas"]["UserDetail"];
        };
        /** SessionGrant */
        SessionGrant: {
            /** Permissions */
            permissions: string[];
            /** Scope Id */
            scope_id: string | null;
            /** Scope Type */
            scope_type: string;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to: string | null;
        };
        /** SessionTenant */
        SessionTenant: {
            /** Default Country Code */
            default_country_code: string;
            /** Default State Code */
            default_state_code?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /** Status */
            status: string;
            /** Suspended Reason */
            suspended_reason?: string | null;
        };
        /** SetupAdministrator */
        SetupAdministrator: {
            /** Email */
            email: string;
        };
        /** SetupCheck */
        SetupCheck: {
            /** Message */
            message: string;
            /** Name */
            name: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ready" | "failed" | "optional";
        };
        /** SetupChecks */
        SetupChecks: {
            /** Checks */
            checks: components["schemas"]["SetupCheck"][];
            /** Countries */
            countries: components["schemas"]["SetupChoice"][];
            /** Currencies */
            currencies: components["schemas"]["SetupChoice"][];
            /** Languages */
            languages: components["schemas"]["SetupChoice"][];
            /** Ready */
            ready: boolean;
            /** Timezones */
            timezones: components["schemas"]["SetupChoice"][];
        };
        /** SetupChoice */
        SetupChoice: {
            /** Code */
            code: string;
            /** Name */
            name: string;
        };
        /** SetupFeature */
        SetupFeature: {
            /** Feature Key */
            feature_key: string;
            /** Lock Reason */
            lock_reason: string | null;
            /** Locked At */
            locked_at: string | null;
            /** Missing Prerequisites */
            missing_prerequisites: string[];
            /** Required Features */
            required_features: string[];
            /** Source Updated At */
            source_updated_at: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "ENABLED" | "DISABLED" | "INCONSISTENT";
            /** Tax System Supported */
            tax_system_supported: boolean;
        };
        /** SetupRequest */
        SetupRequest: {
            /** Administrator Name */
            administrator_name: string;
            /** Country Code */
            country_code: string;
            /** Currency Code */
            currency_code: string;
            /**
             * Locale
             * @default en
             */
            locale?: string;
            /** Platform Name */
            platform_name: string;
            /** Public Url */
            public_url: string;
            /** Timezone */
            timezone: string;
            /** Workspace Name */
            workspace_name: string;
            /** Workspace Slug */
            workspace_slug: string;
        };
        /** SetupResult */
        SetupResult: {
            /**
             * Administrator Id
             * Format: uuid
             */
            administrator_id: string;
            /**
             * Completed
             * @default true
             */
            completed?: boolean;
            /** Platform Name */
            platform_name: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
        };
        /** SetupStatus */
        SetupStatus: {
            /** Available */
            available: boolean;
            /** Completed */
            completed: boolean;
        };
        /** SetupStepView */
        SetupStepView: {
            /** Failure Code */
            failure_code: string | null;
            /** Key */
            key: string;
            /** Status */
            status: string;
        };
        /** SnapshotManifest */
        SnapshotManifest: {
            /**
             * Company Id
             * Format: uuid
             */
            company_id: string;
            /** Content Sha256 */
            content_sha256: string;
            /** Contract */
            contract: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /**
             * Generated At
             * Format: date-time
             */
            generated_at: string;
            /** Page Sha256 */
            page_sha256: string[];
            /** Record Count */
            record_count: number;
            /**
             * Snapshot Id
             * Format: uuid
             */
            snapshot_id: string;
            /** Source Version */
            source_version: number;
            /** Stream Counts */
            stream_counts: {
                [key: string]: number;
            };
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
        };
        /** SnapshotPage */
        SnapshotPage: {
            /** Page Number */
            page_number: number;
            /** Records */
            records: components["schemas"]["SnapshotRecord"][];
            /**
             * Snapshot Id
             * Format: uuid
             */
            snapshot_id: string;
        };
        /** SnapshotRecord */
        SnapshotRecord: {
            /** Data */
            data: {
                [key: string]: unknown;
            };
            /**
             * Deleted
             * @default false
             */
            deleted?: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Kind */
            kind: string;
        };
        /** StateData */
        StateData: {
            /** Code */
            code: string;
            /** Country Code */
            country_code: string;
            /**
             * Is Active
             * @default true
             */
            is_active?: boolean;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "state";
            /** Name */
            name: string;
            /** Subdivision Type */
            subdivision_type: string;
            /** Tax Jurisdiction Code */
            tax_jurisdiction_code?: string | null;
        };
        /** StatutoryIdCreate */
        StatutoryIdCreate: {
            /** Holder Name */
            holder_name?: string | null;
            /** Issued On */
            issued_on?: string | null;
            /** Kind */
            kind: string;
            /** Valid To */
            valid_to?: string | null;
            /** Value */
            value: string;
            /** Verification Reference */
            verification_reference?: string | null;
        };
        /** StatutoryIdItem */
        StatutoryIdItem: {
            /** Holder Name */
            holder_name: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Issued On */
            issued_on: string | null;
            /** Kind */
            kind: string;
            /** Valid To */
            valid_to: string | null;
            /** Value */
            value: string | null;
            /** Value Last4 */
            value_last4: string;
            /** Verification Reference */
            verification_reference: string | null;
        };
        /** SupportSession */
        SupportSession: {
            /**
             * Actor User Id
             * Format: uuid
             */
            actor_user_id: string;
            /** Ended At */
            ended_at: string | null;
            /** Ended Reason */
            ended_reason: string | null;
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
            /** Reason */
            reason: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /**
             * Target User Id
             * Format: uuid
             */
            target_user_id: string;
        };
        /** SupportStart */
        SupportStart: {
            /**
             * Minutes
             * @default 15
             */
            minutes?: number;
            /** Reason */
            reason: string;
            /**
             * Target User Id
             * Format: uuid
             */
            target_user_id: string;
            /** Ticket Reference */
            ticket_reference?: string | null;
        };
        /** TaxRegimeChoice */
        TaxRegimeChoice: {
            /** Label */
            label: string;
            /** Value */
            value: string;
        };
        /** TaxRegistrationChoice */
        TaxRegistrationChoice: {
            /** Jurisdiction Scope */
            jurisdiction_scope: string;
            /** Number Label */
            number_label: string;
            /** Regimes */
            regimes: components["schemas"]["TaxRegimeChoice"][];
            /** Tax System */
            tax_system: string;
        };
        /** TaxRegistrationCreate */
        TaxRegistrationCreate: {
            /**
             * Is Primary
             * @default false
             */
            is_primary?: boolean;
            /** Jurisdiction Code */
            jurisdiction_code: string;
            /** Legal Name On Registration */
            legal_name_on_registration?: string | null;
            /** Number */
            number: string;
            /** Regime */
            regime: string;
            /** Registered Address Id */
            registered_address_id?: string | null;
            /** Tax System */
            tax_system: string;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to?: string | null;
        };
        /** TaxRegistrationItem */
        TaxRegistrationItem: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Primary */
            is_primary: boolean;
            /** Jurisdiction Code */
            jurisdiction_code: string;
            /** Legal Name On Registration */
            legal_name_on_registration: string | null;
            /** Number */
            number: string;
            /** Regime */
            regime: string;
            /** Registered Address Id */
            registered_address_id: string | null;
            /** Registration Class */
            registration_class: string;
            /** Tax System */
            tax_system: string;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /** Valid To */
            valid_to: string | null;
        };
        /**
         * TaxRegistrationUpdate
         * @description An amendment. ``regime``, ``number``, ``jurisdiction_code`` and ``valid_from``
         *     are accepted only unchanged — echoing the row back is not an edit — and any real
         *     change is a 422 ``immutable_field`` for every actor (docs/company.md §4.2). A
         *     regime change is "set ``valid_to`` here, then add a new registration".
         */
        TaxRegistrationUpdate: {
            /** Is Primary */
            is_primary?: boolean;
            /** Jurisdiction Code */
            jurisdiction_code?: string;
            /** Legal Name On Registration */
            legal_name_on_registration?: string | null;
            /** Number */
            number?: string;
            /** Regime */
            regime?: string;
            /** Registered Address Id */
            registered_address_id?: string | null;
            /**
             * Valid From
             * Format: date
             */
            valid_from?: string;
            /** Valid To */
            valid_to?: string | null;
        };
        /** TenantChoice */
        TenantChoice: {
            /** Code */
            code: string;
            /** Name */
            name: string;
        };
        /** TenantChoices */
        TenantChoices: {
            /** Countries */
            countries: components["schemas"]["TenantChoice"][];
            /** Currencies */
            currencies: components["schemas"]["TenantChoice"][];
            /** Languages */
            languages: components["schemas"]["TenantChoice"][];
            /** States */
            states: components["schemas"]["identity__services__tenant_choices__StateChoice"][];
            /** Timezones */
            timezones: components["schemas"]["TenantChoice"][];
        };
        /** TenantDetail */
        TenantDetail: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Default Country Code */
            default_country_code: string;
            /** Default Currency Code */
            default_currency_code: string;
            /** Default Locale */
            default_locale: string;
            /** Default State Code */
            default_state_code: string | null;
            /** Default Timezone */
            default_timezone: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Plan Id */
            plan_id: string | null;
            /** Primary Contact Email */
            primary_contact_email: string;
            /** Slug */
            slug: string;
            /** Status */
            status: string;
            /** Trial Ends On */
            trial_ends_on: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** TenantStatus */
        TenantStatus: {
            /**
             * Expected Updated At
             * Format: date-time
             */
            expected_updated_at: string;
            /** Reason */
            reason: string;
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "suspended";
        };
        /** TenantUpdate */
        TenantUpdate: {
            /** Default Country Code */
            default_country_code?: string;
            /** Default Currency Code */
            default_currency_code?: string;
            /** Default Locale */
            default_locale?: string;
            /** Default State Code */
            default_state_code?: string | null;
            /** Default Timezone */
            default_timezone?: string;
            /** Name */
            name?: string;
            /** Primary Contact Email */
            primary_contact_email?: string;
        };
        /**
         * TimezoneChoice
         * @description Installation-maintained IANA identifiers; offsets depend on the instant.
         */
        TimezoneChoice: {
            /** Code */
            code: string;
            /** Is Active */
            is_active: boolean;
            /** Name */
            name: string;
        };
        /** ToggleRequest */
        ToggleRequest: {
            /** Is Active */
            is_active: boolean;
            /** Reason */
            reason: string;
        };
        /** TokenCreate */
        TokenCreate: {
            /** Company Id */
            company_id?: string | null;
            /**
             * Expires In Days
             * @default 30
             */
            expires_in_days?: number;
            /** Name */
            name: string;
            /** Permissions */
            permissions: string[];
        };
        /** TokenIssued */
        TokenIssued: {
            details: components["schemas"]["TokenItem"];
            /** Token */
            token: string;
        };
        /** TokenItem */
        TokenItem: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Expires At */
            expires_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Used At */
            last_used_at: string | null;
            /** Name */
            name: string;
            /** Revoked At */
            revoked_at: string | null;
            /** Token Prefix */
            token_prefix: string;
        };
        /** UserDetail */
        UserDetail: {
            /** Activated At */
            activated_at: string | null;
            /** Anonymized At */
            anonymized_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency Display */
            currency_display: string | null;
            /** Date Format */
            date_format: string | null;
            /** Date Of Exit */
            date_of_exit: string | null;
            /** Date Of Joining */
            date_of_joining: string | null;
            /** Datetime Format */
            datetime_format: string | null;
            /** Deactivated At */
            deactivated_at: string | null;
            /** Default Company Id */
            default_company_id: string | null;
            /** Default Department Id */
            default_department_id: string | null;
            /** Digit Grouping */
            digit_grouping: string | null;
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /** Email Verified At */
            email_verified_at: string | null;
            /** Employee Code */
            employee_code: string | null;
            /** First Name */
            first_name: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Invited At */
            invited_at: string | null;
            /** Job Title */
            job_title: string | null;
            /** Landing Page */
            landing_page: string | null;
            /** Last Name */
            last_name: string | null;
            /** Locale */
            locale: string | null;
            /** Middle Name */
            middle_name: string | null;
            /** Phone */
            phone: string | null;
            /** Phone Country Code */
            phone_country_code: string | null;
            /** Phone Verified At */
            phone_verified_at: string | null;
            /** Reporting Manager Id */
            reporting_manager_id: string | null;
            /** Salutation */
            salutation: string | null;
            /** Status */
            status: string;
            /** Theme */
            theme: string | null;
            /** Timezone */
            timezone: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** User Type */
            user_type: string;
        };
        /** UserGroupCreate */
        UserGroupCreate: {
            /** Code */
            code: string;
            /** Description */
            description?: string | null;
            /** Name */
            name: string;
        };
        /** UserGroupItem */
        UserGroupItem: {
            /** Code */
            code: string;
            /** Description */
            description: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Name */
            name: string;
        };
        /** UserGroupListItem */
        UserGroupListItem: {
            /** Code */
            code: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Is Active */
            is_active: boolean;
            /** Name */
            name: string;
        };
        /** UserIdentityCreate */
        UserIdentityCreate: {
            /** Provider */
            provider: string;
            /** Provider Sub */
            provider_sub: string;
        };
        /** UserIdentityItem */
        UserIdentityItem: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Login At */
            last_login_at: string | null;
            /**
             * Linked At
             * Format: date-time
             */
            linked_at: string;
            /** Provider */
            provider: string;
            /** Provider Sub */
            provider_sub: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** UserInvite */
        UserInvite: {
            /** Date Of Joining */
            date_of_joining?: string | null;
            /** Default Company Id */
            default_company_id?: string | null;
            /** Display Name */
            display_name?: string | null;
            /** Email */
            email: string;
            /** Employee Code */
            employee_code?: string | null;
            /** First Name */
            first_name: string;
            /** Job Title */
            job_title?: string | null;
            /** Last Name */
            last_name?: string | null;
            /** Middle Name */
            middle_name?: string | null;
            /** Phone */
            phone?: string | null;
            /** Phone Country Code */
            phone_country_code?: string | null;
            /** Reporting Manager Id */
            reporting_manager_id?: string | null;
            /** Salutation */
            salutation?: string | null;
            /**
             * User Type
             * @default tenant_user
             */
            user_type?: string;
        };
        /** UserLifecycle */
        UserLifecycle: {
            /** Reason */
            reason: string;
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "suspended";
        };
        /** UserListItem */
        UserListItem: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Job Title */
            job_title: string | null;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** User Type */
            user_type: string;
        };
        /** UserPage */
        UserPage: {
            /** Items */
            items: components["schemas"]["UserListItem"][];
            page: components["schemas"]["PageMeta"];
        };
        /** UserUpdate */
        UserUpdate: {
            /** Currency Display */
            currency_display?: string | null;
            /** Date Format */
            date_format?: string | null;
            /** Date Of Exit */
            date_of_exit?: string | null;
            /** Date Of Joining */
            date_of_joining?: string | null;
            /** Datetime Format */
            datetime_format?: string | null;
            /** Default Company Id */
            default_company_id?: string | null;
            /** Default Department Id */
            default_department_id?: string | null;
            /** Digit Grouping */
            digit_grouping?: string | null;
            /** Display Name */
            display_name?: string;
            /** Employee Code */
            employee_code?: string | null;
            /** First Name */
            first_name?: string;
            /** Job Title */
            job_title?: string | null;
            /** Landing Page */
            landing_page?: string | null;
            /** Last Name */
            last_name?: string | null;
            /** Locale */
            locale?: string | null;
            /** Middle Name */
            middle_name?: string | null;
            /** Phone */
            phone?: string | null;
            /** Phone Country Code */
            phone_country_code?: string | null;
            /** Reporting Manager Id */
            reporting_manager_id?: string | null;
            /** Salutation */
            salutation?: string | null;
            /** Theme */
            theme?: string | null;
            /** Timezone */
            timezone?: string | null;
        };
        /** ValidationRules */
        "ValidationRules-Input": {
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
        /** ValidationRules */
        "ValidationRules-Output": {
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
            max?: string | null;
            /**
             * Max Length
             * @default 4096
             */
            max_length?: number;
            /** Min */
            min?: string | null;
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
        /** WorkspaceCreate */
        WorkspaceCreate: {
            /** Administrator Name */
            administrator_name: string;
            /** Country Code */
            country_code: string;
            /** Currency Code */
            currency_code?: string | null;
            /** Locale */
            locale?: string | null;
            /** Name */
            name: string;
            /** State Code */
            state_code?: string | null;
            /** Timezone */
            timezone?: string | null;
        };
        /** EnrollmentPage */
        identity__schemas__catalog_enrollment__EnrollmentPage: {
            /** Next Cursor */
            next_cursor?: string | null;
            /** Scopes */
            scopes: components["schemas"]["CompanyServiceScope"][];
        };
        /** StateChoice */
        identity__schemas__reference__StateChoice: {
            /** Code */
            code: string;
            /** Country Code */
            country_code: string;
            /** Name */
            name: string;
        };
        /** StateChoice */
        identity__services__tenant_choices__StateChoice: {
            /** Code */
            code: string;
            /** Country Code */
            country_code: string;
            /** Name */
            name: string;
        };
        /** EnrollmentPage */
        reporting_contract__enrollment__EnrollmentPage: {
            /** Next Cursor */
            next_cursor?: string | null;
            /** Scopes */
            scopes: components["schemas"]["CompanyServiceScope"][];
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
    list_catalog_enrollments: {
        parameters: {
            query?: never;
            header: {
                /** @description Scoped Catalog-to-Identity service key identifier. */
                "x-source-key-id": string;
                /** @description Unix timestamp covered by the service signature. */
                "x-source-issued-at": string;
                /** @description HMAC of the method/path/query/body-hash request frame. */
                "x-source-signature": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** Cursor */
                    cursor?: string | null;
                    /**
                     * Limit
                     * @default 100
                     */
                    limit?: number;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["identity__schemas__catalog_enrollment__EnrollmentPage"];
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
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorEnvelope"];
                };
            };
        };
    };
    changes_internal_v1_reference_changes__service__get: {
        parameters: {
            query?: {
                cursor?: string | null;
            };
            header?: never;
            path: {
                service: string;
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
        };
    };
    acknowledge_internal_v1_reference_changes__service__ack_post: {
        parameters: {
            query: {
                cursor: string;
            };
            header?: never;
            path: {
                service: string;
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
        };
    };
    report_authority_internal_v1_report_authority__tenant_id___company_id__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** Permissions */
                    permissions: string[];
                    /**
                     * Request Id
                     * Format: uuid
                     */
                    request_id: string;
                    /**
                     * User Id
                     * Format: uuid
                     */
                    user_id: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportAuthority"];
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
            /** @description Unprocessable Entity */
            422: {
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
    enrollments_internal_v1_report_enrollments_post: {
        parameters: {
            query?: never;
            header?: never;
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
                    "application/json": components["schemas"]["reporting_contract__enrollment__EnrollmentPage"];
                };
            };
        };
    };
    authorize_catalog_job_actor: {
        parameters: {
            query?: never;
            header: {
                /** @description Scoped Catalog-to-Identity service key identifier. */
                "x-source-key-id": string;
                /** @description Unix timestamp covered by the service signature. */
                "x-source-issued-at": string;
                /** @description HMAC of the method/path/query/body-hash request frame. */
                "x-source-signature": string;
            };
            path: {
                tenant_id: string;
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** Permissions */
                    permissions: string[];
                    /**
                     * Request Id
                     * Format: uuid
                     */
                    request_id: string;
                    /**
                     * User Id
                     * Format: uuid
                     */
                    user_id: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActorAuthorizationProof"];
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
            /** @description Unprocessable Entity */
            422: {
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
    create_catalog_source_snapshot: {
        parameters: {
            query?: never;
            header: {
                /** @description Scoped Catalog-to-Identity service key identifier. */
                "x-source-key-id": string;
                /** @description Unix timestamp covered by the service signature. */
                "x-source-issued-at": string;
                /** @description HMAC of the method/path/query/body-hash request frame. */
                "x-source-signature": string;
            };
            path: {
                tenant_id: string;
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /**
                     * Request Id
                     * Format: uuid
                     */
                    request_id: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotManifest"];
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
        };
    };
    get_catalog_source_snapshot: {
        parameters: {
            query?: never;
            header: {
                /** @description Scoped Catalog-to-Identity service key identifier. */
                "x-source-key-id": string;
                /** @description Unix timestamp covered by the service signature. */
                "x-source-issued-at": string;
                /** @description HMAC of the method/path/query/body-hash request frame. */
                "x-source-signature": string;
            };
            path: {
                snapshot_id: string;
                tenant_id: string;
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
                    "application/json": components["schemas"]["SnapshotManifest"];
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
        };
    };
    get_catalog_source_snapshot_page: {
        parameters: {
            query?: never;
            header: {
                /** @description Scoped Catalog-to-Identity service key identifier. */
                "x-source-key-id": string;
                /** @description Unix timestamp covered by the service signature. */
                "x-source-issued-at": string;
                /** @description HMAC of the method/path/query/body-hash request frame. */
                "x-source-signature": string;
            };
            path: {
                snapshot_id: string;
                page_number: number;
                tenant_id: string;
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
                    "application/json": components["schemas"]["SnapshotPage"];
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
        };
    };
    configuration_internal_v1_tenants__tenant_id__companies__company_id__posting_configuration_get: {
        parameters: {
            query?: never;
            header: {
                "x-source-key-id": string;
                "x-source-issued-at": string;
                "x-source-signature": string;
            };
            path: {
                tenant_id: string;
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
                    "application/json": components["schemas"]["PostingConfiguration"];
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
        };
    };
    reserve_internal_v1_tenants__tenant_id__companies__company_id__posting_reservations_post: {
        parameters: {
            query?: never;
            header: {
                "x-source-key-id": string;
                "x-source-issued-at": string;
                "x-source-signature": string;
            };
            path: {
                tenant_id: string;
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /**
                     * Actor User Id
                     * Format: uuid
                     */
                    actor_user_id: string;
                    /** Configuration Hash */
                    configuration_hash: string;
                    /** Features */
                    features?: string[];
                    /**
                     * Operation Id
                     * Format: uuid
                     */
                    operation_id: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostingReceipt"];
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
        };
    };
    terminal_internal_v1_tenants__tenant_id__companies__company_id__posting_reservations__operation_id___outcome__post: {
        parameters: {
            query?: never;
            header: {
                "x-source-key-id": string;
                "x-source-issued-at": string;
                "x-source-signature": string;
            };
            path: {
                tenant_id: string;
                company_id: string;
                operation_id: string;
                outcome: "confirmed" | "aborted";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    intent?: {
                        /**
                         * Actor User Id
                         * Format: uuid
                         */
                        actor_user_id: string;
                        /** Configuration Hash */
                        configuration_hash: string;
                        /** Features */
                        features?: string[];
                        /**
                         * Operation Id
                         * Format: uuid
                         */
                        operation_id: string;
                    } | null;
                    /** Posted At */
                    posted_at?: string | null;
                    /** Terminal Reference */
                    terminal_reference: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostingReceipt"];
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
        };
    };
    reserve_internal_v1_tenants__tenant_id__companies__company_id__stock_posting_reservations_post: {
        parameters: {
            query?: never;
            header: {
                "x-source-key-id": string;
                "x-source-issued-at": string;
                "x-source-signature": string;
            };
            path: {
                tenant_id: string;
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /**
                     * Actor User Id
                     * Format: uuid
                     */
                    actor_user_id: string;
                    /** StockAuthority */
                    authority: {
                        /** Actor Context */
                        actor_context: string;
                        /** Actor Signature */
                        actor_signature: string;
                        /** Company Context */
                        company_context: string;
                        /** Company Signature */
                        company_signature: string;
                    };
                    /** Configuration Hash */
                    configuration_hash: string;
                    /** Features */
                    features: string[];
                    /**
                     * Operation Id
                     * Format: uuid
                     */
                    operation_id: string;
                    /** StockReservationSource */
                    source: {
                        /**
                         * Action
                         * @enum {string}
                         */
                        action: "POST" | "REVERSE";
                        /** Command Hash */
                        command_hash: string;
                        /**
                         * Execution Id
                         * Format: uuid
                         */
                        execution_id: string;
                    };
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostingReceipt"];
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
        };
    };
    terminal_internal_v1_tenants__tenant_id__companies__company_id__stock_posting_reservations__operation_id___outcome__post: {
        parameters: {
            query?: never;
            header: {
                "x-source-key-id": string;
                "x-source-issued-at": string;
                "x-source-signature": string;
            };
            path: {
                tenant_id: string;
                company_id: string;
                operation_id: string;
                outcome: "confirmed" | "aborted";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    intent?: {
                        /**
                         * Actor User Id
                         * Format: uuid
                         */
                        actor_user_id: string;
                        /** StockAuthority */
                        authority: {
                            /** Actor Context */
                            actor_context: string;
                            /** Actor Signature */
                            actor_signature: string;
                            /** Company Context */
                            company_context: string;
                            /** Company Signature */
                            company_signature: string;
                        };
                        /** Configuration Hash */
                        configuration_hash: string;
                        /** Features */
                        features: string[];
                        /**
                         * Operation Id
                         * Format: uuid
                         */
                        operation_id: string;
                        /** StockReservationSource */
                        source: {
                            /**
                             * Action
                             * @enum {string}
                             */
                            action: "POST" | "REVERSE";
                            /** Command Hash */
                            command_hash: string;
                            /**
                             * Execution Id
                             * Format: uuid
                             */
                            execution_id: string;
                        };
                    } | null;
                    /** Posted At */
                    posted_at?: string | null;
                    /** Terminal Reference */
                    terminal_reference: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostingReceipt"];
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
        };
    };
    enrollments_internal_v1_voucher_enrollments_post: {
        parameters: {
            query?: never;
            header?: never;
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
                    "application/json": components["schemas"]["identity__schemas__catalog_enrollment__EnrollmentPage"];
                };
            };
        };
    };
    revoke_token_v1_api_tokens__token_id__revoke_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                token_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReasonRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokenItem"];
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
        };
    };
    list_companies_v1_companies_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                status?: "active" | "closed" | "suspended";
                include_unlisted?: boolean;
                q?: string | null;
                sort?: string;
                custom_field?: string | null;
                custom_value?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["CompanyPage"];
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
        };
    };
    create_company_v1_companies_post: {
        parameters: {
            query?: never;
            header?: {
                "Idempotency-Key"?: string | null;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CompanyCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyDetail"];
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
        };
    };
    get_company_v1_companies__company_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["CompanyDetail"];
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
        };
    };
    update_company_v1_companies__company_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CompanyUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyDetail"];
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
        };
    };
    list_addresses_v1_companies__company_id__addresses_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_AddressItem_"];
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
        };
    };
    add_address_v1_companies__company_id__addresses_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AddressCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AddressItem"];
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
        };
    };
    banks_v1_companies__company_id__bank_accounts_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_BankItem_"];
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
        };
    };
    create_bank_v1_companies__company_id__bank_accounts_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BankWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BankItem"];
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
        };
    };
    get_bank_v1_companies__company_id__bank_accounts__bank_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                bank_id: string;
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
                    "application/json": components["schemas"]["BankItem"];
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
        };
    };
    update_bank_v1_companies__company_id__bank_accounts__bank_id__put: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                bank_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BankWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BankItem"];
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
        };
    };
    bank_lifecycle_v1_companies__company_id__bank_accounts__bank_id__lifecycle_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                bank_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ToggleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BankItem"];
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
        };
    };
    reveal_bank_v1_companies__company_id__bank_accounts__bank_id__reveal_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                bank_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReasonRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BankReveal"];
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
        };
    };
    rotate_encryption_v1_companies__company_id__bank_encryption_rotate_post: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                        [key: string]: number;
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
        };
    };
    contacts_v1_companies__company_id__contacts_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_ContactItem_"];
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
        };
    };
    create_contact_v1_companies__company_id__contacts_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ContactCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContactItem"];
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
        };
    };
    get_contact_v1_companies__company_id__contacts__contact_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                contact_id: string;
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
                    "application/json": components["schemas"]["ContactItem"];
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
        };
    };
    update_contact_v1_companies__company_id__contacts__contact_id__put: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                contact_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ContactUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContactItem"];
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
        };
    };
    contact_lifecycle_v1_companies__company_id__contacts__contact_id__lifecycle_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                contact_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ToggleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ContactItem"];
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
        };
    };
    list_departments_v1_companies__company_id__departments_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                sort?: string;
                q?: string | null;
                id?: string | null;
                is_active?: boolean | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["DepartmentPage"];
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
        };
    };
    create_department_v1_companies__company_id__departments_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DepartmentCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DepartmentItem"];
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
        };
    };
    department_fields_v1_companies__company_id__departments_field_set_get: {
        parameters: {
            query?: {
                operation?: "create" | "update";
                id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["FieldSet"];
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
        };
    };
    get_department_v1_companies__company_id__departments__department_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                department_id: string;
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
                    "application/json": components["schemas"]["DepartmentItem"];
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
        };
    };
    update_department_v1_companies__company_id__departments__department_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                department_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DepartmentUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DepartmentItem"];
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
        };
    };
    department_lifecycle_v1_companies__company_id__departments__department_id__lifecycle_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                department_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ToggleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DepartmentItem"];
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
        };
    };
    reparent_department_v1_companies__company_id__departments__department_id__reparent_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                department_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DepartmentReparent"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DepartmentItem"];
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
        };
    };
    get_display_config_v1_companies__company_id__display_config_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["DisplayConfig"];
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
        };
    };
    documents_v1_companies__company_id__documents_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_DocumentItem_"];
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
        };
    };
    reconcile_v1_companies__company_id__documents_reconcile_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["ReconcileResult"];
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
        };
    };
    download_v1_companies__company_id__documents__document_id__download_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                document_id: string;
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
                    "application/json": components["schemas"]["DocumentLink"];
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
        };
    };
    finalize_v1_companies__company_id__documents__document_id__finalize_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                document_id: string;
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
                    "application/json": components["schemas"]["DocumentItem"];
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
        };
    };
    lifecycle_v1_companies__company_id__documents__document_id__lifecycle_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ToggleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentItem"];
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
        };
    };
    upload_v1_companies__company_id__documents__document_id__upload_put: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DocumentWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentLink"];
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
        };
    };
    list_features_v1_companies__company_id__features_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["FeatureList"];
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
        };
    };
    disable_feature_v1_companies__company_id__features__feature_key__disable_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                feature_key: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["FeatureActionRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureView"];
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
        };
    };
    enable_feature_v1_companies__company_id__features__feature_key__enable_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                feature_key: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["FeatureActionRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FeatureView"];
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
        };
    };
    read_v1_companies__company_id__gst_filing_preferences_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_GstFilingItem_"];
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
        };
    };
    create_v1_companies__company_id__gst_filing_preferences_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GstFilingCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GstFilingItem"];
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
        };
    };
    close_v1_companies__company_id__gst_filing_preferences__object_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GstFilingClose"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GstFilingItem"];
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
        };
    };
    setup_v1_companies__company_id__gst_outward_profile_setup_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["GstOutwardProfileSetup"];
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
        };
    };
    read_v1_companies__company_id__gst_outward_profiles_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_GstOutwardProfileItem_"];
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
        };
    };
    create_v1_companies__company_id__gst_outward_profiles_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GstOutwardProfileCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GstOutwardProfileItem"];
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
        };
    };
    close_v1_companies__company_id__gst_outward_profiles__object_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                object_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GstOutwardProfileClose"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GstOutwardProfileItem"];
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
        };
    };
    registration_setup_v1_companies__company_id__gst_registration_setup_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["GstRegistrationSetup"];
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
        };
    };
    list_licences_v1_companies__company_id__licences_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_LicenceItem_"];
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
        };
    };
    add_licence_v1_companies__company_id__licences_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LicenceCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LicenceItem"];
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
        };
    };
    company_lifecycle_v1_companies__company_id__lifecycle_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CompanyLifecycle"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyState"];
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
        };
    };
    list_memberships_v1_companies__company_id__memberships_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                user_id?: string | null;
                department_id?: string | null;
                is_active?: boolean | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_MembershipItem_"];
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
        };
    };
    create_membership_v1_companies__company_id__memberships_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MembershipCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MembershipItem"];
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
        };
    };
    list_salespeople_v1_companies__company_id__salespeople_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["SalespersonPage"];
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
        };
    };
    create_salesperson_v1_companies__company_id__salespeople_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SalespersonCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SalespersonItem"];
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
        };
    };
    get_salesperson_v1_companies__company_id__salespeople__salesperson_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                salesperson_id: string;
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
                    "application/json": components["schemas"]["SalespersonItem"];
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
        };
    };
    update_salesperson_v1_companies__company_id__salespeople__salesperson_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                salesperson_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SalespersonUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SalespersonItem"];
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
        };
    };
    read_v1_companies__company_id__setup_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["CompanySetupStatus"];
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
        };
    };
    setup_readiness_v1_companies__company_id__setup_readiness_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["CompanySetupReadiness"];
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
        };
    };
    enroll_existing_reports_v1_companies__company_id__setup_enroll_reports_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["ReportEnrollmentStatus"];
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
        };
    };
    retry_v1_companies__company_id__setup_retry_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["CompanySetupStatus"];
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
        };
    };
    list_statutory_ids_v1_companies__company_id__statutory_ids_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_StatutoryIdItem_"];
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
        };
    };
    add_statutory_id_v1_companies__company_id__statutory_ids_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["StatutoryIdCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StatutoryIdItem"];
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
        };
    };
    challenge_v1_companies__company_id__step_up_challenge_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Challenge"];
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
        };
    };
    complete_v1_companies__company_id__step_up_complete_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Complete"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Proof"];
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
        };
    };
    list_tax_registrations_v1_companies__company_id__tax_registrations_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                q?: string | null;
                id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_TaxRegistrationItem_"];
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
        };
    };
    add_tax_registration_v1_companies__company_id__tax_registrations_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaxRegistrationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaxRegistrationItem"];
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
        };
    };
    amend_tax_registration_v1_companies__company_id__tax_registrations__registration_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                registration_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaxRegistrationUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaxRegistrationItem"];
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
        };
    };
    list_currencies_v1_companies__company_id__transaction_currencies_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["CompanyCurrenciesView"];
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
        };
    };
    set_currency_v1_companies__company_id__transaction_currencies__currency_code__put: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                currency_code: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CurrencyAllowanceWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurrencyAllowanceView"];
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
        };
    };
    list_company_users_v1_companies__company_id__users_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                q?: string | null;
                status?: "active" | "deactivated" | "invited" | "suspended";
                sort?: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["UserPage"];
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
        };
    };
    invite_company_user_v1_companies__company_id__users_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CompanyUserInvite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserListItem"];
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
        };
    };
    get_company_user_v1_companies__company_id__users__user_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
                user_id: string;
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
                    "application/json": components["schemas"]["UserListItem"];
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
        };
    };
    set_visibility_v1_companies__company_id__visibility_post: {
        parameters: {
            query: {
                visibility: string;
                requires_step_up?: boolean | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                company_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["FeatureActionRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CompanyDetail"];
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
        };
    };
    list_company_classifications_v1_company_classifications_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["CompanyClassifications"];
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
        };
    };
    list_feature_catalogue_v1_company_features_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["FeatureCatalogue"];
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
        };
    };
    creation_receipt_v1_company_setup_commands__key__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                key: string;
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
                    "application/json": components["schemas"]["CreationReceipt"];
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
        };
    };
    list_definitions_v1_custom_field_definitions_get: {
        parameters: {
            query?: {
                entity_type?: string;
                company_id?: string | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_DefinitionListItem_"];
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
        };
    };
    create_definition_v1_custom_field_definitions_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DefinitionWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DefinitionItem"];
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
        };
    };
    get_definition_v1_custom_field_definitions__definition_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                definition_id: string;
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
                    "application/json": components["schemas"]["DefinitionItem"];
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
        };
    };
    update_definition_v1_custom_field_definitions__definition_id__put: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                definition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DefinitionWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DefinitionItem"];
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
        };
    };
    rebuild_definition_v1_custom_field_definitions__definition_id__rebuild_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                definition_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RebuildRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RebuildResult"];
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
        };
    };
    product_field_contract_v1_entities__entity_type__custom_field_contract_get: {
        parameters: {
            query?: {
                company_id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                entity_type: string;
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
        };
    };
    layouts_v1_entities__entity_type__field_config_get: {
        parameters: {
            query?: {
                company_id?: string | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                entity_type: string;
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
                    "application/json": components["schemas"]["Page_LayoutItem_"];
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
        };
    };
    configure_field_v1_entities__entity_type__field_config__field_key__put: {
        parameters: {
            query?: {
                company_id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                entity_type: string;
                field_key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LayoutWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LayoutItem"];
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
        };
    };
    get_field_set_v1_entities__entity_type__field_set_get: {
        parameters: {
            query?: {
                company_id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                entity_type: string;
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
                    "application/json": components["schemas"]["FieldSet"];
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
        };
    };
    policies_v1_field_policies_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                entity_type?: string;
                company_id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_PolicyItem_"];
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
        };
    };
    create_policy_v1_field_policies_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PolicyWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PolicyItem"];
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
        };
    };
    update_policy_v1_field_policies__policy_id__put: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                policy_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PolicyWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PolicyItem"];
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
        };
    };
    cancel_invitation_v1_invitations__invitation_id__cancel_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                invitation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReasonRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InvitationItem"];
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
        };
    };
    end_membership_v1_memberships__membership_id__end_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                membership_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MembershipEnd"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MembershipItem"];
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
        };
    };
    make_primary_v1_memberships__membership_id__make_primary_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                membership_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReasonRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MembershipItem"];
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
        };
    };
    status_v1_onboarding_status_get: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string | null;
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
                    "application/json": components["schemas"]["OnboardingStatus"];
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
        };
    };
    create_workspace_v1_onboarding_tenant_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkspaceCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantDetail"];
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
        };
    };
    list_permissions_v1_permissions_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["PermissionCatalogue"];
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
        };
    };
    role_v1_platform_access_role_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["PlatformAdministratorRole"];
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
        };
    };
    tenants_v1_platform_access_tenants_get: {
        parameters: {
            query?: {
                q?: string | null;
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_AdministratorTenant_"];
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
        };
    };
    tenant_v1_platform_access_tenants__tenant_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
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
                    "application/json": components["schemas"]["AdministratorTenant"];
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
        };
    };
    administrators_v1_platform_access_tenants__tenant_id__administrators_get: {
        parameters: {
            query?: {
                q?: string | null;
                status?: ("active" | "invited" | "suspended" | "deactivated") | null;
                sort?: string;
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
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
                    "application/json": components["schemas"]["Page_AdministratorListItem_"];
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
        };
    };
    invite_v1_platform_access_tenants__tenant_id__administrators_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AdministratorInvite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdministratorReceipt"];
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
        };
    };
    administrator_v1_platform_access_tenants__tenant_id__administrators__user_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
                user_id: string;
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
                    "application/json": components["schemas"]["PlatformAdministrator"];
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
        };
    };
    change_v1_platform_access_tenants__tenant_id__administrators__user_id__commands_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AdministratorCommand"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdministratorReceipt"];
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
        };
    };
    password_recovery_v1_platform_access_tenants__tenant_id__administrators__user_id__password_recovery_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AdministratorRecoveryRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdministratorRecoveryLink"];
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
        };
    };
    accounts_v1_platform_accounts_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                q?: string | null;
                status?: ("pending" | "approved" | "rejected") | null;
                sort?: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_AccountReviewItem_"];
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
    account_options_v1_platform_accounts_options_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["TenantChoices"];
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
    pending_registration_v1_platform_accounts_pending_registration_get: {
        parameters: {
            query: {
                email: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["PendingRegistrationResult"];
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
    sync_accounts_v1_platform_accounts_sync_post: {
        parameters: {
            query?: {
                page?: number;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["AccountSyncResult"];
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
    account_v1_platform_accounts__account_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                account_id: string;
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
                    "application/json": components["schemas"]["AccountReviewDetail"];
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
    reconcile_account_v1_platform_accounts__account_id__reconcile_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                account_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AccountReconciliation"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AccountReviewDetail"];
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
    review_v1_platform_accounts__account_id__review_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                account_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AccountDecision"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AccountReviewDetail"];
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
    platform_details_v1_platform_details_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["PlatformDetails"];
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
        };
    };
    update_platform_details_v1_platform_details_patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlatformDetails"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlatformDetails"];
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
        };
    };
    list_prices_v1_platform_pricing_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                category?: ("platform" | "whatsapp" | "sms" | "email" | "llm" | "document") | null;
                status?: "active" | "inactive" | "deleted" | "all";
                q?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_PlatformPriceItem_"];
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
        };
    };
    create_price_v1_platform_pricing_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlatformPriceInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlatformPriceDetail"];
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
        };
    };
    get_price_v1_platform_pricing__price_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                price_id: string;
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
                    "application/json": components["schemas"]["PlatformPriceDetail"];
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
        };
    };
    update_price_v1_platform_pricing__price_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                price_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlatformPriceUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlatformPriceDetail"];
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
        };
    };
    revisions_v1_platform_pricing__price_id__revisions_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                price_id: string;
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
                    "application/json": components["schemas"]["Page_PlatformPriceRevisionItem_"];
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
        };
    };
    lifecycle_v1_platform_pricing__price_id___action__post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                price_id: string;
                action: "delete" | "restore";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlatformPriceLifecycle"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlatformPriceDetail"];
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
        };
    };
    options_v1_platform_references_options_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["ReferenceOptions"];
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
        };
    };
    timezone_listing_v1_platform_references_timezones_get: {
        parameters: {
            query?: {
                q?: string | null;
                status?: ("active" | "archived") | null;
                sort?: string;
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_TimezoneChoice_"];
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
        };
    };
    listing_v1_platform_references__kind__get: {
        parameters: {
            query?: {
                q?: string | null;
                status?: ("active" | "archived") | null;
                country_code?: string | null;
                sort?: string;
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                kind: "countries" | "states" | "languages" | "currencies";
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
                    "application/json": components["schemas"]["Page_ReferenceItem_"];
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
        };
    };
    create_v1_platform_references__kind__post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                kind: "countries" | "states" | "languages" | "currencies";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CountryData"] | components["schemas"]["StateData"] | components["schemas"]["CurrencyData"] | components["schemas"]["LanguageData"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReferenceDetail"];
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
        };
    };
    get_v1_platform_references__kind___code__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                kind: "countries" | "states" | "languages" | "currencies";
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
                    "application/json": components["schemas"]["ReferenceDetail"];
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
        };
    };
    edit_v1_platform_references__kind___code__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                kind: "countries" | "states" | "languages" | "currencies";
                code: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReferenceUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReferenceDetail"];
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
        };
    };
    lifecycle_v1_platform_references__kind___code___action__post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                kind: "countries" | "states" | "languages" | "currencies";
                code: string;
                action: "archive" | "restore";
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReferenceLifecycle"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReferenceDetail"];
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
        };
    };
    preview_v1_platform_system_roles_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["RoleSeedPlan"];
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
        };
    };
    reconcile_v1_platform_system_roles_reconcile_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleSeedCommand"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleSeedResult"];
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
        };
    };
    available_administrator_v1_platform_tenant_administrators_available_get: {
        parameters: {
            query: {
                email: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["AdministratorAvailability"];
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
        };
    };
    tenant_options_v1_platform_tenant_options_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["TenantChoices"];
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
        };
    };
    tenants_v1_platform_tenants_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                q?: string | null;
                status?: ("active" | "suspended" | "closed") | null;
                sort?: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_PlatformTenantItem_"];
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
        };
    };
    provision_v1_platform_tenants_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlatformTenantProvision"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlatformTenantCreated"];
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
        };
    };
    tenant_detail_v1_platform_tenants__tenant_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
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
                    "application/json": components["schemas"]["PlatformTenantDetail"];
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
        };
    };
    update_platform_tenant_v1_platform_tenants__tenant_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlatformTenantDetail"];
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
        };
    };
    administrator_invitation_v1_platform_tenants__tenant_id__administrator_invitation_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
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
                    "application/json": components["schemas"]["PlatformInvitation"];
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
        };
    };
    start_v1_platform_tenants__tenant_id__impersonation_sessions_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SupportStart"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupportSession"];
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
        };
    };
    end_v1_platform_tenants__tenant_id__impersonation_sessions__session_id__end_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
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
                    "application/json": components["schemas"]["SupportSession"];
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
        };
    };
    tenant_lifecycle_v1_platform_tenants__tenant_id__lifecycle_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantStatus"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlatformTenantItem"];
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
        };
    };
    countries_v1_reference_countries_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["CountryChoice"][];
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
        };
    };
    licence_types_v1_reference_countries__country_code__licence_types_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                country_code: string;
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
                    "application/json": components["schemas"]["LicenceTypeChoice"][];
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
        };
    };
    states_v1_reference_countries__country_code__states_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                country_code: string;
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
                    "application/json": components["schemas"]["identity__schemas__reference__StateChoice"][];
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
        };
    };
    currencies_v1_reference_currencies_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["CurrencyChoice"][];
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
        };
    };
    timezones_v1_reference_timezones_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["TimezoneChoice"][];
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
        };
    };
    invitation_v1_registration_invitation_get: {
        parameters: {
            query: {
                tenant: string;
                invitation: string;
                email: string;
            };
            header?: never;
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
                    "application/json": components["schemas"]["InvitationAvailability"];
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
        };
    };
    options_v1_registration_options_get: {
        parameters: {
            query?: never;
            header?: never;
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
                    "application/json": components["schemas"]["RegistrationChoices"];
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
        };
    };
    list_assignments_v1_role_assignments_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                subject_id?: string | null;
                subject_type?: ("user" | "user_group") | null;
                role_id?: string | null;
                scope_type?: ("tenant" | "company" | "department") | null;
                active?: boolean | null;
                sort?: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["AssignmentPage"];
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
        };
    };
    assign_role_v1_role_assignments_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
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
        };
    };
    check_assignment_v1_role_assignments_check_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssignmentCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssignmentCheck"];
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
        };
    };
    regrant_assignment_v1_role_assignments__assignment_id__regrant_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                assignment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssignmentRegrant"];
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
        };
    };
    revoke_assignment_v1_role_assignments__assignment_id__revoke_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                assignment_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["RevokeRequest"] | null;
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
        };
    };
    list_roles_v1_roles_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                scope_hint?: ("platform" | "tenant" | "company" | "department") | null;
                q?: string | null;
                sort?: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["RolePage"];
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
        };
    };
    create_role_v1_roles_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleComposed"];
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
        };
    };
    get_role_v1_roles__role_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                role_id: string;
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
                    "application/json": components["schemas"]["RoleDetail"];
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
        };
    };
    update_role_v1_roles__role_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                role_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleComposed"];
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
        };
    };
    clone_role_v1_roles__role_id__clone_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                role_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleClone"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleDetail"];
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
        };
    };
    role_lifecycle_v1_roles__role_id__lifecycle_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                role_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ToggleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleListItem"];
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
        };
    };
    current_session_v1_session_get: {
        parameters: {
            query?: {
                company_id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["SessionDetail"];
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
        };
    };
    tokens_v1_session_api_tokens_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_TokenItem_"];
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
        };
    };
    issue_token_v1_session_api_tokens_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TokenCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokenIssued"];
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
        };
    };
    list_session_companies_v1_session_companies_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                q?: string | null;
                id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["SessionCompanyPage"];
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
        };
    };
    change_own_password_v1_session_password_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordChange"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
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
        };
    };
    update_preferences_v1_session_preferences_patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PreferenceUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserDetail"];
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
        };
    };
    revoke_own_sessions_v1_session_revoke_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
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
        };
    };
    administrator_v1_setup_administrator_get: {
        parameters: {
            query?: never;
            header?: {
                "x-setup-key"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["SetupAdministrator"];
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
        };
    };
    checks_v1_setup_checks_get: {
        parameters: {
            query?: never;
            header?: {
                "x-setup-key"?: string | null;
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
                    "application/json": components["schemas"]["SetupChecks"];
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
        };
    };
    complete_v1_setup_complete_post: {
        parameters: {
            query?: never;
            header?: {
                "x-setup-key"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetupRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SetupResult"];
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
        };
    };
    status_v1_setup_status_get: {
        parameters: {
            query?: never;
            header?: never;
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
                    "application/json": components["schemas"]["SetupStatus"];
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
        };
    };
    get_tenant_v1_tenant_get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["TenantDetail"];
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
        };
    };
    update_tenant_v1_tenant_patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantDetail"];
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
        };
    };
    accept_invitation_v1_tenants__tenant_id__invitations__invitation_id__accept_post: {
        parameters: {
            query?: never;
            header?: {
                authorization?: string | null;
            };
            path: {
                tenant_id: string;
                invitation_id: string;
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
                    "application/json": components["schemas"]["UserDetail"];
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
        };
    };
    list_groups_v1_user_groups_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                q?: string | null;
                sort?: string;
                is_active?: boolean | null;
                id?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["Page_UserGroupListItem_"];
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
        };
    };
    create_group_v1_user_groups_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserGroupCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserGroupItem"];
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
        };
    };
    group_fields_v1_user_groups_field_set_get: {
        parameters: {
            query?: {
                operation?: "create" | "update";
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["FieldSet"];
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
        };
    };
    get_group_v1_user_groups__group_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                group_id: string;
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
                    "application/json": components["schemas"]["UserGroupItem"];
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
        };
    };
    update_group_v1_user_groups__group_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                group_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GroupUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserGroupItem"];
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
        };
    };
    group_lifecycle_v1_user_groups__group_id__lifecycle_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                group_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ToggleRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserGroupItem"];
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
        };
    };
    list_group_members_v1_user_groups__group_id__members_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                group_id: string;
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
                    "application/json": components["schemas"]["Page_GroupMemberListItem_"];
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
        };
    };
    add_group_member_v1_user_groups__group_id__members_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                group_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GroupMemberAdd"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GroupMemberItem"];
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
        };
    };
    remove_member_v1_user_groups__group_id__members__user_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                group_id: string;
                user_id: string;
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
        };
    };
    list_users_v1_users_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
                status?: "active" | "deactivated" | "invited" | "suspended";
                user_type?: "customer_portal_user" | "platform_admin" | "service_account" | "tenant_user";
                q?: string | null;
                sort?: string;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
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
                    "application/json": components["schemas"]["UserPage"];
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
        };
    };
    invite_user_v1_users_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserInvite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserDetail"];
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
        };
    };
    get_user_v1_users__user_id__get: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["UserDetail"];
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
        };
    };
    update_user_v1_users__user_id__patch: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserDetail"];
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
        };
    };
    deactivate_user_v1_users__user_id__deactivate_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["DeactivateRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserDetail"];
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
        };
    };
    list_identities_v1_users__user_id__identities_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["Page_UserIdentityItem_"];
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
        };
    };
    link_identity_v1_users__user_id__identities_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserIdentityCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserIdentityItem"];
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
        };
    };
    unlink_identity_v1_users__user_id__identities__identity_id__delete: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
                identity_id: string;
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
        };
    };
    list_invitations_v1_users__user_id__invitations_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["Page_InvitationItem_"];
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
        };
    };
    resend_invitation_v1_users__user_id__invitations_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InvitationItem"];
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
        };
    };
    user_lifecycle_v1_users__user_id__lifecycle_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserLifecycle"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserDetail"];
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
        };
    };
    preferences_v1_users__user_id__notification_preferences_get: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["Page_PreferenceItem_"];
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
        };
    };
    set_preference_v1_users__user_id__notification_preferences__event_key___channel__put: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
                event_key: string;
                channel: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PreferenceWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PreferenceItem"];
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
        };
    };
    issue_recovery_link_v1_users__user_id__password_recovery_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReasonRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecoveryLink"];
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
        };
    };
    revoke_user_sessions_v1_users__user_id__revoke_sessions_post: {
        parameters: {
            query?: never;
            header?: {
                "x-actor-context"?: string | null;
                "x-actor-signature"?: string | null;
                authorization?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReasonRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
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
        };
    };
}
