"""
Views for the backup dashboard.
"""
import mimetypes

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from .models import BackupRecord, BackupTarget
from .services import BackupService
from .tasks import run_backup_task


class DashboardView(LoginRequiredMixin, ListView):
    """Main dashboard — lists all backup records."""

    model = BackupRecord
    template_name = 'backups/dashboard.html'
    context_object_name = 'backups'
    paginate_by = 20

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        all_records = BackupRecord.objects.all()
        success_records = all_records.filter(status=BackupRecord.Status.SUCCESS)

        ctx['total_backups'] = all_records.count()
        ctx['successful_backups'] = success_records.count()
        ctx['failed_backups'] = all_records.filter(status=BackupRecord.Status.FAILED).count()

        # Total size of successful backups
        total_size = sum(r.file_size or 0 for r in success_records)
        ctx['total_size'] = self._format_size(total_size)

        # Last successful backup
        last_success = success_records.first()
        ctx['last_success'] = last_success

        # Active targets
        ctx['targets'] = BackupTarget.objects.filter(is_active=True)

        # Next scheduled run
        ctx['schedule_hour'] = settings.BACKUP_SCHEDULE_HOUR
        ctx['schedule_minute'] = settings.BACKUP_SCHEDULE_MINUTE

        # Running backups
        ctx['running_count'] = all_records.filter(
            status=BackupRecord.Status.RUNNING
        ).count()

        return ctx

    @staticmethod
    def _format_size(size_bytes):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f'{size_bytes:.1f} {unit}'
            size_bytes /= 1024
        return f'{size_bytes:.1f} TB'


class BackupDetailView(LoginRequiredMixin, DetailView):
    """Detail page for a single backup — shows logs and metadata."""

    model = BackupRecord
    template_name = 'backups/detail.html'
    context_object_name = 'backup'


class TriggerBackupView(LoginRequiredMixin, View):
    """Trigger a manual backup for a specific target."""

    def post(self, request):
        target_id = request.POST.get('target_id')
        if not target_id:
            messages.error(request, 'No target specified.')
            return redirect('dashboard')

        try:
            target = BackupTarget.objects.get(pk=target_id, is_active=True)
        except BackupTarget.DoesNotExist:
            messages.error(request, 'Target not found or inactive.')
            return redirect('dashboard')

        run_backup_task.delay(target.pk, triggered_by='manual')
        messages.success(
            request,
            f'Backup queued for "{target.name}". It will start shortly.',
        )
        return redirect('dashboard')


class DownloadBackupView(LoginRequiredMixin, View):
    """Stream a backup file for download."""

    def get(self, request, pk):
        record = get_object_or_404(BackupRecord, pk=pk)
        filepath = BackupService.get_backup_filepath(record)

        if filepath is None:
            raise Http404('Backup file not found on disk.')

        content_type, _ = mimetypes.guess_type(str(filepath))
        response = FileResponse(
            open(filepath, 'rb'),
            content_type=content_type or 'application/gzip',
        )
        response['Content-Disposition'] = f'attachment; filename="{record.filename}"'
        return response


class DeleteBackupView(LoginRequiredMixin, View):
    """Delete a backup record and its file."""

    def post(self, request, pk):
        record = get_object_or_404(BackupRecord, pk=pk)
        filepath = BackupService.get_backup_filepath(record)

        filename = record.filename or f'Record #{record.pk}'

        if filepath and filepath.exists():
            filepath.unlink()

        record.delete()
        messages.success(request, f'Backup "{filename}" deleted.')
        return redirect('dashboard')


class ConfigView(LoginRequiredMixin, TemplateView):
    """View and manage backup targets."""

    template_name = 'backups/config.html'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['targets'] = BackupTarget.objects.all()
        ctx['retention_days'] = settings.BACKUP_RETENTION_DAYS
        ctx['schedule_hour'] = settings.BACKUP_SCHEDULE_HOUR
        ctx['schedule_minute'] = settings.BACKUP_SCHEDULE_MINUTE
        return ctx


class TestConnectionView(LoginRequiredMixin, View):
    """Test SSH connection to a target server."""

    def post(self, request):
        target_id = request.POST.get('target_id')
        if not target_id:
            return JsonResponse({'ok': False, 'message': 'No target specified.'})

        try:
            target = BackupTarget.objects.get(pk=target_id)
        except BackupTarget.DoesNotExist:
            return JsonResponse({'ok': False, 'message': 'Target not found.'})

        service = BackupService(target)
        result = service.verify_ssh_connection()
        return JsonResponse(result)
