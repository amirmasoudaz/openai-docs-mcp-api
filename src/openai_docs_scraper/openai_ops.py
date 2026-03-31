from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from . import env as _env_dotenv  # loads .env (see env.py)

del _env_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential_jitter


@dataclass(frozen=True)
class OpenAIModels:
    summary_model: str = "gpt-5-nano"
    embedding_model: str = "text-embedding-3-small"
    answer_model: str = "gpt-5-nano"


def _client() -> OpenAI:
    return OpenAI()


@retry(wait=wait_exponential_jitter(initial=1, max=20), stop=stop_after_attempt(5))
def summarize_very_short(*, text: str, model: str, max_chars: int = 20_000) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    text = text[:max_chars]

    client = _client()
    resp = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You summarize OpenAI API documentation pages for retrieval. "
                    "Write a VERY short summary: 1–2 sentences, plain text, no bullets, no hype. "
                    "State what the page is for and who it helps."
                ),
            },
            {"role": "user", "content": text},
        ],
    )

    out = getattr(resp, "output_text", None)
    if isinstance(out, str) and out.strip():
        return out.strip()
    # Fallback if SDK shape changes.
    return str(resp).strip()


@retry(wait=wait_exponential_jitter(initial=1, max=20), stop=stop_after_attempt(5))
def embed_texts(*, texts: list[str], model: str) -> list[list[float]]:
    client = _client()
    resp = client.embeddings.create(model=model, input=texts)
    return [d.embedding for d in resp.data]


@retry(wait=wait_exponential_jitter(initial=1, max=20), stop=stop_after_attempt(5))
def answer_with_citations(*, question: str, evidence: list[dict[str, str]], model: str) -> str:
    client = _client()
    evidence_lines = []
    for item in evidence:
        evidence_lines.append(
            "\n".join(
                [
                    f"[{item['index']}] title: {item['title']}",
                    f"[{item['index']}] url: {item['url']}",
                    f"[{item['index']}] file: {item['md_relpath']}",
                    f"[{item['index']}] snippet: {item['snippet']}",
                ]
            )
        )

    resp = client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "Answer questions strictly from the provided documentation evidence. "
                    "Do not use outside knowledge. "
                    "If the evidence is insufficient, say so directly. "
                    "Every factual claim must include bracket citations like [1] or [2]. "
                    "Use only the citation numbers provided in the evidence."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    "Evidence:\n"
                    + "\n\n".join(evidence_lines)
                ),
            },
        ],
    )

    out = getattr(resp, "output_text", None)
    if isinstance(out, str) and out.strip():
        return out.strip()
    return str(resp).strip()
