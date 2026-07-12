"""Synth-/Assertion-Tests für den Haupt-Stack."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from anwendungshinweise_infra.config import StackConfig
from anwendungshinweise_infra.main_stack import AnwendungshinweiseStack


def _template() -> Template:
    app = cdk.App()
    config = StackConfig.from_app(app)
    stack = AnwendungshinweiseStack(
        app,
        "TestStack",
        config=config,
        env=cdk.Environment(account="123456789012", region="eu-central-1"),
    )
    return Template.from_stack(stack)


def test_creates_core_resources():
    t = _template()
    t.resource_count_is("AWS::S3Vectors::VectorBucket", 1)
    t.resource_count_is("AWS::S3Vectors::Index", 1)
    t.resource_count_is("AWS::Bedrock::KnowledgeBase", 1)
    t.resource_count_is("AWS::Bedrock::DataSource", 1)
    t.resource_count_is("AWS::CloudFront::Distribution", 1)


def test_knowledge_base_uses_s3_vectors():
    t = _template()
    t.has_resource_properties(
        "AWS::Bedrock::KnowledgeBase",
        {"StorageConfiguration": {"Type": "S3_VECTORS"}},
    )


def test_index_has_bedrock_reserved_metadata_keys():
    t = _template()
    t.has_resource_properties(
        "AWS::S3Vectors::Index",
        {
            "DataType": "float32",
            "Dimension": 1024,
            "DistanceMetric": "cosine",
            "MetadataConfiguration": {
                "NonFilterableMetadataKeys": Match.array_with(
                    ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
                )
            },
        },
    )


def test_two_lambda_functions_and_rest_api():
    t = _template()
    # API + Ingest (Log-Retention nutzt keine zusätzliche Custom-Resource-Lambda)
    t.resource_count_is("AWS::Lambda::Function", 2 + _custom_resource_lambdas(t))
    t.resource_count_is("AWS::ApiGateway::RestApi", 1)


def _custom_resource_lambdas(t: Template) -> int:
    # auto_delete_objects + BucketNotifications + BucketDeployment erzeugen
    # jeweils eigene Provider-Lambdas; deren Anzahl interessiert hier nicht,
    # daher zählen wir sie separat heraus.
    funcs = t.find_resources("AWS::Lambda::Function")
    ours = [
        k
        for k, v in funcs.items()
        if v["Properties"].get("Handler", "").startswith("anwendungshinweise.")
    ]
    return len(funcs) - len(ours)
