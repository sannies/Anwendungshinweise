"""Haupt-Stack: verdrahtet Knowledge Base, Backend und Frontend."""

from __future__ import annotations

from aws_cdk import CfnOutput, Stack
from constructs import Construct

from .backend_construct import Backend
from .config import StackConfig
from .frontend_construct import Frontend
from .knowledge_base_construct import KnowledgeBase


class AnwendungshinweiseStack(Stack):
    def __init__(
        self, scope: Construct, construct_id: str, *, config: StackConfig, **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        knowledge_base = KnowledgeBase(self, "KnowledgeBase", config=config)
        backend = Backend(
            self, "Backend", config=config, knowledge_base=knowledge_base
        )
        frontend = Frontend(self, "Frontend", api_url=backend.api_url)

        CfnOutput(self, "ApiUrl", value=backend.api_url, description="Basis-URL der REST-API")
        CfnOutput(
            self,
            "FrontendUrl",
            value=frontend.url,
            description="URL des Demo-Frontends (CloudFront)",
        )
        CfnOutput(
            self,
            "DocumentsBucketName",
            value=knowledge_base.documents_bucket.bucket_name,
            description="S3-Bucket für die PDF-Anwendungshinweise (Prefix: "
            + config.documents_prefix
            + ")",
        )
        CfnOutput(
            self,
            "KnowledgeBaseId",
            value=knowledge_base.knowledge_base_id,
            description="ID der Bedrock Knowledge Base",
        )
        CfnOutput(
            self,
            "DataSourceId",
            value=knowledge_base.data_source_id,
            description="ID der S3-Datenquelle",
        )
