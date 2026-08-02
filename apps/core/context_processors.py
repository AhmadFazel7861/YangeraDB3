from django.conf import settings


def site_settings(request):
    """Inject business settings + alerts into every template."""
    from django.utils import timezone
    from django.conf import settings as django_settings

    usd_rate    = None
    alert_count = 0
    biz_name      = getattr(django_settings, 'BUSINESS_NAME', '')
    biz_name_en   = ''
    biz_phone1    = getattr(django_settings, 'BUSINESS_PHONE_1', '')
    biz_phone2    = getattr(django_settings, 'BUSINESS_PHONE_2', '')
    biz_address   = getattr(django_settings, 'BUSINESS_ADDRESS', '')
    biz_email     = ''
    biz_logo      = None
    default_currency        = getattr(django_settings, 'DEFAULT_CURRENCY', 'AFN')
    designer_credit         = getattr(django_settings, 'DESIGNER_CREDIT', 'YangEra')
    invoice_footer_text     = 'با تشکر از خرید شما'
    invoice_show_fifo_cost  = False
    credit_warning_amount   = None
    low_stock_threshold     = 10
    backup_reminder_days    = 1
    log_retention_days      = 90

    # Load from DB settings if available — this is the single source of
    # truth for everything configurable on the settings page.
    try:
        from apps.settings_app.models import BusinessSettings
        s = BusinessSettings.get_solo()
        biz_name      = s.business_name or biz_name
        biz_name_en   = s.business_name_en or biz_name_en
        biz_phone1    = s.phone1 or biz_phone1
        biz_phone2    = s.phone2 or biz_phone2
        biz_address   = s.address or biz_address
        biz_email     = s.email or biz_email
        biz_logo      = s.logo if s.logo else None
        default_currency       = s.default_currency or default_currency
        designer_credit        = s.designer_credit or designer_credit
        invoice_footer_text    = s.invoice_footer_text or invoice_footer_text
        invoice_show_fifo_cost = s.invoice_show_fifo_cost
        credit_warning_amount  = s.credit_warning_amount
        low_stock_threshold    = s.low_stock_threshold
        backup_reminder_days   = s.backup_reminder_days
        log_retention_days     = s.log_retention_days
    except Exception:
        pass

    try:
        from apps.currency.models import ExchangeRate
        today = timezone.now().date()
        rate_obj = ExchangeRate.objects.filter(
            currency__code='USD',
            rate_date__lte=today,
        ).order_by('-rate_date').first()
        if rate_obj:
            usd_rate = rate_obj.rate_to_afn
    except Exception:
        pass

    if request.user.is_authenticated:
        try:
            from apps.alerts.services import AlertService
            alert_count = AlertService.get_unread_count()
        except Exception:
            pass

    return {
        'BUSINESS_NAME':       biz_name,
        'BUSINESS_NAME_EN':    biz_name_en,
        'BUSINESS_PHONE_1':    biz_phone1,
        'BUSINESS_PHONE_2':    biz_phone2,
        'BUSINESS_ADDRESS':    biz_address,
        'BUSINESS_EMAIL':      biz_email,
        'BUSINESS_LOGO':       biz_logo,
        'DEFAULT_CURRENCY':    default_currency,
        'DESIGNER_CREDIT':     designer_credit,
        'INVOICE_FOOTER_TEXT':       invoice_footer_text,
        'INVOICE_SHOW_FIFO_COST':    invoice_show_fifo_cost,
        'CREDIT_WARNING_AMOUNT':     credit_warning_amount,
        'LOW_STOCK_THRESHOLD':       low_stock_threshold,
        'BACKUP_REMINDER_DAYS':      backup_reminder_days,
        'LOG_RETENTION_DAYS':        log_retention_days,
        'TODAY_USD_RATE':      usd_rate,
        'ALERT_COUNT':         alert_count,
    }


