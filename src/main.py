# main.py
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

import argparse
import json
import logging
import os
import sys

import gi

from gettext import gettext as _

_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument('--debug', action='store_true')
_parser.add_argument('--check-updates', action='store_true')
_parser.add_argument('--demo', nargs='?', const=True, default=None,
                     metavar='SCENARIO_FILE',
                     help='Run with mock backends. Optionally specify a scenario JSON file.')
_args, _remaining_argv = _parser.parse_known_args()

logging.basicConfig(
    level=logging.DEBUG if _args.debug else logging.INFO,
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

    def __init__(self, pkgdatadir, demo_scenario=None):
        super().__init__(application_id='me.blq.FedoraUpdater',
                         flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
                         resource_base_path='/me/blq/FedoraUpdater')
        self.pkgdatadir = pkgdatadir
        self._demo_scenario = demo_scenario
        self.create_action('quit', lambda *_: self.quit(), ['<control>q'])
        self.create_action('about', self.on_about_action)
        self.create_action('preferences', self.on_preferences_action)
        self.create_action('refresh', self.on_refresh_action, ['<control>r'])

    def do_activate(self):
        win = self.props.active_window
        if not win:
            if self._demo_scenario is not None:
                from .mock_backends import MockDnfBackend, MockFlatpakBackend
                win = FedoraUpdaterWindow(
                    application=self,
                    dnf_backend=MockDnfBackend(self._demo_scenario.get('dnf', {})),
                    flatpak_backend=MockFlatpakBackend(self._demo_scenario.get('flatpak', {})),
                )
            else:
                win = FedoraUpdaterWindow(application=self)
        win.present()

    def on_about_action(self, *args):
        about = Adw.AboutDialog(
            application_name='Fedora Updater',
            application_icon='me.blq.FedoraUpdater',
            version='0.1.0',
            developers=['Benjamin Quinn'],
            # Translators: Replace "translator-credits" with your name/username, and optionally an email or URL.
            translator_credits=_('translator-credits'),
            copyright='© 2026 Benjamin Quinn',
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


def _load_demo_scenario(demo_arg, pkgdatadir):
    """Load a demo scenario JSON file. Returns the parsed dict, or None."""
    if demo_arg is None:
        return None

    if demo_arg is True:
        # --demo with no file: use bundled default
        path = os.path.join(pkgdatadir, 'demo_scenarios', 'updates_available.json')
    else:
        path = demo_arg

    log.info('Loading demo scenario from %s', path)
    with open(path) as f:
        return json.load(f)


def main(version, pkgdatadir=None):
    """The application's entry point."""
    log.info('Fedora Updater %s starting', version)

    if _args.check_updates:
        return _check_updates_headless()

    pkgdatadir = pkgdatadir or ''
    demo_scenario = _load_demo_scenario(_args.demo, pkgdatadir)
    if demo_scenario is not None:
        log.info('Running in demo mode')

    app = FedoraUpdaterApplication(pkgdatadir, demo_scenario=demo_scenario)
    return app.run([sys.argv[0]] + _remaining_argv)
