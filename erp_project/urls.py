from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

handler404 = 'apps.core.views.error_404'
handler500 = 'apps.core.views.error_500'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', lambda request: redirect('dashboard:index'), name='home'),
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),
    path('dashboard/', include('apps.dashboard.urls', namespace='dashboard')),
    path('inventory/', include('apps.inventory.urls', namespace='inventory')),
    path('warehouse/', include('apps.warehouse.urls', namespace='warehouse')),
    path('sales/', include('apps.sales.urls', namespace='sales')),
    path('customers/', include('apps.customers.urls', namespace='customers')),
    path('suppliers/', include('apps.suppliers.urls', namespace='suppliers')),
    path('purchases/', include('apps.purchases.urls', namespace='purchases')),
    path('expenses/', include('apps.expenses.urls', namespace='expenses')),
    path('currency/', include('apps.currency.urls', namespace='currency')),
    path('capital/', include('apps.capital.urls', namespace='capital')),
    path('loans/', include('apps.loans.urls', namespace='loans')),
    path('banker/', include('apps.banker.urls', namespace='banker')),
    path('reports/', include('apps.reports.urls', namespace='reports')),
    path('alerts/', include('apps.alerts.urls', namespace='alerts')),
    path('backups/', include('apps.backup_system.urls', namespace='backups')),
    path('activity-logs/', include('apps.activity_logs.urls', namespace='activity_logs')),
    path('settings/', include('apps.settings_app.urls', namespace='settings_app')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)