def sidebar_context(request):
    if not request.user.is_authenticated:
        return {}

    menu = [
        {
            'label': 'داشبورد',
            'icon': 'bi-speedometer2',
            'url': '/dashboard/',
        },
        {
            'label': 'محصولات',
            'icon': 'bi-box-seam',
            'url': '#',
            'children': [
                {'label': 'لیست محصولات',     'icon': 'bi-list-ul',    'url': '/inventory/products/'},
                {'label': 'محصول جدید',        'icon': 'bi-plus-circle','url': '/inventory/products/new/'},
                {'label': 'دسته‌بندی‌ها',      'icon': 'bi-tags',       'url': '/inventory/categories/'},
                {'label': 'واحد اندازه‌گیری', 'icon': 'bi-rulers',     'url': '/inventory/units/'},
            ],
        },
        {
            'label': 'انبار',
            'icon': 'bi-building',
            'url': '#',
            'children': [
                {'label': 'انبارها',        'icon': 'bi-building',          'url': '/warehouse/'},
                {'label': 'دریافت موجودی', 'icon': 'bi-box-arrow-in-down', 'url': '/warehouse/receive/'},
                {'label': 'لیست بچ‌ها',    'icon': 'bi-stack',             'url': '/warehouse/batches/'},
                {'label': 'ارزیابی انبار', 'icon': 'bi-graph-up',          'url': '/warehouse/valuation/'},
            ],
        },
        {
            'label': 'فروش',
            'icon': 'bi-cart3',
            'url': '#',
            'children': [
                {'label': 'فاکتورهای فروش', 'icon': 'bi-receipt',     'url': '/sales/'},
                {'label': 'فاکتور جدید',    'icon': 'bi-plus-circle', 'url': '/sales/new/'},
            ],
        },
        {
            'label': 'خریداری',
            'icon': 'bi-truck',
            'url': '#',
            'children': [
                {'label': 'فاکتورهای خرید', 'icon': 'bi-receipt-cutoff', 'url': '/purchases/'},
                {'label': 'خرید جدید',      'icon': 'bi-plus-circle',    'url': '/purchases/new/'},
            ],
        },
        {
            'label': 'مشتریان',
            'icon': 'bi-people',
            'url': '#',
            'children': [
                {'label': 'لیست مشتریان',  'icon': 'bi-people',              'url': '/customers/'},
                {'label': 'مشتری جدید',    'icon': 'bi-person-plus',         'url': '/customers/new/'},
                {'label': 'گزارش بدهی‌ها', 'icon': 'bi-exclamation-triangle', 'url': '/customers/debts/'},
            ],
        },
        {
            'label': 'تامین‌کنندگان',
            'icon': 'bi-person-workspace',
            'url': '#',
            'children': [
                {'label': 'لیست تامین‌کنندگان', 'icon': 'bi-people',              'url': '/suppliers/'},
                {'label': 'تامین‌کننده جدید',   'icon': 'bi-person-plus',         'url': '/suppliers/new/'},
                {'label': 'بدهی‌های ما',         'icon': 'bi-exclamation-triangle', 'url': '/suppliers/debts/'},
            ],
        },
        {
            'label': 'مصارف',
            'icon': 'bi-cash-stack',
            'url': '#',
            'children': [
                {'label': 'لیست مصارف',   'icon': 'bi-list-ul',    'url': '/expenses/'},
                {'label': 'مصرف جدید',    'icon': 'bi-plus-circle','url': '/expenses/new/'},
                {'label': 'گزارش مصارف',  'icon': 'bi-bar-chart',  'url': '/expenses/report/'},
                {'label': 'دسته‌بندی‌ها', 'icon': 'bi-tags',       'url': '/expenses/categories/'},
            ],
        },
        # ↓ ADD THIS BLOCK
        {
            'label': 'سرمایه دکان',
            'icon': 'bi-safe2',
            'url': '/capital/',
        },
        {
            'label': 'قرضه‌ها',
            'icon': 'bi-cash-stack',
            'url': '/loans/',
        },
        {
            'label': 'ارز و صراف',
            'icon': 'bi-cash-coin',
            'url': '#',
            'children': [
                {'label': 'داشبورد صراف',    'icon': 'bi-speedometer',      'url': '/banker/'},
                {'label': 'لیست صرافان',     'icon': 'bi-people',           'url': '/banker/bankers/'},
                {'label': 'صراف جدید',       'icon': 'bi-person-plus',      'url': '/banker/bankers/new/'},
                {'label': 'تراکنش جدید',     'icon': 'bi-plus-circle',      'url': '/banker/transaction/new/'},
                {'label': 'گزارش صراف',      'icon': 'bi-bar-chart',        'url': '/banker/report/'},
                {'label': 'نرخ‌های ارز',     'icon': 'bi-graph-up',         'url': '/currency/'},
                {'label': 'ثبت نرخ جدید',   'icon': 'bi-plus-circle',      'url': '/currency/rates/new/'},
            ],
        },
        {
            'label': 'گزارشات',
            'icon': 'bi-bar-chart-line',
            'url': '#',
            'children': [
                {'label': 'گزارش فروش',    'icon': 'bi-cart3',          'url': '/reports/sales/'},
                {'label': 'گزارش خریداری', 'icon': 'bi-truck',          'url': '/reports/purchases/'},
                {'label': 'سود و زیان',    'icon': 'bi-graph-up-arrow', 'url': '/reports/profit-loss/'},
                {'label': 'گزارش موجودی',  'icon': 'bi-boxes',          'url': '/reports/inventory/'},
                {'label': 'خلاصه مالی',    'icon': 'bi-clipboard-data', 'url': '/reports/financial/'},
            ],
        },
        {
            'label': 'تنظیمات',
            'icon': 'bi-gear',
            'url': '#',
            'children': [
                {'label': 'هشدارها',        'icon': 'bi-bell',             'url': '/alerts/'},
                {'label': 'بکاپ و بازیابی', 'icon': 'bi-cloud-arrow-down', 'url': '/backups/'},
                {'label': 'لاگ فعالیت‌ها',  'icon': 'bi-list-columns',     'url': '/activity-logs/'},
                {'label': 'تنظیمات سیستم',  'icon': 'bi-gear',             'url': '/settings/'},
            ],
        },
    ]

    return {'sidebar_menu': menu}