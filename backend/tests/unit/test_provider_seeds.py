from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

EXPECTED = {
    "openai": ["gpt-5.6", "gpt-5.6-mini", "gpt-5.1", "o4-mini"],
    "anthropic": ["claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5"],
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
    "groq": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "deepseek-r1-distill-llama-70b"],
    "mistral": ["mistral-large-latest", "mistral-small-latest", "codestral-latest"],
    "together": ["meta-llama/Llama-3.3-70B-Instruct-Turbo", "Qwen/Qwen2.5-72B-Instruct-Turbo", "deepseek-ai/DeepSeek-R1"],
    "cohere": ["command-r-plus", "command-r"],
    "moonshot": ["kimi-k2", "moonshot-v1-32k", "moonshot-v1-128k"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "azure_openai": ["gpt-5.6", "gpt-5.1", "gpt-4o"],
    "local": ["llama3.1", "mistral", "gemma2", "qwen2"],
}

def test_provider_seeds_are_current():
    res = client.get("/api/v1/models/providers")
    assert res.status_code == 200
    by_name = {p["name"]: p for p in res.json()}
    for name, models in EXPECTED.items():
        assert by_name[name]["popular_models"] == models, name
