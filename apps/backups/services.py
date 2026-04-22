"""
Backup service — SSH tunnel + pg_dump logic.

This module handles:
1. Opening an SSH tunnel to the production server
2. Running pg_dump through the tunnel
3. Compressing and saving the dump
4. Cleaning up old backups
"""
import logging
import os
import signal
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union, Any

from django.conf import settings
from django.utils import timezone

from .models import BackupRecord, BackupTarget

logger = logging.getLogger(__name__)

TUNNEL_LOCAL_PORT = 15432
TUNNEL_WAIT_SECONDS = 3
TUNNEL_MAX_RETRIES = 3


class BackupError(Exception):
    """Raised when a backup operation fails."""
    pass


class BackupService:
    """Manages SSH tunnel creation and pg_dump execution."""

    def __init__(self, target: BackupTarget):
        self.target = target
        self.tunnel_process = None

    # ------------------------------------------------------------------
    # SSH connectivity
    # ------------------------------------------------------------------

    def verify_ssh_connection(self) -> dict:
        """
        Test that SSH key auth works against the target server.
        Returns {'ok': True/False, 'message': str}.
        """
        cmd = [
            'ssh',
            '-i', self.target.ssh_key_path,
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ConnectTimeout=10',
            '-o', 'BatchMode=yes',
            '-p', str(self.target.ssh_port),
            f'{self.target.ssh_user}@{self.target.ssh_host}',
            'echo "SSH_OK"',
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15,
            )
            if 'SSH_OK' in result.stdout:
                return {'ok': True, 'message': 'SSH connection successful.'}
            return {
                'ok': False,
                'message': f'SSH connected but unexpected output: {result.stdout}\n{result.stderr}',
            }
        except subprocess.TimeoutExpired:
            return {'ok': False, 'message': 'SSH connection timed out after 15 seconds.'}
        except Exception as e:
            return {'ok': False, 'message': f'SSH connection error: {e}'}

    # ------------------------------------------------------------------
    # SSH tunnel management
    # ------------------------------------------------------------------

    def _open_tunnel(self) -> subprocess.Popen:
        """
        Opens an SSH tunnel: localhost:15432 -> remote:5432.
        Returns the tunnel subprocess.
        """
        cmd = [
            'ssh',
            '-i', self.target.ssh_key_path,
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'ExitOnForwardFailure=yes',
            '-o', 'ServerAliveInterval=30',
            '-o', 'ServerAliveCountMax=3',
            '-p', str(self.target.ssh_port),
            '-N',  # no remote command
            '-L', f'{TUNNEL_LOCAL_PORT}:localhost:5432',
            f'{self.target.ssh_user}@{self.target.ssh_host}',
        ]

        logger.info('Opening SSH tunnel: %s', ' '.join(cmd))

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Give the tunnel a moment to establish
        time.sleep(TUNNEL_WAIT_SECONDS)

        if proc.poll() is not None:
            stderr = proc.stderr.read().decode() if proc.stderr else ''
            raise BackupError(f'SSH tunnel failed to start: {stderr}')

        logger.info('SSH tunnel established on localhost:%d', TUNNEL_LOCAL_PORT)
        return proc

    def _close_tunnel(self):
        """Kill the SSH tunnel process."""
        if self.tunnel_process and self.tunnel_process.poll() is None:
            logger.info('Closing SSH tunnel (PID %d)', self.tunnel_process.pid)
            os.kill(self.tunnel_process.pid, signal.SIGTERM)
            try:
                self.tunnel_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.kill(self.tunnel_process.pid, signal.SIGKILL)
            self.tunnel_process = None

    # ------------------------------------------------------------------
    # pg_dump execution
    # ------------------------------------------------------------------

    def _build_pgdump_command(self) -> list:
        """
        Build the pg_dump command.
        If the remote DB is inside a Docker container, we use
        `docker exec` via SSH instead of a local tunnel.
        """
        if self.target.db_container:
            # pg_dump runs inside the remote container via SSH
            remote_cmd = (
                f'docker exec {self.target.db_container} '
                f'pg_dump -U {self.target.db_user} {self.target.db_name}'
            )
            return [
                'ssh',
                '-i', self.target.ssh_key_path,
                '-o', 'StrictHostKeyChecking=no',
                '-p', str(self.target.ssh_port),
                f'{self.target.ssh_user}@{self.target.ssh_host}',
                remote_cmd,
            ]
        else:
            # pg_dump connects through the local SSH tunnel
            cmd = [
                'pg_dump',
                '-h', 'localhost',
                '-p', str(TUNNEL_LOCAL_PORT),
                '-U', self.target.db_user,
                self.target.db_name,
            ]
            return cmd

    def _generate_filename(self) -> str:
        """Generate a timestamped filename for the backup."""
        now = timezone.localtime()
        timestamp = now.strftime('%Y-%m-%d_%H%M%S')
        return f'{self.target.db_name}_{timestamp}.sql.gz'

    # ------------------------------------------------------------------
    # Main backup flow
    # ------------------------------------------------------------------

    def run_backup(self, record: BackupRecord) -> BackupRecord:
        """
        Execute a full backup:
        1. Open SSH tunnel (if not using docker exec)
        2. Run pg_dump
        3. Pipe through gzip
        4. Save to disk
        5. Update the BackupRecord
        """
        record.status = BackupRecord.Status.RUNNING
        record.started_at = timezone.now()
        record.save(update_fields=['status', 'started_at'])

        log_lines = []
        use_tunnel = not self.target.db_container

        try:
            # Ensure backup directory exists
            backup_dir = Path(settings.BACKUP_DIR)
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Phase 1: Open tunnel if needed
            if use_tunnel:
                log_lines.append('[INFO] Opening SSH tunnel...')
                self.tunnel_process = self._open_tunnel()
                log_lines.append(f'[INFO] Tunnel open on localhost:{TUNNEL_LOCAL_PORT}')

            # Phase 2: Build and run pg_dump
            filename = self._generate_filename()
            filepath = backup_dir / filename
            pgdump_cmd = self._build_pgdump_command()

            log_lines.append(f'[INFO] Running: {" ".join(pgdump_cmd)}')

            # Set PGPASSWORD if provided
            env = os.environ.copy()
            if self.target.db_password:
                env['PGPASSWORD'] = self.target.db_password

            # Run pg_dump and pipe through gzip
            dump_proc = subprocess.Popen(
                pgdump_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )

            gzip_proc = subprocess.Popen(
                ['gzip'],
                stdin=dump_proc.stdout,
                stdout=open(filepath, 'wb'),
                stderr=subprocess.PIPE,
            )

            # Allow dump_proc to receive SIGPIPE if gzip exits
            dump_proc.stdout.close()

            # Wait for both to finish
            gzip_proc.wait()
            dump_proc.wait()

            # Check for errors
            dump_stderr = dump_proc.stderr.read().decode().strip()
            gzip_stderr = gzip_proc.stderr.read().decode().strip()

            if dump_proc.returncode != 0:
                error_msg = dump_stderr or 'pg_dump exited with non-zero status'
                log_lines.append(f'[ERROR] pg_dump failed: {error_msg}')
                raise BackupError(error_msg)

            if gzip_proc.returncode != 0:
                error_msg = gzip_stderr or 'gzip exited with non-zero status'
                log_lines.append(f'[ERROR] gzip failed: {error_msg}')
                raise BackupError(error_msg)

            if dump_stderr:
                log_lines.append(f'[WARN] pg_dump stderr: {dump_stderr}')

            # Phase 3: Update record with success info
            file_size = filepath.stat().st_size
            completed_at = timezone.now()
            duration = int((completed_at - record.started_at).total_seconds())

            record.status = BackupRecord.Status.SUCCESS
            record.filename = filename
            record.file_size = file_size
            record.completed_at = completed_at
            record.duration_seconds = duration
            log_lines.append(
                f'[INFO] Backup completed: {filename} '
                f'({record.file_size_display}, {duration}s)'
            )
            record.log = '\n'.join(log_lines)
            record.save()

            logger.info(
                'Backup succeeded: %s (%s)',
                filename,
                record.file_size_display,
            )

        except BackupError as e:
            record.status = BackupRecord.Status.FAILED
            record.completed_at = timezone.now()
            if record.started_at:
                record.duration_seconds = int(
                    (record.completed_at - record.started_at).total_seconds()
                )
            record.log = '\n'.join(log_lines)
            record.save()
            logger.error('Backup failed for %s: %s', self.target.name, e)

        except Exception as e:
            record.status = BackupRecord.Status.FAILED
            record.completed_at = timezone.now()
            if record.started_at:
                record.duration_seconds = int(
                    (record.completed_at - record.started_at).total_seconds()
                )
            log_lines.append(f'[ERROR] Unexpected error: {e}')
            record.log = '\n'.join(log_lines)
            record.save()
            logger.exception('Unexpected backup error for %s', self.target.name)

        finally:
            self._close_tunnel()

        return record

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    @staticmethod
    def cleanup_old_backups(days: int = None):
        """
        Delete backup files and records older than `days` days.
        """
        if days is None:
            days = settings.BACKUP_RETENTION_DAYS

        cutoff = timezone.now() - timedelta(days=days)
        old_records = BackupRecord.objects.filter(created_at__lt=cutoff)
        backup_dir = Path(settings.BACKUP_DIR)

        deleted_count = 0
        for record in old_records:
            if record.filename:
                filepath = backup_dir / record.filename
                if filepath.exists():
                    filepath.unlink()
                    logger.info('Deleted old backup file: %s', record.filename)
            deleted_count += 1

        old_records.delete()
        logger.info('Cleaned up %d old backup records (cutoff: %s)', deleted_count, cutoff)
        return deleted_count

    @staticmethod
    def get_backup_filepath(record: BackupRecord) -> Optional[Path]:
        """Return the full path to a backup file, or None if missing."""
        if not record.filename:
            return None
        filepath = Path(settings.BACKUP_DIR) / record.filename
        return filepath if filepath.exists() else None
