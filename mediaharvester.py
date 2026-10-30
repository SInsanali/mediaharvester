#!/usr/bin/env python3
"""
Media Harvester
Double-click to run. Opens a page in your web browser where you can paste a
link, check it, and download the video or audio to your computer.
"""

import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

VERSION = "1.0.0"
APP_NAME = "Media Harvester"
DEFAULT_PORT = 8765
MAX_PARALLEL_DOWNLOADS = 2
MAX_PLAYLIST_ITEMS = 500
IDLE_QUIT_SECONDS = 10 * 60  # Mac app only: quit once no page has checked in for this long


def user_data_dir() -> Path:
    """Per-user folder for settings and app-installed FFmpeg. The app folder may be read-only."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA") or Path.home())
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_NAME


SCRIPT_DIR = Path(__file__).parent.resolve()
WEB_DIR = SCRIPT_DIR / "web"
SHARE_SCRIPT = SCRIPT_DIR / "macos" / "share.js"
DATA_DIR = user_data_dir()
BIN_DIR = DATA_DIR / "bin"
SETTINGS_FILE = DATA_DIR / "settings.json"
INSTANCE_FILE = DATA_DIR / "instance.json"

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def ensure_yt_dlp() -> bool:
    """Import yt-dlp, installing it on first run if needed."""
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        pass

    print("First run - installing yt-dlp (this only happens once)...")
    install_commands = [
        [sys.executable, "-m", "pip", "install", "--user", "--break-system-packages", "-q", "yt-dlp"],
        [sys.executable, "-m", "pip", "install", "--user", "-q", "yt-dlp"],
        [sys.executable, "-m", "pip", "install", "-q", "yt-dlp"],
    ]
    for cmd in install_commands:
        try:
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        # A --user install may land in a directory that wasn't on sys.path yet
        import importlib
        import site
        importlib.invalidate_caches()
        user_site = site.getusersitepackages()
        if user_site not in sys.path:
            sys.path.append(user_site)
        try:
            import yt_dlp  # noqa: F401
            print("  yt-dlp installed.")
            return True
        except ImportError:
            continue

    print("\nCould not install yt-dlp automatically. Install it manually:")
    if platform.system() == "Darwin":
        print("    brew install yt-dlp     (or)     pip3 install --user yt-dlp")
    elif platform.system() == "Windows":
        print("    pip install yt-dlp")
    else:
        print("    pip3 install --user yt-dlp")
    return False


def ffmpeg_path() -> Optional[str]:
    """Path to ffmpeg, preferring a copy in the local bin/ folder."""
    for name in ("ffmpeg", "ffmpeg.exe"):
        if (BIN_DIR / name).exists():
            return str(BIN_DIR / name)
    return shutil.which("ffmpeg")


def ffprobe_path() -> Optional[str]:
    for name in ("ffprobe", "ffprobe.exe"):
        if (BIN_DIR / name).exists():
            return str(BIN_DIR / name)
    return shutil.which("ffprobe")


def install_ffmpeg() -> tuple[bool, str]:
    """Install FFmpeg for the current platform. Returns (ok, message)."""
    system = platform.system()

    if system == "Darwin":
        if shutil.which("brew"):
            try:
                subprocess.check_call(["brew", "install", "ffmpeg"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True, "FFmpeg installed with Homebrew."
            except subprocess.CalledProcessError:
                pass  # Fall through to the static binary
        try:
            BIN_DIR.mkdir(parents=True, exist_ok=True)
            # evermeet.cx provides trusted macOS ffmpeg builds
            for name in ("ffmpeg", "ffprobe"):
                zip_path = BIN_DIR / f"{name}.zip"
                urllib.request.urlretrieve(f"https://evermeet.cx/ffmpeg/getrelease/{name}/zip", zip_path)
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(BIN_DIR)
                zip_path.unlink()
                (BIN_DIR / name).chmod(0o755)
            return True, "FFmpeg installed."
        except Exception as e:
            return False, f"Couldn't download FFmpeg ({e}). Install Homebrew, then run: brew install ffmpeg"

    if system == "Windows":
        try:
            BIN_DIR.mkdir(parents=True, exist_ok=True)
            # gyan.dev provides trusted Windows ffmpeg builds
            zip_path = BIN_DIR / "ffmpeg.zip"
            urllib.request.urlretrieve("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip", zip_path)
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.namelist():
                    if member.endswith("/bin/ffmpeg.exe") or member.endswith("/bin/ffprobe.exe"):
                        with zf.open(member) as src, open(BIN_DIR / Path(member).name, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            zip_path.unlink()
            return True, "FFmpeg installed."
        except Exception as e:
            return False, f"Couldn't download FFmpeg ({e}). Try running: winget install ffmpeg"

    return False, "Install FFmpeg with your package manager, e.g. sudo apt install ffmpeg"


def update_yt_dlp() -> tuple[bool, str]:
    """Upgrade yt-dlp in place. Sites change often, so this fixes most new failures."""
    for extra in (["--user", "--break-system-packages"], ["--user"], []):
        cmd = [sys.executable, "-m", "pip", "install", "-U", "-q", *extra, "yt-dlp"]
        try:
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, "yt-dlp updated. Restart Media Harvester to use the new version."
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return False, "Couldn't update yt-dlp. Try running: pip3 install -U yt-dlp"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def default_download_dir() -> Path:
    downloads = Path.home() / "Downloads"
    base = downloads if downloads.is_dir() else Path.home()
    return base / APP_NAME


class Settings:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.download_dir = default_download_dir()
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if data.get("download_dir"):
                self.download_dir = Path(data["download_dir"]).expanduser()
        except (OSError, ValueError):
            pass

    def set_download_dir(self, path: Path) -> None:
        with self.lock:
            self.download_dir = path
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                SETTINGS_FILE.write_text(json.dumps({"download_dir": str(path)}, indent=2), encoding="utf-8")
            except OSError:
                pass

    def to_dict(self) -> dict[str, Any]:
        return {"download_dir": str(self.download_dir), "download_dir_display": pretty_path(self.download_dir)}


def pretty_path(path: Path) -> str:
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Talking to yt-dlp
# ---------------------------------------------------------------------------

class QuietLogger:
    """Swallow yt-dlp's console output; errors reach the page as exceptions instead."""
    def debug(self, msg: str) -> None: pass
    def info(self, msg: str) -> None: pass
    def warning(self, msg: str) -> None: pass
    def error(self, msg: str) -> None: pass


