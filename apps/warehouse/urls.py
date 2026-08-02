from django.urls import path
from . import views

app_name = 'warehouse'

urlpatterns = [
    path('', views.warehouse_list, name='warehouse_list'),
    path('new/', views.warehouse_create, name='warehouse_create'),
    path('<uuid:pk>/', views.warehouse_detail, name='warehouse_detail'),
    path('<uuid:pk>/edit/', views.warehouse_edit, name='warehouse_edit'),
    path('<uuid:pk>/delete/', views.warehouse_delete, name='warehouse_delete'),
    path('<uuid:pk>/delivery-history/', views.delivery_history, name='delivery_history'),
    path('receive/', views.stock_receive, name='stock_receive'),
    path('batches/', views.batch_list, name='batch_list'),
    path('batch/<uuid:pk>/edit/',   views.batch_edit,   name='batch_edit'),
    path('batch/<uuid:pk>/delete/', views.batch_delete, name='batch_delete'),
    path('valuation/', views.valuation_report, name='valuation'),
    path('fifo-preview/', views.fifo_preview, name='fifo_preview'),
    path('delivery/<uuid:delivery_pk>/exit/', views.delivery_exit, name='delivery_exit'),
    path('delivery/<uuid:delivery_pk>/cancel/', views.delivery_cancel, name='delivery_cancel'),
]