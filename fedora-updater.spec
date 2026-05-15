%global app_id me.blq.FedoraUpdater

Name:           fedora-updater
Version:        0.1.0
Release:        1%{?dist}
Summary:        Graphical system updater for Fedora

License:        GPL-3.0-or-later
URL:            https://github.com/Blquinn/fedora-updater
Source0:        %{name}-%{version}.tar.xz

BuildArch:      noarch

BuildRequires:  meson >= 1.0.0
BuildRequires:  python3-devel
BuildRequires:  blueprint-compiler
BuildRequires:  desktop-file-utils
BuildRequires:  appstream
BuildRequires:  glib2-devel
BuildRequires:  gettext
BuildRequires:  systemd-rpm-macros

Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       flatpak-libs
Requires:       dnf5daemon-server
Requires:       polkit

%description
A simple graphical system updater for Fedora. Updates system packages via DNF
and Flatpak applications, shows security advisories, and handles reboot
detection. Includes a systemd timer for periodic background update checks.

%prep
%autosetup -p1

%build
%meson
%meson_build

%install
%meson_install
# %find_lang %{name} — re-enable when translations are added

%check
%meson_test

%post
%systemd_user_post %{app_id}.timer

%preun
%systemd_user_preun %{app_id}.timer

%postun
%systemd_user_postun %{app_id}.timer

%files
%license COPYING
%doc README.md
%{_bindir}/fedora-updater
%{_datadir}/fedora-updater/
%{_datadir}/applications/%{app_id}.desktop
%{_datadir}/metainfo/%{app_id}.metainfo.xml
%{_datadir}/glib-2.0/schemas/%{app_id}.gschema.xml
%{_datadir}/dbus-1/services/%{app_id}.service
%{_datadir}/icons/hicolor/scalable/apps/%{app_id}.svg
%{_datadir}/icons/hicolor/symbolic/apps/%{app_id}-symbolic.svg
%{_datadir}/polkit-1/actions/%{app_id}.policy
%{_prefix}/lib/systemd/user/%{app_id}.timer
%{_prefix}/lib/systemd/user/%{app_id}.check.service

%changelog
* Fri May 15 2026 Benjamin Quinn <ben@blq.me> - 0.1.0-1
- Initial package
