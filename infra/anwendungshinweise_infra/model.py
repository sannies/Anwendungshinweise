"""Ableitung der Bedrock-Modell-ARN aus einer Modell-ID.

Unterstützt drei Schreibweisen der ``generationModelId``:

* vollständige ARN (beginnt mit ``arn:``)           -> unverändert übernommen
* Cross-Region-Inference-Profile (``eu.``/``us.``/…) -> inference-profile-ARN
* Foundation-Model-ID (z. B. ``mistral.…``)          -> foundation-model-ARN

So lässt sich das Generierungsmodell (Claude, Mistral, Nova, …) allein über
den CDK-Context umstellen, ohne Code zu ändern.
"""

from __future__ import annotations

# Geo-Präfixe kennzeichnen ein Cross-Region-Inference-Profile.
INFERENCE_PROFILE_PREFIXES = ("us.", "eu.", "apac.", "us-gov.", "global.")


def is_inference_profile_id(model_id: str) -> bool:
    return any(model_id.startswith(prefix) for prefix in INFERENCE_PROFILE_PREFIXES)


def bedrock_model_arn(
    partition: str, region: str, account: str, model_id: str
) -> str:
    """Baut die passende Bedrock-Modell-ARN für ``model_id``."""
    if model_id.startswith("arn:"):
        return model_id
    if is_inference_profile_id(model_id):
        return f"arn:{partition}:bedrock:{region}:{account}:inference-profile/{model_id}"
    return f"arn:{partition}:bedrock:{region}::foundation-model/{model_id}"
