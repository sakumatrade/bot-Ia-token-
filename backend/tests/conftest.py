from __future__ import annotations

import pytest

from broker_sakuma.config import Settings
from broker_sakuma.db.base import Base, make_engine, make_session_factory


@pytest.fixture()
def settings() -> Settings:
    return Settings(database={"url": "sqlite:///:memory:"})


@pytest.fixture()
def db_session(settings: Settings):
    engine = make_engine(settings.database.url)
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
