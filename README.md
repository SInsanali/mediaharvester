# Media Harvester

Save videos and audio from YouTube, TikTok, Instagram, X, Vimeo and more than a thousand other sites. Paste a link, check it, and download it. No technical knowledge required.

## Quick start

### 1. Download this program

1. Click the green **Code** button at the top of this page.
2. Click **Download ZIP**.
3. Unzip it anywhere you like, such as your Desktop.

### 2. Start it

- **Mac**: Double-click `Media Harvester.command`. For a real app with an icon, see [Mac app](#mac-app) below.
- **Windows**: Double-click `Run Media Harvester (Windows).bat`

Media Harvester opens in your web browser. To quit, open **Settings** (the gear icon) and choose **Quit Media Harvester**, or close the terminal window.

The first time you start it, Media Harvester installs what it needs. This only happens once.

### 3. Save something

1. Copy a link to a video, from the address bar or the site's **Share** button.
2. Paste it into the box. Media Harvester checks the link and shows a preview.
3. Choose **Video** or **Audio (MP3)**, pick a quality if you like, and press **Download**.

Files are saved to **Downloads → Media Harvester**. When a download finishes, press **Open** to play it, **Show in Finder** (or **Show in folder**) to find it, or, on a Mac, **Share…** to send it with AirDrop, Messages, Mail, Google Drive and anything else in your share menu.

### Handy extras

- **Several links at once**: paste a whole list. Each link gets its own card, and **Download all** saves them together.
- **Groups**: click **+ New group** and give it a name. Links you paste next go into that group (change this with **Add new links to**), or move any link in or out with its **Group** menu. When you download, the group's files are saved in a folder with the group's name, inside your downloads folder.
- **Playlists**: paste a playlist link to download every video in it. They're saved in a folder named after the playlist, or in the group's folder if the playlist is in a group.
- **Drag and drop**: drag a link from another browser tab onto the page.
- **Change the save folder**: click **Saving to…** at the top of the page.

## Mac app

Turn Media Harvester into a normal Mac app with its own icon, so you can keep it in Applications or the Dock:

```bash
python3 macos/build_mac_app.py --install
```

That builds `Media Harvester.app` and copies it into Applications. Leave off `--install` to build it into the `dist/` folder instead. The app has no Dock icon or terminal window; it simply opens in your browser. Opening it again while it's running brings the page back, and it quits on its own a few minutes after you close the page. If it won't start, the details are in `~/Library/Logs/Media Harvester.log`.

## Troubleshooting

| Problem | What to do |
|---------|------------|
| "Python not found" | Install Python from https://www.python.org/downloads/ (on Windows, tick **Add Python to PATH**). |
| A yellow banner asks you to install FFmpeg | Click **Install FFmpeg**. It's needed for MP3s and the best video quality. |
| Links that used to work now fail | Open **Settings** (the gear icon) and click **Update engine**, then restart. |
| "Needs you to be signed in" or "private" | Some videos are private, age-restricted or members-only and can't be downloaded. |
| The page says it lost connection | The terminal window was closed. Start Media Harvester again. |

## Requirements

- Python 3.9 or later
- Everything else installs automatically: [yt-dlp](https://github.com/yt-dlp/yt-dlp) for downloading and FFmpeg for converting.

## Privacy

Media Harvester runs entirely on your computer. The page is served from your own machine (`127.0.0.1`) and can't be reached by anyone else.

## Supported sites

YouTube, Vimeo, X (Twitter), TikTok, Instagram, Facebook, Reddit, Twitch, SoundCloud, Dailymotion, and [many more](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md).
