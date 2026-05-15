# preferences_window.py
#
# Copyright 2026 Benjamin Quinn <benjamin.quinn92@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Adw, Gio, Gtk


@Gtk.Template(resource_path='/me/blq/FedoraUpdater/preferences_window.ui')
class FedoraUpdaterPreferencesWindow(Adw.PreferencesDialog):
    __gtype_name__ = 'FedoraUpdaterPreferencesWindow'

    auto_check_row = Gtk.Template.Child()
    check_interval_row = Gtk.Template.Child()
    include_flatpak_row = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._settings = Gio.Settings(schema_id='me.blq.FedoraUpdater')
        self._settings.bind('auto-check-enabled', self.auto_check_row, 'active',
                            Gio.SettingsBindFlags.DEFAULT)
        self._settings.bind('check-interval-hours', self.check_interval_row, 'value',
                            Gio.SettingsBindFlags.DEFAULT)
        self._settings.bind('include-flatpak', self.include_flatpak_row, 'active',
                            Gio.SettingsBindFlags.DEFAULT)
