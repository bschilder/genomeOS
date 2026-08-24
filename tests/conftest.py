import os

os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from sqlalchemy.orm import sessionmaker

from genomeos.db import Base, make_engine


@pytest.fixture()
def db_session():
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
