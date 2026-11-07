"""Local-command test double for Identity's separately tested signed transport."""

from billing_platform.ids import uuid7
from identity_posting import Receipt


class TrackingFeatureClient:
    def __init__(self):
        self.calls = []
        self.failure = None

    async def request(self, path, operation, body):
        self.calls.append((path, operation, body))
        if self.failure:
            raise self.failure
        intent = body if operation == "tracking-reserve" else body.intent
        status = (
            "pending" if operation == "tracking-reserve" else operation.removeprefix("tracking-")
        )
        return Receipt(
            operation_id=intent.operation_id,
            reservation_id=uuid7(),
            status=status,
            configuration_hash="a" * 64,
            features=["inventory", *intent.features],
            confirmed_at=getattr(body, "committed_at", None),
        )
