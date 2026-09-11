from src import config


def test_urls_are_https():
    assert config.OPENAI_RSS_URL.startswith("https://")
    assert config.HF_API_BASE.startswith("https://")
    assert config.MS_SEARCH_URL.startswith("https://")
    assert config.OPENROUTER_MODELS_URL.startswith("https://")


def test_watchlists_are_lists():
    assert isinstance(config.HF_ORGS, list) and config.HF_ORGS
    assert isinstance(config.MS_KEYWORDS, list) and config.MS_KEYWORDS
    assert isinstance(config.GH_REPOS, list)
    assert isinstance(config.HN_QUERIES, list) and config.HN_QUERIES


def test_microsoft_org_map_keys_match_keywords():
    for kw in config.MS_KEYWORDS:
        assert kw in config.MS_ORG_MAP


def test_tuning_constants():
    assert config.MAX_CANDIDATES_PER_JUDGE == 60
    assert config.SKIP_OLDER_THAN_HOURS == 48
    assert config.DEEPSEEK_MODEL == "deepseek-chat"
