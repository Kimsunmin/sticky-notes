#!/bin/sh
# 패키지(.deb, snap)에 넣을 파일을 DEST 아래에 /usr 구조로 모은다.
set -e
# 패키지 안의 파일 권한이 빌드하는 사람의 umask 에 따라 달라지지 않게 한다
umask 022
DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$1"
APP_ID=io.github.kimsunmin.StickyNotes

install -Dm755 "$DIR/sticky_notes.py" "$DEST/usr/share/sticky-notes/sticky_notes.py"
mkdir -p "$DEST/usr/bin"
ln -sf ../share/sticky-notes/sticky_notes.py "$DEST/usr/bin/sticky-notes"
mkdir -p "$DEST/usr/share/applications"
sed "s|@EXEC@|sticky-notes|" "$DIR/data/$APP_ID.desktop.in" > "$DEST/usr/share/applications/$APP_ID.desktop"
install -Dm644 "$DIR/data/$APP_ID.svg" "$DEST/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
install -Dm644 "$DIR/data/$APP_ID.metainfo.xml" "$DEST/usr/share/metainfo/$APP_ID.metainfo.xml"
install -Dm644 "$DIR/LICENSE" "$DEST/usr/share/doc/sticky-notes/copyright"
