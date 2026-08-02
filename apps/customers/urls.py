from django.urls import path
from . import views

app_name = 'customers'

urlpatterns = [
    path('', views.customer_list, name='customer_list'),
    path('new/', views.customer_create, name='customer_create'),
    path('debts/', views.customer_debts, name='customer_debts'),
    path('<uuid:pk>/', views.customer_detail, name='customer_detail'),
    path('<uuid:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('<uuid:pk>/delete/', views.customer_delete, name='customer_delete'),
    path('<uuid:pk>/statement/', views.customer_statement, name='customer_statement'),
    path('tx/<uuid:tx_pk>/reverse/', views.reverse_transaction, name='reverse_transaction'),
    path('api/search/', views.customer_search_ajax, name='customer_search_ajax'),
]