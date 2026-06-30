from hypothesis import given, strategies as st

from core import paginate
from models import PageRequest
from reference_impl import paginate as reference

_reqs = st.builds(
    PageRequest,
    total=st.integers(min_value=0, max_value=1_000_000),
    page_size=st.integers(min_value=1, max_value=100),
    page=st.integers(min_value=1, max_value=5000),
)


@given(_reqs)
def test_agrees_with_reference(req: PageRequest) -> None:
    assert paginate(req) == reference(req)
