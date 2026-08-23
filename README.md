# Image Viewer

ImageViewer is a folder-oriented thumbnail browser for quickly browsing image collections.
It is built with GTK4 and libadwaita and supports common image formats.
![Image 1](https://github.com/user-attachments/assets/ca99fb13-cd7b-4d13-aec3-c09f3dfbdfbf)
![Image 2](https://github.com/user-attachments/assets/6ef008ce-2875-4b27-9ce9-b64ad94f273b)

## Installation before building

```
sudo apt install flatpak flatpak-builder
flatpak install -y org.gnome.Sdk//50
flatpak install -y org.gnome.Platform//50
```

## Build

```
git clone https://github.com/masatn2026/ImageViewer.git
cd ImageViewer
flatpak-builder --repo=repo --force-clean builddir io.github.masatn2026.ImageViewer.json
flatpak build-bundle repo io.github.masatn2026.ImageViewer.flatpak io.github.masatn1973.ImageViewer
```

## Install

```
flatpak remote-add --user --no-gpg-verify imageviewer-repo repo
flatpak install -y io.github.masatn2026.ImageViewer
```
