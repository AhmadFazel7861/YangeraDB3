# سرمایه دکان — Integration Guide
# =====================================
# Follow these steps EXACTLY. Do NOT touch any existing app logic.

# ─────────────────────────────────────
# STEP 1: Copy the app folder
# ─────────────────────────────────────
# Copy the entire `capital_app/` folder into your project as:
#   apps/capital/
#
# Your structure should look like:
#   apps/
#     capital/
#       __init__.py
#       apps.py
#       models.py
#       services.py
#       views.py
#       urls.py
#       migrations/
#         __init__.py
#         0001_initial.py
#       templates/
#         capital/
#           dashboard.html

# ─────────────────────────────────────
# STEP 2: settings.py — add the app
# ─────────────────────────────────────
# In your INSTALLED_APPS list, add:

    'apps.capital.apps.CapitalConfig',

# ─────────────────────────────────────
# STEP 3: urls.py (main) — add the URL
# ─────────────────────────────────────
# In your root urls.py, add this line inside urlpatterns:

    path('capital/', include('apps.capital.urls', namespace='capital')),

# ─────────────────────────────────────
# STEP 4: Run migrations
# ─────────────────────────────────────

    python manage.py migrate

# ─────────────────────────────────────
# STEP 5: Sidebar — add menu item
# ─────────────────────────────────────
# Find wherever your sidebar_menu is built (likely a context_processor
# or a view that passes sidebar_menu to templates).
# Add this entry in the appropriate position (e.g. after مصارف):

    {
        'label': 'سرمایه دکان',
        'icon': 'bi-safe2',
        'url': reverse('capital:dashboard'),   # or just '/capital/'
    },

# ─────────────────────────────────────
# STEP 6: Verify the invoice_detail URL
# ─────────────────────────────────────
# The template uses:
#   {% url 'sales:invoice_detail' p.invoice.pk %}
# Make sure this URL name exists in your sales/urls.py.
# If your URL name is different (e.g. 'sales:detail'), update line ~175
# in templates/capital/dashboard.html accordingly.

# ─────────────────────────────────────
# STEP 7: Verify the banker:detail URL
# ─────────────────────────────────────
# The template uses:
#   {% url 'banker:detail' banker.pk %}
# Make sure this exists in your banker/urls.py.
# If different, update line ~322 in the template.

# ─────────────────────────────────────
# NOTHING ELSE CHANGES
# ─────────────────────────────────────
# - No existing models touched
# - No existing services touched
# - No existing templates touched
# - The ShopIncomeTransfer model is new (its own table)
# - BankerService.record_transaction() is called (already exists, untouched)
