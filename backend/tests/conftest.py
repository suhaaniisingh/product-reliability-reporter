"""Shared test setup.

Every test gets a FakeExtractor and a FakeResolver in place of the real ones, so no
test can reach a live LLM or real DNS by accident. Tests that need specific answers
change the fakes' settings.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_domain_resolver, get_extractor, get_signals
from app.extraction.fake import FakeExtractor, FakeResolver
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    """Run `@pytest.mark.anyio` tests on asyncio only (the default also tries trio)."""
    return "asyncio"


@pytest.fixture
def fake_extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def fake_resolver() -> FakeResolver:
    return FakeResolver()


@pytest.fixture
def fake_signals() -> list:
    """Signals used by the `client` fixture. Empty by default; tests append FakeSignals."""
    return []


@pytest.fixture
def client(fake_extractor: FakeExtractor, fake_resolver: FakeResolver, fake_signals: list) -> Iterator[TestClient]:
    app.dependency_overrides[get_extractor] = lambda: fake_extractor
    app.dependency_overrides[get_domain_resolver] = lambda: fake_resolver
    app.dependency_overrides[get_signals] = lambda: fake_signals
    yield TestClient(app)
    app.dependency_overrides.clear()
