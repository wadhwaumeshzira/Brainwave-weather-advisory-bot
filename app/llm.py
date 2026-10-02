import os
import logging
from langchain.chat_models import init_chat_model

logger = logging.getLogger(__name__)

def get_llm():
    provider = os.getenv("LLM_PROVIDER", "google_genai")
    p_model = os.getenv("LLM_MODEL")
    if not p_model:
        raise RuntimeError("LLM_MODEL is not set in environment")

    key_env_map = {"google_genai": "GOOGLE_API_KEY", "openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "groq": "GROQ_API_KEY"}
    key_env = key_env_map.get(provider, f"{provider.upper()}_API_KEY")
    p_key = os.getenv(key_env)
    if provider == "google_genai" and not p_key:
        p_key = os.getenv("GEMINI_API_KEY")

    kwargs_p = {}
    if p_key: kwargs_p["api_key"] = p_key

    primary = init_chat_model(p_model, model_provider=provider, **kwargs_p)

    f_model = os.getenv("LLM_MODEL_FALLBACK")
    f_key = os.getenv(f"{key_env}_FALLBACK")

    if f_model or f_key:
        try:
            fb_model = f_model or p_model
            fb_key = f_key or p_key

            kwargs_f = {}
            if fb_key: kwargs_f["api_key"] = fb_key

            # Fallback uses same provider as primary — cross-provider fallback is not supported.
            # If the model name is incompatible with the provider, this will silently skip fallback.
            fallback = init_chat_model(fb_model, model_provider=provider, **kwargs_f)
            return primary.with_fallbacks([fallback])
        except Exception as e:
            # Bad fallback config (e.g. gemini model name with groq provider) — log and continue without fallback.
            logger.warning(f"Fallback LLM init failed ({e}), running without fallback.")

    return primary
