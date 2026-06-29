"""Manual Cerebras API smoke test. Run directly: `python test_api.py`.

NOTE: guarded by __main__ so pytest can't import-and-fire the live call during
collection (it's not a pytest test — it just checks the key/model work).
"""
import os
from dotenv import load_dotenv
from openai import OpenAI


def main():
    load_dotenv()
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        raise ValueError(
            "CEREBRAS_API_KEY not set — add it to your .env file "
            '(or in PowerShell run: $env:CEREBRAS_API_KEY="csk-...")'
        )

    client = OpenAI(base_url="https://api.cerebras.ai/v1", api_key=api_key)
    model  = os.environ.get("CEREBRAS_MODEL", "gemma-4-31b")
    effort = os.environ.get("CEREBRAS_EFFORT", "none")

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: API connection confirmed."}],
        reasoning_effort=effort,
        max_tokens=200,
    )
    print("Model used:  ", response.model)
    print("Response:    ", response.choices[0].message.content)
    print("Tokens used: ", response.usage.total_tokens if response.usage else None)
    print("Time info:   ", getattr(response, "time_info", None))


if __name__ == "__main__":
    main()
