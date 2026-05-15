# flatpak_backend.py
#
# Copyright 2026 Ben
#
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Gio, GLib, GObject

try:
    import gi as _gi
    _gi.require_version('Flatpak', '1.0')
    from gi.repository import Flatpak
    HAS_FLATPAK = True
except (ValueError, ImportError):
    HAS_FLATPAK = False


class FlatpakBackend(GObject.Object):
    """Async Flatpak update operations using GI bindings."""

    __gsignals__ = {
        'check-completed': (GObject.SignalFlags.RUN_LAST, None, (object,)),
        'error': (GObject.SignalFlags.RUN_LAST, None, (str,)),
        'upgrade-completed': (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self):
        super().__init__()

    def check_updates_async(self):
        if not HAS_FLATPAK:
            self.emit('check-completed', [])
            return
        task = Gio.Task.new(self, None, self._on_check_task_done)
        task.run_in_thread(self._check_thread)

    def _check_thread(self, task, _source, _data, _cancellable):
        try:
            installation = Flatpak.Installation.new_system(None)
            refs = installation.list_installed_refs_for_update(None)
            result = []
            for ref in refs:
                result.append({
                    'name': ref.get_appdata_name() or ref.get_name(),
                    'ref': ref.format_ref(),
                    'branch': ref.get_branch(),
                    'origin': ref.get_origin(),
                })
            task.return_value(result)
        except GLib.Error as e:
            task.return_value(None)
            GLib.idle_add(self.emit, 'error', f'Flatpak check failed: {e.message}')

    def _on_check_task_done(self, source, result, _data=None):
        value = result.propagate_value().value
        if value is not None:
            self.emit('check-completed', value)

    def update_all_async(self):
        if not HAS_FLATPAK:
            self.emit('upgrade-completed')
            return
        task = Gio.Task.new(self, None, self._on_update_task_done)
        task.run_in_thread(self._update_thread)

    def _update_thread(self, task, _source, _data, _cancellable):
        try:
            installation = Flatpak.Installation.new_system(None)
            transaction = Flatpak.Transaction.new_for_installation(installation, None)
            refs = installation.list_installed_refs_for_update(None)
            for ref in refs:
                transaction.add_update(ref.format_ref(), None, None)
            transaction.run(None)
            task.return_boolean(True)
        except GLib.Error as e:
            task.return_boolean(False)
            GLib.idle_add(self.emit, 'error', f'Flatpak update failed: {e.message}')

    def _on_update_task_done(self, source, result, _data=None):
        try:
            result.propagate_boolean()
            self.emit('upgrade-completed')
        except GLib.Error:
            pass
