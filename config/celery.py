"""
Celery configuration for the Backup System.
"""
import os

from celery import Celery
from celery.schedules import crontab
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('backup_system')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


app.conf.beat_schedule = {
    'run-scheduled-backup': {
        'task': 'apps.backups.tasks.run_scheduled_backup',
        'schedule': crontab(
            hour=int(os.environ.get('BACKUP_SCHEDULE_HOUR', 3)),
            minute=int(os.environ.get('BACKUP_SCHEDULE_MINUTE', 0)),
        ),
    },
    'cleanup-old-backups': {
        'task': 'apps.backups.tasks.cleanup_old_backups',
        'schedule': crontab(hour=4, minute=0),
    },
}
