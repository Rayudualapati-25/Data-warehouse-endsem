import os

from huggingface_hub import InferenceClient

from utils.env_loader import load_environments

_DEFAULT_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
_DEFAULT_TIMEOUT = 30

_cached_client: InferenceClient | None = None
_cached_token: str | None = None


def _get_client() -> InferenceClient:
    global _cached_client, _cached_token
    load_environments()
    token = os.getenv("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN is required")
    timeout = int(os.getenv("HF_TIMEOUT_SEC", str(_DEFAULT_TIMEOUT)))
    if _cached_client is not None and _cached_token == token:
        return _cached_client
    _cached_client = InferenceClient(token=token, timeout=timeout)
    _cached_token = token
    return _cached_client


def hf_generate(prompt: str, model_override: str | None = None, temperature: float = 0.01) -> str:
    load_environments()
    model = model_override or os.getenv("HF_MODEL", _DEFAULT_MODEL)
    client = _get_client()

    response = client.text_generation(
        prompt,
        model=model,
        max_new_tokens=1024,
        temperature=max(temperature, 0.01),
        return_full_text=False,
    )

    text = response.strip() if isinstance(response, str) else str(response).strip()
    if not text:
        raise RuntimeError(f"HF model '{model}' returned empty response")
    return text
