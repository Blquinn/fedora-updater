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
