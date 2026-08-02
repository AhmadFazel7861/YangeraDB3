from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('sales/', views.sales_report, name='sales_report'),
    path('purchases/', views.purchase_report, name='purchase_report'),
    path('profit-loss/', views.profit_loss, name='profit_loss'),
    path('inventory/', views.inventory_report, name='inventory_report'),
    path('financial/', views.financial_summary, name='financial_summary'),
]