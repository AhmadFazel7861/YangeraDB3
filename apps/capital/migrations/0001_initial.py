from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('banker', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ShopIncomeTransfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('banker', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='shop_income_transfers',
                    to='banker.banker',
                    verbose_name='صراف'
                )),
                ('amount', models.DecimalField(
                    decimal_places=2, max_digits=16,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
                    verbose_name='مبلغ انتقال'
                )),
                ('currency', models.CharField(
                    choices=[('AFN', 'افغانی ؋'), ('USD', 'دالر $')],
                    default='AFN', max_length=3, verbose_name='واحد پول'
                )),
                ('transfer_date', models.DateField(verbose_name='تاریخ انتقال')),
                ('notes', models.TextField(blank=True, verbose_name='یادداشت')),
                ('created_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='shop_income_transfers',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='ثبت‌کننده'
                )),
            ],
            options={
                'verbose_name': 'انتقال دخل دکان به صراف',
                'verbose_name_plural': 'انتقال‌های دخل دکان به صراف',
                'db_table': 'capital_shop_income_transfer',
                'ordering': ['-transfer_date', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='shopincometransfer',
            index=models.Index(fields=['-transfer_date'], name='capital_sit_date_idx'),
        ),
        migrations.AddIndex(
            model_name='shopincometransfer',
            index=models.Index(fields=['banker'], name='capital_sit_banker_idx'),
        ),
        migrations.AddIndex(
            model_name='shopincometransfer',
            index=models.Index(fields=['currency'], name='capital_sit_currency_idx'),
        ),
    ]
