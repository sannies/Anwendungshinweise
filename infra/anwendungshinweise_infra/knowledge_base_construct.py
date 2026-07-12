"""Knowledge-Base-Kern: Dokumenten-Bucket, S3-Vectors-Speicher und Bedrock KB."""

from __future__ import annotations

from aws_cdk import Aws, RemovalPolicy, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3vectors as s3vectors
from constructs import Construct

from .config import StackConfig

# Von Bedrock reservierte Metadaten-Schlüssel, die im S3-Vector-Index als
# nicht-filterbar deklariert werden müssen (enthalten den Chunk-Text bzw. die
# Quell-Metadaten und würden sonst das Filter-Größenlimit sprengen).
BEDROCK_RESERVED_METADATA_KEYS = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]


class KnowledgeBase(Construct):
    """Bündelt Speicher (S3 + S3 Vectors) und die Bedrock Knowledge Base."""

    def __init__(self, scope: Construct, construct_id: str, *, config: StackConfig) -> None:
        super().__init__(scope, construct_id)
        stack = Stack.of(self)
        prefix = config.resource_prefix

        # --- 1) Bucket für die hochgeladenen PDF-Anwendungshinweise -----------
        self.documents_bucket = s3.Bucket(
            self,
            "DocumentsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # --- 2) S3-Vectors-Speicher (günstiger Vektorstore) ------------------
        self.vector_bucket = s3vectors.CfnVectorBucket(self, "VectorBucket")

        self.vector_index = s3vectors.CfnIndex(
            self,
            "VectorIndex",
            index_name=f"{prefix}-index",
            vector_bucket_arn=self.vector_bucket.attr_vector_bucket_arn,
            data_type="float32",
            dimension=config.embedding_dimensions,
            distance_metric="cosine",
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=BEDROCK_RESERVED_METADATA_KEYS,
            ),
        )

        embedding_model_arn = (
            f"arn:{Aws.PARTITION}:bedrock:{config.region}::"
            f"foundation-model/{config.embedding_model_id}"
        )

        # --- 3) Service-Rolle der Knowledge Base -----------------------------
        self.kb_role = iam.Role(
            self,
            "KnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={"StringEquals": {"aws:SourceAccount": stack.account}},
            ),
            description="Service-Rolle der Bedrock Knowledge Base (Anwendungshinweise)",
        )
        # Embedding-Modell aufrufen
        self.kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[embedding_model_arn],
            )
        )
        # Quelldokumente lesen
        self.documents_bucket.grant_read(self.kb_role)
        # S3-Vectors-Zugriff (Bucket + Index)
        self.kb_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3vectors:*"],
                resources=[
                    self.vector_bucket.attr_vector_bucket_arn,
                    f"{self.vector_bucket.attr_vector_bucket_arn}/*",
                    self.vector_index.attr_index_arn,
                ],
            )
        )

        # --- 4) Knowledge Base -----------------------------------------------
        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name=f"{prefix}-kb",
            role_arn=self.kb_role.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=embedding_model_arn,
                    embedding_model_configuration=bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                        bedrock_embedding_model_configuration=bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                            dimensions=config.embedding_dimensions,
                            embedding_data_type="FLOAT",
                        ),
                    ),
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    index_arn=self.vector_index.attr_index_arn,
                    vector_bucket_arn=self.vector_bucket.attr_vector_bucket_arn,
                ),
            ),
        )
        # Index muss vor der KB existieren; Rolle inkl. Policies ebenfalls,
        # damit Bedrock die Zugriffsrechte bei der Erstellung validieren kann.
        self.knowledge_base.add_dependency(self.vector_index)
        self.knowledge_base.node.add_dependency(self.kb_role)

        # --- 5) Datenquelle (S3) ---------------------------------------------
        self.data_source = bedrock.CfnDataSource(
            self,
            "DataSource",
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            name=f"{prefix}-s3-source",
            # Beim Löschen der Datenquelle die zugehörigen Vektoren mit entfernen.
            data_deletion_policy="DELETE",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=self.documents_bucket.bucket_arn,
                    inclusion_prefixes=[config.documents_prefix],
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy="FIXED_SIZE",
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=config.chunk_max_tokens,
                        overlap_percentage=config.chunk_overlap_percentage,
                    ),
                ),
            ),
        )

    @property
    def knowledge_base_id(self) -> str:
        return self.knowledge_base.attr_knowledge_base_id

    @property
    def knowledge_base_arn(self) -> str:
        return self.knowledge_base.attr_knowledge_base_arn

    @property
    def data_source_id(self) -> str:
        return self.data_source.attr_data_source_id
