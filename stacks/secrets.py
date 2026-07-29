from aws_cdk import CfnOutput, SecretValue, Stack
from aws_cdk import (
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct

from config import AppConfig


class SecretsStack(Stack):
    """Secrets Manager infrastructure for DIA."""

    def __init__(self, scope: Construct, construct_id: str, *, config: AppConfig, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- Agent secrets (tavily, endpoints, kb arn) ---

        self.kb_arns = secretsmanager.Secret(
            self,
            "KnowledgeBasesArns",
            secret_name=config.kb_arns,
            description="Bedrock Knowledge Base ARNs",
            secret_object_value={
                "kb_gats_business_cases": SecretValue.unsafe_plain_text(""),
                "kb_sr25_bids": SecretValue.unsafe_plain_text(""),
                "kb_sr21_bids": SecretValue.unsafe_plain_text(""),
                "kb_nao_reports": SecretValue.unsafe_plain_text(""),
                "kb_efficiency_reports": SecretValue.unsafe_plain_text(""),
            },
        )

        self.tavily_secret = secretsmanager.Secret(
            self,
            "TavilySecret",
            secret_name=config.tavily_secret,
            description="Secrets Manager name for the Tavily API key",
        )

        self.neptune_endpoint_secret = secretsmanager.Secret(
            self,
            "NeptuneEndpointSecret",
            secret_name=config.neptune_endpoint_secret,
            description="Neptune endpoint",
        )

        self.aoss_endpoint_secret = secretsmanager.Secret(
            self,
            "AossEndpointSecret",
            secret_name=config.aoss_endpoint_secret,
            description="OpenSearch endpoint",
        )

        CfnOutput(
            self,
            "SetTavilySecretCommand",
            value=f"aws secretsmanager put-secret-value --secret-id {self.tavily_secret.secret_name} --secret-string 'YOUR_TAVILY_API_KEY' --region {self.region}",  # noqa: E501
            description="Command to set the Tavily API key value",
        )

        CfnOutput(
            self,
            "SetNeptuneEndpointCommand",
            value=f"aws secretsmanager put-secret-value --secret-id {self.neptune_endpoint_secret.secret_name} --secret-string 'YOUR_NEPTUNE_ENDPOINT' --region {self.region}",  # noqa: E501
            description="Command to set the Neptune endpoint hostname value",
        )

        CfnOutput(
            self,
            "SetAossEndpointCommand",
            value=f"aws secretsmanager put-secret-value --secret-id {self.aoss_endpoint_secret.secret_name} --secret-string 'YOUR_AOSS_ENDPOINT' --region {self.region}",  # noqa: E501
            description="Command to set the AOSS endpoint hostname value",
        )
