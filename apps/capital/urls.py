from django.urls import path
from . import views

app_name = 'capital'

urlpatterns = [
    path('', views.capital_dashboard, name='dashboard'),
    path('transfer/', views.transfer_to_banker, name='transfer_to_banker'),
]
