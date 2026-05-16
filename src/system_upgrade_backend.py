# system_upgrade_backend.py
#
# Copyright 2026 Benjamin Quinn <benjamin.quinn92@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Backend for major Fedora version upgrades via dnf system-upgrade."""

import json
import logging
import time

import libdnf5.base
import libdnf5.repo
import libdnf5.rpm

from gi.repository import Gio, GLib, GObject

log = logging.getLogger(__name__)

HELPER_NAME = 'system_upgrade_helper.py'


def _get_current_version():
    """Read the current Fedora version from /etc/os-release."""
    with open('/etc/os-release') as f:
        for line in f:
            if line.startswith('VERSION_ID='):
                return int(line.strip().split('=', 1)[1].strip('"'))
    raise RuntimeError('Could not determine Fedora version from /etc/os-release')


class SystemUpgradeBackend(GObject.Object):
    """Backend for checking and performing major Fedora version upgrades.

    Uses libdnf5 for read-only version detection and pkexec + a root helper
    for the privileged download and reboot operations.
    """

    __gsignals__ = {
        'check-completed': (GObject.SignalFlags.RUN_LAST, None, (int,)),
        'download-progress': (GObject.SignalFlags.RUN_LAST, None,
                              (str, int, int, str)),
        # nevra, pkgs_done, pkgs_total, speed
        'download-status': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'download-completed': (GObject.SignalFlags.RUN_LAST, None, ()),
        'error': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, pkgdatadir):
        super().__init__()
        self._helper_path = f'{pkgdatadir}/{HELPER_NAME}'

    # ── Check for available upgrade (no root) ─────────────────────

    def check_available_upgrade_async(self):
        task = Gio.Task.new(self, None, self._on_check_task_done)
        task.run_in_thread(self._check_thread)

    def _check_thread(self, task, _source, _data, _cancellable):
        try:
            current = _get_current_version()
            log.info('Current Fedora version: %d', current)
            target = current + 1

            log.info('Checking if Fedora %d is available', target)
            t0 = time.monotonic()

            base = libdnf5.base.Base()
            base.load_config()
            base.get_config().get_metadata_expire_option().set(0)
            vars = base.get_vars()
            vars.set('releasever', str(target))
            base.setup()
            base.get_repo_sack().create_repos_from_system_configuration()

            try:
                base.get_repo_sack().load_repos()
            except Exception:
                log.info('Could not load repos for Fedora %d, not available yet', target)
                task.return_value(0)
                return

            query = libdnf5.rpm.PackageQuery(base)
            query.filter_name(['fedora-release'])
            query.filter_arch(['noarch'])

            if query.size() > 0:
                log.info('Fedora %d is available (check took %.1fs)',
                         target, time.monotonic() - t0)
                task.return_value(target)
            else:
                log.info('Fedora %d repos exist but no fedora-release found', target)
                task.return_value(0)

        except Exception as e:
            log.exception('Upgrade availability check failed')
            task.return_value(0)
            GLib.idle_add(self.emit, 'error', str(e))

    def _on_check_task_done(self, _source, result, _data=None):
        value = result.propagate_value().value
        self.emit('check-completed', value)

    # ── Download upgrade (pkexec + helper) ────────────────────────

    def download_upgrade_async(self, target_version):
        log.info('Starting system upgrade download for Fedora %d', target_version)
        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
        )
        try:
            self._proc = launcher.spawnv(
                ['pkexec', self._helper_path, str(target_version)]
            )
        except GLib.Error as e:
            log.error('Failed to launch system upgrade helper: %s', e.message)
            self.emit('error', f'Failed to start upgrade download: {e.message}')
            return

        stdout = self._proc.get_stdout_pipe()
        self._stream = Gio.DataInputStream.new(stdout)
        self._read_next_line()

    def _read_next_line(self):
        self._stream.read_line_async(
            GLib.PRIORITY_DEFAULT, None, self._on_line_read
        )

    def _on_line_read(self, stream, result):
        try:
            line, _length = stream.read_line_finish_utf8(result)
        except GLib.Error as e:
            log.error('Error reading helper output: %s', e.message)
            self.emit('error', f'Lost communication with upgrade helper: {e.message}')
            return

        if line is None:
            self._proc.wait_async(None, self._on_proc_exited)
            return

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log.warning('Unexpected helper output: %s', line)
            self._read_next_line()
            return

        msg_type = msg.get('type')
        log.debug('System upgrade helper: %s', msg)

        if msg_type == 'download-progress':
            self.emit('download-progress',
                       msg.get('nevra', ''),
                       msg.get('packages_done', 0),
                       msg.get('packages_total', 0),
                       msg.get('speed', ''))
        elif msg_type == 'status':
            self.emit('download-status', msg.get('message', ''))
        elif msg_type == 'error':
            log.error('System upgrade helper error: %s', msg.get('message', ''))
            self.emit('error', msg.get('message', 'Unknown error'))
            return
        elif msg_type == 'done':
            log.info('System upgrade download completed')
            self.emit('download-completed')
            return

        self._read_next_line()

    def _on_proc_exited(self, proc, result):
        try:
            proc.wait_finish(result)
        except GLib.Error:
            pass
        status = proc.get_exit_status()
        if status != 0:
            log.error('System upgrade helper exited with status %d', status)
            self.emit('error', f'Upgrade download failed (exit code {status})')

    # ── Trigger offline reboot (pkexec + helper) ──────────────────

    def trigger_offline_reboot(self):
        log.info('Triggering offline upgrade reboot')
        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
        )
        try:
            proc = launcher.spawnv(['pkexec', self._helper_path, 'reboot'])
            proc.wait_async(None, self._on_reboot_proc_exited)
        except GLib.Error as e:
            log.error('Failed to trigger offline reboot: %s', e.message)
            self.emit('error', f'Failed to trigger reboot: {e.message}')

    def _on_reboot_proc_exited(self, proc, result):
        try:
            proc.wait_finish(result)
        except GLib.Error:
            pass
        status = proc.get_exit_status()
        if status != 0:
            log.error('Offline reboot command exited with status %d', status)
            self.emit('error', f'Failed to trigger offline reboot (exit code {status})')
