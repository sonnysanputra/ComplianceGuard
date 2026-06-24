import os
from openai import OpenAI

# ---- Config (override via environment / .env if you like) ----
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:7b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

_client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")


# ======================================================================
# LLM
# ======================================================================
def chat(prompt: str, system: str | None = None, temperature: float = 0.2) -> str:
    """Single LLM call to Qwen. Low temperature for consistent compliance output."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = _client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()


def embed(texts: list[str]) -> list[list[float]]:
    """Turn strings into vectors using the local embed model."""
    resp = _client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]
