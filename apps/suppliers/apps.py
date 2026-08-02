from django.apps import AppConfig

class SuppliersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.suppliers'
    verbose_name = 'تامین‌کنندگان'

    def ready(self):
        import apps.suppliers.signals  # noqa