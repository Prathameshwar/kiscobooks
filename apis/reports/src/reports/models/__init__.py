from billing_platform.db.platform_models import IdempotencyKey, Outbox, ProcessedMessage

from reports.models.core import (
    ReportAccountTotal,
    ReportActivation,
    ReportArtifact,
    ReportBundle,
    ReportCompany,
    ReportDefinition,
    ReportFact,
    ReportGeneration,
    ReportLine,
    ReportRow,
    ReportRun,
    ReportSourceClaim,
    ReportStagedFact,
)
from reports.models.daily_balances import ReportDailyBalance
from reports.models.export_artifacts import ReportExportArtifact
from reports.models.framework import FRAMEWORK_MODELS
from reports.models.gst_outward_review import GstOutwardReview
from reports.models.gst_return_review import GstReturnReview
from reports.models.hierarchy import ReportHierarchyNode
from reports.models.posted_lines import ReportPostedLine
from reports.models.readiness import ReportReadiness
from reports.models.source_links import ReportJournalLink
from reports.models.source_versions import VERSION_MODELS

BUSINESS_MODELS = (
    GstReturnReview,
    GstOutwardReview,
    ReportCompany,
    ReportGeneration,
    ReportBundle,
    ReportStagedFact,
    ReportFact,
    ReportLine,
    ReportAccountTotal,
    ReportActivation,
    ReportSourceClaim,
    ReportDefinition,
    ReportRun,
    ReportRow,
    ReportArtifact,
)
MODELS = (
    ReportReadiness,
    *BUSINESS_MODELS,
    *FRAMEWORK_MODELS,
    ReportHierarchyNode,
    *VERSION_MODELS,
    ReportJournalLink,
    ReportPostedLine,
    ReportDailyBalance,
    ReportExportArtifact,
    IdempotencyKey,
    Outbox,
    ProcessedMessage,
)
