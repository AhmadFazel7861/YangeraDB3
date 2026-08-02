from django.urls import path
from . import views

app_name = 'purchases'

urlpatterns = [
    path('', views.purchase_list, name='purchase_list'),
    path('new/', views.purchase_create, name='purchase_create'),
    path('<uuid:pk>/', views.purchase_detail, name='purchase_detail'),
    path('<uuid:pk>/edit/', views.purchase_edit, name='purchase_edit'),
    path('<uuid:pk>/print/', views.purchase_print, name='purchase_print'),
    path('<uuid:pk>/delete/', views.purchase_delete, name='purchase_delete'),
]