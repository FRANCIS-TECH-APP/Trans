from django.db import migrations


def copy_credentials_forward(apps, schema_editor):
    BuyLogDetails = apps.get_model("Business", "BuyLogDetails")
    BuyLogDetailField = apps.get_model("Business", "BuyLogDetailField")

    for detail in BuyLogDetails.objects.all():
        order = 0
        if detail.email:
            BuyLogDetailField.objects.create(
                detail=detail, label="Email", value=detail.email,
                is_sensitive=True, sort_order=order,
            )
            order += 1
        if detail.password:
            BuyLogDetailField.objects.create(
                detail=detail, label="Password", value=detail.password,
                is_sensitive=True, sort_order=order,
            )
            order += 1
        if detail.recovery_email:
            BuyLogDetailField.objects.create(
                detail=detail, label="Recovery Email", value=detail.recovery_email,
                is_sensitive=True, sort_order=order,
            )
            order += 1
        if detail.two_factor_code:
            BuyLogDetailField.objects.create(
                detail=detail, label="2FA Code", value=detail.two_factor_code,
                is_sensitive=True, sort_order=order,
            )
            order += 1


def copy_credentials_backward(apps, schema_editor):
    """
    Reverse: push BuyLogDetailField values back onto the legacy
    columns by matching on label. Best-effort — only restores the
    four known labels; anything else added later is dropped on
    reverse migration.
    """
    BuyLogDetails = apps.get_model("Business", "BuyLogDetails")

    label_to_field = {
        "Email": "email",
        "Password": "password",
        "Recovery Email": "recovery_email",
        "2FA Code": "two_factor_code",
    }

    for detail in BuyLogDetails.objects.all():
        for field in detail.credential_fields.all():
            attr = label_to_field.get(field.label)
            if attr:
                setattr(detail, attr, field.value)
        detail.save()


class Migration(migrations.Migration):

    dependencies = [
        # Replace with the actual migration name generated in Step 1
        ("Business", "0002_alter_buylogdetails_email_and_more"),
    ]

    operations = [
        migrations.RunPython(copy_credentials_forward, copy_credentials_backward),
    ]