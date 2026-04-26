import os

from groq import Groq

from utils.env_loader import load_environments

_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_DEFAULT_TIMEOUT = 30

_cached_client: Groq | None = None
_cached_key: str | None = None


def _get_client() -> Groq:
    global _cached_client, _cached_key
    load_environments()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is required")
    timeout = int(os.getenv("GROQ_TIMEOUT_SEC", str(_DEFAULT_TIMEOUT)))
    if _cached_client is not None and _cached_key == api_key:
        return _cached_client
    _cached_client = Groq(api_key=api_key, timeout=timeout)
    _cached_key = api_key
    return _cached_client


def groq_generate(prompt: str, model_override: str | None = None, temperature: float = 0.01) -> str:
    load_environments()
    model = model_override or os.getenv("GROQ_MODEL", _DEFAULT_MODEL)
    client = _get_client()

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=max(temperature, 0.01),
    )

    text = (response.choices[0].message.content or "").strip()
    if not text:
        raise RuntimeError(f"Groq model '{model}' returned empty response")
    return text
