from django.urls import path
from . import views

app_name = 'currency'

urlpatterns = [
    path('', views.currency_list, name='currency_list'),
    path('rates/', views.rate_list, name='rate_list'),
    path('rates/new/', views.rate_create, name='rate_create'),
    path('rates/<uuid:pk>/edit/', views.rate_edit, name='rate_edit'),
    path('setup/', views.setup_currencies, name='setup_currencies'),

    # AJAX
    path('api/rate/', views.get_rate_ajax, name='get_rate_ajax'),
    path('api/convert/', views.convert_ajax, name='convert_ajax'),
]