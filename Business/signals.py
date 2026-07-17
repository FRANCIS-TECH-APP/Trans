from django.db.models.signals import post_save
from django.dispatch import receiver
from Business.models import Shipment, TransitCheckpoint, Payment


@receiver(post_save, sender=Shipment)
def on_shipment_created(sender, instance, created, **kwargs):
    if not created:
        return
    context = {
        "shipment":    instance,
        "tracking_id": instance.tracking_id,
    }


@receiver(post_save, sender=TransitCheckpoint)
def on_checkpoint_added(sender, instance, created, **kwargs):
    if not created:
        return
    shipment = instance.shipment
    context  = {
        "shipment":   shipment,
        "checkpoint": instance,
        "new_status": shipment.get_status_display(),
    }


@receiver(post_save, sender=Payment)
def on_payment_updated(sender, instance, created, **kwargs):
    if instance.status == "paid" and instance.paid_at:
        context = {
            "shipment": instance.shipment,
            "payment":  instance,
        }
        



