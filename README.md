# Media Harvester

Download videos from YouTube, TikTok, Twitter, and more. No technical knowledge required.

## Quick Start

### 1. Download This Program

1. Click the green **Code** button at the top of this page
2. Click **Download ZIP**
3. Unzip the downloaded file to your Desktop (or anywhere you like)

### 2. Run the Program

- **Mac**: Double-click `Media Harvester.command`
- **Windows**: Double-click `Run Media Harvester (Windows).bat`

The first time you run it, the program will create a file called `urls.txt`.

### 3. Add Your Videos

1. Open `urls.txt` in any text editor (Notepad, TextEdit, etc.)
2. Paste video URLs, one per line
3. Save the file

**Organizing into Folders**

You can organize downloads into folders by adding headers:

```
\\ This is a comment
# Music Videos
https://www.youtube.com/watch?v=abc123
https://www.youtube.com/watch?v=def456

# Tutorials
https://www.youtube.com/watch?v=xyz789
```

- `# FolderName` - creates a folder for URLs below it
- `\\` - comment line (ignored)

Videos will be saved into matching folders:

```
video/
  Music Videos/
    Song Title.mp4
  Tutorials/
    Tutorial Title.mp4
```

### 4. Download

Run the program again and choose option **2** to download videos or option **3** for MP3 audio.

Your files will be saved in the `video/` or `audio/` folder.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python not found" | Install Python from https://www.python.org/downloads/ |
| Videos won't download | Try option **1** first to check if the URLs are valid |
| Download fails | Make sure you have a stable internet connection |
| Some videos skip/fail | Some videos may be age-restricted, region-locked, or require FFmpeg. Install FFmpeg via option **4** |
| Low video quality | Install FFmpeg (option **4**) to enable best quality video+audio merging |

## Requirements

- Python 3.8 or later (usually pre-installed on Mac/Linux)
- Everything else installs automatically
- **FFmpeg** (optional but recommended): Enables MP3 conversion and best video quality. Install via menu option **4**

## Supported Sites

- YouTube
- Vimeo
- Twitter/X
- TikTok
- Instagram
- Reddit
- And many more (powered by yt-dlp)
