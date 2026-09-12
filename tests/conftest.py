from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def library():
    return FIXTURES / "library.ttl"


@pytest.fixture
def library_extra():
    return FIXTURES / "library-extra.ttl"


@pytest.fixture
def tiny_nt():
    return FIXTURES / "tiny.nt"


@pytest.fixture
def library_trig():
    return FIXTURES / "library.trig"


@pytest.fixture
def tiny_nq():
    return FIXTURES / "tiny.nq"
