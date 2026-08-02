from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Categories
    path('categories/', views.category_list, name='category_list'),
    path('categories/new/', views.category_create, name='category_create'),
    path('categories/<uuid:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<uuid:pk>/delete/', views.category_delete, name='category_delete'),

    # Units
    path('units/', views.unit_list, name='unit_list'),
    path('units/new/', views.unit_create, name='unit_create'),
    path('units/<uuid:pk>/edit/', views.unit_edit, name='unit_edit'),
    path('units/<uuid:pk>/delete/', views.unit_delete, name='unit_delete'),

    # Products
    path('products/', views.product_list, name='product_list'),
    path('products/new/', views.product_create, name='product_create'),
    path('products/<uuid:pk>/', views.product_detail, name='product_detail'),
    path('products/<uuid:pk>/edit/', views.product_edit, name='product_edit'),
    path('products/<uuid:pk>/delete/', views.product_delete, name='product_delete'),
    path('products/<uuid:pk>/toggle/', views.product_toggle_active, name='product_toggle'),
    path('products/<uuid:pk>/adjust/', views.stock_adjust, name='stock_adjust'),
]