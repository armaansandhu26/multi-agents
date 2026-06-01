import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    model: str
    temperature: float
    top_p: float
    max_output_tokens: int

    @classmethod
    def from_env(cls) -> "Settings":
        base_url = os.getenv(
            "AZURE_OPENAI_BASE_URL",
            "https://armaan-foundry.services.ai.azure.com/openai/v1/",
        )
        if not base_url.endswith("/"):
            base_url += "/"

        api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "AZURE_OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
            )

        return cls(
            base_url=base_url,
            api_key=api_key,
            model=os.getenv("AZURE_OPENAI_MODEL", "gpt-5.4-mini"),
            temperature=float(os.getenv("TEMPERATURE", "0.7")),
            top_p=float(os.getenv("TOP_P", "1.0")),
            max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "800")),
        )
