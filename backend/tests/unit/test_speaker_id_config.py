from backend.core.config import settings


def test_speaker_id_defaults():
    assert settings.SPEAKER_ID_ENABLED is True
    assert settings.SPEAKER_ID_MODEL_SOURCE == "speechbrain/spkrec-ecapa-voxceleb"
    assert settings.SPEAKER_ID_THRESHOLD == 0.70
    assert settings.SPEAKER_ID_MIN_DURATION_S == 1.0
    assert settings.SPEAKER_ID_CACHE_DIR == "./models/speechbrain"
    assert settings.SPEAKER_ID_REQUIRE_LIVENESS is False
