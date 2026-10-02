import os
from langchain.chat_models import init_chat_model

def get_llm():
    provider = os.getenv("LLM_PROVIDER", "google_genai")
    p_model = os.getenv("LLM_MODEL")
    if not p_model:
        raise RuntimeError("LLM_MODEL is not set in environment")
    
    p_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    kwargs_p = {}
    if p_key: kwargs_p["api_key"] = p_key
    
    primary = init_chat_model(p_model, model_provider=provider, **kwargs_p)
    
    f_model = os.getenv("LLM_MODEL_FALLBACK")
    f_key = os.getenv("GOOGLE_API_KEY_FALLBACK")
    
    if f_model or f_key:
        fb_model = f_model or p_model
        fb_key = f_key or p_key
        
        kwargs_f = {}
        if fb_key: kwargs_f["api_key"] = fb_key
        
        fallback = init_chat_model(fb_model, model_provider=provider, **kwargs_f)
        return primary.with_fallbacks([fallback])
        
    return primary
