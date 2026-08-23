from django.db.models.signals import post_save
from django.dispatch import receiver

from .delivery import register_delivery_case
from .models import Incident, ServiceDeskCase


@receiver(post_save, sender=Incident)
@receiver(post_save, sender=ServiceDeskCase)
def maintain_delivery_case(sender, instance, raw=False, **kwargs):
    if not raw:
        register_delivery_case(instance)
