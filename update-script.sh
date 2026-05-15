#!/usr/bin/env zsh

set +e

sudo dnf upgrade --refresh
sudo flatpak update

if sudo dnf needs-restarting -r | grep -qi 'Reboot should not be necessary'; then
  echo "No reboot needed"
else
  read "answer?Reboot required. Reboot now? (Y/n) "
  if [[ "${answer:-Y}" =~ ^[Yy]$ ]]; then
    sudo reboot
  fi
fi

set -e
