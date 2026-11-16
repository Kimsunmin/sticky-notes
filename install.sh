#!/bin/sh
# 앱 목록에 스티커 메모를 등록한다. --autostart 를 붙이면 로그인할 때 자동 실행도 켠다.
# 업데이트(git pull)한 뒤 다시 실행하면 등록 정보를 새로 쓰고, 실행 중인 앱을 새 코드로 다시 띄운다.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ID=com.kimsunmin.StickyNotes
DESKTOP_FILE="$HOME/.local/share/applications/$APP_ID.desktop"
AUTOSTART_FILE="$HOME/.config/autostart/$APP_ID.desktop"

install -Dm644 "$DIR/data/$APP_ID.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"
mkdir -p "$(dirname "$DESKTOP_FILE")"
sed "s|@EXEC@|$DIR/sticky_notes.py|" "$DIR/data/$APP_ID.desktop.in" > "$DESKTOP_FILE"
echo "Installed: $DESKTOP_FILE"

# 자동 실행을 켜 두었으면 함께 새로 쓴다
if [ "$1" = "--autostart" ] || [ -f "$AUTOSTART_FILE" ]; then
    mkdir -p "$(dirname "$AUTOSTART_FILE")"
    cp "$DESKTOP_FILE" "$AUTOSTART_FILE"
    echo "Autostart: $AUTOSTART_FILE"
fi

running() {
    gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.NameHasOwner "$APP_ID" 2>/dev/null | grep -q true
}

# 이 셸이 아니라 로그인 세션의 환경으로 실행한다. 스냅으로 설치한 편집기의 터미널처럼
# 환경 변수가 바뀐 셸에서 바로 실행하면 앱이 뜨지 않는다
if command -v systemd-run >/dev/null 2>&1; then
    quit_app() { systemd-run --user --collect --quiet --wait "$DIR/sticky_notes.py" --quit; }
    start_app() { systemd-run --user --collect --quiet "$DIR/sticky_notes.py"; }
else
    quit_app() { "$DIR/sticky_notes.py" --quit; }
    start_app() { nohup "$DIR/sticky_notes.py" >/dev/null 2>&1 & }
fi

# 실행 중이면 저장하고 끈 뒤 새 코드로 다시 띄운다
if running; then
    quit_app
    i=0
    while running && [ $i -lt 50 ]; do
        sleep 0.1
        i=$((i + 1))
    done
    start_app
    echo "Restarted the running app"
fi
