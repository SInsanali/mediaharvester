#!/usr/bin/env python3
"""
Media Harvester
Double-click to run. Downloads media from urls.txt.
"""

import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

# ANSI color codes
class Colors:
    PURPLE = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

LOGO = f"""
{Colors.RED}███╗   ███╗███████╗██████╗ ██╗ █████╗
████╗ ████║██╔════╝██╔══██╗██║██╔══██╗
██╔████╔██║█████╗  ██║  ██║██║███████║
██║╚██╔╝██║██╔══╝  ██║  ██║██║██╔══██║
██║ ╚═╝ ██║███████╗██████╔╝██║██║  ██║
╚═╝     ╚═╝╚══════╝╚═════╝ ╚═╝╚═╝  ╚═╝
{Colors.YELLOW}██╗  ██╗ █████╗ ██████╗ ██╗   ██╗███████╗███████╗████████╗███████╗██████╗
██║  ██║██╔══██╗██╔══██╗██║   ██║██╔════╝██╔════╝╚══██╔══╝██╔════╝██╔══██╗
███████║███████║██████╔╝██║   ██║█████╗  ███████╗   ██║   █████╗  ██████╔╝
██╔══██║██╔══██║██╔══██╗╚██╗ ██╔╝██╔══╝  ╚════██║   ██║   ██╔══╝  ██╔══██╗
██║  ██║██║  ██║██║  ██║ ╚████╔╝ ███████╗███████║   ██║   ███████╗██║  ██║
╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚══════╝╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝{Colors.RESET}
"""

# URL patterns that yt-dlp can handle
URL_PATTERN = re.compile(
    r'^https?://'  # http:// or https://
    r'(?:www\.)?'  # optional www.
    r'(?:'
    r'youtube\.com/(?:watch\?v=|shorts/|playlist\?list=|embed/|v/)'
    r'|youtu\.be/'
    r'|vimeo\.com/'
    r'|dailymotion\.com/'
    r'|twitter\.com/.*/status/'
    r'|x\.com/.*/status/'
    r'|tiktok\.com/'
    r'|instagram\.com/'
    r'|facebook\.com/'
    r'|twitch\.tv/'
    r'|soundcloud\.com/'
    r'|reddit\.com/'
    r'|[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'  # Generic domain fallback
    r')',
    re.IGNORECASE
)


def install_dependencies() -> bool:
    """Install required packages if missing."""
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        print("First run - installing dependencies...")

        # Try different install methods (order matters)
        install_commands = [
            # Try pipx first (cleanest for macOS)
            (["pipx", "install", "yt-dlp"], "pipx"),
            # Try pip with --user and --break-system-packages (for PEP 668 systems)
            ([sys.executable, "-m", "pip", "install", "--user", "--break-system-packages", "-q", "yt-dlp"], "pip"),
            # Try without --break-system-packages (older systems)
            ([sys.executable, "-m", "pip", "install", "--user", "-q", "yt-dlp"], "pip"),
            # Try pip3 directly
            (["pip3", "install", "--user", "--break-system-packages", "-q", "yt-dlp"], "pip3"),
            (["pip3", "install", "--user", "-q", "yt-dlp"], "pip3"),
        ]

        for cmd, method in install_commands:
            try:
                subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"Done! (via {method})\n")
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue

        # All methods failed - show helpful error
        print(f"{Colors.RED}Error: Failed to auto-install yt-dlp.{Colors.RESET}")
        print(f"\n{Colors.YELLOW}Please install manually using one of these methods:{Colors.RESET}")
        if platform.system() == "Darwin":
            print("\n  Option 1 (recommended for Mac):")
            print("    brew install yt-dlp")
            print("\n  Option 2:")
            print("    pipx install yt-dlp")
            print("\n  Option 3:")
            print("    pip3 install --user --break-system-packages yt-dlp")
        elif platform.system() == "Windows":
            print("    pip install yt-dlp")
        else:
            print("    pip3 install --user yt-dlp")
        return False


