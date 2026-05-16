#!/usr/bin/env python3
# upgrade_helper.py
#
# Copyright 2026 Benjamin Quinn <benjamin.quinn92@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Root helper for running DNF upgrades via libdnf5.
# Launched by the main app through pkexec for polkit authentication.
# Communicates progress back via JSON lines on stdout.

import json
import subprocess
import sys
import time

import libdnf5.base
import libdnf5.repo
import libdnf5.rpm


def emit(msg_type, **kwargs):
    kwargs['type'] = msg_type
    print(json.dumps(kwargs), flush=True)


class DownloadProgressCB(libdnf5.repo.DownloadCallbacks):
    """Report per-package download progress via JSON on stdout."""

    def __init__(self, total_packages):
        super().__init__()
        self._total_packages = total_packages
        self._done_packages = 0
        self._last_progress_time = 0

    def add_new_download(self, user_data, description, total_to_download):
        emit('download-start', nevra=description,
             total_to_download=int(total_to_download),
             packages_done=self._done_packages,
             packages_total=self._total_packages)
        return user_data

    def progress(self, user_cb_data, total_to_download, downloaded):
        now = time.monotonic()
        if now - self._last_progress_time < 0.1:
            return 0  # OK
        self._last_progress_time = now
        emit('download-progress',
             downloaded=int(downloaded),
             total_to_download=int(total_to_download),
             packages_done=self._done_packages,
             packages_total=self._total_packages)
        return 0  # OK

    def end(self, user_cb_data, status, msg):
        self._done_packages += 1
        emit('download-end',
             packages_done=self._done_packages,
             packages_total=self._total_packages)
        return 0  # OK


class ProgressCB(libdnf5.rpm.TransactionCallbacks):
    def __init__(self):
        super().__init__()
        self._total_items = 0
        self._done_items = 0
        self._started = False

    def install_progress(self, item, amount, total):
        self._report(item, amount, total)

    def uninstall_progress(self, item, amount, total):
        self._report(item, amount, total)

    def transaction_progress(self, amount, total):
        self._total_items = total

    def install_start(self, item, total):
        if self._started:
            self._done_items += 1
        self._started = True
        nevra = item.get_package().get_nevra() if item.get_package() else ''
        emit('item-start', nevra=nevra, action='install')

    def uninstall_start(self, item, total):
        if self._started:
            self._done_items += 1
        self._started = True
        nevra = item.get_package().get_nevra() if item.get_package() else ''
        emit('item-start', nevra=nevra, action='remove')

    def _report(self, item, amount, total):
        nevra = item.get_package().get_nevra() if item.get_package() else ''
        emit('install-progress', nevra=nevra,
             item_amount=amount, item_total=total,
             items_done=self._done_items, items_total=self._total_items)


def main():
    try:
        emit('status', message='Loading repos')

        base = libdnf5.base.Base()
        base.load_config()
        base.setup()
        base.get_repo_sack().create_repos_from_system_configuration()
        base.get_repo_sack().load_repos()

        emit('status', message='Resolving upgrades')

        goal = libdnf5.base.Goal(base)
        goal.add_rpm_upgrade()
        transaction = goal.resolve()

        problems = transaction.get_problems()
        if problems:
            emit('error', message=f'Transaction resolve failed: {problems}')
            return 1

        packages = transaction.get_transaction_packages()
        nevras = []
        for pkg in packages:
            nevras.append(pkg.get_package().get_nevra())
        emit('resolved', count=len(nevras), nevras=nevras)

        if not nevras:
            emit('done', reboot_needed=False)
            return 0

        emit('phase', phase=1, total_phases=2, label='Downloading')
        dl_cb = DownloadProgressCB(len(nevras))
        dl_cb_ptr = libdnf5.repo.DownloadCallbacksUniquePtr(dl_cb)
        base.set_download_callbacks(dl_cb_ptr)
        transaction.download()

        emit('phase', phase=2, total_phases=2, label='Installing')

        cb = ProgressCB()
        cb_ptr = libdnf5.rpm.TransactionCallbacksUniquePtr(cb)
        transaction.set_callbacks(cb_ptr)
        result = transaction.run()

        if result != 0:
            problems = transaction.get_transaction_problems()
            msg = '; '.join(problems) if problems else f'code {result}'
            emit('error', message=f'Transaction failed: {msg}')
            return 1

        result = subprocess.run(
            ['dnf5', 'needs-restarting', '--json'],
            capture_output=True, text=True,
        )
        reboot_needed = False
        if result.returncode == 0:
            for entry in json.loads(result.stdout):
                if entry.get('type') == 'reboot' and entry.get('reboot_required'):
                    reboot_needed = True
                    break

        emit('done', reboot_needed=reboot_needed)
        return 0

    except Exception as e:
        emit('error', message=str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())
