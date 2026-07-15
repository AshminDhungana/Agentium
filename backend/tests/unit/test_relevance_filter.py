from backend.services import knowledge_service
from backend.core.config import settings as _settings


def test_min_relevance_helper_off_by_default():
    assert knowledge_service._passes_min_relevance(0.01, _settings.EMBEDDING_MIN_RELEVANCE) is True


def test_min_relevance_helper_filters_low():
    # threshold 0.35 -> relevance 0.2 must fail, 0.5 must pass
    assert knowledge_service._passes_min_relevance(0.2, 0.35) is False
    assert knowledge_service._passes_min_relevance(0.5, 0.35) is True
