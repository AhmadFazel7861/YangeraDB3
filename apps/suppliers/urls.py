from django.urls import path
from . import views

app_name = 'suppliers'

urlpatterns = [
    path('', views.supplier_list, name='supplier_list'),
    path('new/', views.supplier_create, name='supplier_create'),
    path('debts/', views.supplier_debts, name='supplier_debts'),
    path('<uuid:pk>/', views.supplier_detail, name='supplier_detail'),
    path('<uuid:pk>/edit/', views.supplier_edit, name='supplier_edit'),
    path('<uuid:pk>/delete/', views.supplier_delete, name='supplier_delete'),
    path('<uuid:pk>/statement/', views.supplier_statement, name='supplier_statement'),
    path('<uuid:pk>/offset/', views.mutual_offset, name='mutual_offset'),
    path('tx/<uuid:tx_pk>/reverse/', views.reverse_transaction, name='reverse_transaction'),
    path('api/search/', views.supplier_search_ajax, name='supplier_search_ajax'),
]