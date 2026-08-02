from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('', views.expense_list, name='expense_list'),
    path('new/', views.expense_create, name='expense_create'),
    path('report/', views.expense_report, name='expense_report'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/new/', views.category_create, name='category_create'),
    path('categories/<uuid:pk>/edit/', views.category_edit, name='category_edit'),
    path('<uuid:pk>/edit/', views.expense_edit, name='expense_edit'),
    path('<uuid:pk>/delete/', views.expense_delete, name='expense_delete'),
    path('<uuid:pk>/settle-saraf/', views.settle_saraf_debt, name='settle_saraf_debt'),
]