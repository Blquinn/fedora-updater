# dnf_backend.py
#
# Copyright 2026 Ben
#
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import time

import libdnf5.base
import libdnf5.repo
import libdnf5.rpm

from gi.repository import Gio, GLib, GObject

log = logging.getLogger(__name__)

DNF_BUS_NAME = 'org.rpm.dnf.v0'
DNF_OBJECT_PATH = '/org/rpm/dnf/v0'
SESSION_MANAGER_IFACE = 'org.rpm.dnf.v0.SessionManager'
BASE_IFACE = 'org.rpm.dnf.v0.Base'
RPM_IFACE = 'org.rpm.dnf.v0.rpm.Rpm'
GOAL_IFACE = 'org.rpm.dnf.v0.Goal'
ADVISORY_IFACE = 'org.rpm.dnf.v0.Advisory'

# GDBus timeout: -1 means "default" (~25s), not infinite.
# Repo metadata refresh and transactions can take minutes.
TIMEOUT_LONG = 600000   # 10 minutes
TIMEOUT_SHORT = 120000  # 2 minutes

REBOOT_PACKAGES = {
    'kernel', 'kernel-core', 'kernel-modules', 'kernel-modules-core',
    'glibc', 'systemd', 'dbus', 'dbus-daemon', 'linux-firmware',
    'gnutls', 'openssl-libs',
}


