# Fedora Updater

A graphical system updater for Fedora. Updates system packages via DNF and Flatpak applications, shows security advisories, and handles reboot detection. Includes a systemd timer for periodic background update checks.

## Dependencies

- Python 3
- PyGObject (python3-gobject)
- GTK 4
- libadwaita
- flatpak-libs
- dnf5daemon-server
- polkit
- meson (>= 1.0.0)
- blueprint-compiler

On Fedora, install build and runtime dependencies with:

```sh
sudo dnf install meson python3-devel blueprint-compiler desktop-file-utils \
    appstream glib2-devel gettext systemd-rpm-macros \
    python3-gobject gtk4 libadwaita flatpak-libs dnf5daemon-server polkit
```

You'll most likely have all these dependencies other than `blueprint-compiler`.

## Running Locally

A convenience script builds and runs the app from a local prefix:

```sh
./run.sh
```

This will:
1. Configure a Meson build directory at `_build/` with a local install prefix at `_install/`
2. Compile the project
3. Install to the local prefix
4. Run the application

## Building and Installing the RPM

Use the included build script:

```sh
./build-rpm.sh
```

This creates a source archive from the current HEAD via `git archive`, then builds the RPM with `rpmbuild`. Output locations are printed when the build completes:

Install the built RPM with:

```sh
sudo dnf install ~/rpmbuild/RPMS/noarch/fedora-updater-*.noarch.rpm
```

## License

GPL-3.0-or-later. See [COPYING](COPYING) for details.
