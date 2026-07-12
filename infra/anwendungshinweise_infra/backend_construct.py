"""Compute-Schicht: API-Lambda, Ingest-Lambda, REST-API und S3-Trigger."""

from __future__ import annotations

from aws_cdk import Aws, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from constructs import Construct

from .config import StackConfig
from .knowledge_base_construct import KnowledgeBase
from .model import bedrock_model_arn
from .paths import BACKEND_SRC


class Backend(Construct):
    """Lambdas + API Gateway rund um die Knowledge Base."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        config: StackConfig,
        knowledge_base: KnowledgeBase,
    ) -> None:
        super().__init__(scope, construct_id)
        stack = Stack.of(self)

        # ARN des Generierungsmodells (Foundation-Model wie Mistral oder ein
        # Cross-Region-Inference-Profile wie Claude) – automatisch abgeleitet.
        generation_model_arn = bedrock_model_arn(
            Aws.PARTITION, config.region, stack.account, config.generation_model_id
        )

        common_env = {
            "KNOWLEDGE_BASE_ID": knowledge_base.knowledge_base_id,
            "DATA_SOURCE_ID": knowledge_base.data_source_id,
            "DOCUMENTS_BUCKET": knowledge_base.documents_bucket.bucket_name,
            "DOCUMENTS_PREFIX": config.documents_prefix,
            "GENERATION_MODEL_ARN": generation_model_arn,
            "MAX_RESULTS": str(config.max_results),
        }

        # Ein gemeinsames Code-Asset für beide Handler (nur boto3 nötig -> keine
        # Fremdabhängigkeiten, daher kein Bundling erforderlich).
        code = lambda_.Code.from_asset(str(BACKEND_SRC))

        # --- API-Lambda -------------------------------------------------------
        self.api_fn = lambda_.Function(
            self,
            "ApiFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="anwendungshinweise.api.handler",
            code=code,
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=common_env,
            log_group=logs.LogGroup(
                self,
                "ApiLogs",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        self._grant_query_permissions(
            self.api_fn, knowledge_base, generation_model_arn
        )
        knowledge_base.documents_bucket.grant_read(self.api_fn)

        # --- Ingest-Lambda (S3 -> Bedrock Ingestion-Job) ----------------------
        self.ingest_fn = lambda_.Function(
            self,
            "IngestFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="anwendungshinweise.ingest.handler",
            code=code,
            timeout=Duration.seconds(30),
            memory_size=256,
            environment=common_env,
            log_group=logs.LogGroup(
                self,
                "IngestLogs",
                retention=logs.RetentionDays.ONE_WEEK,
                removal_policy=RemovalPolicy.DESTROY,
            ),
        )
        self.ingest_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:StartIngestionJob"],
                resources=[
                    knowledge_base.knowledge_base_arn,
                    f"{knowledge_base.knowledge_base_arn}/*",
                ],
            )
        )

        # S3-Trigger: neue/gelöschte Objekte unter dem Dokument-Prefix
        notification = s3n.LambdaDestination(self.ingest_fn)
        key_filter = s3.NotificationKeyFilter(prefix=config.documents_prefix)
        knowledge_base.documents_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED, notification, key_filter
        )
        knowledge_base.documents_bucket.add_event_notification(
            s3.EventType.OBJECT_REMOVED, notification, key_filter
        )

        # --- REST-API (Proxy auf die API-Lambda) ------------------------------
        self.rest_api = apigw.LambdaRestApi(
            self,
            "RestApi",
            handler=self.api_fn,
            proxy=True,
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=20,
                throttling_burst_limit=10,
            ),
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type"],
            ),
        )

    @property
    def api_url(self) -> str:
        return self.rest_api.url

    @staticmethod
    def _grant_query_permissions(
        fn: lambda_.Function,
        knowledge_base: KnowledgeBase,
        generation_model_arn: str,
    ) -> None:
        kb_arn = knowledge_base.knowledge_base_arn
        # Retrieve / RetrieveAndGenerate gegen die KB
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:Retrieve",
                    "bedrock:RetrieveAndGenerate",
                    "bedrock:ListIngestionJobs",
                    "bedrock:GetIngestionJob",
                ],
                resources=[kb_arn, f"{kb_arn}/*"],
            )
        )
        # Generierungsmodell aufrufen (Inference-Profile + zugrunde liegende FMs)
        fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    generation_model_arn,
                    f"arn:{Aws.PARTITION}:bedrock:*::foundation-model/*",
                ],
            )
        )
