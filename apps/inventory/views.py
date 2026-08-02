"""
Inventory Views — Phase 2
Category, Unit, Product CRUD + Stock History
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Category, Unit, Product, StockHistory
from .forms import CategoryForm, UnitForm, ProductForm


# ══════════════════════════════════════════════════════════════
# CATEGORY VIEWS
# ══════════════════════════════════════════════════════════════

@login_required
def category_list(request):
    search = request.GET.get('q', '').strip()
    qs = Category.objects.filter(is_deleted=False).order_by('name')
    if search:
        qs = qs.filter(name__icontains=search)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventory/category_list.html', {
        'page_title': 'دسته‌بندی‌ها',
        'categories': page,
        'search': search,
        'total': paginator.count,
    })


@login_required
def category_create(request):
    form = CategoryForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'دسته‌بندی با موفقیت ثبت شد.')
        return redirect('inventory:category_list')
    return render(request, 'inventory/category_form.html', {
        'page_title': 'دسته‌بندی جدید',
        'form': form,
        'action': 'ثبت',
    })


@login_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk, is_deleted=False)
    form = CategoryForm(request.POST or None, instance=category)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'دسته‌بندی با موفقیت ویرایش شد.')
        return redirect('inventory:category_list')
    return render(request, 'inventory/category_form.html', {
        'page_title': 'ویرایش دسته‌بندی',
        'form': form,
        'action': 'ویرایش',
        'object': category,
    })


@login_required
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk, is_deleted=False)
    if category.products.filter(is_deleted=False).exists():
        messages.error(request, 'این دسته‌بندی دارای محصول است و قابل حذف نیست.')
        return redirect('inventory:category_list')
    category.is_deleted = True
    category.deleted_at = timezone.now()
    category.save(update_fields=['is_deleted', 'deleted_at'])
    messages.success(request, 'دسته‌بندی حذف شد.')
    return redirect('inventory:category_list')


# ══════════════════════════════════════════════════════════════
# UNIT VIEWS
# ══════════════════════════════════════════════════════════════

@login_required
def unit_list(request):
    search = request.GET.get('q', '').strip()
    qs = Unit.objects.filter(is_deleted=False).order_by('name')
    if search:
        qs = qs.filter(Q(name__icontains=search) | Q(abbreviation__icontains=search))

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'inventory/unit_list.html', {
        'page_title': 'واحدهای اندازه‌گیری',
        'units': page,
        'search': search,
        'total': paginator.count,
    })


@login_required
def unit_create(request):
    form = UnitForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'واحد با موفقیت ثبت شد.')
        return redirect('inventory:unit_list')
    return render(request, 'inventory/unit_form.html', {
        'page_title': 'واحد جدید',
        'form': form,
        'action': 'ثبت',
    })


@login_required
def unit_edit(request, pk):
    unit = get_object_or_404(Unit, pk=pk, is_deleted=False)
    form = UnitForm(request.POST or None, instance=unit)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'واحد با موفقیت ویرایش شد.')
        return redirect('inventory:unit_list')
    return render(request, 'inventory/unit_form.html', {
        'page_title': 'ویرایش واحد',
        'form': form,
        'action': 'ویرایش',
        'object': unit,
    })


@login_required
@require_POST
def unit_delete(request, pk):
    unit = get_object_or_404(Unit, pk=pk, is_deleted=False)
    if unit.products.filter(is_deleted=False).exists():
        messages.error(request, 'این واحد در محصولات استفاده شده و قابل حذف نیست.')
        return redirect('inventory:unit_list')
    unit.is_deleted = True
    unit.deleted_at = timezone.now()
    unit.save(update_fields=['is_deleted', 'deleted_at'])
    messages.success(request, 'واحد حذف شد.')
    return redirect('inventory:unit_list')


# ══════════════════════════════════════════════════════════════
# PRODUCT VIEWS
# ══════════════════════════════════════════════════════════════

@login_required
def product_list(request):
    search = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '')
    stock_filter = request.GET.get('stock', '')

    qs = Product.objects.filter(is_deleted=False).select_related('category', 'unit')

    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(code__icontains=search) |
            Q(barcode__icontains=search) |
            Q(name_en__icontains=search)
        )

    if category_filter:
        qs = qs.filter(category_id=category_filter)

    if stock_filter == 'low':
        from django.db.models import F
        qs = qs.filter(minimum_stock__gt=0, current_stock__lte=F('minimum_stock'))
    elif stock_filter == 'out':
        qs = qs.filter(current_stock__lte=0)

    qs = qs.order_by('name')
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get('page'))

    categories = Category.objects.filter(is_active=True, is_deleted=False).order_by('name')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return render(request, 'inventory/partials/product_rows.html', {
            'products': page,
        })

    return render(request, 'inventory/product_list.html', {
        'page_title': 'محصولات',
        'products': page,
        'categories': categories,
        'search': search,
        'category_filter': category_filter,
        'stock_filter': stock_filter,
        'total': paginator.count,
    })


@login_required
def product_create(request):
    form = ProductForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        product = form.save()
        messages.success(request, f'محصول «{product.name}» با موفقیت ثبت شد.')
        if request.POST.get('save_and_new'):
            return redirect('inventory:product_create')
        return redirect('inventory:product_list')
    return render(request, 'inventory/product_form.html', {
        'page_title': 'محصول جدید',
        'form': form,
        'action': 'ثبت',
    })


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, is_deleted=False)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'محصول «{product.name}» ویرایش شد.')
        return redirect('inventory:product_list')
    return render(request, 'inventory/product_form.html', {
        'page_title': 'ویرایش محصول',
        'form': form,
        'action': 'ویرایش',
        'object': product,
    })


@login_required
def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related('category', 'unit'),
        pk=pk, is_deleted=False
    )
    history = StockHistory.objects.filter(
        product=product
    ).select_related('created_by').order_by('-created_at')[:50]

    return render(request, 'inventory/product_detail.html', {
        'page_title': product.name,
        'product': product,
        'history': history,
    })


@login_required
@require_POST
def product_delete(request, pk):
    from apps.warehouse.models import StockBatch
    product = get_object_or_404(Product, pk=pk, is_deleted=False)
    name = product.name

    # Check remaining stock using Django's Sum (not models.Sum)
    total_stock = StockBatch.objects.filter(
        product=product,
        remaining_quantity__gt=0,
        is_deleted=False,
    ).aggregate(total=Sum('remaining_quantity'))['total'] or 0

    if total_stock > 0:
        messages.error(
            request,
            f'محصول «{name}» دارای {total_stock} واحد موجودی در انبار است. '
            f'ابتدا موجودی را به صفر برسانید سپس حذف کنید.'
        )
        return redirect('inventory:product_list')

    # Zero out all batches
    StockBatch.objects.filter(
        product=product,
        is_deleted=False,
    ).update(
        remaining_quantity=0,
        is_deleted=True,
        deleted_at=timezone.now(),
    )

    product.current_stock = 0
    product.is_deleted = True
    product.deleted_at = timezone.now()
    product.save(update_fields=['current_stock', 'is_deleted', 'deleted_at', 'updated_at'])

    messages.success(request, f'محصول «{name}» و تمام بچ‌های آن حذف شدند.')
    return redirect('inventory:product_list')


@login_required
@require_POST
def product_toggle_active(request, pk):
    product = get_object_or_404(Product, pk=pk, is_deleted=False)
    product.is_active = not product.is_active
    product.save(update_fields=['is_active', 'updated_at'])
    return JsonResponse({
        'success': True,
        'is_active': product.is_active,
        'label': 'فعال' if product.is_active else 'غیرفعال',
    })


# ══════════════════════════════════════════════════════════════
# STOCK ADJUSTMENT VIEW
# ══════════════════════════════════════════════════════════════

@login_required
def stock_adjust(request, pk):
    product = get_object_or_404(Product, pk=pk, is_deleted=False)

    if request.method == 'POST':
        try:
            qty = float(request.POST.get('quantity', 0))
            movement_type = request.POST.get('movement_type', 'adjustment')
            notes = request.POST.get('notes', '')
            unit_cost = request.POST.get('unit_cost') or None
            if unit_cost:
                unit_cost = float(unit_cost)

            from .services import StockService
            from decimal import Decimal

            StockService.adjust_stock(
                product=product,
                quantity=Decimal(str(qty)),
                movement_type=movement_type,
                unit_cost=Decimal(str(unit_cost)) if unit_cost else None,
                notes=notes,
                user=request.user,
            )
            messages.success(request, 'موجودی با موفقیت تعدیل شد.')
        except ValueError as e:
            messages.error(request, str(e))

        return redirect('inventory:product_detail', pk=pk)

    return render(request, 'inventory/stock_adjust.html', {
        'page_title': f'تعدیل موجودی — {product.name}',
        'product': product,
        'movement_types': StockHistory.MovementType.choices,
    })