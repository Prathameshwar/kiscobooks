"""Reusable profiles adopt the existing native master command pipeline."""

from catalog.models.boms import Bom
from catalog.models.handling import HandlingProfile
from catalog.models.inventory_templates import InventoryProfileTemplate
from catalog.models.manufacturing_operations import ManufacturingOperation
from catalog.models.manufacturing_routes import ManufacturingRoute
from catalog.models.profiles import IdentifierProfile
from catalog.models.promotion_limits import PromotionLimitDefinition
from catalog.models.returns import ReturnPolicy
from catalog.models.sales_channel import SalesChannel
from catalog.models.warranties import WarrantyPolicy
from catalog.schemas.boms import BomCreate, BomDetail, BomListItem
from catalog.schemas.handling import (
    HandlingProfileCreate,
    HandlingProfileDetail,
    HandlingProfileListItem,
)
from catalog.schemas.inventory_templates import (
    InventoryTemplateCreate,
    InventoryTemplateDetail,
    InventoryTemplateListItem,
)
from catalog.schemas.manufacturing_operations import (
    OperationCreate,
    OperationDetail,
    OperationListItem,
)
from catalog.schemas.manufacturing_routes import RouteCreate, RouteDetail, RouteListItem
from catalog.schemas.profiles import (
    IdentifierProfileCreate,
    IdentifierProfileDetail,
    IdentifierProfileListItem,
)
from catalog.schemas.promotion_limits import LimitCreate, LimitDetail, LimitListItem
from catalog.schemas.returns import ReturnPolicyCreate, ReturnPolicyDetail, ReturnPolicyListItem
from catalog.schemas.sales_channel import (
    SalesChannelCreate,
    SalesChannelDetail,
    SalesChannelListItem,
)
from catalog.schemas.warranties import (
    WarrantyPolicyCreate,
    WarrantyPolicyDetail,
    WarrantyPolicyListItem,
)
from catalog.tasks.classification import Classification
from catalog.tasks.promotion_limits import validate_header as validate_limit_header

BOM = Classification(
    Bom,
    "catalog.bom",
    "bom",
    BomCreate,
    BomDetail,
    BomListItem,
    frozenset({"is_active", "code"}),
    required_feature="bom_definitions",
)

MANUFACTURING_OPERATION = Classification(
    ManufacturingOperation,
    "catalog.manufacturing_operation",
    "manufacturing_operation",
    OperationCreate,
    OperationDetail,
    OperationListItem,
    frozenset({"is_active", "code"}),
)

IDENTIFIER_PROFILE = Classification(
    IdentifierProfile,
    "catalog.identifier_profile",
    "identifier_profile",
    IdentifierProfileCreate,
    IdentifierProfileDetail,
    IdentifierProfileListItem,
    frozenset({"is_active", "code"}),
)

INVENTORY_TEMPLATE = Classification(
    InventoryProfileTemplate,
    "catalog.inventory_profile_template",
    "inventory_profile_template",
    InventoryTemplateCreate,
    InventoryTemplateDetail,
    InventoryTemplateListItem,
    frozenset({"is_active", "code"}),
)


WARRANTY_POLICY = Classification(
    WarrantyPolicy,
    "catalog.warranty_policy",
    "warranty_policy",
    WarrantyPolicyCreate,
    WarrantyPolicyDetail,
    WarrantyPolicyListItem,
    frozenset({"is_active", "code"}),
)


RETURN_POLICY = Classification(
    ReturnPolicy,
    "catalog.return_policy",
    "return_policy",
    ReturnPolicyCreate,
    ReturnPolicyDetail,
    ReturnPolicyListItem,
    frozenset({"is_active", "code"}),
)


HANDLING_PROFILE = Classification(
    HandlingProfile,
    "catalog.handling_profile",
    "handling_profile",
    HandlingProfileCreate,
    HandlingProfileDetail,
    HandlingProfileListItem,
    frozenset({"is_active", "code"}),
)


SALES_CHANNEL = Classification(
    SalesChannel,
    "catalog.sales_channel",
    "sales_channel",
    SalesChannelCreate,
    SalesChannelDetail,
    SalesChannelListItem,
    frozenset({"is_active", "code"}),
)


MANUFACTURING_ROUTE = Classification(
    ManufacturingRoute,
    "catalog.manufacturing_route",
    "manufacturing_route",
    RouteCreate,
    RouteDetail,
    RouteListItem,
    frozenset({"is_active", "code"}),
)


PROMOTION_LIMIT = Classification(
    PromotionLimitDefinition,
    "catalog.promotion_limit_definition",
    "promotion_limit",
    LimitCreate,
    LimitDetail,
    LimitListItem,
    frozenset({"is_active", "code", "scope_kind", "metric"}),
    required_feature="sales_promotions",
    validate=validate_limit_header,
)
