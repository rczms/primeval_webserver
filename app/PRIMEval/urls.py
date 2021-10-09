from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from submission import views as submission_views

urlpatterns = [
    path('', submission_views.UploadView.as_view(), name='home'),
    path('arvi/', submission_views.ARVIUploadView.as_view(), name='arvi'),

    path('run/<int:runid>/status', submission_views.RunStatusJSONView.as_view()),
    path('run/<int:runid>/<action>', submission_views.RunView.as_view(), name='run'),
    path('run/<int:runid>', submission_views.RunView.as_view(), {'action': 'results'}, name='run'),
    path('run/<int:runid>/heatmap/<sheet>/<dtype>', submission_views.HeatmapView.as_view(), name='heatmap'),

    path('runserver/download/<key>', submission_views.RunserverDownloadView.as_view()),
    path('runserver/update/<key>/<int:runid>/<step>/<substep>/<int:running>/<int:finished>/<error_message>', submission_views.RunserverUpdateView.as_view()),
    path('runserver/update/<key>/<int:runid>/<step>/<substep>/<int:running>/<int:finished>/', submission_views.RunserverUpdateView.as_view()),
    path('runserver/upload/<key>/<int:runid>', submission_views.RunserverUploadView.as_view()),

    path('help', submission_views.HelpView.as_view(), name = "help"),
    path('impressum', submission_views.ImpressumView.as_view(), name = "impressum"),

    path('admin/', admin.site.urls),
]

if bool(settings.DEBUG):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
