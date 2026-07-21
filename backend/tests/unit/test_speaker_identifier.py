import hashlib
import math
import wave
import io
import struct

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock

from backend.models.database import Base
from backend.models.entities.speaker_profile import SpeakerProfile
from backend.services.audio_service import (
    SpeakerIdentifier,
    SpeakerIDConfig,
    SpeechBrainEncoder,
)


# --- helpers ---------------------------------------------------------------

def _make_wav(duration_s=1.0, framerate=16000, amp=0):
    buf = io.BytesIO()
    n = int(duration_s * framerate)
    samples = [amp] * n
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(struct.pack("<%dh" % n, *samples))
    return buf.getvalue()


class FakeEncoder:
    """Deterministic, torch-free embedder: identical bytes -> identical vector."""
    def __init__(self, dim=8):
        self.dim = dim

    def embed(self, audio_bytes: bytes):
        h = hashlib.sha256(audio_bytes).digest()
        vec = [((h[i % len(h)] / 255.0) - 0.5) for i in range(self.dim)]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class CountingEncoder(FakeEncoder):
    def __init__(self):
        super().__init__()
        self.calls = 0

    def embed(self, audio_bytes):
        self.calls += 1
        return super().embed(audio_bytes)


def _cfg(**kw):
    defaults = dict(
        enabled=True, model_source="x", threshold=0.70,
        min_duration_s=1.0, cache_dir="/tmp", require_liveness=False,
    )
    defaults.update(kw)
    return SpeakerIDConfig(**defaults)


@pytest.fixture
def session():
    eng = create_engine("sqlite://")
    SpeakerProfile.__table__.create(eng, checkfirst=True)
    Session = sessionmaker(bind=eng)
    s = Session()
    yield s
    s.close()
    eng.dispose()


# --- tests -----------------------------------------------------------------

def test_enroll_creates_profile(session):
    si = SpeakerIdentifier(classifier=FakeEncoder(), config=_cfg())
    clip = _make_wav(1.0, amp=1)
    prof = si.enroll(session, "u1", "Alice", clip)
    assert prof is not None
    assert prof.name == "Alice"
    assert prof.is_deleted is False
    assert session.query(SpeakerProfile).count() == 1


def test_identify_known_speaker(session):
    si = SpeakerIdentifier(classifier=FakeEncoder(), config=_cfg())
    clip = _make_wav(1.0, amp=7)
    si.enroll(session, "u1", "Alice", clip)
    res = si.identify(session, clip)
    assert res["is_known"] is True
    assert res["name"] == "Alice"
    assert res["confidence"] >= 0.99


def test_identify_unknown_speaker(session):
    si = SpeakerIdentifier(classifier=FakeEncoder(), config=_cfg())
    si.enroll(session, "u1", "Alice", _make_wav(1.0, amp=3))
    other = _make_wav(1.0, amp=9)
    res = si.identify(session, other)
    assert res["is_known"] is False
    assert res["speaker_id"] == "unknown"


def test_identify_skips_too_short_audio(session):
    enc = CountingEncoder()
    si = SpeakerIdentifier(classifier=enc, config=_cfg(min_duration_s=1.0))
    si.enroll(session, "u1", "Alice", _make_wav(1.0, amp=2))
    short = _make_wav(0.1, amp=2)
    res = si.identify(session, short)
    assert res["is_known"] is False
    assert enc.calls == 1


def test_enroll_returns_none_when_disabled(session):
    si = SpeakerIdentifier(classifier=FakeEncoder(), config=_cfg(enabled=False))
    assert si.enroll(session, "u1", "Alice", _make_wav(1.0)) is None


def test_identify_returns_unknown_when_disabled(session):
    si = SpeakerIdentifier(classifier=FakeEncoder(), config=_cfg(enabled=False))
    res = si.identify(session, _make_wav(1.0))
    assert res["is_known"] is False
    assert res["speaker_id"] == "unknown"


def test_liveness_rejects_spoof_on_enroll(session):
    si = SpeakerIdentifier(
        classifier=FakeEncoder(),
        config=_cfg(require_liveness=True),
        liveness_check=lambda audio: False,
    )
    assert si.enroll(session, "u1", "Alice", _make_wav(1.0)) is None


def test_liveness_rejects_spoof_on_identify(session):
    si = SpeakerIdentifier(
        classifier=FakeEncoder(),
        config=_cfg(require_liveness=True),
        liveness_check=lambda audio: False,
    )
    si.enroll(session, "u1", "Alice", _make_wav(1.0, amp=1))
    res = si.identify(session, _make_wav(1.0, amp=1))
    assert res["is_known"] is False
    assert res["speaker_id"] == "unknown"


def test_liveness_allows_when_live(session):
    si = SpeakerIdentifier(
        classifier=FakeEncoder(),
        config=_cfg(require_liveness=True),
        liveness_check=lambda audio: True,
    )
    clip = _make_wav(1.0, amp=4)
    si.enroll(session, "u1", "Alice", clip)
    res = si.identify(session, clip)
    assert res["is_known"] is True


def test_is_available_false_when_disabled():
    si = SpeakerIdentifier(classifier=FakeEncoder(), config=_cfg(enabled=False))
    assert si.is_available() is False


def test_is_available_true_with_injected_encoder():
    si = SpeakerIdentifier(classifier=FakeEncoder(), config=_cfg(enabled=True))
    assert si.is_available() is True


def test_speechbrain_encoder_is_speaker_encoder():
    assert hasattr(SpeechBrainEncoder, "embed")


from backend.services.audio_service import AudioService


def test_status_includes_speaker_id_fields():
    svc = AudioService()
    status = svc.get_status(db=MagicMock(), user_id="u1")
    assert "speaker_id_enabled" in status
    assert "speaker_id_available" in status
    assert isinstance(status["speaker_id_enabled"], bool)
