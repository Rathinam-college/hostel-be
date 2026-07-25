from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings
import os

urlpatterns = [
    path('api/', include('api.urls')),
    path('hostel/api/', include('api.urls')),
]

# Serve built frontend static files from /app/fe/dist
from django.views.static import serve
urlpatterns += [
    re_path(r'^(?:hostel/)?assets/(?P<path>.*)$', serve, {
        'document_root': os.path.join(settings.FRONTEND_DIR, 'assets')
    }),
    re_path(r'^assets/(?P<path>.*)$', serve, {
        'document_root': os.path.join(settings.FRONTEND_DIR, 'assets')
    }),
    re_path(r'^$', TemplateView.as_view(template_name='index.html')),
    re_path(r'^(?!api/|hostel/api/|assets/|hostel/assets/).*$', TemplateView.as_view(template_name='index.html')),
]
