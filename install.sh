#!/bin/sh
# 앱 목록에 스티커 메모를 등록한다. --autostart 를 붙이면 로그인할 때 자동 실행도 켠다.
# 업데이트(git pull)한 뒤 다시 실행하면 등록 정보를 새로 쓰고, 실행 중인 앱을 새 코드로 다시 띄운다.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ID=io.github.kimsunmin.StickyNotes
OLD_ID=com.kimsunmin.StickyNotes
DESKTOP_FILE="$HOME/.local/share/applications/$APP_ID.desktop"
AUTOSTART_FILE="$HOME/.config/autostart/$APP_ID.desktop"

# 예전 앱 ID 로 설치한 파일을 지운다. 자동 실행을 켜 두었으면 새 ID 로 옮긴다
rm -f "$HOME/.local/share/applications/$OLD_ID.desktop" "$HOME/.local/share/icons/hicolor/scalable/apps/$OLD_ID.svg"
if [ -f "$HOME/.config/autostart/$OLD_ID.desktop" ]; then
    rm "$HOME/.config/autostart/$OLD_ID.desktop"
    OLD_AUTOSTART=1
fi

install -Dm644 "$DIR/data/$APP_ID.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/$APP_ID.svg"
mkdir -p "$(dirname "$DESKTOP_FILE")"
sed "s|@EXEC@|$DIR/sticky_notes.py|" "$DIR/data/$APP_ID.desktop.in" > "$DESKTOP_FILE"
echo "Installed: $DESKTOP_FILE"

# 자동 실행을 켜 두었으면 함께 새로 쓴다
if [ "$1" = "--autostart" ] || [ -f "$AUTOSTART_FILE" ] || [ -n "$OLD_AUTOSTART" ]; then
    mkdir -p "$(dirname "$AUTOSTART_FILE")"
    cp "$DESKTOP_FILE" "$AUTOSTART_FILE"
    echo "Autostart: $AUTOSTART_FILE"
fi

bus() {
    gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method "org.freedesktop.DBus.$1" "$2" 2>/dev/null
}

running() {
    bus NameHasOwner "$1" | grep -q true
}

wait_until_quit() {
    i=0
    while running "$1" && [ $i -lt 50 ]; do
        sleep 0.1
        i=$((i + 1))
    done
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
if running "$APP_ID"; then
    quit_app
    wait_until_quit "$APP_ID"
    RESTART=1
fi
# 예전 ID 로 실행 중인 앱은 새 ID 로 보내는 --quit 을 받지 못하므로 프로세스를 끝낸다.
# 메모는 바뀐 뒤 0.5초 안에 저장되므로 잃지 않는다
if running "$OLD_ID"; then
    kill "$(bus GetConnectionUnixProcessID "$OLD_ID" | sed -n 's/.*uint32 \([0-9]*\).*/\1/p')"
    wait_until_quit "$OLD_ID"
    RESTART=1
fi
if [ -n "$RESTART" ]; then
    start_app
    echo "Restarted the running app"
fi
