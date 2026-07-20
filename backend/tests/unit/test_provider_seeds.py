from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

EXPECTED = {
    "openai": ["gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna"],
    "anthropic": ["claude-opus-4-8", "claude-sonnet-5", "claude-fable-5", "claude-haiku-4-5"],
    "gemini": ["gemini-3.5-pro", "gemini-3.5-flash", "gemini-3.5-flash-lite"],
    "groq": ["llama-4-scout-17b-16e-instruct", "llama-4-maverick-17b-128e-instruct", "deepseek-r1-distill-llama-70b"],
    "mistral": ["mistral-medium-latest", "mistral-small-latest", "codestral-latest"],
    "together": ["Qwen/Qwen3.7-Max", "deepseek-ai/DeepSeek-V4-Pro", "meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    "cohere": ["command-a-plus-05-2026", "command-a-03-2025", "command-a-reasoning-08-2025"],
    "moonshot": ["kimi-k2", "moonshot-v1-32k", "moonshot-v1-128k"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "azure_openai": ["gpt-5.6", "gpt-5.6-terra", "gpt-5.6-luna"],
    "local": ["llama3.3", "qwen2.5", "gemma2", "mistral"],
}

def test_provider_seeds_are_current():
    res = client.get("/api/v1/models/providers")
    assert res.status_code == 200
    by_name = {p["name"]: p for p in res.json()}
    for name, models in EXPECTED.items():
        assert by_name[name]["popular_models"] == models, name
