from django.apps import AppConfig

class CustomersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.customers'
    verbose_name = 'مشتریان'

    def ready(self):
        import apps.customers.signals  # noqa