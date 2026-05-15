desktop_file = i18n.merge_file(
        input: 'me.blq.FedoraUpdater.desktop.in',
       output: 'me.blq.FedoraUpdater.desktop',
         type: 'desktop',
       po_dir: '../po',
      install: true,
  install_dir: get_option('datadir') / 'applications'
)

desktop_utils = find_program('desktop-file-validate', required: false)
if desktop_utils.found()
  test('Validate desktop file', desktop_utils, args: [desktop_file])
endif

appstream_file = i18n.merge_file(
        input: 'me.blq.FedoraUpdater.metainfo.xml.in',
       output: 'me.blq.FedoraUpdater.metainfo.xml',
       po_dir: '../po',
      install: true,
  install_dir: get_option('datadir') / 'metainfo'
)

appstreamcli = find_program('appstreamcli', required: false, disabler: true)
test('Validate appstream file', appstreamcli,
     args: ['validate', '--no-net', '--explain', appstream_file])

install_data('me.blq.FedoraUpdater.gschema.xml',
  install_dir: get_option('datadir') / 'glib-2.0' / 'schemas'
)

compile_schemas = find_program('glib-compile-schemas', required: false, disabler: true)
test('Validate schema file',
     compile_schemas,
     args: ['--strict', '--dry-run', meson.current_source_dir()])


service_conf = configuration_data()
service_conf.set('bindir', get_option('prefix') / get_option('bindir'))
configure_file(
  input: 'me.blq.FedoraUpdater.service.in',
  output: 'me.blq.FedoraUpdater.service',
  configuration: service_conf,
  install_dir: get_option('datadir') / 'dbus-1' / 'services'
)

systemd_user_dir = get_option('prefix') / 'lib' / 'systemd' / 'user'

install_data('me.blq.FedoraUpdater.timer',
  install_dir: systemd_user_dir)
install_data('me.blq.FedoraUpdater.check.service',
  install_dir: systemd_user_dir)

pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()

policy_conf = configuration_data()
policy_conf.set('pkgdatadir', pkgdatadir)
configure_file(
  input: 'me.blq.FedoraUpdater.policy.in',
  output: 'me.blq.FedoraUpdater.policy',
  configuration: policy_conf,
  install_dir: get_option('datadir') / 'polkit-1' / 'actions',
)

install_data('me.blq.FedoraUpdater.upgrade_helper.py',
  install_dir: pkgdatadir,
  install_mode: 'rwxr-xr-x',
)

subdir('icons')
