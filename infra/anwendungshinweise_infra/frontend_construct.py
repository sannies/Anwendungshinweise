"""Statisches Vue-Frontend auf S3 + CloudFront (Demo)."""

from __future__ import annotations

from aws_cdk import RemovalPolicy
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

from .paths import FRONTEND_DIST

# Platzhalter, falls das Frontend noch nicht gebaut wurde (z. B. reines
# ``cdk synth`` in der CI ohne vorherigen ``npm run build``).
_PLACEHOLDER_HTML = (
    "<!doctype html><html lang=de><meta charset=utf-8>"
    "<title>Anwendungshinweise</title>"
    "<body style='font-family:sans-serif;padding:2rem'>"
    "<h1>Frontend noch nicht gebaut</h1>"
    "<p>Bitte <code>make build-frontend</code> ausführen und erneut deployen.</p>"
)


class Frontend(Construct):
    """S3-Bucket + CloudFront-Distribution mit dem gebauten Vue-Frontend."""

    def __init__(
        self, scope: Construct, construct_id: str, *, api_url: str, oac_name: str
    ) -> None:
        super().__init__(scope, construct_id)

        self.bucket = s3.Bucket(
            self,
            "SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Origin Access Control ist eine KONTO-WEITE (globale) Ressource mit
        # eindeutigem Namen. Daher explizit prefix-/regionsbasiert benennen –
        # sonst kollidiert der von CDK aus dem Stack-Pfad abgeleitete Name mit
        # Alt-Beständen bzw. mit weiteren Installationen.
        oac = cloudfront.S3OriginAccessControl(
            self,
            "OAC",
            origin_access_control_name=oac_name,
        )

        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_root_object="index.html",
            comment="Anwendungshinweise Demo-Frontend",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    self.bucket, origin_access_control=oac
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            error_responses=[
                # SPA-Fallback: unbekannte Pfade auf index.html leiten.
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
        )

        # Quellen: gebautes Frontend (oder Platzhalter) + Laufzeit-Konfiguration.
        sources = [self._frontend_source()]
        sources.append(
            s3deploy.Source.json_data("config.json", {"apiBaseUrl": api_url})
        )

        s3deploy.BucketDeployment(
            self,
            "DeployFrontend",
            sources=sources,
            destination_bucket=self.bucket,
            distribution=self.distribution,
            distribution_paths=["/*"],
        )

        self.url = f"https://{self.distribution.distribution_domain_name}"

    @staticmethod
    def _frontend_source() -> s3deploy.ISource:
        if FRONTEND_DIST.is_dir() and any(FRONTEND_DIST.iterdir()):
            return s3deploy.Source.asset(str(FRONTEND_DIST))
        return s3deploy.Source.data("index.html", _PLACEHOLDER_HTML)
