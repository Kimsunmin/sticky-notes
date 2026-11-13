#!/bin/sh
# 앱 목록에 스티커 메모를 등록한다. --autostart 를 붙이면 로그인할 때 자동 실행도 켠다.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ID=com.kimsunmin.StickyNotes
DESKTOP_FILE="$HOME/.local/share/applications/$APP_ID.desktop"

install -Dm644 "$DIR/data/$APP_ID.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"
mkdir -p "$(dirname "$DESKTOP_FILE")"
sed "s|@EXEC@|$DIR/sticky_notes.py|" "$DIR/data/$APP_ID.desktop.in" > "$DESKTOP_FILE"
echo "설치 완료: $DESKTOP_FILE"

if [ "$1" = "--autostart" ]; then
    mkdir -p "$HOME/.config/autostart"
    cp "$DESKTOP_FILE" "$HOME/.config/autostart/"
    echo "자동 실행 켬: $HOME/.config/autostart/$APP_ID.desktop"
fi
