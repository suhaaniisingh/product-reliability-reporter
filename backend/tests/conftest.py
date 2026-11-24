"""Shared test setup.

Every test gets a FakeExtractor in place of the real one, so no test can reach a
live LLM by accident. Tests that need a specific result swap in their own fake.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_extractor
from app.extraction.fake import FakeExtractor
from app.main import app


@pytest.fixture
def fake_extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def client(fake_extractor: FakeExtractor) -> Iterator[TestClient]:
    app.dependency_overrides[get_extractor] = lambda: fake_extractor
    yield TestClient(app)
    app.dependency_overrides.clear()
