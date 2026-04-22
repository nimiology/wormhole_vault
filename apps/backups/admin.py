from django.contrib import admin

from .models import BackupRecord, BackupTarget


@admin.register(BackupTarget)
class BackupTargetAdmin(admin.ModelAdmin):
    list_display = ('name', 'ssh_host', 'db_name', 'is_active', 'updated_at')
    list_filter = ('is_active',)


@admin.register(BackupRecord)
class BackupRecordAdmin(admin.ModelAdmin):
    list_display = ('target', 'status', 'filename', 'file_size_display', 'duration_display', 'triggered_by', 'created_at')
    list_filter = ('status', 'triggered_by', 'target')
    readonly_fields = ('log',)
