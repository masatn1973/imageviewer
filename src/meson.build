python = import('python').find_installation('python3')
gnome = import('gnome')

gnome.compile_resources(
  'imageviewer',
  'imageviewer.gresource.xml',
  source_dir: '.',
  gresource_bundle: true,
  install: true,
  install_dir: '/app/share/imageviewer'
)

install_data(
  'imageviewer',
  install_dir: get_option('bindir')
)

install_data([
  'main.py',
  'imagestate.py',
  'imageops.py',
  'renderer.py',
  'window.py',
  'viewer.py',
  'shortcuts.py',
  'preferences.py',
], install_dir: '/app/share/imageviewer')
