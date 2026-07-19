import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Business', '0009_category_alter_buylogs_category'),
    ]

    operations = [

        # Step 1 — Fix category id field
        migrations.AlterField(
            model_name='category',
            name='id',
            field=models.BigAutoField(
                auto_created=True,
                primary_key=True,
                serialize=False,
                verbose_name='ID',
            ),
        ),

        # Step 2 — Insert default categories AND fix null rows in one go
        migrations.RunSQL(
            sql=[
                # Insert common categories
                "INSERT OR IGNORE INTO Business_category (name, slug, icon, is_active, \"order\") VALUES ('Facebook', 'facebook', 'fab fa-facebook', 1, 1)",
                "INSERT OR IGNORE INTO Business_category (name, slug, icon, is_active, \"order\") VALUES ('WhatsApp', 'whatsapp', 'fab fa-whatsapp', 1, 2)",
                "INSERT OR IGNORE INTO Business_category (name, slug, icon, is_active, \"order\") VALUES ('Google', 'google', 'fab fa-google', 1, 3)",
                "INSERT OR IGNORE INTO Business_category (name, slug, icon, is_active, \"order\") VALUES ('Other', 'other', '', 1, 99)",
                # Update ALL buylogs rows to point to facebook category
                "UPDATE Business_buylogs SET category_id = (SELECT id FROM Business_category WHERE slug = 'facebook' LIMIT 1)",
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),

        # Step 3 — NOW make FK non-nullable (all rows already have valid category_id)
        migrations.AlterField(
            model_name='buylogs',
            name='category',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='products',
                to='Business.category',
            ),
        ),

    ]