BASE_YDL_OPTS: dict[str, Any] = {
    "logger": QuietLogger(),
    "quiet": True,
    "no_warnings": True,
    "noprogress": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "retries": 3,
}


def friendly_error(err: Exception) -> str:
    """Turn a yt-dlp error into something a person can act on."""
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(err))
    msg = re.sub(r"^ERROR:\s*", "", msg)
    low = msg.lower()
    if "unsupported url" in low:
        return "This site isn't supported, or the link doesn't point to a video."
    if "private" in low:
        return "This video is private."
    if "sign in to confirm your age" in low or "age-restricted" in low or "age restricted" in low:
        return "This video is age-restricted and needs a signed-in account."
    if "login" in low or "sign in" in low or "log in" in low or "cookies" in low:
        return "This site needs you to be signed in to get this video."
    if "not available in your country" in low or ("geo" in low and "restrict" in low):
        return "This video isn't available in your country."
    if "http error 404" in low:
        return "Couldn't find anything at this link. Check that it was copied correctly."
    if "unavailable" in low or "not available" in low or "has been removed" in low:
        return "This video is unavailable. It may have been deleted."
    if "ffmpeg" in low:
        return "FFmpeg is needed for this. Install it from the banner at the top of the page."
    if "urlopen error" in low or "getaddrinfo" in low or "timed out" in low or "connection" in low:
        return "Couldn't reach the site. Check your internet connection and try again."
    if "drm" in low:
        return "This video is DRM-protected and can't be downloaded."
    short = msg.strip().splitlines()[0] if msg.strip() else type(err).__name__
    return short[:240]


