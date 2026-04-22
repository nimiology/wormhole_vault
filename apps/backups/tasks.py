"""
Celery tasks for the backup system.
"""
import logging

from celery import shared_task

from .models import BackupRecord, BackupTarget
from .services import BackupService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1, default_retry_delay=300)
def run_backup_task(self, target_id: int, triggered_by: str = 'manual'):
    """
    Run a backup for a specific BackupTarget.
    Creates a BackupRecord and delegates to BackupService.
    """
    try:
        target = BackupTarget.objects.get(pk=target_id, is_active=True)
    except BackupTarget.DoesNotExist:
        logger.error('BackupTarget %d not found or inactive', target_id)
        return

    record = BackupRecord.objects.create(
        target=target,
        triggered_by=triggered_by,
        status=BackupRecord.Status.PENDING,
    )

    logger.info(
        'Starting backup for "%s" (record #%d, trigger=%s)',
        target.name, record.pk, triggered_by,
    )

    service = BackupService(target)
    result = service.run_backup(record)

    return {
        'record_id': result.pk,
        'status': result.status,
        'filename': result.filename,
        'file_size': result.file_size,
        'duration_seconds': result.duration_seconds,
    }


@shared_task
def run_scheduled_backup():
    """
    Scheduled task: runs backups for ALL active targets.
    Called by Celery Beat.
    """
    targets = BackupTarget.objects.filter(is_active=True)

    if not targets.exists():
        logger.warning('No active backup targets configured.')
        return

    for target in targets:
        logger.info('Queuing scheduled backup for "%s"', target.name)
        run_backup_task.delay(target.pk, triggered_by='schedule')


@shared_task
def cleanup_old_backups():
    """
    Scheduled task: removes backups older than BACKUP_RETENTION_DAYS.
    Called by Celery Beat.
    """
    deleted = BackupService.cleanup_old_backups()
    logger.info('Cleanup complete: %d records removed', deleted)
    return {'deleted': deleted}
