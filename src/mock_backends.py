# mock_backends.py
#
# Copyright 2026 Benjamin Quinn <benjamin.quinn92@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mock backends driven by a JSON scenario dict for UI testing."""

import logging

from gi.repository import GLib, GObject

log = logging.getLogger(__name__)


class MockDnfBackend(GObject.Object):
    """Mock DNF backend that emits signals based on scenario configuration."""

    __gsignals__ = {
        'check-completed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'error': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'upgrade-progress': (GObject.SignalFlags.RUN_LAST, None, (str, int, int)),
        'upgrade-completed': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    def __init__(self, scenario):
        super().__init__()
        self._check = scenario.get('check', {})
        self._upgrade = scenario.get('upgrade', {})

    def check_updates_async(self):
        delay = self._check.get('delay_ms', 1000)
        log.info('[demo] Mock DNF check starting (delay=%dms)', delay)
        GLib.timeout_add(delay, self._emit_check_result)

    def _emit_check_result(self):
        error = self._check.get('error')
        if error:
            log.info('[demo] Mock DNF check emitting error')
            self.emit('error', error)
        else:
            packages = self._check.get('packages', [])
            log.info('[demo] Mock DNF check completed with %d packages', len(packages))
            self.emit('check-completed', packages)
        return GLib.SOURCE_REMOVE

    def upgrade_all_async(self):
        error = self._upgrade.get('error')
        if error:
            delay = self._upgrade.get('progress_interval_ms', 400)
            log.info('[demo] Mock DNF upgrade will fail after %dms', delay)
            GLib.timeout_add(delay, self._emit_upgrade_error, error)
            return

        packages = self._check.get('packages', [])
        self._upgrade_index = 0
        self._upgrade_total = len(packages)
        interval = self._upgrade.get('progress_interval_ms', 400)
        log.info('[demo] Mock DNF upgrade starting (%d packages, %dms interval)',
                 self._upgrade_total, interval)
        GLib.timeout_add(interval, self._emit_next_progress)

    def _emit_upgrade_error(self, message):
        self.emit('error', message)
        return GLib.SOURCE_REMOVE

    def _emit_next_progress(self):
        packages = self._check.get('packages', [])
        if self._upgrade_index < self._upgrade_total:
            pkg = packages[self._upgrade_index]
            self._upgrade_index += 1
            self.emit('upgrade-progress',
                      pkg.get('nevra', pkg.get('name', '')),
                      self._upgrade_index,
                      self._upgrade_total)
            return GLib.SOURCE_CONTINUE
        else:
            reboot = self._upgrade.get('reboot_needed', False)
            log.info('[demo] Mock DNF upgrade completed (reboot_needed=%s)', reboot)
            self.emit('upgrade-completed', reboot)
            return GLib.SOURCE_REMOVE


class MockSystemUpgradeBackend(GObject.Object):
    """Mock system upgrade backend for demo mode."""

    __gsignals__ = {
        'check-completed': (GObject.SignalFlags.RUN_LAST, None, (int,)),
        'download-progress': (GObject.SignalFlags.RUN_LAST, None, (str, float)),
        'download-completed': (GObject.SignalFlags.RUN_LAST, None, ()),
        'error': (GObject.SignalFlags.RUN_LAST, None, (str,)),
    }

    def __init__(self, scenario):
        super().__init__()
        self._check = scenario.get('check', {})
        self._download = scenario.get('download', {})

    def check_available_upgrade_async(self):
        delay = self._check.get('delay_ms', 800)
        log.info('[demo] Mock system upgrade check starting (delay=%dms)', delay)
        GLib.timeout_add(delay, self._emit_check_result)

    def _emit_check_result(self):
        target = self._check.get('target_version', 0)
        log.info('[demo] Mock system upgrade check: target=%d', target)
        self.emit('check-completed', target)
        return GLib.SOURCE_REMOVE

    def download_upgrade_async(self, target_version):
        self._download_step = 0
        total = self._download.get('steps', 5)
        interval = self._download.get('progress_interval_ms', 800)
        self._download_total = total
        log.info('[demo] Mock system upgrade download starting (%d steps)', total)
        GLib.timeout_add(interval, self._emit_download_progress)

    def _emit_download_progress(self):
        self._download_step += 1
        if self._download_step < self._download_total:
            fraction = self._download_step / self._download_total
            self.emit('download-progress',
                      f'Downloading package {self._download_step}/{self._download_total}',
                      fraction)
            return GLib.SOURCE_CONTINUE
        else:
            error = self._download.get('error')
            if error:
                self.emit('error', error)
            else:
                log.info('[demo] Mock system upgrade download completed')
                self.emit('download-completed')
            return GLib.SOURCE_REMOVE

    def trigger_offline_reboot(self):
        log.info('[demo] Mock offline reboot triggered (no-op in demo mode)')


class MockFlatpakBackend(GObject.Object):
    """Mock Flatpak backend that emits signals based on scenario configuration."""

    __gsignals__ = {
        'check-completed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'error': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'upgrade-completed': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, scenario):
        super().__init__()
        self._check = scenario.get('check', {})
        self._upgrade = scenario.get('upgrade', {})

    def check_updates_async(self):
        delay = self._check.get('delay_ms', 500)
        log.info('[demo] Mock Flatpak check starting (delay=%dms)', delay)
        GLib.timeout_add(delay, self._emit_check_result)

    def _emit_check_result(self):
        error = self._check.get('error')
        if error:
            log.info('[demo] Mock Flatpak check emitting error')
            self.emit('error', error)
        else:
            refs = self._check.get('refs', [])
            log.info('[demo] Mock Flatpak check completed with %d refs', len(refs))
            self.emit('check-completed', refs)
        return GLib.SOURCE_REMOVE

    def update_all_async(self):
        error = self._upgrade.get('error')
        if error:
            delay = self._upgrade.get('delay_ms', 2000)
            log.info('[demo] Mock Flatpak upgrade will fail after %dms', delay)
            GLib.timeout_add(delay, self._emit_upgrade_error, error)
            return

        delay = self._upgrade.get('delay_ms', 2000)
        log.info('[demo] Mock Flatpak upgrade starting (delay=%dms)', delay)
        GLib.timeout_add(delay, self._emit_upgrade_completed)

    def _emit_upgrade_error(self, message):
        self.emit('error', message)
        return GLib.SOURCE_REMOVE

    def _emit_upgrade_completed(self):
        log.info('[demo] Mock Flatpak upgrade completed')
        self.emit('upgrade-completed')
        return GLib.SOURCE_REMOVE
