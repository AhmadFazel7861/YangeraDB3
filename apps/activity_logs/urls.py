from django.urls import path
from . import views

app_name = 'activity_logs'

urlpatterns = [
    path('', views.log_list, name='log_list'),
]