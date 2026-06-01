#!/usr/bin/env python3
"""Verify Azure Foundry connectivity before running the full experiment."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.client import generate_response, make_client
from src.config import Settings


def main() -> None:
    settings = Settings.from_env()
    client = make_client(settings)

    print("Testing Azure Foundry connection...")
    print(f"  base_url: {settings.base_url}")
    print(f"  model:    {settings.model}")

    reply = generate_response(
        client,
        settings,
        instructions="You are a helpful assistant.",
        input_messages=[
            {
                "type": "message",
                "role": "user",
                "content": "Reply with exactly: foundry-ok",
            }
        ],
    )

    print(f"\nModel reply: {reply}")
    print("\nConnection successful.")


if __name__ == "__main__":
    main()
