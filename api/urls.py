from django.urls import path
from api.views import AvailableSlotsView, BookView
from api.views_ops import schedule_view, preview_api, apply_api

app_name = 'api'

urlpatterns = [
    path('available-slots/', AvailableSlotsView.as_view(), name='available-slots'),
    path('book/', BookView.as_view(), name='book'),
    path('ops/schedule/', schedule_view, name='ops-schedule'),
    path('ops/preview/', preview_api, name='ops-preview'),
    path('ops/apply/', apply_api, name='ops-apply'),
]

