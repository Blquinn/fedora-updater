# utils.py
#
# Copyright 2026 Benjamin Quinn <benjamin.quinn92@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import logging

from gi.repository import Gio, GLib

log = logging.getLogger(__name__)


def request_reboot():
    """Request a system reboot via systemd-logind D-Bus interface."""
    log.info('Requesting system reboot via logind')
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
        log.error('Failed to request reboot: %s', e.message)
