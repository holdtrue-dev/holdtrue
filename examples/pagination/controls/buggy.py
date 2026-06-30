from models import Page, PageRequest


def paginate(req: PageRequest) -> Page:
    # bug: floor division drops the last partial page
    return Page(
        offset=(req.page - 1) * req.page_size,
        limit=req.page_size,
        total_pages=req.total // req.page_size,
    )
