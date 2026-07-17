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
  'window.py',
  'viewer.py',
  'imagecanvas.py',
  'shortcuts.py',
  'preferences.py',
], install_dir: '/app/share/imageviewer')

install_data([
  'models/__init__.py',
  'models/gallerymodel.py',
  'models/imagestate.py',
  'models/exifinfo.py',
  'models/geometry.py',
], install_dir: '/app/share/imageviewer/models')

install_data([
  'controllers/__init__.py',
  'controllers/gallerycontroller.py',
  'controllers/viewercontroller.py',
], install_dir: '/app/share/imageviewer/controllers')
