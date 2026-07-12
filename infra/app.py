#!/usr/bin/env python3
"""CDK-Einstiegspunkt für die Anwendungshinweise-Wissensbasis."""

from __future__ import annotations

import os

import aws_cdk as cdk

from anwendungshinweise_infra.config import StackConfig
from anwendungshinweise_infra.main_stack import AnwendungshinweiseStack

app = cdk.App()
config = StackConfig.from_app(app)

AnwendungshinweiseStack(
    app,
    "AnwendungshinweiseStack",
    config=config,
    # Region fest auf Frankfurt; Account aus der CLI-Umgebung.
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", config.region),
    ),
    description=(
        "Anwendungshinweise-Wissensbasis: Bedrock Knowledge Base + S3 Vectors "
        "+ REST-API + Vue-Frontend (Demo)"
    ),
)

app.synth()
