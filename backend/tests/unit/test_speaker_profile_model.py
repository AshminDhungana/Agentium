import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.database import Base
from backend.models.entities.speaker_profile import SpeakerProfile


@pytest.fixture
def session():
    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    s = Session()
    yield s
    s.close()
    eng.dispose()


def test_is_deleted_column_is_mapped(session):
    p = SpeakerProfile(id="p1", name="Alice", embedding=[0.1, 0.2], is_deleted=False)
    session.add(p)
    session.commit()
    got = session.query(SpeakerProfile).filter(SpeakerProfile.is_deleted == False).first()
    assert got is not None
    assert got.is_deleted is False


def test_soft_delete_sets_flag(session):
    p = SpeakerProfile(id="p2", name="Bob", embedding=[0.3], is_deleted=False)
    session.add(p)
    session.commit()
    p.soft_delete()
    session.commit()
    assert p.is_deleted is True
    visible = session.query(SpeakerProfile).filter(SpeakerProfile.is_deleted == False).all()
    assert visible == []


def test_to_dict_includes_is_deleted(session):
    p = SpeakerProfile(id="p3", name="Cara", embedding=[0.4], is_deleted=True)
    session.add(p)
    session.commit()
    assert p.to_dict()["is_deleted"] is True
