# Commercial API operation contracts

Generated from the current Catalog OpenAPI during C6.02 verification. The OpenAPI file
remains the wire contract. All routes require the current actor, company scope and source
context. Reads enforce native/custom field policies. Writes require Idempotency-Key and
check permissions again on replay; mutation schemas carry expected_version, while brand
reparent also requires expected_generation. No endpoint creates a party or stock record.

| Method | Path | Resource permission | Body schema |
|---|---|---|---|
| GET | `/v1/companies/{company_id}/brand-manufacturers` | `brand_manufacturer.read` | - |
| POST | `/v1/companies/{company_id}/brand-manufacturers` | `brand_manufacturer.manage` | BrandManufacturerCreate |
| GET | `/v1/companies/{company_id}/brand-manufacturers/{object_id}` | `brand_manufacturer.read` | - |
| POST | `/v1/companies/{company_id}/brand-manufacturers/{object_id}/close` | `brand_manufacturer.manage` | BrandManufacturerClose |
| GET | `/v1/companies/{company_id}/brand-series` | `brand_series.read` | - |
| POST | `/v1/companies/{company_id}/brand-series` | `brand_series.manage` | BrandSeriesCreate |
| GET | `/v1/companies/{company_id}/brand-series/{object_id}` | `brand_series.read` | - |
| PATCH | `/v1/companies/{company_id}/brand-series/{object_id}` | `brand_series.manage` | BrandSeriesUpdate |
| POST | `/v1/companies/{company_id}/brand-series/{object_id}/activate` | `brand_series.manage` | ExpectedVersion |
| POST | `/v1/companies/{company_id}/brand-series/{object_id}/deactivate` | `brand_series.manage` | ExpectedVersion |
| GET | `/v1/companies/{company_id}/brands` | `brand.read` | - |
| POST | `/v1/companies/{company_id}/brands` | `brand.manage` | BrandCreate |
| GET | `/v1/companies/{company_id}/brands/{object_id}` | `brand.read` | - |
| PATCH | `/v1/companies/{company_id}/brands/{object_id}` | `brand.manage` | BrandUpdate |
| POST | `/v1/companies/{company_id}/brands/{object_id}/activate` | `brand.manage` | ExpectedVersion |
| POST | `/v1/companies/{company_id}/brands/{object_id}/deactivate` | `brand.manage` | ExpectedVersion |
| POST | `/v1/companies/{company_id}/brands/{object_id}/reparent` | `brand.move` | BrandReparent |
| GET | `/v1/companies/{company_id}/manufacturer-sites` | `manufacturer_site.read` | - |
| POST | `/v1/companies/{company_id}/manufacturer-sites` | `manufacturer_site.manage` | ManufacturerSiteCreate |
| GET | `/v1/companies/{company_id}/manufacturer-sites/{object_id}` | `manufacturer_site.read` | - |
| PATCH | `/v1/companies/{company_id}/manufacturer-sites/{object_id}` | `manufacturer_site.manage` | ManufacturerSiteUpdate |
| POST | `/v1/companies/{company_id}/manufacturer-sites/{object_id}/activate` | `manufacturer_site.manage` | ExpectedVersion |
| POST | `/v1/companies/{company_id}/manufacturer-sites/{object_id}/deactivate` | `manufacturer_site.manage` | ExpectedVersion |
| GET | `/v1/companies/{company_id}/manufacturers` | `manufacturer.read` | - |
| POST | `/v1/companies/{company_id}/manufacturers` | `manufacturer.manage` | ManufacturerCreate |
| GET | `/v1/companies/{company_id}/manufacturers/{object_id}` | `manufacturer.read` | - |
| PATCH | `/v1/companies/{company_id}/manufacturers/{object_id}` | `manufacturer.manage` | ManufacturerUpdate |
| POST | `/v1/companies/{company_id}/manufacturers/{object_id}/activate` | `manufacturer.manage` | ExpectedVersion |
| POST | `/v1/companies/{company_id}/manufacturers/{object_id}/deactivate` | `manufacturer.manage` | ExpectedVersion |
| GET | `/v1/companies/{company_id}/product-types` | `product_type.read` | - |
| POST | `/v1/companies/{company_id}/product-types` | `product_type.manage` | ProductTypeCreate |
| GET | `/v1/companies/{company_id}/product-types/{object_id}` | `product_type.read` | - |
| PATCH | `/v1/companies/{company_id}/product-types/{object_id}` | `product_type.manage` | ProductTypeUpdate |
| POST | `/v1/companies/{company_id}/product-types/{object_id}/activate` | `product_type.manage` | ExpectedVersion |
| POST | `/v1/companies/{company_id}/product-types/{object_id}/deactivate` | `product_type.manage` | ExpectedVersion |
| GET | `/v1/companies/{company_id}/product-types/{product_type_id}/revisions` | `product_type.read` | - |
| POST | `/v1/companies/{company_id}/product-types/{product_type_id}/revisions` | `product_type.manage` | TypeRevisionInput |
| GET | `/v1/companies/{company_id}/product-types/{product_type_id}/revisions/{object_id}` | `product_type.read` | - |
| PATCH | `/v1/companies/{company_id}/product-types/{product_type_id}/revisions/{object_id}` | `product_type.manage` | TypeRevisionUpdate |
| POST | `/v1/companies/{company_id}/product-types/{product_type_id}/revisions/{object_id}/publish` | `product_type.publish` | ExpectedVersion |

Lists use signed keyset cursors and a 50/default, 200/maximum limit. Master lists expose
code/name prefix search, native id/code/name sorts and declared company/parent/kind filters.
History lists expose typed date/publication filters and supported date/revision/id sorts;
unsupported text search is rejected. Filter/sort/parent fields must be readable.
