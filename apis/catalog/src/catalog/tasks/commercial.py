"""Commercial masters reuse the classification command and query pipeline."""

from catalog.models.commercial import (
    Brand,
    BrandSeries,
    Manufacturer,
    ManufacturerSite,
    ProductType,
)
from catalog.schemas.commercial import (
    BrandCreate,
    BrandDetail,
    BrandListItem,
    BrandSeriesCreate,
    BrandSeriesDetail,
    BrandSeriesListItem,
    ManufacturerCreate,
    ManufacturerDetail,
    ManufacturerListItem,
    ManufacturerSiteCreate,
    ManufacturerSiteDetail,
    ManufacturerSiteListItem,
    ProductTypeCreate,
    ProductTypeDetail,
    ProductTypeListItem,
)
from catalog.tasks.classification import Classification

BRAND = Classification(
    Brand,
    "catalog.brand",
    "brand",
    BrandCreate,
    BrandDetail,
    BrandListItem,
    frozenset({"code", "is_active", "parent_brand_id"}),
)
MANUFACTURER = Classification(
    Manufacturer,
    "catalog.manufacturer",
    "manufacturer",
    ManufacturerCreate,
    ManufacturerDetail,
    ManufacturerListItem,
    frozenset({"code", "is_active"}),
)
BRAND_SERIES = Classification(
    BrandSeries,
    "catalog.brand_series",
    "brand_series",
    BrandSeriesCreate,
    BrandSeriesDetail,
    BrandSeriesListItem,
    frozenset({"code", "brand_id", "is_active"}),
)
MANUFACTURER_SITE = Classification(
    ManufacturerSite,
    "catalog.manufacturer_site",
    "manufacturer_site",
    ManufacturerSiteCreate,
    ManufacturerSiteDetail,
    ManufacturerSiteListItem,
    frozenset({"country_code", "state_code", "code", "manufacturer_id", "is_active"}),
)
PRODUCT_TYPE = Classification(
    ProductType,
    "catalog.product_type",
    "product_type",
    ProductTypeCreate,
    ProductTypeDetail,
    ProductTypeListItem,
    frozenset({"kind", "code", "is_active"}),
)
