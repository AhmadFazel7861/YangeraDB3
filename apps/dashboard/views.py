from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View


@method_decorator(login_required, name='dispatch')
class DashboardView(View):
    template_name = 'dashboard/index.html'

    def get(self, request):
        from apps.reports.services import ReportService
        stats = ReportService.get_dashboard_stats()
        return render(request, self.template_name, {
            'page_title': 'داشبورد',
            **stats,
        })