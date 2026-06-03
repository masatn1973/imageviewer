# Image Viewer

Image Viewer is a lightweight application for browsing and viewing image files.
It is built with GTK4 and libadwaita and supports common image formats.
![Image 1](https://blog-imgs-201.fc2.com/p/l/a/plamokozo/image1.png)
![Image 2](https://blog-imgs-201.fc2.com/p/l/a/plamokozo/image2.png)

## Installation before building

```
sudo apt install flatpak flatpak-builder
flatpak install -y org.gnome.Sdk//50
flatpak install -y org.gnome.Platform//50
```

## Build

```
git clone https://github.com/masatn1973/ImageViewer.git
cd ImageViewer
flatpak-builder --repo=repo --force-clean builddir io.github.masatn1973.ImageViewer.json
flatpak build-bundle repo io.github.masatn1973.ImageViewer.flatpak io.github.masatn1973.ImageViewer
```

## Install

```
flatpak remote-add --user --no-gpg-verify imageviewer-repo repo
flatpak install -y io.github.masatn1973.ImageViewer
```
