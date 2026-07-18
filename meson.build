project('imageviewer',
          version: '0.2.1',
    meson_version: '>= 1.0.0',
    license: 'GPL-3.0-or-later',
  default_options: [ 'warning_level=2', 'werror=false', ],
)

gettext_package = 'io.github.masatn1973.ImageViewer'

i18n = import('i18n')
gnome = import('gnome')

install_data(
  'data/icons/hicolor/scalable/apps/io.github.masatn1973.ImageViewer.svg',
  install_dir: join_paths(get_option('datadir'),
                          'icons/hicolor/scalable/apps')
)

subdir('data')
subdir('src')
subdir('po')

gnome.post_install(
     glib_compile_schemas: true,
    gtk_update_icon_cache: true,
  update_desktop_database: true,
)
