# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## Project

GNOME system updater app for Fedora. App ID `me.blq.FedoraUpdater`, resource base path `/me/blq/FedoraUpdater`. Updates DNF system packages (via dnf5daemon-server D-Bus API) and Flatpak applications (via GI bindings), shows security advisories, detects reboot requirements, and supports background update checking via a systemd timer.

Uses libadwaita (`Adw.Application`, `Adw.ApplicationWindow`), Blueprint (`.blp` → `.ui`), and Python.

## Build, run, test

Meson + Ninja, out-of-tree build in `build/`:

```sh
meson setup build                       # first time / after changing meson.build
meson compile -C build                   # or: ninja -C build
meson test -C build                      # runs desktop-file/appstream/gschema validators
meson install -C build --destdir=_inst   # stage install to inspect layout
```

The `fedora-updater` launcher is generated from `src/fedora-updater.in` — `@PYTHON@`, `@VERSION@`, `@pkgdatadir@`, `@localedir@` are substituted at configure time, so running the in-tree `src/main.py` directly won't work; install first.

Build dependencies: `blueprint-compiler`, `python3` (system, with `gi` module), `meson >= 1.0.0`.

Flatpak (matches what GNOME Builder uses):

```sh
flatpak-builder --user --install --force-clean build-flatpak me.blq.FedoraUpdater.json
flatpak run me.blq.FedoraUpdater
```

Note `me.blq.FedoraUpdater.json` points `sources[0].url` at `file:///home/ben/Code/gnome` — flatpak-builder clones from that local git path, so commit changes before rebuilding the Flatpak or it won't pick them up.

## Architecture notes worth knowing up front

- **Blueprint UI.** `.blp` files in `src/` are compiled to `.ui` XML by `blueprint-compiler batch-compile` via a `custom_target` in `src/meson.build`. The compiled `.ui` files go into the build directory and are bundled into the GResource. Add new `.blp` files to both the `blueprints` custom_target input list and `fedora-updater.gresource.xml`.
- **GResource bundle.** `src/fedora-updater.gresource.xml` lists UI files compiled into `fedora-updater.gresource`. The `gnome.compile_resources()` call depends on the `blueprints` target. Static `.ui` files (like `gtk/help-overlay.ui`) live in source; blueprint-compiled ones come from the build dir.
- **Python package layout.** All `.py` modules under `src/` are listed in `fedora_updater_sources` in `src/meson.build` and installed to `$pkgdatadir/fedora_updater/`. Adding a new module means adding it to that list.
- **DNF backend.** `src/dnf_backend.py` communicates with `dnf5daemon-server` over the system D-Bus (`org.rpm.dnf.v0`). Session-based: opens a session, calls methods (`Base.read_all_repos`, `Rpm.list`, `Rpm.upgrade`, `Goal.resolve`, `Goal.do_transaction`, `Advisory.list`), subscribes to progress signals, then closes the session. All calls are async via `Gio.DBusConnection.call()`. Note: `read_all_repos` and `do_transaction` can take minutes — use `TIMEOUT_LONG` (600s), not the GDBus default 25s.
- **Flatpak backend.** `src/flatpak_backend.py` uses `gi.repository.Flatpak` GI bindings. Read operations (listing updates) are fast; write operations (`Flatpak.Transaction.run()`) block and must run in `Gio.Task.run_in_thread()`.
- **Privilege escalation.** The app runs as normal user. dnf5daemon uses polkit for auth (prompts handled by GNOME Shell's polkit agent). Flatpak system transactions also use polkit.
- **GSettings.** Schema `me.blq.FedoraUpdater.gschema.xml` in `data/` with keys: `auto-check-enabled` (bool), `check-interval-hours` (int), `include-flatpak` (bool).
- **i18n.** Every translatable source file (`.blp`, `.py`) must be listed in `po/POTFILES.in` (sorted).
- **App actions.** Registered in `FedoraUpdaterApplication.__init__` via `create_action` helper: `quit` (Ctrl+Q), `about`, `preferences`, `refresh` (Ctrl+R).
- **Background checking.** `fedora-updater --check-updates` runs headless (no window), uses libdnf5 directly for read-only package queries, and sends a `Gio.Notification`. Triggered by systemd user timer `me.blq.FedoraUpdater.timer`.
