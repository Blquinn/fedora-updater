# window.py
#
# Copyright 2026 Benjamin Quinn <benjamin.quinn92@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import collections
import logging

from gi.repository import Adw, Gio, GLib, Gtk

from .dnf_backend import DnfBackend
from .flatpak_backend import FlatpakBackend
from .system_upgrade_backend import SystemUpgradeBackend

log = logging.getLogger(__name__)


@Gtk.Template(resource_path='/me/blq/FedoraUpdater/window.ui')
class FedoraUpdaterWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'FedoraUpdaterWindow'

    main_stack = Gtk.Template.Child()
    refresh_button = Gtk.Template.Child()
    updates_summary_label = Gtk.Template.Child()
    dnf_group = Gtk.Template.Child()
    flatpak_group = Gtk.Template.Child()
    update_all_button = Gtk.Template.Child()
    phase_label = Gtk.Template.Child()
    overall_progress_bar = Gtk.Template.Child()
    item_progress_bar = Gtk.Template.Child()
    progress_detail_label = Gtk.Template.Child()
    done_status_page = Gtk.Template.Child()
    error_status_page = Gtk.Template.Child()
    restart_button = Gtk.Template.Child()
    upgrade_banner = Gtk.Template.Child()
    upgrade_available_status_page = Gtk.Template.Child()
    start_upgrade_button = Gtk.Template.Child()
    upgrade_progress_bar = Gtk.Template.Child()
    upgrade_progress_label = Gtk.Template.Child()
    upgrade_reboot_button = Gtk.Template.Child()

    def __init__(self, dnf_backend=None, flatpak_backend=None,
                 system_upgrade_backend=None, **kwargs):
        super().__init__(**kwargs)
        self._settings = Gio.Settings(schema_id='me.blq.FedoraUpdater')
        pkgdatadir = self.get_application().pkgdatadir
        self.dnf_backend = dnf_backend or DnfBackend(pkgdatadir)
        self.flatpak_backend = flatpak_backend or FlatpakBackend()
        self.system_upgrade_backend = (
            system_upgrade_backend or SystemUpgradeBackend(pkgdatadir)
        )

        self.refresh_button.connect('clicked', lambda _btn: self.check_for_updates())
        self.update_all_button.connect('clicked', lambda _btn: self.start_update())
        self.restart_button.connect('clicked', lambda _btn: self._do_restart())
        self.start_upgrade_button.connect('clicked', lambda _btn: self._start_system_upgrade())
        self.upgrade_reboot_button.connect('clicked', lambda _btn: self._do_upgrade_reboot())

        self.dnf_backend.connect('check-completed', self._on_dnf_check_completed)
        self.dnf_backend.connect('error', self._on_error)
        self.dnf_backend.connect('upgrade-phase', self._on_upgrade_phase)
        self.dnf_backend.connect('download-progress', self._on_download_progress)
        self.dnf_backend.connect('install-progress', self._on_install_progress)
        self.dnf_backend.connect('upgrade-completed', self._on_upgrade_completed)

        self.flatpak_backend.connect('check-completed', self._on_flatpak_check_completed)
        self.flatpak_backend.connect('error', self._on_error)
        self.flatpak_backend.connect('upgrade-completed', self._on_flatpak_upgrade_completed)

        self.system_upgrade_backend.connect('check-completed', self._on_system_upgrade_check_completed)
        self.system_upgrade_backend.connect('download-progress', self._on_system_upgrade_download_progress)
        self.system_upgrade_backend.connect('download-completed', self._on_system_upgrade_download_completed)
        self.system_upgrade_backend.connect('error', self._on_error)

        self._dnf_packages = []
        self._flatpak_refs = []
        self._dnf_rows = []
        self._flatpak_rows = []
        self._dnf_check_done = False
        self._flatpak_check_done = False
        self._dnf_upgrade_done = False
        self._flatpak_upgrade_done = False
        self._reboot_needed = False
        self._upgrade_target_version = 0

        self.check_for_updates()

    def check_for_updates(self):
        include_flatpak = self._settings.get_boolean('include-flatpak')
        log.info('Checking for updates (flatpak=%s)', include_flatpak)
        self._dnf_check_done = False
        self._flatpak_check_done = False
        self._dnf_packages = []
        self._flatpak_refs = []
        self.main_stack.set_visible_child_name('checking')
        self.refresh_button.set_sensitive(False)
        self.dnf_backend.check_updates_async()
        self.system_upgrade_backend.check_available_upgrade_async()
        if include_flatpak:
            self.flatpak_backend.check_updates_async()
        else:
            self._flatpak_refs = []
            self._flatpak_check_done = True

    def _on_dnf_check_completed(self, _backend, packages):
        self._dnf_packages = packages
        self._dnf_check_done = True
        self._maybe_show_results()

    def _on_flatpak_check_completed(self, _backend, refs):
        self._flatpak_refs = refs
        self._flatpak_check_done = True
        self._maybe_show_results()

    def _maybe_show_results(self):
        if not (self._dnf_check_done and self._flatpak_check_done):
            return

        self.refresh_button.set_sensitive(True)
        self._update_upgrade_banner()

        if not self._dnf_packages and not self._flatpak_refs:
            if self._upgrade_target_version > 0:
                log.info('System is up to date, Fedora %d upgrade available',
                         self._upgrade_target_version)
                self.upgrade_available_status_page.set_description(
                    f'Fedora {self._upgrade_target_version} is ready to download and install.'
                )
                self.main_stack.set_visible_child_name('upgrade-available')
            else:
                log.info('System is up to date')
                self.main_stack.set_visible_child_name('up-to-date')
            return

        log.info('Updates available: %d DNF, %d Flatpak',
                 len(self._dnf_packages), len(self._flatpak_refs))
        self._populate_package_lists()
        self.main_stack.set_visible_child_name('updates-available')

    def _populate_package_lists(self):
        for row in self._dnf_rows:
            self.dnf_group.remove(row)
        for row in self._flatpak_rows:
            self.flatpak_group.remove(row)
        self._dnf_rows.clear()
        self._flatpak_rows.clear()

        security_count = sum(1 for p in self._dnf_packages
                             if p.get('advisory_type') == 'security')
        total = len(self._dnf_packages) + len(self._flatpak_refs)

        parts = [f"{total} update{'s' if total != 1 else ''} available"]
        if security_count:
            parts.append(f"{security_count} security")
        self.updates_summary_label.set_label(', '.join(parts))

        if self._dnf_packages:
            self.dnf_group.set_visible(True)
            for pkg in self._dnf_packages:
                row = Adw.ActionRow(
                    title=pkg['name'],
                    subtitle=f"{pkg.get('installed_evr', '')} \u2192 {pkg.get('evr', '')}",
                )
                adv_type = pkg.get('advisory_type', '')
                severity = pkg.get('severity', '')
                if adv_type == 'security':
                    icon = Gtk.Image(icon_name='security-medium-symbolic')
                    row.add_prefix(icon)
                if severity:
                    label = Gtk.Label(label=severity, css_classes=['dim-label'])
                    label.set_valign(Gtk.Align.CENTER)
                    row.add_suffix(label)
                self.dnf_group.add(row)
                self._dnf_rows.append(row)
        else:
            self.dnf_group.set_visible(False)

        if self._flatpak_refs:
            self.flatpak_group.set_visible(True)
            for ref in self._flatpak_refs:
                row = Adw.ActionRow(
                    title=ref['name'],
                    subtitle=ref.get('branch', ''),
                )
                self.flatpak_group.add(row)
                self._flatpak_rows.append(row)
        else:
            self.flatpak_group.set_visible(False)

    def start_update(self):
        log.info('Starting update (dnf=%d, flatpak=%d)',
                 len(self._dnf_packages), len(self._flatpak_refs))
        self._dnf_upgrade_done = False
        self._flatpak_upgrade_done = False
        self._reboot_needed = False
        self._speed_samples = collections.deque(maxlen=30)
        self._last_speed_update = 0.0
        self._current_dl_nevra = ''
        self.main_stack.set_visible_child_name('updating')
        self.phase_label.set_label('')
        self.overall_progress_bar.set_fraction(0.0)
        self.overall_progress_bar.set_text('')
        self.item_progress_bar.set_fraction(0.0)
        self.item_progress_bar.set_visible(False)
        self.progress_detail_label.set_label('')
        self.refresh_button.set_sensitive(False)

        if self._dnf_packages:
            self.dnf_backend.upgrade_all_async()
        else:
            self._dnf_upgrade_done = True

        if self._flatpak_refs:
            self.flatpak_backend.update_all_async()
        else:
            self._flatpak_upgrade_done = True

        self._maybe_finish_update()

    def _on_upgrade_phase(self, _backend, phase, total_phases, label):
        self.phase_label.set_label(f'Step {phase} of {total_phases}: {label}')
        self.overall_progress_bar.set_fraction(0.0)
        self.overall_progress_bar.set_text('')
        self.item_progress_bar.set_fraction(0.0)
        self.progress_detail_label.set_label('')
        self.item_progress_bar.set_visible(phase == 1)
        self._speed_samples.clear()
        self._last_speed_update = 0.0

    def _on_download_progress(self, _backend, nevra, downloaded,
                              total_bytes, pkgs_done, pkgs_total):
        if nevra:
            self._current_dl_nevra = nevra
        if pkgs_total > 0:
            self.overall_progress_bar.set_fraction(pkgs_done / pkgs_total)
            self.overall_progress_bar.set_text(
                f'{pkgs_done} / {pkgs_total} packages')
        if total_bytes > 0:
            self.item_progress_bar.set_fraction(downloaded / total_bytes)

        now = GLib.get_monotonic_time() / 1_000_000
        self._speed_samples.append((now, downloaded))
        while (self._speed_samples
               and (now - self._speed_samples[0][0]) > 3.0):
            self._speed_samples.popleft()

        if now - self._last_speed_update >= 0.5 and len(self._speed_samples) >= 2:
            self._last_speed_update = now
            dt = self._speed_samples[-1][0] - self._speed_samples[0][0]
            db = self._speed_samples[-1][1] - self._speed_samples[0][1]
            if dt > 0 and db >= 0:
                speed = db / dt
                speed_str = self._format_speed(speed)
                name = self._current_dl_nevra or ''
                if name:
                    self.progress_detail_label.set_label(
                        f'{name} \u2014 {speed_str}')
                else:
                    self.progress_detail_label.set_label(speed_str)

    def _on_install_progress(self, _backend, nevra, item_amount,
                             item_total, items_done, items_total):
        if items_total > 0:
            item_frac = item_amount / item_total if item_total > 0 else 0
            fraction = (items_done + item_frac) / items_total
            fraction = max(self.overall_progress_bar.get_fraction(), fraction)
            self.overall_progress_bar.set_fraction(fraction)
            self.overall_progress_bar.set_text(
                f'{items_done} / {items_total}')
        if nevra:
            self.progress_detail_label.set_label(nevra)

    @staticmethod
    def _format_speed(bps):
        if bps >= 1_000_000:
            return f'{bps / 1_000_000:.1f} MB/s'
        if bps >= 1_000:
            return f'{bps / 1_000:.0f} KB/s'
        return f'{bps:.0f} B/s'

    def _on_upgrade_completed(self, _backend, reboot_needed):
        self._dnf_upgrade_done = True
        self._reboot_needed = self._reboot_needed or reboot_needed
        self._maybe_finish_update()

    def _on_flatpak_upgrade_completed(self, _backend):
        self._flatpak_upgrade_done = True
        self._maybe_finish_update()

    def _maybe_finish_update(self):
        if not (self._dnf_upgrade_done and self._flatpak_upgrade_done):
            return

        self.refresh_button.set_sensitive(True)
        self.overall_progress_bar.set_fraction(1.0)

        if self._reboot_needed:
            log.info('Update finished, reboot required')
            self.main_stack.set_visible_child_name('restart-needed')
        else:
            log.info('Update finished successfully')
            self.main_stack.set_visible_child_name('done')

    def _on_error(self, _backend, message):
        log.error('Backend error: %s', message)
        self.refresh_button.set_sensitive(True)
        self.error_status_page.set_description(GLib.markup_escape_text(message))
        self.main_stack.set_visible_child_name('error')

    # ── System upgrade handlers ───────────────────────────────────

    def _on_system_upgrade_check_completed(self, _backend, target_version):
        self._upgrade_target_version = target_version
        if target_version > 0:
            log.info('Fedora %d upgrade available', target_version)
        self._update_upgrade_banner()

    def _update_upgrade_banner(self):
        """Show the upgrade banner only when updates must be installed first.

        When the system is up to date, the upgrade is shown as a main stack
        page instead of a banner.
        """
        if (self._upgrade_target_version <= 0
                or not self._dnf_check_done
                or not self._dnf_packages):
            self.upgrade_banner.set_revealed(False)
            return

        ver = self._upgrade_target_version
        self.upgrade_banner.set_title(
            f'Fedora {ver} is available \u2014 install updates and restart first'
        )
        self.upgrade_banner.set_revealed(True)

    def _start_system_upgrade(self):
        log.info('User initiated system upgrade download for Fedora %d',
                 self._upgrade_target_version)
        self.main_stack.set_visible_child_name('system-upgrade-downloading')
        self.upgrade_progress_bar.set_fraction(0.0)
        self.upgrade_progress_label.set_label('')
        self.refresh_button.set_sensitive(False)
        self.system_upgrade_backend.download_upgrade_async(
            self._upgrade_target_version
        )

    def _on_system_upgrade_download_progress(self, _backend, message, fraction):
        if fraction >= 0:
            self.upgrade_progress_bar.set_fraction(fraction)
        else:
            self.upgrade_progress_bar.pulse()
        self.upgrade_progress_label.set_label(message)

    def _on_system_upgrade_download_completed(self, _backend):
        log.info('System upgrade download complete, ready for reboot')
        self.refresh_button.set_sensitive(True)
        self.main_stack.set_visible_child_name('system-upgrade-ready')

    def _do_upgrade_reboot(self):
        self.system_upgrade_backend.trigger_offline_reboot()

    def _do_restart(self):
        from .utils import request_reboot
        request_reboot()
