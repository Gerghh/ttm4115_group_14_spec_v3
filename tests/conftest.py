import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use an in-memory SQLite DB for tests
os.environ["DATABASE_URL"] = "sqlite:///./test_drones.db"

from app.db.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

TEST_ENGINE = create_engine(
    "sqlite:///./test_drones.db", connect_args={"check_same_thread": False}
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)
    if os.path.exists("test_drones.db"):
        os.remove("test_drones.db")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def seed_test_data(setup_test_db):
    """Re-seed before each test so tests are independent."""
    from app.db.seed import reseed_drones
    db = TestSessionLocal()
    try:
        reseed_drones(db)
    finally:
        db.close()
