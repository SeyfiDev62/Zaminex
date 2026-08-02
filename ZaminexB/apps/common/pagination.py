from rest_framework.pagination import PageNumberPagination

class StandardResultsSetPagination(PageNumberPagination):
    """
    Server-side pagination for large lists (properties, listings).
    Supports ?page= and ?page_size= (e.g. page_size=10 or 20).
    Frontend Pagination component expects total count via `count` field.
    """
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 1000
    page_query_param = "page"
