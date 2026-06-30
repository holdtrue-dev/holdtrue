from hypothesis import given, strategies as st

from core import paginate
from models import PageRequest

_reqs = st.builds(
    PageRequest,
    total=st.integers(min_value=0, max_value=100_000),
    page_size=st.integers(min_value=1, max_value=100),
    page=st.integers(min_value=1, max_value=1000),
)


@given(_reqs)
def test_page_maths(req: PageRequest) -> None:
    p = paginate(req)
    assert p.offset == (req.page - 1) * req.page_size
    assert p.limit == req.page_size
    assert p.total_pages == (req.total + req.page_size - 1) // req.page_size
    assert p.offset >= 0
