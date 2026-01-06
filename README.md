# Docker Torrent WebUI
fork from https://github.com/seaside111/docker-torrent-webui/fork for a quick english language version, using deepl to translate.

This is a lightweight PT torrent seed creation tool based on Docker. It integrates mktorrent, MediaInfo, and FFmpeg, offering a modern web interface that enables one-click generation of torrent files, media information (MediaInfo), and video thumbnail previews.

## ✨ Key Features

* **Visual Operations**: Enter paths and trackers via the web interface—no command line required.
* **Automatic Torrent Generation**: Powered by `mktorrent`, supporting configurable chunk sizes and PT private tags.
* **MediaInfo Integration**: Automatically scans the largest video file in the directory to generate detailed parameter reports.
* **Video Thumbnails**: Utilises `FFmpeg` for rapid generation of 4x4 video preview collages.
* **Task Queue**: Asynchronous background processing supports large file operations without interface lag.
* **Automatic Archiving**: All generated files are automatically organised into the `/torrent` folder within the source directory.
* **Security Protection**: Built-in login verification interface.

## 🛠️ Installation Guide (Docker)

### Method One: Using Docker CLI



Translated with DeepL.com (free version)

1. **Clone code**
   ```bash
   git clone [https://github.com/Marvnonya/docker-torrent-webui.git](https://github.com/Marvnonya/docker-torrent-webui.git)
   cd docker-torrent-webui
