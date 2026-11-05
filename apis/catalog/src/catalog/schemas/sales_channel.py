"""Sales-channel master schemas — a plain classification master, no extra fields."""

from catalog.schemas.classification import (
    DetailFields,
    MasterInput,
    MasterListItem,
    MasterQuery,
    MasterUpdate,
)


class SalesChannelCreate(MasterInput):
    pass


class SalesChannelUpdate(MasterUpdate):
    pass


class SalesChannelListItem(MasterListItem):
    pass


class SalesChannelDetail(SalesChannelListItem, DetailFields):
    pass


class SalesChannelQuery(MasterQuery):
    pass
