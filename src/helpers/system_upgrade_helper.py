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
import re
import subprocess
import sys


def emit(msg_type, **kwargs):
    kwargs['type'] = msg_type
    print(json.dumps(kwargs), flush=True)


# Matches dnf5 download progress lines like:
#   [  1/502] package-1.0-1.fc43.x86_64.rpm    5.0 MiB/s |   2.1 MiB |  00m00s
_DL_RE = re.compile(
    r'^\[\s*(\d+)/(\d+)\]\s+(\S+)'
)
_SPEED_RE = re.compile(
    r'([\d.]+\s*\S+/s)'
)


def do_download(releasever):
    """Download system upgrade packages for the target release."""
    emit('status', message=f'Preparing upgrade to Fedora {releasever}')

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

        m = _DL_RE.match(line)
        if m:
            pkg_done = int(m.group(1))
            pkg_total = int(m.group(2))
            nevra = m.group(3)
            speed_m = _SPEED_RE.search(line)
            speed = speed_m.group(1) if speed_m else ''
            emit('download-progress',
                 nevra=nevra, packages_done=pkg_done,
                 packages_total=pkg_total, speed=speed)
        else:
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
