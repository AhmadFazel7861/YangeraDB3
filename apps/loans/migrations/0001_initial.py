"""
Initial migration for the loans app.
Creates LoanPerson, LoanTransaction, LoanDakkhanEntry tables.
"""
import uuid
from decimal import Decimal
import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('banker', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LoanPerson',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='حذف شده')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='تاریخ حذف')),
                ('name', models.CharField(max_length=200, verbose_name='نام')),
                ('phone', models.CharField(blank=True, max_length=20, verbose_name='تلفن')),
                ('notes', models.TextField(blank=True, verbose_name='یادداشت')),
                ('is_active', models.BooleanField(default=True, verbose_name='فعال')),
                ('balance_afn', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18, verbose_name='مانده قرضه (افغانی)')),
                ('balance_usd', models.DecimalField(decimal_places=4, default=Decimal('0'), max_digits=18, verbose_name='مانده قرضه (دالر)')),
            ],
            options={
                'verbose_name': 'شخص قرضه‌گیر',
                'verbose_name_plural': 'اشخاص قرضه‌گیر',
                'db_table': 'loans_person',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='LoanTransaction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='حذف شده')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='تاریخ حذف')),
                ('tx_type', models.CharField(choices=[('given', 'دادن قرض'), ('received', 'بازپرداخت قرض')], max_length=20, verbose_name='نوع تراکنش')),
                ('currency', models.CharField(choices=[('AFN', 'افغانی'), ('USD', 'دالر')], default='AFN', max_length=3, verbose_name='ارز')),
                ('amount', models.DecimalField(decimal_places=4, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal('0.0001'))], verbose_name='مبلغ')),
                ('payment_method', models.CharField(choices=[('cash', 'نقدی'), ('saraf', 'صراف'), ('dakkan', 'دخل دکان')], default='cash', max_length=20, verbose_name='روش پرداخت')),
                ('balance_before_afn', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18, verbose_name='مانده AFN قبل')),
                ('balance_after_afn', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=18, verbose_name='مانده AFN بعد')),
                ('balance_before_usd', models.DecimalField(decimal_places=4, default=Decimal('0'), max_digits=18, verbose_name='مانده USD قبل')),
                ('balance_after_usd', models.DecimalField(decimal_places=4, default=Decimal('0'), max_digits=18, verbose_name='مانده USD بعد')),
                ('transaction_date', models.DateField(verbose_name='تاریخ')),
                ('notes', models.TextField(blank=True, verbose_name='یادداشت')),
                ('is_reversed', models.BooleanField(default=False, verbose_name='برگشت شده')),
                ('banker', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='loan_transactions', to='banker.banker', verbose_name='صراف')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='loan_transactions', to=settings.AUTH_USER_MODEL, verbose_name='ثبت‌کننده')),
                ('person', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='loans.loanperson', verbose_name='شخص')),
                ('reversed_by', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reversal_of', to='loans.loantransaction', verbose_name='برگشت داده شده توسط')),
            ],
            options={
                'verbose_name': 'تراکنش قرضه',
                'verbose_name_plural': 'تراکنش‌های قرضه',
                'db_table': 'loans_transaction',
                'ordering': ['-transaction_date', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LoanDakkhanEntry',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='آخرین ویرایش')),
                ('is_deleted', models.BooleanField(default=False, verbose_name='حذف شده')),
                ('deleted_at', models.DateTimeField(blank=True, null=True, verbose_name='تاریخ حذف')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=18, validators=[django.core.validators.MinValueValidator(Decimal('0.01'))], verbose_name='مبلغ')),
                ('currency', models.CharField(choices=[('AFN', 'افغانی'), ('USD', 'دالر')], default='AFN', max_length=3, verbose_name='ارز')),
                ('is_outflow', models.BooleanField(verbose_name='خروج از دخل دکان')),
                ('entry_date', models.DateField(verbose_name='تاریخ')),
                ('notes', models.TextField(blank=True, verbose_name='یادداشت')),
                ('loan_transaction', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='dakkan_entry', to='loans.loantransaction', verbose_name='تراکنش قرضه')),
            ],
            options={
                'verbose_name': 'ورودی دخل دکان قرضه',
                'verbose_name_plural': 'ورودی‌های دخل دکان قرضه',
                'db_table': 'loans_dakkan_entry',
                'ordering': ['-entry_date', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='loanperson',
            index=models.Index(fields=['name'], name='loans_perso_name_idx'),
        ),
        migrations.AddIndex(
            model_name='loanperson',
            index=models.Index(fields=['is_active'], name='loans_perso_active_idx'),
        ),
        migrations.AddIndex(
            model_name='loantransaction',
            index=models.Index(fields=['person', '-transaction_date'], name='loans_tx_person_date_idx'),
        ),
        migrations.AddIndex(
            model_name='loantransaction',
            index=models.Index(fields=['tx_type'], name='loans_tx_type_idx'),
        ),
        migrations.AddIndex(
            model_name='loantransaction',
            index=models.Index(fields=['currency'], name='loans_tx_currency_idx'),
        ),
        migrations.AddIndex(
            model_name='loantransaction',
            index=models.Index(fields=['payment_method'], name='loans_tx_method_idx'),
        ),
        migrations.AddIndex(
            model_name='loantransaction',
            index=models.Index(fields=['is_reversed'], name='loans_tx_reversed_idx'),
        ),
        migrations.AddIndex(
            model_name='loandakkhanentry',
            index=models.Index(fields=['-entry_date'], name='loans_dakkan_date_idx'),
        ),
        migrations.AddIndex(
            model_name='loandakkhanentry',
            index=models.Index(fields=['currency'], name='loans_dakkan_currency_idx'),
        ),
        migrations.AddIndex(
            model_name='loandakkhanentry',
            index=models.Index(fields=['is_outflow'], name='loans_dakkan_outflow_idx'),
        ),
    ]
