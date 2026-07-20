from backend.models.entities.constitution import Ethos


def _make_ethos(**kwargs) -> Ethos:
    base = dict(
        agentium_id="E30001",
        agent_type="task_agent",
        mission_statement="Do tasks.",
        core_values="[]",
        behavioral_rules="[]",
        restrictions="[]",
        capabilities="[]",
        created_by_agentium_id="00001",
        agent_id="00000000-0000-0000-0000-000000000001",
    )
    base.update(kwargs)
    return Ethos(**base)


def test_ethos_has_working_method_column():
    assert "working_method" in Ethos.__table__.columns
    ethos = _make_ethos()
    ethos.working_method = "read ethos then act"
    assert ethos.working_method == "read ethos then act"


def test_to_dict_includes_working_method():
    ethos = _make_ethos(working_method="read ethos then act")
    d = ethos.to_dict()
    assert d["working_method"] == "read ethos then act"
    assert isinstance(d["capabilities"], list)


def test_compress_preserves_working_method():
    ethos = _make_ethos(version=1, working_method="read ethos then act")
    ethos.compress()
    assert ethos.working_method == "read ethos then act"


def test_clear_working_state_preserves_working_method():
    ethos = _make_ethos(working_method="read ethos then act")
    ethos.clear_working_state()
    assert ethos.working_method == "read ethos then act"


def test_apply_llm_compression_preserves_working_method():
    ethos = _make_ethos(version=1, working_method="read ethos then act")
    ethos.apply_llm_compression({"outcome_summary": "done"})
    assert ethos.working_method == "read ethos then act"
    assert ethos.outcome_summary == "done"
