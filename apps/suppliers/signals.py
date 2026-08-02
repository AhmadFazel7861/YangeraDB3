from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Supplier


@receiver(post_save, sender=Supplier)
def initialize_supplier_opening_balance(sender, instance, created, **kwargs):
    if created and instance.opening_balance > 0:
        from .services.accounting import SupplierAccountingService
        SupplierAccountingService.initialize_opening_balance(instance)