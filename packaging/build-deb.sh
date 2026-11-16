#!/bin/sh
# dist/sticky-notes.deb 를 만든다. 릴리스에 이 이름 그대로 올리므로
# releases/latest/download/sticky-notes.deb 주소가 늘 최신 버전을 가리킨다.
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$("$DIR/packaging/version.sh")"
ROOT="$(mktemp -d)"
trap 'rm -rf "$ROOT"' EXIT
chmod 755 "$ROOT"

"$DIR/packaging/stage.sh" "$ROOT"
# PATH 에 먼저 잡히는 다른 파이썬(pyenv, venv 등)에는 PyGObject 가 없을 수 있다
sed -i '1s|.*|#!/usr/bin/python3|' "$ROOT/usr/share/sticky-notes/sticky_notes.py"

mkdir -p "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/control" <<CONTROL
Package: sticky-notes
Version: $VERSION
Architecture: all
Maintainer: 김선민 <sunmin0406@naver.com>
Depends: python3, python3-gi, gir1.2-gtk-3.0
Recommends: fonts-noto-cjk
Section: utils
Priority: optional
Homepage: https://github.com/Kimsunmin/sticky-notes
Description: Sticky notes that live on your desktop
 Desktop sticky notes for GNOME on Wayland. Notes stay on the wallpaper on
 every workspace, below other windows, and come to the front while in use.
 Terminal theme by default, plus paper themes and custom theme files.
CONTROL

mkdir -p "$DIR/dist"
# Debian 에서도 설치되도록 기본값(zstd)이 아닌 xz 로 묶는다
dpkg-deb --build --root-owner-group -Zxz "$ROOT" "$DIR/dist/sticky-notes.deb"
