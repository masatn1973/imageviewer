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
  '__init__.py',
  'main.py',
  'window.py',
  'viewer.py',
  'about.py',
  'shortcuts.py',
], install_dir: '/app/share/imageviewer/imageviewer')
