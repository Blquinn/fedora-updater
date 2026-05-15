# main.py
#
# Copyright 2026 Ben
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

import logging
import sys

import gi

from gettext import gettext as _

logging.basicConfig(
    level=logging.DEBUG if '--debug' in sys.argv else logging.INFO,
    format='%(name)s: %(levelname)s: %(message)s',
)
log = logging.getLogger(__name__)

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Gio, Adw
from .window import FedoraUpdaterWindow
from .preferences_window import FedoraUpdaterPreferencesWindow


class FedoraUpdaterApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self, pkgdatadir):
        super().__init__(application_id='me.blq.FedoraUpdater',
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
                         resource_base_path='/me/blq/FedoraUpdater')
        self.pkgdatadir = pkgdatadir
        self.create_action('quit', lambda *_: self.quit(), ['<control>q'])
        self.create_action('about', self.on_about_action)
        self.create_action('preferences', self.on_preferences_action)
        self.create_action('refresh', self.on_refresh_action, ['<control>r'])

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = FedoraUpdaterWindow(application=self)
        win.present()

    def on_about_action(self, *args):
        about = Adw.AboutDialog(
            application_name='Fedora Updater',
            application_icon='me.blq.FedoraUpdater',
            version='0.1.0',
            developers=['Ben'],
            # Translators: Replace "translator-credits" with your name/username, and optionally an email or URL.
            translator_credits=_('translator-credits'),
            copyright='© 2026 Ben',
            license_type=Gtk.License.GPL_3_0,
        )
        about.present(self.props.active_window)

    def on_preferences_action(self, widget, _):
        prefs = FedoraUpdaterPreferencesWindow()
        prefs.present(self.props.active_window)

    def on_refresh_action(self, *args):
        win = self.props.active_window
        if win:
            win.check_for_updates()

    def create_action(self, name, callback, shortcuts=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)


def _check_updates_headless():
    """Headless update check for systemd timer — sends desktop notification."""
    import libdnf5.base
    import libdnf5.rpm

    log.info('Running headless update check')
    settings = Gio.Settings(schema_id='me.blq.FedoraUpdater')

    base = libdnf5.base.Base()
    base.load_config()
    base.setup()
    base.get_repo_sack().create_repos_from_system_configuration()
    base.get_repo_sack().load_repos()

    query = libdnf5.rpm.PackageQuery(base)
    query.filter_upgrades()
    dnf_count = query.size()
    log.info('Headless check: %d DNF update(s)', dnf_count)

    flatpak_count = 0
    if settings.get_boolean('include-flatpak'):
        try:
            gi.require_version('Flatpak', '1.0')
            from gi.repository import Flatpak
            installation = Flatpak.Installation.new_system(None)
            flatpak_count = len(installation.list_installed_refs_for_update(None))
            log.info('Headless check: %d Flatpak update(s)', flatpak_count)
        except Exception:
            log.warning('Flatpak check failed in headless mode', exc_info=True)

    total = dnf_count + flatpak_count
    if total == 0:
        log.info('No updates found')
        return 0

    app = Gio.Application(application_id='me.blq.FedoraUpdater',
                          flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
    app.register(None)

    notification = Gio.Notification.new(_('Updates Available'))
    parts = []
    if dnf_count:
        parts.append(f'{dnf_count} system package{"s" if dnf_count != 1 else ""}')
    if flatpak_count:
        parts.append(f'{flatpak_count} Flatpak app{"s" if flatpak_count != 1 else ""}')
    notification.set_body(', '.join(parts))
    notification.set_default_action('app.show-updates')
    app.send_notification('updates-available', notification)
    return 0


def main(version, pkgdatadir=None):
    """The application's entry point."""
    log.info('Fedora Updater %s starting', version)

    if '--check-updates' in sys.argv:
        return _check_updates_headless()

    app = FedoraUpdaterApplication(pkgdatadir or '')
    return app.run(sys.argv)