class DnfBackend(GObject.Object):
    """DNF update backend.

    Uses libdnf5 directly for fast read-only queries (check for updates).
    Uses dnf5daemon-server over D-Bus for privileged operations (upgrade)
    where polkit handles authentication.
    """

    __gsignals__ = {
        'check-completed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'error': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'upgrade-progress': (GObject.SignalFlags.RUN_LAST, None, (str, int, int)),
        'upgrade-completed': (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    def __init__(self):
        super().__init__()
        self._bus = None
        self._session_path = None
        self._signal_subscriptions = []

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

    # ── D-Bus helpers (for privileged upgrade operations) ──────────

    def _get_bus(self, callback):
        if self._bus:
            callback(self._bus)
            return
        Gio.bus_get(Gio.BusType.SYSTEM, None, self._on_bus_ready, callback)

    def _on_bus_ready(self, _source, result, callback):
        try:
            self._bus = Gio.bus_get_finish(result)
            log.debug('Connected to system bus')
            callback(self._bus)
        except GLib.Error as e:
            log.error('Failed to connect to system bus: %s', e.message)
            self.emit('error', f'Failed to connect to system bus: {e.message}')

    def _open_session(self, callback):
        def on_bus(bus):
            bus.call(
                DNF_BUS_NAME, DNF_OBJECT_PATH, SESSION_MANAGER_IFACE,
                'open_session',
                GLib.Variant('(a{sv})', ({},)),
                GLib.VariantType('(o)'),
                Gio.DBusCallFlags.NONE, TIMEOUT_SHORT, None,
                self._on_session_opened, callback,
            )
        self._get_bus(on_bus)

    def _on_session_opened(self, bus, result, callback):
        try:
            reply = bus.call_finish(result)
            self._session_path = reply.unpack()[0]
            log.info('Opened dnf5daemon session: %s', self._session_path)
            callback()
        except GLib.Error as e:
            log.error('Failed to open dnf session: %s', e.message)
            self.emit('error', f'Failed to open dnf session: {e.message}')

    def _close_session(self):
        if not self._bus or not self._session_path:
            return
        log.info('Closing dnf5daemon session: %s', self._session_path)
        for sub_id in self._signal_subscriptions:
            self._bus.signal_unsubscribe(sub_id)
        self._signal_subscriptions.clear()
        self._bus.call(
            DNF_BUS_NAME, DNF_OBJECT_PATH, SESSION_MANAGER_IFACE,
            'close_session',
            GLib.Variant('(o)', (self._session_path,)),
            GLib.VariantType('(b)'),
            Gio.DBusCallFlags.NONE, -1, None,
            lambda _bus, result, _data: None, None,
        )
        self._session_path = None

    def _call_session(self, iface, method, params, reply_type, callback,
                       timeout=TIMEOUT_SHORT):
        self._bus.call(
            DNF_BUS_NAME, self._session_path, iface, method,
            params, reply_type,
            Gio.DBusCallFlags.NONE, timeout, None,
            callback, None,
        )

    # ── Upgrade all (dnf5daemon D-Bus, needs polkit) ──────────────

    def upgrade_all_async(self):
        log.info('Starting system upgrade via dnf5daemon')
        self._open_session(self._do_upgrade)

    def _do_upgrade(self):
        self._subscribe_progress_signals()

        self._call_session(
            BASE_IFACE, 'read_all_repos', None,
            GLib.VariantType('(b)'),
            self._on_upgrade_repos_loaded,
            timeout=TIMEOUT_LONG,
        )

    def _on_upgrade_repos_loaded(self, bus, result, _data):
        try:
            bus.call_finish(result)
            log.debug('D-Bus repos loaded, queuing upgrade')
        except GLib.Error as e:
            log.error('Failed to load repos via D-Bus: %s', e.message)
            self._close_session()
            self.emit('error', f'Failed to load repos: {e.message}')
            return

        self._call_session(
            RPM_IFACE, 'upgrade',
            GLib.Variant('(asa{sv})', ([], {})),
            None,
            self._on_upgrade_queued,
        )

    def _on_upgrade_queued(self, bus, result, _data):
        try:
            bus.call_finish(result)
            log.debug('Upgrade queued, resolving transaction')
        except GLib.Error as e:
            log.error('Failed to queue upgrade: %s', e.message)
            self._close_session()
            self.emit('error', f'Failed to queue upgrade: {e.message}')
            return

        self._call_session(
            GOAL_IFACE, 'resolve',
            GLib.Variant('(a{sv})', ({},)),
            GLib.VariantType('(a(sssa{sv}a{sv})u)'),
            self._on_resolved,
        )

    def _on_resolved(self, bus, result, _data):
        try:
            reply = bus.call_finish(result)
            transaction_items, _result_code = reply.unpack()
        except GLib.Error as e:
            log.error('Failed to resolve transaction: %s', e.message)
            self._close_session()
            self.emit('error', f'Failed to resolve transaction: {e.message}')
            return

        self._resolved_packages = []
        for item in transaction_items:
            nevra = item[2] if len(item) > 2 else ''
            self._resolved_packages.append(nevra)

        log.info('Transaction resolved: %d item(s)', len(self._resolved_packages))

        self._call_session(
            GOAL_IFACE, 'do_transaction',
            GLib.Variant('(a{sv})', ({},)),
            None,
            self._on_transaction_complete,
            timeout=TIMEOUT_LONG,
        )

    def _on_transaction_complete(self, bus, result, _data):
        try:
            bus.call_finish(result)
        except GLib.Error as e:
            log.error('Transaction failed: %s', e.message)
            self._close_session()
            self.emit('error', f'Transaction failed: {e.message}')
            return

        reboot_needed = self._check_reboot_needed()
        log.info('Upgrade completed (reboot_needed=%s)', reboot_needed)
        self._close_session()
        self.emit('upgrade-completed', reboot_needed)

    def _check_reboot_needed(self):
        for nevra in getattr(self, '_resolved_packages', []):
            name = nevra.split('-')[0] if nevra else ''
            if name in REBOOT_PACKAGES:
                return True
        return False

    def _subscribe_progress_signals(self):
        sub_id = self._bus.signal_subscribe(
            DNF_BUS_NAME, RPM_IFACE,
            'transaction_action_progress',
            self._session_path,
            None, Gio.DBusSignalFlags.NONE,
            self._on_dbus_progress_signal,
        )
        self._signal_subscriptions.append(sub_id)

    def _on_dbus_progress_signal(self, _conn, _sender, _path, _iface, _signal, params):
        _session, nevra, processed, total = params.unpack()
        self.emit('upgrade-progress', nevra, processed, total)
