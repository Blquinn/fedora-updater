# dnf_backend.py
#
# Copyright 2026 Ben
#
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import logging
import time

import libdnf5.base
import libdnf5.repo
import libdnf5.rpm

from gi.repository import Gio, GLib, GObject

log = logging.getLogger(__name__)

HELPER_NAME = 'me.blq.FedoraUpdater.upgrade_helper.py'


class DnfBackend(GObject.Object):
    """DNF update backend.

    Uses libdnf5 directly for fast read-only queries (check for updates).
    Uses pkexec + a root helper for privileged upgrade operations
    where polkit handles authentication.
    """

    __gsignals__ = {
        'check-completed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'error': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'upgrade-progress': (GObject.SignalFlags.RUN_LAST, None, (str, int, int)),
        'upgrade-completed': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    def __init__(self, pkgdatadir):
        super().__init__()
        self._helper_path = f'{pkgdatadir}/{HELPER_NAME}'

    # ── Check for updates (libdnf5 direct, no root) ───────────────

    def check_updates_async(self):
        task = Gio.Task.new(self, None, self._on_check_task_done)
        task.run_in_thread(self._check_thread)

    def _check_thread(self, task, _source, _data, _cancellable):
        try:
            log.info('Starting update check via libdnf5')
            t0 = time.monotonic()

            base = libdnf5.base.Base()
            base.load_config()
            base.get_config().get_metadata_expire_option().set(0)
            base.setup()
            base.get_repo_sack().create_repos_from_system_configuration()

            log.debug('Loading repos (metadata refresh forced)')
            base.get_repo_sack().load_repos()
            log.debug('Repos loaded in %.1fs', time.monotonic() - t0)

            query = libdnf5.rpm.PackageQuery(base)
            query.filter_upgrades()

            packages = []
            for pkg in query:
                packages.append({
                    'name': pkg.get_name(),
                    'evr': pkg.get_evr(),
                    'nevra': pkg.get_nevra(),
                    'arch': pkg.get_arch(),
                    'repo_id': pkg.get_repo_id(),
                    'summary': pkg.get_summary(),
                })

            log.info('Found %d upgradable package(s)', len(packages))

            # Query advisories for security classification
            adv_query = libdnf5.advisory.AdvisoryQuery(base)
            pkg_advisory_map = {}
            for advisory in adv_query:
                adv_type = advisory.get_type()
                severity = advisory.get_severity()
                for collection in advisory.get_collections():
                    for adv_pkg in collection.get_packages():
                        pkg_name = adv_pkg.get_name()
                        existing = pkg_advisory_map.get(pkg_name)
                        if not existing or adv_type == 'security':
                            pkg_advisory_map[pkg_name] = (adv_type, severity)

            security_count = sum(1 for t, _ in pkg_advisory_map.values() if t == 'security')
            if security_count:
                log.info('%d package(s) have security advisories', security_count)

            for pkg in packages:
                pkg_name = pkg.get('name', '')
                if pkg_name in pkg_advisory_map:
                    adv_type, severity = pkg_advisory_map[pkg_name]
                    pkg['advisory_type'] = adv_type
                    if severity:
                        pkg['severity'] = severity

            log.info('Update check completed in %.1fs', time.monotonic() - t0)
            task.return_value(packages)
        except Exception as e:
            log.exception('Update check failed')
            task.return_value(None)
            GLib.idle_add(self.emit, 'error', str(e))

    def _on_check_task_done(self, _source, result, _data=None):
        value = result.propagate_value().value
        if value is not None:
            self.emit('check-completed', value)

    # ── Upgrade all (pkexec + libdnf5 helper) ────────────────────

    def upgrade_all_async(self):
        log.info('Starting system upgrade via pkexec helper')
        launcher = Gio.SubprocessLauncher.new(
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
        )
        try:
            self._proc = launcher.spawnv(['pkexec', self._helper_path])
        except GLib.Error as e:
            log.error('Failed to launch upgrade helper: %s', e.message)
            self.emit('error', f'Failed to start upgrade: {e.message}')
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
            # EOF — process exited, wait for exit status
            self._proc.wait_async(None, self._on_proc_exited)
            return

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log.warning('Unexpected helper output: %s', line)
            self._read_next_line()
            return

        msg_type = msg.get('type')
        log.debug('Helper message: %s', msg)

        if msg_type == 'progress':
            self.emit('upgrade-progress',
                       msg.get('nevra', ''),
                       msg.get('processed', 0),
                       msg.get('total', 0))
        elif msg_type == 'status':
            self.emit('upgrade-progress', msg.get('message', ''), 0, 0)
        elif msg_type == 'resolved':
            log.info('Transaction resolved: %d item(s)', msg.get('count', 0))
        elif msg_type == 'error':
            log.error('Helper error: %s', msg.get('message', ''))
            self.emit('error', msg.get('message', 'Unknown upgrade error'))
            return
        elif msg_type == 'done':
            reboot_needed = msg.get('reboot_needed', False)
            log.info('Upgrade completed (reboot_needed=%s)', reboot_needed)
            self.emit('upgrade-completed', reboot_needed)
            return

        self._read_next_line()

    def _on_proc_exited(self, proc, result):
        try:
            proc.wait_finish(result)
        except GLib.Error:
            pass
        status = proc.get_exit_status()
        if status != 0:
            log.error('Upgrade helper exited with status %d', status)
            self.emit('error', f'Upgrade process failed (exit code {status})')
