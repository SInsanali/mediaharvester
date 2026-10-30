#!/usr/bin/env python3
"""
Build "Media Harvester.app" into dist/.

The app is self-contained: it carries mediaharvester.py and web/ inside its bundle, so it
can be dragged to /Applications. Settings and FFmpeg live in ~/Library/Application Support.

    python3 macos/build_mac_app.py            # build dist/Media Harvester.app
    python3 macos/build_mac_app.py --install  # also copy it to /Applications
"""

import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

MAC_DIR = Path(__file__).parent.resolve()
ROOT = MAC_DIR.parent
DIST = ROOT / "dist"
APP = DIST / "Media Harvester.app"
EXECUTABLE = "Media Harvester"


def app_version() -> str:
    match = re.search(r'^VERSION = "([^"]+)"', (ROOT / "mediaharvester.py").read_text(encoding="utf-8"), re.M)
    return match.group(1) if match else "0.0.0"


def build() -> Path:
    if APP.exists():
        shutil.rmtree(APP)
    contents = APP / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    bundled = resources / "app"
    macos.mkdir(parents=True)
    bundled.mkdir(parents=True)

    launcher = macos / EXECUTABLE
    shutil.copy2(MAC_DIR / "launcher.sh", launcher)
    launcher.chmod(0o755)

    shutil.copy2(MAC_DIR / "AppIcon.icns", resources / "AppIcon.icns")
    shutil.copy2(ROOT / "mediaharvester.py", bundled / "mediaharvester.py")
    shutil.copytree(ROOT / "web", bundled / "web")
    (bundled / "macos").mkdir()
    shutil.copy2(MAC_DIR / "share.js", bundled / "macos" / "share.js")

    version = app_version()
    info = {
        "CFBundleName": "Media Harvester",
        "CFBundleDisplayName": "Media Harvester",
        "CFBundleIdentifier": "io.github.sinsanali.mediaharvester",
        "CFBundleExecutable": EXECUTABLE,
        "CFBundleIconFile": "AppIcon",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "10.15",
        # No Dock icon: the app lives in the browser, and the launcher exits once it's up
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSAppleEventsUsageDescription": "Media Harvester shows alerts and the share menu.",
    }
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(info, f)
    (contents / "PkgInfo").write_text("APPL????", encoding="ascii")

    # Ad-hoc signature keeps macOS from calling a locally built app "damaged"
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(APP)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Nudge Finder to pick up the new icon
    subprocess.run(["touch", str(APP)])
    return APP


def install(app: Path) -> Path:
    target = Path("/Applications") / app.name
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(app, target, symlinks=True)
    return target


def main() -> None:
    app = build()
    print(f"Built {app}")
    if "--install" in sys.argv:
        print(f"Installed {install(app)}")
    else:
        print("Drag it to your Applications folder, or run again with --install.")


if __name__ == "__main__":
    main()
