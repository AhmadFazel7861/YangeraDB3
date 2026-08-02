from django.urls import path
from . import views

app_name = 'alerts'

urlpatterns = [
    path('', views.alert_list, name='alert_list'),
    path('refresh/', views.refresh_alerts, name='refresh'),
    path('mark-all-read/', views.mark_all_read, name='mark_all_read'),
    path('<uuid:pk>/read/', views.mark_read, name='mark_read'),
    path('<uuid:pk>/dismiss/', views.dismiss, name='dismiss'),
    path('api/count/', views.get_alert_count, name='get_count'),
]