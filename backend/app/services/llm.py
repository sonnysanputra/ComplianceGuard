from openai import OpenAI

from app.core.config import (
    LLM_BASE_URL,
    LLM_API_KEY,
    EMBED_BASE_URL,
    EMBED_API_KEY,
    CHAT_MODEL,
    EMBED_MODEL,
)

# One OpenAI-compatible client for chat, one for embeddings (they may point at
# different providers). With the defaults both target local Ollama.
_chat_client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)
_embed_client = OpenAI(base_url=EMBED_BASE_URL, api_key=EMBED_API_KEY)


# ======================================================================
# LLM
# ======================================================================
def chat(prompt: str, system: str | None = None, temperature: float = 0.2) -> str:
    """Single chat completion. Low temperature for consistent compliance output."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = _chat_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()


def embed(texts: list[str]) -> list[list[float]]:
    """Turn strings into vectors using the configured embedding model."""
    resp = _embed_client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]
