#!/usr/bin/env python3
# system_upgrade_helper.py
#
# Copyright 2026 Benjamin Quinn <benjamin.quinn92@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Root helper for Fedora major version upgrades.
# Launched by the main app through pkexec for polkit authentication.
# Communicates progress back via JSON lines on stdout.
#
# Usage:
#   system_upgrade_helper.py <releasever>   — download upgrade packages
#   system_upgrade_helper.py reboot         — trigger offline upgrade reboot

import json
import subprocess
import sys


def emit(msg_type, **kwargs):
    kwargs['type'] = msg_type
    print(json.dumps(kwargs), flush=True)


def do_download(releasever):
    """Download system upgrade packages for the target release."""
    emit('status', message=f'Downloading upgrade packages for Fedora {releasever}')

    proc = subprocess.Popen(
        ['dnf5', 'system-upgrade', 'download',
         f'--releasever={releasever}', '-y'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        emit('status', message=line)

    rc = proc.wait()
    if rc != 0:
        emit('error', message=f'dnf5 system-upgrade download failed (exit code {rc})')
        return 1

    emit('done')
    return 0


def do_reboot():
    """Trigger offline upgrade reboot."""
    emit('status', message='Triggering offline upgrade reboot')

    result = subprocess.run(
        ['dnf5', 'offline', 'reboot'],
        capture_output=True, text=True,
    )

    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or 'Unknown error'
        emit('error', message=f'Failed to trigger offline reboot: {msg}')
        return 1

    emit('done')
    return 0


def main():
    if len(sys.argv) < 2:
        emit('error', message='Usage: system_upgrade_helper.py <releasever|reboot>')
        return 1

    command = sys.argv[1]

    if command == 'reboot':
        return do_reboot()
    else:
        try:
            releasever = int(command)
        except ValueError:
            emit('error', message=f'Invalid releasever: {command}')
            return 1
        return do_download(releasever)


if __name__ == '__main__':
    sys.exit(main())
