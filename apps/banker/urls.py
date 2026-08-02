from django.urls import path
from . import views

app_name = 'banker'

urlpatterns = [
    # Dashboard
    path('', views.banker_dashboard, name='dashboard'),

    # Banker CRUD
    path('bankers/', views.banker_list, name='banker_list'),
    path('bankers/new/', views.banker_create, name='banker_create'),
    path('bankers/<uuid:pk>/', views.banker_detail, name='banker_detail'),
    path('bankers/<uuid:pk>/edit/', views.banker_edit, name='banker_edit'),
    path('bankers/<uuid:pk>/toggle/', views.banker_toggle_active, name='banker_toggle'),
    path('bankers/<uuid:pk>/recalculate/', views.recalculate_balance, name='recalculate'),

    # Transactions
    path('transaction/new/', views.transaction_create, name='transaction_create'),
    path('transaction/<uuid:pk>/delete/', views.transaction_delete, name='transaction_delete'),

    # Ledger
    path('ledger/<uuid:pk>/', views.ledger, name='ledger'),
    path('ledger/<uuid:pk>/print/', views.ledger_print, name='ledger_print'),

    # Reports
    path('report/', views.report, name='report'),

    # AJAX
    path('api/balance/', views.get_banker_balance, name='get_balance'),
    path('transfer/new/', views.banker_transfer, name='banker_transfer'),
]