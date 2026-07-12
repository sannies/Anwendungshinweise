"""Tests für die Bedrock-Modell-ARN-Ableitung."""

from __future__ import annotations

from anwendungshinweise_infra.model import bedrock_model_arn, is_inference_profile_id


def test_foundation_model_id_yields_foundation_model_arn():
    arn = bedrock_model_arn(
        "aws", "eu-central-1", "123456789012", "mistral.mistral-large-2402-v1:0"
    )
    assert arn == "arn:aws:bedrock:eu-central-1::foundation-model/mistral.mistral-large-2402-v1:0"


def test_inference_profile_id_yields_profile_arn():
    arn = bedrock_model_arn(
        "aws", "eu-central-1", "123456789012", "eu.anthropic.claude-3-5-sonnet-20240620-v1:0"
    )
    assert arn == (
        "arn:aws:bedrock:eu-central-1:123456789012:inference-profile/"
        "eu.anthropic.claude-3-5-sonnet-20240620-v1:0"
    )


def test_full_arn_is_passed_through():
    given = "arn:aws:bedrock:eu-central-1::foundation-model/mistral.mistral-large-2402-v1:0"
    assert bedrock_model_arn("aws", "eu-central-1", "1", given) == given


def test_is_inference_profile_id():
    assert is_inference_profile_id("eu.anthropic.claude-3-5-sonnet-20240620-v1:0")
    assert not is_inference_profile_id("mistral.mistral-large-2402-v1:0")
