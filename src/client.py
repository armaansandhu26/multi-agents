from openai import OpenAI

from src.config import Settings

MAX_RETRIES = 2


def make_client(settings: Settings) -> OpenAI:
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
    )


def generate_response(
    client: OpenAI,
    settings: Settings,
    *,
    instructions: str,
    input_messages: list[dict],
) -> str:
    last_text = ""
    for _ in range(MAX_RETRIES + 1):
        response = client.responses.create(
            model=settings.model,
            instructions=instructions,
            input=input_messages,
            temperature=settings.temperature,
            top_p=settings.top_p,
            max_output_tokens=settings.max_output_tokens,
            store=False,
        )
        last_text = response.output_text.strip()
        if last_text:
            return last_text

    return last_text
