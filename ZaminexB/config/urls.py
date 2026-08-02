from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from apps.properties.views import property_list
from . import views 

admin.site.site_header = "مدیریت زمینکس"
admin.site.site_title = "مدیریت زمینکس"
admin.site.index_title = "مدیریت زمینکس"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.dashboard, name="dashboard"),
    path("accounts/", include("apps.accounts.urls")),
    path("properties/", include("apps.properties.urls")),
    path("listings/", include("apps.listings.urls")),
    path("followupa/api/", include("apps.followups.urls")),
    path("tasks/api/", include("apps.tasks.urls")),
    path("common/api/", include("apps.common.urls")),
    path("basics/api/", include("apps.basics.urls")),
    path("", include("apps.reports.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
