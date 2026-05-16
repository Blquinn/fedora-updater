pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()
moduledir = pkgdatadir / 'fedora_updater'
gnome = import('gnome')

blueprint_compiler = find_program('blueprint-compiler')

blueprints = custom_target('blueprints',
  input: files(
    'window.blp',
    'preferences_window.blp',
  ),
  output: '.',
  command: [blueprint_compiler, 'batch-compile', '@OUTPUT@', '@CURRENT_SOURCE_DIR@', '@INPUT@'],
)

gnome.compile_resources('fedora-updater',
  'fedora-updater.gresource.xml',
  gresource_bundle: true,
  install: true,
  install_dir: pkgdatadir,
  dependencies: blueprints,
)

python = import('python')

conf = configuration_data()
conf.set('PYTHON', python.find_installation('python3.14').full_path())
conf.set('VERSION', meson.project_version())
conf.set('localedir', get_option('prefix') / get_option('localedir'))
conf.set('pkgdatadir', pkgdatadir)

configure_file(
  input: 'fedora-updater.in',
  output: 'fedora-updater',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x'
)

fedora_updater_sources = [
  '__init__.py',
  'main.py',
  'window.py',
  'dnf_backend.py',
  'flatpak_backend.py',
  'system_upgrade_backend.py',
  'mock_backends.py',
  'utils.py',
  'preferences_window.py',
]

install_data(fedora_updater_sources, install_dir: moduledir)

install_data('helpers/upgrade_helper.py',
  install_dir: pkgdatadir,
  install_mode: 'rwxr-xr-x',
)

install_data('helpers/system_upgrade_helper.py',
  install_dir: pkgdatadir,
  install_mode: 'rwxr-xr-x',
)

install_data(
  'demo_scenarios/updates_available.json',
  'demo_scenarios/upgrade_available.json',
  install_dir: pkgdatadir / 'demo_scenarios',
)
