"""
Loans App URLs
"""
from django.urls import path
from . import views

app_name = 'loans'

urlpatterns = [
    # Person CRUD
    path('', views.person_list, name='person_list'),
    path('new/', views.person_create, name='person_create'),
    path('<uuid:pk>/', views.person_detail, name='person_detail'),
    path('<uuid:pk>/edit/', views.person_edit, name='person_edit'),
    path('<uuid:pk>/delete/', views.person_delete, name='person_delete'),

    # Transaction actions
    path('transaction/<uuid:tx_pk>/reverse/', views.reverse_transaction, name='reverse_transaction'),
]
