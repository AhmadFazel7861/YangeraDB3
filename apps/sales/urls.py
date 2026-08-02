from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    path('', views.invoice_list, name='invoice_list'),
    path('new/', views.invoice_create, name='invoice_create'),
    path('<uuid:pk>/', views.invoice_detail, name='invoice_detail'),
    path('<uuid:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('<uuid:pk>/print/', views.invoice_print, name='invoice_print'),
    path('<uuid:pk>/cancel/', views.invoice_cancel, name='invoice_cancel'),

    # AJAX
    path('api/product-price/', views.get_product_price, name='product_price_api'),
    path('api/customer-info/', views.get_customer_info, name='customer_info_api'),
    path('api/warehouse-stock/', views.get_warehouse_stock, name='warehouse_stock_api'),
]