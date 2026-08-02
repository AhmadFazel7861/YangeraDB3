from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Customer


@receiver(post_save, sender=Customer)
def initialize_customer_opening_balance(sender, instance, created, **kwargs):
    """When a new customer is created with opening_balance > 0, record it."""
    if created and instance.opening_balance > 0:
        from .services.accounting import CustomerAccountingService
        CustomerAccountingService.initialize_opening_balance(instance)