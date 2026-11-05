from reporting_contract.gst import GstReturnRecord as GstInput
from reporting_contract.gst_outward import GstOutwardRecord as OutwardInput

from accounting.models.gst_return import GstReturnRecord
from accounting.models.gst_outward import GstOutwardRecord
from accounting.resources import Resource
from accounting.schemas.gst_return import GstRecordDetail
from accounting.schemas.gst_outward import GstOutwardDetail
from accounting.schemas.masters import Input

GST_RESOURCES = (
    Resource(
        "gst_outward_record",
        "gst-outward-records",
        "command",
        GstOutwardRecord,
        OutwardInput,
        Input,
        GstOutwardDetail,
        {"original_record_id": "gst_outward_record"},
        frozenset(),
    ),
    Resource(
        "gst_return_record",
        "gst-return-records",
        "command",
        GstReturnRecord,
        GstInput,
        Input,
        GstRecordDetail,
        {"original_record_id": "gst_return_record"},
        frozenset(),
    ),
)
