# utils.py
#
# Copyright 2026 Ben
#
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Gio, GLib


def request_reboot():
    """Request a system reboot via systemd-logind D-Bus interface."""
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        bus.call_sync(
            'org.freedesktop.login1',
            '/org/freedesktop/login1',
            'org.freedesktop.login1.Manager',
            'Reboot',
            GLib.Variant('(b)', (True,)),
            None,
            Gio.DBusCallFlags.NONE,
            -1, None,
        )
    except GLib.Error as e:
        print(f'Failed to request reboot: {e.message}')