def quality_options(info: dict[str, Any]) -> list[int]:
    """Video heights a person can choose from, highest first."""
    heights = {f.get("height") for f in info.get("formats") or []
               if f.get("vcodec") not in (None, "none") and f.get("height")}
    if not heights and info.get("height"):
        heights = {info["height"]}
    if not heights:
        return []
    top = max(heights)
    steps = [h for h in (2160, 1440, 1080, 720, 480, 360) if h <= top]
    return sorted(set(steps) | {top}, reverse=True)[:6]


def inspect_url(url: str) -> dict[str, Any]:
    """Look up a link without downloading it."""
    import yt_dlp

    opts = {**BASE_YDL_OPTS, "skip_download": True, "extract_flat": "in_playlist",
            "playlistend": MAX_PLAYLIST_ITEMS}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        raise ValueError("No video found at this link.")

    if info.get("_type") == "playlist" or info.get("entries") is not None:
        entries = []
        for entry in info.get("entries") or []:
            if not entry:
                continue
            entry_url = entry.get("webpage_url") or entry.get("url")
            if not entry_url:
                continue
            thumbs = entry.get("thumbnails") or []
            entries.append({
                "url": entry_url,
                "title": entry.get("title") or entry_url,
                "duration": entry.get("duration"),
                "thumbnail": entry.get("thumbnail") or (thumbs[-1]["url"] if thumbs else None),
            })
        if not entries:
            raise ValueError("This playlist is empty or couldn't be read.")
        if len(entries) == 1:
            # Some sites wrap a single post in a playlist; treat it as one video.
            return inspect_url(entries[0]["url"])
        return {
            "kind": "playlist",
            "url": url,
            "title": info.get("title") or "Playlist",
            "uploader": info.get("uploader") or info.get("channel"),
            "site": info.get("extractor_key"),
            "thumbnail": entries[0]["thumbnail"],
            "entries": entries,
        }

    return {
        "kind": "video",
        "url": info.get("webpage_url") or url,
        "title": info.get("title") or "Untitled",
        "uploader": info.get("uploader") or info.get("channel") or info.get("uploader_id"),
        "site": info.get("extractor_key"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "heights": quality_options(info),
        "audio_only": not any(f.get("vcodec") not in (None, "none") for f in info.get("formats") or [])
                       and not info.get("height"),
    }


def video_format(height: Optional[int], have_ffmpeg: bool) -> str:
    """Prefer H.264 (avc1) so files play everywhere, including QuickTime."""
    if not have_ffmpeg:
        # Without FFmpeg we can't merge separate video+audio streams.
        cap = f"[height<={height}]" if height else ""
        return f"best{cap}[ext=mp4]/best{cap}/best"
    cap = f"[height<={height}]" if height else ""
    return (f"bestvideo{cap}[vcodec^=avc1]+bestaudio[ext=m4a]/"
            f"bestvideo{cap}[vcodec^=avc1]+bestaudio/"
            f"best{cap}[vcodec^=avc1]/"
            f"bestvideo{cap}+bestaudio/best{cap}/best")


def safe_folder_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .")
    return cleaned[:80] or "Playlist"


# ---------------------------------------------------------------------------
# Download jobs
# ---------------------------------------------------------------------------

class Cancelled(Exception):
    pass


class Job:
    def __init__(self, url: str, mode: str, height: Optional[int], title: str,
                 thumbnail: Optional[str], folder: Optional[str]) -> None:
        self.id = uuid.uuid4().hex[:12]
        self.url = url
        self.mode = mode  # "video" or "audio"
        self.height = height
        self.title = title
        self.thumbnail = thumbnail
        self.folder = folder
        self.status = "queued"  # queued, downloading, processing, done, error, cancelled
        self.stage = "Waiting to start"
        self.progress = 0.0
        self.speed: Optional[float] = None
        self.eta: Optional[int] = None
        self.size: Optional[int] = None
        self.filepath: Optional[str] = None
        self.error: Optional[str] = None
        self.created = time.time()
        self.cancel_requested = False
        self.partial_files: set[str] = set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "url": self.url, "mode": self.mode, "height": self.height,
            "title": self.title, "thumbnail": self.thumbnail, "folder": self.folder,
            "status": self.status, "stage": self.stage, "progress": round(self.progress, 4),
            "speed": self.speed, "eta": self.eta, "size": self.size,
            "filename": Path(self.filepath).name if self.filepath else None,
            "error": self.error, "created": self.created,
        }


class JobManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=MAX_PARALLEL_DOWNLOADS)

    def add(self, **kwargs: Any) -> Job:
        job = Job(**kwargs)
        with self.lock:
            self.jobs[job.id] = job
        self.pool.submit(self._run, job)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self.lock:
            return self.jobs.get(job_id)

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            return [j.to_dict() for j in sorted(self.jobs.values(), key=lambda j: j.created, reverse=True)]

    def cancel(self, job_id: str) -> None:
        job = self.get(job_id)
        if job and job.status in ("queued", "downloading", "processing"):
            job.cancel_requested = True
            if job.status == "queued":
                job.status, job.stage = "cancelled", "Cancelled"

    def retry(self, job_id: str) -> Optional[Job]:
        job = self.get(job_id)
        if not job or job.status not in ("error", "cancelled"):
            return None
        self.remove(job_id)
        return self.add(url=job.url, mode=job.mode, height=job.height, title=job.title,
                        thumbnail=job.thumbnail, folder=job.folder)

    def remove(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job and job.status in ("done", "error", "cancelled"):
                del self.jobs[job_id]

    def busy(self) -> bool:
        with self.lock:
            return any(j.status in ("queued", "downloading", "processing") for j in self.jobs.values())

    def cancel_all(self) -> None:
        with self.lock:
            ids = list(self.jobs)
        for job_id in ids:
            self.cancel(job_id)
        self.pool.shutdown(wait=False, cancel_futures=True)

    def clear_finished(self) -> None:
        with self.lock:
            for job_id in [j.id for j in self.jobs.values() if j.status in ("done", "error", "cancelled")]:
                del self.jobs[job_id]

    # -- worker ---------------------------------------------------------

    def _run(self, job: Job) -> None:
        if job.cancel_requested:
            return
        try:
            self._download(job)
        except Exception as e:
            if isinstance(e, Cancelled) or job.cancel_requested:
                job.status, job.stage = "cancelled", "Cancelled"
                job.speed = job.eta = None
                self._remove_partials(job)
            else:
                job.status, job.stage, job.error = "error", "Failed", friendly_error(e)

    @staticmethod
    def _remove_partials(job: Job) -> None:
        for name in job.partial_files:
            for path in (Path(name), Path(name + ".ytdl")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _download(self, job: Job) -> None:
        import yt_dlp

        out_dir = self.settings.download_dir
        if job.folder:
            out_dir = out_dir / safe_folder_name(job.folder)
        out_dir.mkdir(parents=True, exist_ok=True)

        ffmpeg = ffmpeg_path()
        job.status, job.stage = "downloading", "Starting"

        def on_progress(d: dict[str, Any]) -> None:
            if job.cancel_requested:
                raise Cancelled()
            if d["status"] == "downloading":
                if d.get("tmpfilename"):
                    job.partial_files.add(d["tmpfilename"])
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes") or 0
                fmt = d.get("info_dict") or {}
                is_audio_stream = fmt.get("vcodec") == "none"
                if job.mode == "audio":
                    job.stage = "Downloading audio"
                else:
                    job.stage = "Downloading audio track" if is_audio_stream else "Downloading video"
                job.progress = (done / total) if total else job.progress
                job.speed = d.get("speed")
                job.eta = d.get("eta")
                job.size = total
            elif d["status"] == "finished":
                job.progress = 1.0

        def on_postprocess(d: dict[str, Any]) -> None:
            if job.cancel_requested:
                raise Cancelled()
            if d["status"] == "started":
                job.status = "processing"
                job.speed = job.eta = None
                name = d.get("postprocessor", "")
                job.stage = {"Merger": "Joining video and audio",
                             "ExtractAudio": "Converting to MP3"}.get(name, "Finishing up")

        opts: dict[str, Any] = {
            **BASE_YDL_OPTS,
            "outtmpl": str(out_dir / "%(title).150B [%(id)s].%(ext)s"),
            "windowsfilenames": True,
            "progress_hooks": [on_progress],
            "postprocessor_hooks": [on_postprocess],
        }
        if ffmpeg:
            opts["ffmpeg_location"] = str(Path(ffmpeg).parent)

        if job.mode == "audio":
            if not ffmpeg:
                raise RuntimeError("FFmpeg is needed to make MP3 files.")
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3",
                                       "preferredquality": "192"}]
        else:
            opts["format"] = video_format(job.height, bool(ffmpeg))
            opts["merge_output_format"] = "mp4"

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(job.url, download=True)

        downloads = (info or {}).get("requested_downloads") or []
        filepath = downloads[0].get("filepath") if downloads else None
        if not filepath or not Path(filepath).exists():
            raise RuntimeError("The download finished but the file couldn't be found.")

        if job.mode == "video" and ffmpeg:
            filepath = self._ensure_playable(job, filepath, ffmpeg)

        job.filepath = filepath
        job.size = Path(filepath).stat().st_size
        job.progress = 1.0
        job.status, job.stage = "done", "Saved"
        job.speed = job.eta = None

    def _ensure_playable(self, job: Job, filepath: str, ffmpeg: str) -> str:
        """Re-encode to H.264 only when the video uses a codec QuickTime can't play (e.g. VP9 from Instagram)."""
        ffprobe = ffprobe_path()
        if not ffprobe:
            return filepath
        try:
            codec = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                 "-of", "default=nw=1:nk=1", filepath],
                capture_output=True, text=True, timeout=60,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return filepath
        if not codec or codec in ("h264", "hevc"):
            return filepath

        job.status, job.stage, job.progress = "processing", "Converting so it plays everywhere", 0.0
        src = Path(filepath)
        tmp = src.with_name(src.stem + ".converting.mp4")
        final = src.with_suffix(".mp4")
        duration = self._probe_duration(ffprobe, filepath)
        proc = subprocess.Popen(
            [ffmpeg, "-y", "-v", "error", "-progress", "pipe:1", "-i", filepath,
             "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-movflags", "+faststart", str(tmp)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            if job.cancel_requested:
                proc.kill()
                proc.wait()
                tmp.unlink(missing_ok=True)
                raise Cancelled()
            if line.startswith("out_time_us=") and duration:
                try:
                    job.progress = min(int(line.split("=", 1)[1]) / 1_000_000 / duration, 1.0)
                except ValueError:
                    pass
        if proc.wait() != 0 or not tmp.exists():
            tmp.unlink(missing_ok=True)
            return filepath  # Keep the original rather than failing the whole download
        src.unlink(missing_ok=True)
        tmp.replace(final)
        return str(final)

    @staticmethod
    def _probe_duration(ffprobe: str, filepath: str) -> Optional[float]:
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", filepath],
                capture_output=True, text=True, timeout=60,
            ).stdout.strip()
            return float(out)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None


# ---------------------------------------------------------------------------
# Opening files and folders
# ---------------------------------------------------------------------------

def open_path(path: Path) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", str(path)])
    elif system == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


def reveal_path(path: Path) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", "-R", str(path)])
    elif system == "Windows":
        subprocess.Popen(["explorer", f"/select,{path}"])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


def can_share() -> bool:
    return platform.system() == "Darwin" and SHARE_SCRIPT.exists()


def share_path(path: Path) -> None:
    """Show the macOS share menu (AirDrop, Messages, Mail, Drive…) next to the pointer."""
    subprocess.Popen(["osascript", "-l", "JavaScript", str(SHARE_SCRIPT), str(path)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def choose_folder(start: Path) -> Optional[Path]:
    """Show the system folder picker. Returns None if cancelled or unavailable."""
    system = platform.system()
    try:
        if system == "Darwin":
            script = ('POSIX path of (choose folder with prompt "Choose where to save downloads" '
                      f'default location (POSIX file "{start if start.exists() else Path.home()}"))')
            result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=600)
        elif system == "Windows":
            script = ("Add-Type -AssemblyName System.Windows.Forms;"
                      "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
                      "$d.Description = 'Choose where to save downloads';"
                      "$d.ShowNewFolderButton = $true;"
                      "$f = New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
                      "if ($d.ShowDialog($f) -eq 'OK') { $d.SelectedPath }")
            result = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", script],
                                    capture_output=True, text=True, timeout=600)
        elif shutil.which("zenity"):
            result = subprocess.run(["zenity", "--file-selection", "--directory",
                                     "--title=Choose where to save downloads"],
                                    capture_output=True, text=True, timeout=600)
        else:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    chosen = result.stdout.strip()
    return Path(chosen) if result.returncode == 0 and chosen else None


# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------

class App:
    def __init__(self, port: int) -> None:
        self.port = port
        self.token = secrets.token_urlsafe(24)
        self.settings = Settings()
        self.jobs = JobManager(self.settings)
        self.task_lock = threading.Lock()
        self.task: dict[str, Any] = {"name": None, "running": False, "ok": None, "message": None}
        self.server: Optional[ThreadingHTTPServer] = None
        self.last_seen = time.time()

    def quit(self) -> None:
        self.jobs.cancel_all()
        if self.server:
            # shutdown() blocks until serve_forever returns, so it can't run on a request thread
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def watch_idle(self) -> None:
        """Mac app mode has no terminal window to close, so quit once every page is gone."""
        while True:
            time.sleep(30)
            idle = time.time() - self.last_seen > IDLE_QUIT_SECONDS
            if idle and not self.jobs.busy() and not self.task["running"]:
                print("  No open pages for a while. Quitting.")
                self.quit()
                return

    def run_task(self, name: str, fn: Any) -> bool:
        """Run a one-off maintenance task (FFmpeg install, yt-dlp update) in the background."""
        with self.task_lock:
            if self.task["running"]:
                return False
            self.task = {"name": name, "running": True, "ok": None, "message": None}

        def worker() -> None:
            ok, message = fn()
            self.task = {"name": name, "running": False, "ok": ok, "message": message}

        threading.Thread(target=worker, daemon=True).start()
        return True

    def state(self) -> dict[str, Any]:
        import yt_dlp
        self.last_seen = time.time()
        return {
            "version": VERSION,
            "platform": platform.system(),
            "can_share": can_share(),
            "yt_dlp_version": yt_dlp.version.__version__,
            "ffmpeg": bool(ffmpeg_path()),
            "settings": self.settings.to_dict(),
            "jobs": self.jobs.list(),
            "task": self.task,
        }


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    allowed_hosts = {f"127.0.0.1:{app.port}", f"localhost:{app.port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "MediaHarvester"

        def log_message(self, format: str, *args: Any) -> None:
            pass  # Keep the terminal quiet

        # -- helpers -----------------------------------------------------

        def send_json(self, data: Any, status: int = 200) -> None:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def fail(self, message: str, status: int = 400) -> None:
            self.send_json({"error": message}, status)

        def host_ok(self) -> bool:
            # Blocks DNS-rebinding: only answer requests addressed to this machine
            return self.headers.get("Host", "") in allowed_hosts

        def read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_000_000:
                raise ValueError("Request too large")
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw or b"{}")
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            return data

        # -- GET ---------------------------------------------------------

        def do_GET(self) -> None:
            if not self.host_ok():
                return self.fail("Forbidden", 403)
            path = urlparse(self.path).path

            if path == "/api/ping":
                return self.send_json({"app": APP_NAME, "version": VERSION})

            if path == "/api/state":
                return self.send_json(app.state())

            if path in ("/", "/index.html"):
                html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
                body = html.replace("{{TOKEN}}", app.token).replace("{{VERSION}}", VERSION).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", STATIC_TYPES[".html"])
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            if path.startswith("/static/"):
                target = (WEB_DIR / path[len("/static/"):]).resolve()
                if WEB_DIR not in target.parents or not target.is_file():
                    return self.fail("Not found", 404)
                body = target.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", STATIC_TYPES.get(target.suffix, "application/octet-stream"))
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
                return

            self.fail("Not found", 404)

        # -- POST --------------------------------------------------------

        def do_POST(self) -> None:
            if not self.host_ok() or not secrets.compare_digest(self.headers.get("X-Token", ""), app.token):
                return self.fail("Forbidden", 403)
            path = urlparse(self.path).path
            try:
                data = self.read_json()
            except (ValueError, json.JSONDecodeError):
                return self.fail("Invalid request")

            route = ROUTES.get(path)
            if not route:
                return self.fail("Not found", 404)
            try:
                route(self, data)
            except Exception as e:  # Never let one bad request kill the server
                self.fail(friendly_error(e), 500)

        def api_inspect(self, data: dict[str, Any]) -> None:
            url = str(data.get("url", "")).strip()
            if not re.match(r"^https?://\S+\.\S+", url, re.IGNORECASE):
                return self.fail("That doesn't look like a web link. Links start with https://")
            try:
                self.send_json(inspect_url(url))
            except Exception as e:
                self.fail(friendly_error(e), 422)

        def api_download(self, data: dict[str, Any]) -> None:
            items = data.get("items") or []
            if not isinstance(items, list) or not items:
                return self.fail("Nothing to download")
            created = []
            for item in items[:MAX_PLAYLIST_ITEMS]:
                url = str(item.get("url", "")).strip()
                if not url.lower().startswith(("http://", "https://")):
                    continue
                mode = "audio" if item.get("mode") == "audio" else "video"
                height = item.get("height")
                height = int(height) if isinstance(height, (int, float)) and height > 0 else None
                folder = item.get("folder")
                job = app.jobs.add(url=url, mode=mode, height=height,
                                   title=str(item.get("title") or url)[:300],
                                   thumbnail=item.get("thumbnail"),
                                   folder=str(folder) if folder else None)
                created.append(job.id)
            self.send_json({"ids": created})

        def api_cancel(self, data: dict[str, Any]) -> None:
            app.jobs.cancel(str(data.get("id")))
            self.send_json({"ok": True})

        def api_retry(self, data: dict[str, Any]) -> None:
            job = app.jobs.retry(str(data.get("id")))
            self.send_json({"ok": bool(job)})

        def api_remove(self, data: dict[str, Any]) -> None:
            app.jobs.remove(str(data.get("id")))
            self.send_json({"ok": True})

        def api_clear(self, data: dict[str, Any]) -> None:
            app.jobs.clear_finished()
            self.send_json({"ok": True})

        def api_open(self, data: dict[str, Any]) -> None:
            # Only files this app downloaded can be opened
            job = app.jobs.get(str(data.get("id")))
            if not job or not job.filepath or not Path(job.filepath).exists():
                return self.fail("That file has been moved or deleted.", 404)
            target = Path(job.filepath)
            if data.get("share"):
                if not can_share():
                    return self.fail("Sharing isn't available on this computer.")
                share_path(target)
            elif data.get("reveal"):
                reveal_path(target)
            else:
                open_path(target)
            self.send_json({"ok": True})

        def api_open_folder(self, data: dict[str, Any]) -> None:
            folder = app.settings.download_dir
            folder.mkdir(parents=True, exist_ok=True)
            open_path(folder)
            self.send_json({"ok": True})

        def api_choose_folder(self, data: dict[str, Any]) -> None:
            chosen = choose_folder(app.settings.download_dir)
            if chosen:
                app.settings.set_download_dir(chosen)
            self.send_json({"changed": bool(chosen), "settings": app.settings.to_dict()})

        def api_settings(self, data: dict[str, Any]) -> None:
            raw = str(data.get("download_dir", "")).strip()
            if raw:
                path = Path(raw).expanduser()
                if not path.is_absolute():
                    return self.fail("Use a full folder path, like ~/Downloads/Media Harvester")
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except OSError:
                    return self.fail("Couldn't create that folder. Check the path and try again.")
                app.settings.set_download_dir(path)
            elif data.get("reset"):
                app.settings.set_download_dir(default_download_dir())
            self.send_json({"settings": app.settings.to_dict()})

        def api_install_ffmpeg(self, data: dict[str, Any]) -> None:
            self.send_json({"started": app.run_task("ffmpeg", install_ffmpeg)})

        def api_update_ytdlp(self, data: dict[str, Any]) -> None:
            self.send_json({"started": app.run_task("yt-dlp", update_yt_dlp)})

        def api_quit(self, data: dict[str, Any]) -> None:
            self.send_json({"ok": True})
            app.quit()

    ROUTES = {
        "/api/inspect": Handler.api_inspect,
        "/api/download": Handler.api_download,
        "/api/cancel": Handler.api_cancel,
        "/api/retry": Handler.api_retry,
        "/api/remove": Handler.api_remove,
        "/api/clear": Handler.api_clear,
        "/api/open": Handler.api_open,
        "/api/open-folder": Handler.api_open_folder,
        "/api/choose-folder": Handler.api_choose_folder,
        "/api/settings": Handler.api_settings,
        "/api/install-ffmpeg": Handler.api_install_ffmpeg,
        "/api/update-ytdlp": Handler.api_update_ytdlp,
        "/api/quit": Handler.api_quit,
    }
    return Handler


def find_port() -> int:
    for port in range(DEFAULT_PORT, DEFAULT_PORT + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # Match the server's reuse flag so a just-closed previous run doesn't bump the port
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def running_instance() -> Optional[str]:
    """URL of a Media Harvester that's already running, so a second launch just reopens it."""
    try:
        port = int(json.loads(INSTANCE_FILE.read_text(encoding="utf-8"))["port"])
        url = f"http://127.0.0.1:{port}/"
        with urllib.request.urlopen(url + "api/ping", timeout=1.5) as res:
            if json.loads(res.read()).get("app") == APP_NAME:
                return url
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def write_instance(port: int) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        INSTANCE_FILE.write_text(json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8")
    except OSError:
        pass


def clear_instance() -> None:
    try:
        if json.loads(INSTANCE_FILE.read_text(encoding="utf-8")).get("pid") == os.getpid():
            INSTANCE_FILE.unlink()
    except (OSError, ValueError):
        pass


def signal_ready() -> None:
    """Tell the Mac app launcher (if any) that startup finished, so it can exit."""
    if "--ready-file" in sys.argv:
        try:
            Path(sys.argv[sys.argv.index("--ready-file") + 1]).touch()
        except (IndexError, OSError):
            pass


def main() -> None:
    app_mode = "--app" in sys.argv  # Started by Media Harvester.app: no terminal window
    open_browser = "--no-browser" not in sys.argv

    if platform.system() == "Darwin":
        # Apps opened from Finder get a bare PATH; add Homebrew so FFmpeg is found
        extra = [d for d in ("/opt/homebrew/bin", "/usr/local/bin") if d not in os.environ.get("PATH", "")]
        os.environ["PATH"] = os.pathsep.join([*extra, os.environ.get("PATH", "")])

    existing = running_instance()
    if existing:
        print(f"\n  {APP_NAME} is already running at {existing}")
        if open_browser:
            webbrowser.open(existing)
        signal_ready()
        return

    if not ensure_yt_dlp():
        sys.exit(1)

    port = find_port()
    app = App(port)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    server.daemon_threads = True
    app.server = server
    write_instance(port)
    url = f"http://127.0.0.1:{port}/"

    print(f"\n  {APP_NAME} {VERSION} is running at {url}")
    print(f"  Downloads are saved to {pretty_path(app.settings.download_dir)}")
    if not ffmpeg_path():
        print("  FFmpeg isn't installed yet. You can install it from the page.")
    if not app_mode:
        print("\n  Keep this window open while you use the app. To quit, use Quit in the page's")
        print("  settings, close this window, or press Ctrl+C.\n")

    if app_mode:
        threading.Thread(target=app.watch_idle, daemon=True).start()
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    signal_ready()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        clear_instance()
        print("\n  Media Harvester has quit. Goodbye!")


if __name__ == "__main__":
    main()
