#!/usr/bin/env python3
# upgrade_helper.py
#
# Copyright 2026 Ben
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Root helper for running DNF upgrades via libdnf5.
# Launched by the main app through pkexec for polkit authentication.
# Communicates progress back via JSON lines on stdout.

import json
import sys

import libdnf5.base
import libdnf5.repo
import libdnf5.rpm

REBOOT_PACKAGES = {
    'kernel', 'kernel-core', 'kernel-modules', 'kernel-modules-core',
    'glibc', 'systemd', 'dbus', 'dbus-daemon', 'linux-firmware',
    'gnutls', 'openssl-libs',
}


def emit(msg_type, **kwargs):
    kwargs['type'] = msg_type
    print(json.dumps(kwargs), flush=True)


class ProgressCB(libdnf5.rpm.TransactionCallbacks):
    def __init__(self):
        super().__init__()
        self._total_items = 0
        self._done_items = 0

    def install_progress(self, item, amount, total):
        self._report(item, amount, total)

    def uninstall_progress(self, item, amount, total):
        self._report(item, amount, total)

    def transaction_progress(self, amount, total):
        self._total_items = total
        self._done_items = amount
        emit('progress', nevra='', processed=amount, total=total)

    def install_start(self, item, total):
        nevra = item.get_package().get_nevra() if item.get_package() else ''
        emit('item-start', nevra=nevra, action='install')

    def uninstall_start(self, item, total):
        nevra = item.get_package().get_nevra() if item.get_package() else ''
        emit('item-start', nevra=nevra, action='remove')

    def _report(self, item, amount, total):
        nevra = item.get_package().get_nevra() if item.get_package() else ''
        emit('progress', nevra=nevra, processed=self._done_items,
             total=self._total_items)


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

        emit('status', message='Downloading packages')
        transaction.download()

        emit('status', message='Running transaction')

        cb = ProgressCB()
        cb_ptr = libdnf5.rpm.TransactionCallbacksUniquePtr(cb)
        transaction.set_callbacks(cb_ptr)
        result = transaction.run()

        if result != 0:
            problems = transaction.get_transaction_problems()
            msg = '; '.join(problems) if problems else f'code {result}'
            emit('error', message=f'Transaction failed: {msg}')
            return 1

        reboot_needed = False
        for nevra in nevras:
            name = nevra.split('-')[0] if nevra else ''
            if name in REBOOT_PACKAGES:
                reboot_needed = True
                break

        emit('done', reboot_needed=reboot_needed)
        return 0

    except Exception as e:
        emit('error', message=str(e))
        return 1


if __name__ == '__main__':
    sys.exit(main())
