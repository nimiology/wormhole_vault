from django.db import models
from django.utils import timezone


class BackupTarget(models.Model):
    """
    Represents a remote server / database to back up.
    Stores SSH and PostgreSQL connection details.
    """

    name = models.CharField(
        max_length=100,
        help_text='Human-friendly label, e.g. "Production"',
    )
    ssh_host = models.CharField(max_length=255, help_text='Server IP or hostname')
    ssh_user = models.CharField(max_length=100, default='root')
    ssh_port = models.PositiveIntegerField(default=22)
    ssh_key_path = models.CharField(
        max_length=500,
        default='/app/ssh_keys/id_ed25519',
        help_text='Path to SSH private key inside the container',
    )

    db_name = models.CharField(max_length=100, help_text='PostgreSQL database name')
    db_user = models.CharField(max_length=100, default='postgres')
    db_password = models.CharField(
        max_length=255,
        blank=True,
        help_text='Leave blank to use PGPASSWORD from environment',
    )
    db_container = models.CharField(
        max_length=100,
        blank=True,
        help_text='Docker container name on the remote server (e.g. markaz_db). '
                  'Leave blank if PostgreSQL runs directly on the host.',
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.ssh_host})'


class BackupRecord(models.Model):
    """
    One row per backup attempt. Tracks status, file path, and logs.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        SUCCESS = 'success', 'Success'
        FAILED = 'failed', 'Failed'

    class TriggerType(models.TextChoices):
        SCHEDULE = 'schedule', 'Scheduled'
        MANUAL = 'manual', 'Manual'

    target = models.ForeignKey(
        BackupTarget,
        on_delete=models.CASCADE,
        related_name='backups',
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    filename = models.CharField(max_length=255, blank=True)
    file_size = models.BigIntegerField(
        null=True,
        blank=True,
        help_text='Size in bytes',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    log = models.TextField(blank=True, help_text='stdout / stderr output')
    triggered_by = models.CharField(
        max_length=10,
        choices=TriggerType.choices,
        default=TriggerType.MANUAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.target.name} — {self.filename or "pending"} [{self.status}]'

    @property
    def file_size_display(self):
        """Human-readable file size."""
        if self.file_size is None:
            return '—'
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f'{size:.1f} {unit}'
            size /= 1024
        return f'{size:.1f} TB'

    @property
    def duration_display(self):
        """Human-readable duration."""
        if self.duration_seconds is None:
            return '—'
        mins, secs = divmod(self.duration_seconds, 60)
        if mins:
            return f'{mins}m {secs}s'
        return f'{secs}s'
