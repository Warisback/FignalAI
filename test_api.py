import os
from dotenv import load_dotenv
from openai import OpenAI

# load variables from .env into the environment
load_dotenv()

# load key from environment
api_key = os.environ.get("CEREBRAS_API_KEY")
if not api_key:
    raise ValueError(
        "CEREBRAS_API_KEY not set — add it to your .env file "
        '(or in PowerShell run: $env:CEREBRAS_API_KEY="csk-...")'
    )

client = OpenAI(
    base_url="https://api.cerebras.ai/v1",
    api_key=api_key,
)

# Models available on this key: zai-glm-4.7, gpt-oss-120b
response = client.chat.completions.create(
    model="gpt-oss-120b",
    messages=[{"role": "user", "content": "Reply with exactly: API connection confirmed."}],
    max_tokens=200,  # gpt-oss-120b is a reasoning model — needs room beyond the answer itself
)

print("Response:", response.choices[0].message.content)
print("Model used:", response.model)
print("Tokens used:", response.usage.total_tokens)
print("Time info:", response.time_info)