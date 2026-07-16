from sqlalchemy import create_engine, text


def test_skills_embedding_server_default_is_bge():
    import os
    url = os.environ.get("DATABASE_URL", "postgresql://agentium:agentium@localhost:5432/agentium_test")
    eng = create_engine(url)
    with eng.connect() as conn:
        row = conn.execute(text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name='skills' AND column_name='embedding_model'"
        )).fetchone()
        assert row is not None
        assert "bge-base-en-v1.5" in (row[0] or "")
