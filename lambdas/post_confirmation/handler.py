"""Cognito Post-Confirmation trigger: every newly verified user joins the employee group."""

import os
from typing import Any

import boto3

cognito = boto3.client("cognito-idp")


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    if event["triggerSource"] == "PostConfirmation_ConfirmSignUp":
        cognito.admin_add_user_to_group(
            UserPoolId=event["userPoolId"],
            Username=event["userName"],
            GroupName=os.environ["DEFAULT_GROUP"],
        )
    return event
