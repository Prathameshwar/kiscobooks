import uuid

from reports.schemas.gstr3b import GstContext, Gstr3bParameters


class Gstr1Parameters(Gstr3bParameters):
    comparison_job_id: uuid.UUID | None = None


class Gstr1Context(GstContext):
    """Outward-return authority with the shared calculation-revision contract."""
