from unittest.mock import patch, MagicMock

import pytest

# Skip the whole file if the heavy ML stack is not installed in this env.
pytest.importorskip("speechbrain")
pytest.importorskip("torchaudio")

# API-PATH CHECK: in SpeechBrain 1.1.0 the class is in .classifiers, not .speaker
from speechbrain.inference.classifiers import EncoderClassifier  # must import
from backend.services.audio_service import (
    SpeechBrainEncoder,
    SpeakerIdentifier,
    SpeakerIDConfig,
)


def _cfg(**kw):
    defaults = dict(
        enabled=True, model_source="x", threshold=0.70,
        min_duration_s=1.0, cache_dir="/tmp", require_liveness=False,
    )
    defaults.update(kw)
    return SpeakerIDConfig(**defaults)


def test_real_encoder_construction_does_not_download():
    # Constructing the adapter must NOT trigger from_hparams() (network/model load).
    enc = SpeechBrainEncoder(model_source="speechbrain/spkrec-ecapa-voxceleb", cache_dir="/tmp/sb_test")
    assert enc._classifier is None


def test_real_encoder_exposes_encode_batch():
    assert hasattr(EncoderClassifier, "encode_batch")


def test_is_available_true_with_injected_classifier():
    si = SpeakerIdentifier(classifier=MagicMock(), config=_cfg())
    assert si.is_available() is True


def test_is_available_false_when_backend_missing():
    si = SpeakerIdentifier(config=_cfg())
    with patch.object(SpeakerIdentifier, "_backend_importable", return_value=False):
        assert si.is_available() is False


def test_identify_unknown_when_backend_missing():
    si = SpeakerIdentifier(classifier=None, config=_cfg())
    with patch.object(SpeakerIdentifier, "_backend_importable", return_value=False):
        res = si.identify(db=MagicMock(), audio_bytes=b"x")
    assert res["is_known"] is False
    assert res["speaker_id"] == "unknown"
