from django.utils.deprecation import MiddlewareMixin
from .thread_locals import set_current_user, clear_current_user


class CurrentUserMiddleware(MiddlewareMixin):
    def process_request(self, request):
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            set_current_user(user)
        else:
            set_current_user(None)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        if user and getattr(user, "is_authenticated", False):
            set_current_user(user)
        else:
            set_current_user(None)

    def process_response(self, request, response):
        clear_current_user()
        return response

    def process_exception(self, request, exception):
        clear_current_user()