def get_script_dir() -> Path:
    """Return the directory containing this script."""
    return Path(__file__).parent.resolve()


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available in PATH or local bin directory."""
    script_dir = get_script_dir()
    local_ffmpeg = script_dir / "bin" / "ffmpeg"

    # Check local bin first
    if local_ffmpeg.exists():
        return True

    # Check system PATH
    return shutil.which("ffmpeg") is not None


def get_ffmpeg_path() -> Optional[str]:
    """Get the path to ffmpeg executable."""
    script_dir = get_script_dir()
    local_ffmpeg = script_dir / "bin" / "ffmpeg"

    if local_ffmpeg.exists():
        return str(local_ffmpeg)

    return shutil.which("ffmpeg")


def install_ffmpeg() -> bool:
    """Install ffmpeg based on the current platform."""
    system = platform.system()
    script_dir = get_script_dir()
    bin_dir = script_dir / "bin"

    print("\nInstalling FFmpeg...")

    if system == "Darwin":  # macOS
        # Check for Homebrew first
        if shutil.which("brew"):
            print("Found Homebrew. Installing ffmpeg via brew...")
            try:
                subprocess.check_call(["brew", "install", "ffmpeg"])
                print("FFmpeg installed successfully!")
                return True
            except subprocess.CalledProcessError:
                print("Homebrew install failed, trying static binary...")

        # Download static binary
        print("Downloading FFmpeg static binary...")
        try:
            bin_dir.mkdir(parents=True, exist_ok=True)

            # evermeet.cx provides trusted macOS ffmpeg builds
            ffmpeg_url = "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip"
            ffprobe_url = "https://evermeet.cx/ffmpeg/getrelease/ffprobe/zip"

            for name, url in [("ffmpeg", ffmpeg_url), ("ffprobe", ffprobe_url)]:
                zip_path = bin_dir / f"{name}.zip"
                print(f"  Downloading {name}...")
                urllib.request.urlretrieve(url, zip_path)

                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(bin_dir)

                zip_path.unlink()

                # Make executable
                binary = bin_dir / name
                binary.chmod(0o755)

            print(f"FFmpeg installed to: {bin_dir}")
            return True
        except Exception as e:
            print(f"Failed to download FFmpeg: {e}")
            print("\nManual installation options:")
            print("  - Install Homebrew: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
            print("  - Then run: brew install ffmpeg")
            return False

    elif system == "Windows":
        print("Downloading FFmpeg for Windows...")
        try:
            bin_dir.mkdir(parents=True, exist_ok=True)

            # gyan.dev provides trusted Windows ffmpeg builds
            # Using essentials build (smaller) from GitHub releases
            ffmpeg_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            zip_path = bin_dir / "ffmpeg.zip"

            print("  Downloading (this may take a moment)...")
            urllib.request.urlretrieve(ffmpeg_url, zip_path)

            print("  Extracting...")
            with zipfile.ZipFile(zip_path, 'r') as zf:
                # Find the bin folder in the archive
                for member in zf.namelist():
                    if member.endswith('/bin/ffmpeg.exe') or member.endswith('/bin/ffprobe.exe'):
                        # Extract to bin_dir with just the filename
                        filename = Path(member).name
                        with zf.open(member) as source, open(bin_dir / filename, 'wb') as target:
                            target.write(source.read())

            zip_path.unlink()
            print(f"FFmpeg installed to: {bin_dir}")
            return True
        except Exception as e:
            print(f"Failed to download FFmpeg: {e}")
            print("\nManual installation:")
            print("  - Download from: https://www.gyan.dev/ffmpeg/builds/")
            print("  - Or use: winget install ffmpeg")
            return False

    else:  # Linux
        print("Please install FFmpeg using your package manager:")
        print("  - Ubuntu/Debian: sudo apt install ffmpeg")
        print("  - Fedora: sudo dnf install ffmpeg")
        print("  - Arch: sudo pacman -S ffmpeg")
        return False


def uninstall_dependencies() -> None:
    """Uninstall yt-dlp and optionally ffmpeg."""
    print("\nUninstall Options:")
    print("  1. Uninstall yt-dlp only")
    print("  2. Uninstall local FFmpeg only")
    print("  3. Uninstall both")
    print("  4. Cancel")
    print()

    choice = input("Enter choice (1-4): ").strip()

    if choice == "4" or choice not in ("1", "2", "3"):
        print("Cancelled.")
        return

    if choice in ("1", "3"):
        confirm = input("Uninstall yt-dlp? (y/n): ").strip().lower()
        if confirm == 'y':
            print("Uninstalling yt-dlp...")
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "uninstall", "-y", "yt-dlp"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                print("yt-dlp uninstalled.")
            except subprocess.CalledProcessError:
                print("Failed to uninstall yt-dlp.")

    if choice in ("2", "3"):
        script_dir = get_script_dir()
        bin_dir = script_dir / "bin"

        if bin_dir.exists():
            confirm = input(f"Remove local FFmpeg from {bin_dir}? (y/n): ").strip().lower()
            if confirm == 'y':
                try:
                    shutil.rmtree(bin_dir)
                    print("Local FFmpeg removed.")
                except Exception as e:
                    print(f"Failed to remove: {e}")
        else:
            print("No local FFmpeg installation found.")
            system = platform.system()
            if system == "Darwin" and shutil.which("brew"):
                print("To uninstall system FFmpeg: brew uninstall ffmpeg")
            elif system == "Windows":
                print("To uninstall system FFmpeg: winget uninstall ffmpeg")

    wait_for_enter()


def create_urls_file(file_path: Path) -> None:
    """Create a template urls.txt file."""
    template = """\\\\ Add URLs below, one per line
