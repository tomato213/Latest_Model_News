from src.sources import ALL_SOURCES


def test_registry_has_all_10_sources():
    names = [n for n, _ in ALL_SOURCES]
    assert names == ["openai", "anthropic", "qwen", "deepseek", "hf",
                     "modelscope", "openrouter", "github", "reddit", "hn"]
    assert all(callable(f) for _, f in ALL_SOURCES)
