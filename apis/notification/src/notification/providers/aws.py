"""Operator-bound AWS identities shared by send, setup and confirmation clients."""

from __future__ import annotations

from typing import Any

import boto3  # type: ignore[import-untyped] # AWS SDK does not publish typing in this package.


def client(service: str, region: str | None, credentials: dict[str, Any]) -> Any:
    if credentials.get("role_arn"):
        assumed = boto3.client("sts").assume_role(
            RoleArn=credentials["role_arn"],
            RoleSessionName="notification",
            **(
                {"ExternalId": credentials["external_id"]} if credentials.get("external_id") else {}
            ),
        )["Credentials"]
        return boto3.client(
            service,
            region_name=region,
            aws_access_key_id=assumed["AccessKeyId"],
            aws_secret_access_key=assumed["SecretAccessKey"],
            aws_session_token=assumed["SessionToken"],
        )
    # The registered binding may explicitly select a workload identity or provision
    # an account-specific AWS credential. Values never cross the management API.
    options = {
        key: credentials[key]
        for key in ("aws_access_key_id", "aws_secret_access_key", "aws_session_token")
        if key in credentials
    }
    return boto3.client(service, region_name=region, **options)
