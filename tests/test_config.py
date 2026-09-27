def test_env_example_contains_required_database_keys():
    from pathlib import Path

    text = Path(".env.example").read_text(encoding="utf-8")
    assert "POSTGRES_DSN=" in text
    assert "POSTGRES_HOST_PORT=15432" in text
    assert "MAX_ARTICLES_PER_PAGE=20" in text
