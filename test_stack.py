"""
Quick stack check for CompliGuard AI.
Confirms three things work before we build any agents:
  1. Qwen (via Ollama) responds to a chat request
  2. Ollama embeddings work
  3. ChromaDB can store + retrieve policy docs by similarity (RAG)

Run:  python test_stack.py
"""

from openai import OpenAI
import chromadb

# ---- Connect to Ollama (it speaks the OpenAI API format) ----
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

CHAT_MODEL = "qwen2.5:7b"
EMBED_MODEL = "nomic-embed-text"


def embed(texts):
    """Turn a list of strings into vectors using the local embed model."""
    resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


# ======================================================================
# 1. Test Qwen chat
# ======================================================================
print("=== 1. Testing Qwen chat ===")
resp = client.chat.completions.create(
    model=CHAT_MODEL,
    messages=[
        {"role": "user", "content": "In one sentence, what is structuring in money laundering?"}
    ],
)
print(resp.choices[0].message.content.strip())


# ======================================================================
# 2 + 3. Test ChromaDB + embeddings (this is your RAG layer)
# ======================================================================
print("\n=== 2. Testing ChromaDB + embeddings (RAG) ===")

chroma = chromadb.Client()  # in-memory, just for this test
collection = chroma.create_collection("aml_policies")

policies = [
    "AML Escalation Procedure 4.2: transactions with unusual volume or new high-risk "
    "recipients must be escalated for Level 2 compliance review.",
    "KYC Review Procedure: declared income must be consistent with transaction volume; "
    "mismatches require enhanced due diligence.",
    "Watchlist Screening Procedure: any sanctions or PEP match must be reported to the "
    "compliance officer immediately.",
]

# Embed once and store (this is the 'embed-once' efficiency pattern)
collection.add(
    ids=["p1", "p2", "p3"],
    documents=policies,
    embeddings=embed(policies),
)

query = "customer made many large transfers to a new overseas recipient"
results = collection.query(query_embeddings=embed([query]), n_results=1)

print("Query:", query)
print("Most relevant policy retrieved:")
print(" ->", results["documents"][0][0])

print("\n✅ Stack works: Qwen + ChromaDB + embeddings are all functional.")