\\\\ Use # FolderName to organize into folders
\\\\ Example:
\\\\ # Music
\\\\ https://www.youtube.com/watch?v=VIDEO_ID
"""
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(template)


def is_valid_url_format(url: str) -> bool:
    """Check if a string looks like a valid URL format."""
    if not url or not url.strip():
        return False
    return bool(URL_PATTERN.match(url.strip()))


def load_urls(file_path: Path) -> Optional[dict[str, list[str]]]:
    """Load URLs from a text file, organized by folder headers.

    Returns dict: {folder_name: [urls]} where empty string key means root folder.
    Returns None if file doesn't exist or contains no valid URLs.
    """
    if not file_path.exists():
        return None

    folders: dict[str, list[str]] = {}
    current_folder = ""  # Empty string = root downloads folder
    skipped_lines: list[tuple[int, str]] = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            # Skip comment lines (start with \\)
            if line.startswith('\\\\'):
                continue

            # Check if this is a folder header (# followed by text)
            if line.startswith('# '):
                folder_name = line[2:].strip()
                if folder_name:
                    current_folder = folder_name
                continue

            # Validate URL format before adding
            if not is_valid_url_format(line):
                skipped_lines.append((line_num, line))
                continue

            if current_folder not in folders:
                folders[current_folder] = []
            folders[current_folder].append(line)

    # Report skipped lines
    if skipped_lines:
        print(f"\nSkipped {len(skipped_lines)} invalid line(s):")
        for line_num, line in skipped_lines[:5]:  # Show first 5
            display = line[:50] + "..." if len(line) > 50 else line
            print(f"  Line {line_num}: {display}")
        if len(skipped_lines) > 5:
            print(f"  ... and {len(skipped_lines) - 5} more")

    return folders if folders else None


def validate_urls(url_dict: dict[str, list[str]]) -> tuple[dict, dict]:
    """Validate all URLs and return valid/invalid dicts by folder."""
    import yt_dlp

    valid: dict[str, list[str]] = {}
    invalid: dict[str, list[str]] = {}
    total = sum(len(urls) for urls in url_dict.values())

    print(f"\n{Colors.BOLD}Validating {total} URL(s)...{Colors.RESET}\n")

    count = 0
    for folder, urls in url_dict.items():
        folder_display = folder if folder else "(root)"

        for url in urls:
            count += 1
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'skip_download': True,
                'nocheckcertificate': True,
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', 'Unknown Title')
                    print(f"{Colors.DIM}[{count}/{total}]{Colors.RESET} {Colors.CYAN}[{folder_display}]{Colors.RESET} {Colors.GREEN}{title}{Colors.RESET}")
                    if folder not in valid:
                        valid[folder] = []
                    valid[folder].append(url)
            except Exception:
                print(f"{Colors.DIM}[{count}/{total}]{Colors.RESET} {Colors.CYAN}[{folder_display}]{Colors.RESET} {Colors.RED}Invalid URL{Colors.RESET}")
                if folder not in invalid:
                    invalid[folder] = []
                invalid[folder].append(url)

    return valid, invalid


def progress_hook(d: dict) -> None:
    """Display download progress."""
    if d['status'] == 'downloading':
        percent = d.get('_percent_str', '???%').strip()
        speed = d.get('_speed_str', '???').strip()
        print(f"\r        {Colors.YELLOW}{percent}{Colors.RESET} at {Colors.CYAN}{speed}{Colors.RESET}  ", end='', flush=True)
    elif d['status'] == 'finished':
        print(f"\r        {Colors.GREEN}Done!{Colors.RESET}                    ")


def download_videos(url_dict: dict[str, list[str]], output_dir: Path) -> tuple[int, int]:
    """Download videos from URLs, organized by folder."""
    import yt_dlp

    output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    fail_count = 0
    total = sum(len(urls) for urls in url_dict.values())

    print(f"\n{Colors.BOLD}Downloading {total} video(s)...{Colors.RESET}\n")

    count = 0
    for folder, urls in url_dict.items():
        folder_dir = output_dir / folder if folder else output_dir
        folder_display = folder if folder else "(root)"
        folder_dir.mkdir(parents=True, exist_ok=True)

        for url in urls:
            count += 1

            # Get video title
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'nocheckcertificate': True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', 'Unknown')
            except Exception:
                title = "Unknown"

            print(f"{Colors.DIM}[{count}/{total}]{Colors.RESET} {Colors.CYAN}[{folder_display}]{Colors.RESET} {title}")

            ydl_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': str(folder_dir / f'{count} - %(title).80s [%(id)s].%(ext)s'),
                'windowsfilenames': True,
                'restrictfilenames': True,
                'quiet': True,
                'no_warnings': True,
                'noprogress': True,
                'noplaylist': True,
                'nocheckcertificate': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
                'progress_hooks': [progress_hook],
                'ignoreerrors': False,
                'retries': 3,
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    success_count += 1
            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e)
                print(f"        {Colors.RED}Download failed:{Colors.RESET}")
                # Show helpful context based on error type
                if "ffmpeg" in error_msg.lower() or "merge" in error_msg.lower():
                    print(f"        {Colors.YELLOW}FFmpeg is required to merge video+audio.{Colors.RESET}")
                    print(f"        {Colors.YELLOW}Install it via menu option 4.{Colors.RESET}")
                elif "private" in error_msg.lower():
                    print(f"        {Colors.YELLOW}This video is private.{Colors.RESET}")
                elif "age" in error_msg.lower() or "sign in" in error_msg.lower():
                    print(f"        {Colors.YELLOW}This video requires age verification/login.{Colors.RESET}")
                elif "available" in error_msg.lower():
                    print(f"        {Colors.YELLOW}Video unavailable (deleted or region-locked).{Colors.RESET}")
                else:
                    print(f"        {Colors.DIM}{error_msg[:200]}{Colors.RESET}")
                fail_count += 1
            except Exception as e:
                print(f"        {Colors.RED}Error: {type(e).__name__}: {e}{Colors.RESET}")
                fail_count += 1

    print()
    return success_count, fail_count


def download_audio(url_dict: dict[str, list[str]], output_dir: Path) -> tuple[int, int]:
    """Download audio as MP3 from URLs, organized by folder."""
    import yt_dlp

    output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    fail_count = 0
    total = sum(len(urls) for urls in url_dict.values())

    print(f"\n{Colors.BOLD}Downloading {total} audio file(s)...{Colors.RESET}\n")

    # Get ffmpeg path for yt-dlp
    ffmpeg_path = get_ffmpeg_path()
    ffmpeg_location = str(Path(ffmpeg_path).parent) if ffmpeg_path else None

    count = 0
    for folder, urls in url_dict.items():
        folder_dir = output_dir / folder if folder else output_dir
        folder_display = folder if folder else "(root)"
        folder_dir.mkdir(parents=True, exist_ok=True)

        for url in urls:
            count += 1

            # Get video title
            try:
                with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'nocheckcertificate': True}) as ydl:
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', 'Unknown')
            except Exception:
                title = "Unknown"

            print(f"{Colors.DIM}[{count}/{total}]{Colors.RESET} {Colors.CYAN}[{folder_display}]{Colors.RESET} {title}")

            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(folder_dir / f'{count} - %(title).80s [%(id)s].%(ext)s'),
                'windowsfilenames': True,
                'restrictfilenames': True,
                'quiet': True,
                'no_warnings': True,
                'noprogress': True,
                'noplaylist': True,
                'nocheckcertificate': True,
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
                'progress_hooks': [progress_hook],
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'ignoreerrors': False,
                'retries': 3,
            }

            if ffmpeg_location:
                ydl_opts['ffmpeg_location'] = ffmpeg_location

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    success_count += 1
            except yt_dlp.utils.DownloadError as e:
                error_msg = str(e)
                print(f"        {Colors.RED}Download failed:{Colors.RESET}")
                if "ffmpeg" in error_msg.lower():
                    print(f"        {Colors.YELLOW}FFmpeg is required for MP3 conversion.{Colors.RESET}")
                    print(f"        {Colors.YELLOW}Install it via menu option 4.{Colors.RESET}")
                elif "private" in error_msg.lower():
                    print(f"        {Colors.YELLOW}This video is private.{Colors.RESET}")
                elif "age" in error_msg.lower() or "sign in" in error_msg.lower():
                    print(f"        {Colors.YELLOW}This video requires age verification/login.{Colors.RESET}")
                elif "available" in error_msg.lower():
                    print(f"        {Colors.YELLOW}Video unavailable (deleted or region-locked).{Colors.RESET}")
                else:
                    print(f"        {Colors.DIM}{error_msg[:200]}{Colors.RESET}")
                fail_count += 1
            except Exception as e:
                print(f"        {Colors.RED}Error: {type(e).__name__}: {e}{Colors.RESET}")
                fail_count += 1

    print()
    return success_count, fail_count


def clear_screen() -> None:
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def wait_for_enter() -> None:
    """Wait for user to press Enter."""
    input(f"\n{Colors.DIM}Press Enter to continue...{Colors.RESET}")


def get_menu_choice(ffmpeg_available: bool, url_count: int, folder_count: int) -> str:
    """Get validated menu choice from user."""
    while True:
        clear_screen()
        print(LOGO)
        if folder_count:
            print(f"{Colors.DIM}Found {Colors.YELLOW}{url_count}{Colors.RESET}{Colors.DIM} URL(s) in {Colors.YELLOW}{folder_count}{Colors.RESET}{Colors.DIM} folder(s){Colors.RESET}\n")
        else:
            print(f"{Colors.DIM}Found {Colors.YELLOW}{url_count}{Colors.RESET}{Colors.DIM} URL(s) in urls.txt{Colors.RESET}\n")

        ffmpeg_color = Colors.GREEN if ffmpeg_available else Colors.RED
        ffmpeg_status = "installed" if ffmpeg_available else "not installed"

        print(f"{Colors.BOLD}What would you like to do?{Colors.RESET}")
        print(f"  {Colors.CYAN}1.{Colors.RESET} Validate URLs")
        print(f"  {Colors.CYAN}2.{Colors.RESET} Download all videos")
        print(f"  {Colors.CYAN}3.{Colors.RESET} Download as MP3 {Colors.DIM}[FFmpeg: {ffmpeg_color}{ffmpeg_status}{Colors.RESET}{Colors.DIM}]{Colors.RESET}")
        print(f"  {Colors.CYAN}4.{Colors.RESET} Install/check FFmpeg {Colors.DIM}[{ffmpeg_color}{ffmpeg_status}{Colors.RESET}{Colors.DIM}]{Colors.RESET}")
        print(f"  {Colors.CYAN}5.{Colors.RESET} Uninstall dependencies")
        print(f"  {Colors.CYAN}6.{Colors.RESET} Exit")
        print()

        choice = input(f"{Colors.YELLOW}Enter choice (1-6): {Colors.RESET}").strip()

        if choice in ('1', '2', '3', '4', '5', '6'):
            return choice

        print(f"{Colors.RED}Invalid choice. Please enter 1-6.{Colors.RESET}\n")


def handle_validate(url_dict: dict[str, list[str]]) -> None:
    """Handle the validate URLs menu option."""
    valid, invalid = validate_urls(url_dict)
    valid_count = sum(len(urls) for urls in valid.values())
    invalid_count = sum(len(urls) for urls in invalid.values())

    print(f"\n{Colors.PURPLE}{'=' * 40}{Colors.RESET}")
    print(f"{Colors.GREEN}Valid:   {valid_count}{Colors.RESET}")
    print(f"{Colors.RED}Invalid: {invalid_count}{Colors.RESET}")
    wait_for_enter()


def handle_download(url_dict: dict[str, list[str]], output_dir: Path) -> None:
    """Handle the download all videos menu option."""
    success, failed = download_videos(url_dict, output_dir)

    print(f"{Colors.PURPLE}{'=' * 40}{Colors.RESET}")
    print(f"{Colors.GREEN}Downloaded: {success}{Colors.RESET}")
    print(f"{Colors.RED}Failed:     {failed}{Colors.RESET}")
    print(f"{Colors.CYAN}Saved to:   {output_dir}{Colors.RESET}")
    wait_for_enter()


def handle_download_audio(url_dict: dict[str, list[str]], output_dir: Path) -> bool:
    """Handle the download as MP3 menu option. Returns True if ffmpeg check passed."""
    if not check_ffmpeg():
        print(f"\n{Colors.RED}FFmpeg is required for MP3 conversion.{Colors.RESET}")
        print(f"{Colors.YELLOW}Please use option 4 to install FFmpeg first.{Colors.RESET}")
        wait_for_enter()
        return False

    success, failed = download_audio(url_dict, output_dir)

    print(f"{Colors.PURPLE}{'=' * 40}{Colors.RESET}")
    print(f"{Colors.GREEN}Downloaded: {success}{Colors.RESET}")
    print(f"{Colors.RED}Failed:     {failed}{Colors.RESET}")
    print(f"{Colors.CYAN}Saved to:   {output_dir}{Colors.RESET}")
    wait_for_enter()
    return True


def handle_ffmpeg() -> bool:
    """Handle the FFmpeg install/check menu option. Returns new ffmpeg status."""
    if check_ffmpeg():
        ffmpeg_path = get_ffmpeg_path()
        print(f"\n{Colors.GREEN}FFmpeg is already installed:{Colors.RESET} {Colors.CYAN}{ffmpeg_path}{Colors.RESET}")

        # Get version
        try:
            result = subprocess.run(
                [ffmpeg_path, "-version"],
                capture_output=True,
                text=True
            )
            version_line = result.stdout.split('\n')[0] if result.stdout else "Unknown version"
            print(f"{Colors.DIM}Version: {version_line}{Colors.RESET}")
        except Exception:
            pass

        wait_for_enter()
        return True
    else:
        success = install_ffmpeg()
        wait_for_enter()
        return success


def main() -> None:
    """Main entry point."""
    clear_screen()

    if not install_dependencies():
        return

    script_dir = get_script_dir()
    url_file = script_dir / "urls.txt"
    video_dir = script_dir / "video"
    audio_dir = script_dir / "audio"

    # Check ffmpeg status
    ffmpeg_available = check_ffmpeg()

    if not url_file.exists():
        create_urls_file(url_file)
        print("Created urls.txt")
        print("Add YouTube URLs to it, then run again.")
        return

    url_dict = load_urls(url_file)
    if not url_dict:
        print("No valid URLs in urls.txt - add some and run again.")
        return

    total_urls = sum(len(urls) for urls in url_dict.values())
    folder_count = len([f for f in url_dict.keys() if f])

    while True:
        choice = get_menu_choice(ffmpeg_available, total_urls, folder_count)

        if choice == "1":
            handle_validate(url_dict)
        elif choice == "2":
            handle_download(url_dict, video_dir)
        elif choice == "3":
            handle_download_audio(url_dict, audio_dir)
        elif choice == "4":
            ffmpeg_available = handle_ffmpeg()
        elif choice == "5":
            uninstall_dependencies()
            # Re-check ffmpeg status after potential uninstall
            ffmpeg_available = check_ffmpeg()
        elif choice == "6":
            print(f"{Colors.PURPLE}Goodbye!{Colors.RESET}")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Goodbye!")
        sys.exit(0)
    except BrokenPipeError:
        # Handle broken pipe (e.g., piping to head)
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)
