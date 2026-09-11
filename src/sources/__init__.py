from . import anthropic, deepseek, github, hf, hn, modelscope, openai, openrouter, qwen, reddit

ALL_SOURCES = [
    ("openai", openai.fetch),
    ("anthropic", anthropic.fetch),
    ("qwen", qwen.fetch),
    ("deepseek", deepseek.fetch),
    ("hf", hf.fetch),
    ("modelscope", modelscope.fetch),
    ("openrouter", openrouter.fetch),
    ("github", github.fetch),
    ("reddit", reddit.fetch),
    ("hn", hn.fetch),
]
