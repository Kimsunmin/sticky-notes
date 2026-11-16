#!/usr/bin/env python3
"""바탕화면에 붙여 두는 스티커 메모. 기본 테마는 터미널이다."""

import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

# GNOME Wayland 에서는 앱이 자기 창 위치나 '다른 창 아래에 두기' 같은 상태를 정할 수 없다.
# XWayland 로 띄우면 X11 창 힌트가 통해서 바탕화면 위젯처럼 둘 수 있다. Gtk 를 불러오기 전에 정해야 한다.
os.environ["GDK_BACKEND"] = "x11"

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import GLib  # noqa: E402

APP_ID = "com.kimsunmin.StickyNotes"
# X11 WM_CLASS 가 데스크톱 파일 이름과 같아야 셸이 이 앱의 창으로 알아본다
GLib.set_prgname(APP_ID)

from gi.repository import Gdk, Gio, Gtk, Pango  # noqa: E402

DATA_FILE = Path(GLib.get_user_data_dir()) / "sticky-notes" / "notes.json"
# 사용자 테마 폴더. 파일 하나(이름.theme)가 테마 하나다
THEMES_DIR = Path(GLib.get_user_config_dir()) / "sticky-notes" / "themes"

# 이름: (글자색, 배경색, CRT 효과(스캔라인과 글자 번짐))
THEMES = {
    "green": ("#3df07c", "#06130b", True),
    "amber": ("#ffb547", "#150e02", True),
    "cyan": ("#56d8ff", "#03121b", True),
    "magenta": ("#ff6ad5", "#16071a", True),
    "red": ("#ff6b5e", "#190706", True),
    "white": ("#e2e2e2", "#121212", True),
    # 종이 포스트잇
    "yellow": ("#3b3314", "#fff4a3", False),
    "pink": ("#4a1f32", "#ffd1e3", False),
    "sky": ("#16324a", "#cfe8ff", False),
    "mint": ("#1d3d1f", "#d3f5d0", False),
    "lilac": ("#2f2450", "#e4d9ff", False),
}
DEFAULT_THEME = "green"
# 테마 이름은 CSS 클래스에 들어가므로 이 글자만 쓴다
THEME_NAME = re.compile(r"[A-Za-z0-9_-]+")
# 화면 문구는 영어가 기본이고, 시스템 언어가 한국어·중국어(간체)면 바꿔 보여 준다
TRANSLATIONS = {
    "ko": {
        "New note (Ctrl+N)": "새 메모 (Ctrl+N)",
        "Theme (Ctrl+T: next theme)": "테마 (Ctrl+T: 다음 테마)",
        "Keep above other windows (Ctrl+P)": "다른 창 위에 고정 (Ctrl+P)",
        "Delete note (Ctrl+W)": "메모 삭제 (Ctrl+W)",
        "Resize": "크기 조절",
        "Open themes folder": "테마 폴더 열기",
        "rm: remove '{}'? [y/N]": "'{}' 삭제할까요? [y/N]",
    },
    "zh_CN": {
        "New note (Ctrl+N)": "新建便签 (Ctrl+N)",
        "Theme (Ctrl+T: next theme)": "主题 (Ctrl+T：下一个主题)",
        "Keep above other windows (Ctrl+P)": "固定在其他窗口上方 (Ctrl+P)",
        "Delete note (Ctrl+W)": "删除便签 (Ctrl+W)",
        "Resize": "调整大小",
        "Open themes folder": "打开主题文件夹",
        "rm: remove '{}'? [y/N]": "删除 '{}'？[y/N]",
    },
}
TRANSLATIONS["zh_SG"] = TRANSLATIONS["zh_CN"]
# 한자 모양이 언어마다 달라서 CJK 글꼴도 언어에 맞춘다
CJK_FONTS = {"zh_CN": "SC", "zh_SG": "SC", "zh_TW": "TC", "zh_HK": "HK", "ja": "JP", "ko": "KR"}


def _pick(table, default):
    # ko_KR.UTF-8, ko_KR, ko, C 처럼 구체적인 이름부터 나온다
    return next((table[name] for name in GLib.get_language_names() if name in table), default)


_STRINGS = _pick(TRANSLATIONS, {})


def tr(text):
    return _STRINGS.get(text, text)


FONT = f'"Ubuntu Sans Mono", "Noto Sans Mono CJK {_pick(CJK_FONTS, "KR")}", monospace'
DEFAULT_FONT_SIZE = 12  # pt
MIN_FONT_SIZE, MAX_FONT_SIZE = 8, 32

# (글자, 툴팁, 액션)
TITLE_BUTTONS = (
    ("[+]", tr("New note (Ctrl+N)"), "app.new-note"),
    ("[~]", tr("Theme (Ctrl+T: next theme)"), "win.theme-menu"),
    ("[^]", tr("Keep above other windows (Ctrl+P)"), "win.toggle-pin"),
    ("[x]", tr("Delete note (Ctrl+W)"), "win.delete"),
)
ACCELS = {
    "app.new-note": ["<Control>n"],
    "win.cycle-theme": ["<Control>t"],
    "win.toggle-pin": ["<Control>p"],
    "win.delete": ["<Control>w"],
    "win.undo": ["<Control>z"],
    "win.redo": ["<Control><Shift>z", "<Control>y"],
    "win.zoom-in": ["<Control>equal", "<Control>plus", "<Control>KP_Add"],
    "win.zoom-out": ["<Control>minus", "<Control>KP_Subtract"],
    "win.zoom-reset": ["<Control>0", "<Control>KP_0"],
}

# "[ ] 할 일", "- [x] 끝난 일" 같은 체크박스 줄
TASK = re.compile(r"^(\s*(?:[-*]\s+)?)\[([ xX])\]")
TITLE_PREFIX = re.compile(r"^\s*(?:#+|[-*>$])?\s*(?:\[[ xX]\]\s*)?")

CSS = f"""
window.note {{ background-color: transparent; }}
window.note label, window.note textview {{ font-family: {FONT}; }}
window.note undershoot, window.note overshoot {{ background: none; box-shadow: none; }}
.note-frame {{ border-radius: 6px; border: 1px solid transparent; }}
.note-titlebar {{ min-height: 26px; border-radius: 5px 5px 0 0; }}
.note-titlebar label {{ font-size: 10pt; }}
.note-titlebar button {{ min-width: 0; min-height: 0; padding: 0 3px; margin: 0; border: none; border-radius: 0;
                        background: none; box-shadow: none; text-shadow: none; outline: none; }}
.note-body {{ border-radius: 0 0 5px 5px; }}
.note-body textview, .note-body textview text {{ background-color: transparent; }}
.note-body textview {{ -GtkWidget-cursor-aspect-ratio: 0.1; }}
.statusline {{ padding: 0 2px 3px 6px; }}
.statusline label {{ font-size: 9pt; }}
.statusline .mode {{ padding: 0 6px; font-weight: bold; }}
.statusline .grip {{ background: none; padding: 0 4px; }}
"""


def _theme_css(name, fg, bg, crt):
    scope = f"window.note.theme-{name}"
    css = f"""
{scope} .note-frame {{ border-color: alpha({fg}, 0.35); }}
{scope}:backdrop .note-frame {{ border-color: alpha({fg}, 0.2); }}
{scope} .note-titlebar {{ background-color: alpha(mix({bg}, {fg}, 0.14), 0.95); color: alpha({fg}, 0.8); }}
{scope} .note-body {{ background-color: alpha({bg}, 0.97); }}
{scope} textview text {{ color: {fg}; caret-color: {fg}; }}
{scope} textview text selection {{ background-color: alpha({fg}, 0.85); color: {bg}; }}
{scope} scrollbar slider {{ background-color: alpha({fg}, 0.4); border: none; }}
{scope} .note-titlebar button {{ color: alpha({fg}, 0.7); }}
{scope} .note-titlebar button:hover, {scope} .note-titlebar button.active {{ background-color: {fg}; color: {bg}; }}
{scope} .note-titlebar button:hover label, {scope} .note-titlebar button.active label {{ text-shadow: none; }}
{scope} .statusline {{ color: alpha({fg}, 0.55); }}
{scope} .statusline .mode {{ background-color: alpha({fg}, 0.85); color: {bg}; text-shadow: none; }}
{scope} .statusline .mode.warn {{ background-color: #ff5f56; color: {bg}; }}
"""
    if crt:
        # 옛 CRT 모니터처럼 가로줄을 긋고 글자를 살짝 번지게 한다. 배경화면이 살짝 비치게 조금 더 투명하다
        css += f"""
{scope} .note-body {{ background-color: alpha({bg}, 0.9);
    background-image: repeating-linear-gradient(to bottom, alpha({fg}, 0.035), alpha({fg}, 0.035) 1px,
                                                         transparent 1px, transparent 3px); }}
{scope} label {{ text-shadow: 0 0 5px alpha({fg}, 0.45); }}
"""
    return css


def note_filename(first_line):
    """첫 줄로 터미널 파일 이름처럼 보이는 제목을 만든다."""
    slug = re.sub(r"[\s/]+", "-", TITLE_PREFIX.sub("", first_line).strip().lower()).strip("-.")
    return f"{slug[:24] or 'untitled'}.txt"


def line_tag(line):
    """줄 하나에 입힐 강조 태그 이름. 강조는 줄 단위라 바뀐 줄만 다시 칠하면 된다."""
    if line.lstrip().startswith("#"):
        return "heading"
    task = TASK.match(line)
    if task and task.group(2) in "xX":
        return "done"
    return None


class History:
    """TextBuffer 편집 기록. 사용자 동작 하나(글자 하나 입력, 붙여넣기 한 번 등)씩 되돌린다.

    버퍼 전체를 복사하지 않고 바뀐 부분(종류, 위치, 글자)만 저장하므로 메모가 길어도 가볍다.
    """

    LIMIT = 3000

    def __init__(self, buffer):
        self.buffer = buffer
        self._undo = []  # 각 단계는 [("insert" | "delete", 위치, 글자), ...]
        self._redo = []
        self._action = []  # 사용자 동작 하나(키 입력, 붙여넣기 등) 동안 모은 변경
        self._depth = 0
        self._applying = False
        # 버퍼가 바뀌기 전에 불려야 지워질 글자를 읽을 수 있으므로 connect_after 가 아니다
        buffer.connect("insert-text", self._on_insert)
        buffer.connect("delete-range", self._on_delete)
        buffer.connect("begin-user-action", self._on_begin)
        buffer.connect("end-user-action", self._on_end)

    def undo(self):
        if not self._undo:
            return False
        changes = self._undo.pop()
        self._apply(changes, reverse=True)
        self._redo.append(changes)
        return True

    def redo(self):
        if not self._redo:
            return False
        changes = self._redo.pop()
        self._apply(changes, reverse=False)
        self._undo.append(changes)
        return True

    def _apply(self, changes, reverse):
        self._applying = True
        self.buffer.begin_user_action()
        for kind, offset, text in reversed(changes) if reverse else changes:
            # 되돌릴 때는 넣은 글자를 지우고 지운 글자를 다시 넣는다
            if (kind == "insert") == reverse:
                start = self.buffer.get_iter_at_offset(offset)
                self.buffer.delete(start, self.buffer.get_iter_at_offset(offset + len(text)))
                cursor = offset
            else:
                self.buffer.insert(self.buffer.get_iter_at_offset(offset), text)
                cursor = offset + len(text)
        self.buffer.end_user_action()
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(cursor))
        self._applying = False

    def _on_insert(self, _buffer, location, text, _length):
        self._record(("insert", location.get_offset(), text))

    def _on_delete(self, buffer, start, end):
        self._record(("delete", start.get_offset(), buffer.get_text(start, end, True)))

    def _on_begin(self, _buffer):
        self._depth += 1

    def _on_end(self, _buffer):
        self._depth -= 1
        if self._depth == 0 and self._action:
            self._push(self._action)
            self._action = []

    def _record(self, change):
        if self._applying:
            return
        if self._depth:
            self._action.append(change)
        else:
            self._push([change])

    def _push(self, changes):
        self._redo.clear()
        self._undo.append(changes)
        if len(self._undo) > self.LIMIT:
            del self._undo[0]


def load_notes():
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return data["notes"]
    except FileNotFoundError:
        return []
    except (OSError, ValueError, KeyError, TypeError):
        # 읽을 수 없는 파일을 빈 목록으로 덮어쓰지 않도록 옆으로 치워 둔다
        backup = DATA_FILE.with_name(f"notes.broken-{int(time.time())}.json")
        DATA_FILE.rename(backup)
        print(f"Could not read the notes file; moved it to {backup}", file=sys.stderr)
        return []


def save_notes(notes):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"notes": notes}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, DATA_FILE)


def read_theme(path):
    """[Theme] 그룹에 Foreground, Background, Crt(생략하면 false)를 적은 테마 파일을 읽는다."""
    if not THEME_NAME.fullmatch(path.stem):
        raise ValueError("file name may only contain letters, digits, '-' and '_'")
    keyfile = GLib.KeyFile()
    keyfile.load_from_file(str(path), GLib.KeyFileFlags.NONE)
    colors = []
    for key in ("Foreground", "Background"):
        value = keyfile.get_string("Theme", key).strip()
        rgba = Gdk.RGBA()
        if not rgba.parse(value):
            raise ValueError(f"unknown {key} color: {value}")
        # CSS 와 Pango 마크업에 그대로 넣으므로 #rrggbb 로 맞춰 둔다
        colors.append("#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in (rgba.red, rgba.green, rgba.blue))))
    crt = "Crt" in keyfile.get_keys("Theme")[0] and keyfile.get_boolean("Theme", "Crt")
    return (*colors, crt)


def load_themes():
    """기본 테마에 사용자 테마를 더한다. 이름이 같으면 사용자 테마로 바꾼다."""
    themes = dict(THEMES)
    for path in sorted(THEMES_DIR.glob("*.theme")):
        try:
            themes[path.stem] = read_theme(path)
        except (GLib.Error, ValueError) as error:
            print(f"Skipping theme {path}: {error}", file=sys.stderr)
    return themes


class NoteWindow(Gtk.ApplicationWindow):
    def __init__(self, app, note):
        super().__init__(application=app, show_menubar=False)
        self.note = note
        self._confirm_source = 0
        self._flash_message = ""
        self._flash_source = 0
        self._zoom_scroll = 0.0
        self._theme_menu = None
        # 글자를 칠 때마다 버퍼 전체를 꺼내지 않고, 저장할 때만 note["text"] 로 옮긴다
        self._text_dirty = False
        self.get_style_context().add_class("note")
        self.set_default_size(note.get("width", 300), note.get("height", 240))
        if "x" in note and "y" in note:
            self.move(note["x"], note["y"])
        # 창 장식 없이 직접 그린다. GTK 그림자 장식(CSD)을 쓰면 mutter 가 그림자 폭만큼 어긋나게 배치해서
        # 다시 열 때마다 위치가 밀린다. 둥근 모서리와 반투명 배경은 RGBA 비주얼로 그린다
        self.set_decorated(False)
        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)
        # 모든 작업 공간에 보이게 한다. GNOME 은 독·Alt+Tab 에서 숨긴(skip_taskbar) 창을 개요에서도 숨기므로 숨기지 않는다.
        # 포커스 없이 띄우면 다른 창과 겹칠 때 '준비 완료' 알림이 뜨므로 기본대로 포커스를 받게 둔다
        self.stick()

        for name, callback in (
            ("cycle-theme", self._cycle_theme),
            ("theme-menu", self._show_theme_menu),
            ("toggle-pin", self._toggle_pin),
            ("delete", self._ask_delete),
            ("undo", self._undo),
            ("redo", self._redo),
            ("zoom-in", lambda: self._set_font_size(self.note["font_size"] + 1)),
            ("zoom-out", lambda: self._set_font_size(self.note["font_size"] - 1)),
            ("zoom-reset", lambda: self._set_font_size(DEFAULT_FONT_SIZE)),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _param, callback=callback: callback())
            self.add_action(action)

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.get_style_context().add_class("note-frame")
        frame.pack_start(self._build_titlebar(), False, False, 0)
        frame.pack_start(self._build_body(), True, True, 0)
        self.add(frame)

        self.apply_theme(note.get("theme", DEFAULT_THEME))
        self._apply_font_size(note.get("font_size", DEFAULT_FONT_SIZE))
        self._highlight_lines(0, self.buffer.get_line_count() - 1)
        self._update_title()
        self.apply_layer()
        self.connect("realize", self._on_realize)
        self.connect("configure-event", self._on_configure)
        self.connect("key-press-event", self._on_key_press)
        self.connect("window-state-event", self._on_window_state)
        self.connect("delete-event", self._on_delete_event)

    def _build_titlebar(self):
        self.title_label = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END)
        box = Gtk.Box(spacing=2)
        box.get_style_context().add_class("note-titlebar")
        box.pack_start(self.title_label, True, True, 10)
        for label, tooltip, action_name in TITLE_BUTTONS:
            button = Gtk.Button(label=label, tooltip_text=tooltip, action_name=action_name, can_focus=False)
            box.pack_start(button, False, False, 0)
            if action_name == "win.toggle-pin":
                self.pin_button = button
            elif action_name == "win.theme-menu":
                self.theme_button = button

        # 배경은 안쪽 상자가 그리고, 이벤트 상자는 끌어서 옮기기 입력만 받는다
        titlebar = Gtk.EventBox(child=box, visible_window=False)
        titlebar.connect("button-press-event", self._on_titlebar_pressed)
        return titlebar

    def _build_body(self):
        self.buffer = Gtk.TextBuffer(text=self.note.get("text", ""))
        self.buffer.create_tag("heading", weight=Pango.Weight.BOLD)
        self._done_tag = self.buffer.create_tag("done", strikethrough=True)
        self.history = History(self.buffer)
        self.buffer.connect("changed", self._on_text_changed)
        # 삽입·삭제가 끝난 뒤 바뀐 줄만 다시 칠한다
        self.buffer.connect_after("insert-text", self._on_text_inserted)
        self.buffer.connect_after("delete-range", self._on_range_deleted)
        self.text_view = Gtk.TextView(
            buffer=self.buffer,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            left_margin=12,
            right_margin=12,
            top_margin=8,
            bottom_margin=8,
        )
        self.text_view.add_events(Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK)
        self.text_view.connect("button-release-event", self._on_text_clicked)
        self.text_view.connect("scroll-event", self._on_scroll)
        self._font_css = Gtk.CssProvider()
        self.text_view.get_style_context().add_provider(
            self._font_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scrolled.add(self.text_view)

        self.mode_label = Gtk.Label()
        self.mode_label.get_style_context().add_class("mode")
        self.info_label = Gtk.Label(xalign=1, ellipsize=Pango.EllipsizeMode.START)
        grip = Gtk.EventBox(child=Gtk.Label(label="◢"), tooltip_text=tr("Resize"))
        grip.get_style_context().add_class("grip")
        grip.connect("button-press-event", self._on_grip_pressed)
        grip.connect(
            "realize", lambda w: w.get_window().set_cursor(Gdk.Cursor.new_from_name(w.get_display(), "se-resize"))
        )
        status = Gtk.Box(spacing=8)
        status.get_style_context().add_class("statusline")
        status.pack_start(self.mode_label, False, False, 0)
        status.pack_start(self.info_label, True, True, 0)
        status.pack_start(grip, False, False, 0)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        body.get_style_context().add_class("note-body")
        body.pack_start(scrolled, True, True, 0)
        body.pack_start(status, False, False, 0)
        return body

    def apply_layer(self):
        # 평소에는 다른 창 아래(바탕화면)에 깔고, 고정했거나 꺼내 보는 중이거나 지금 쓰고 있는 메모만 위로 올린다.
        # 그래야 개요·Alt+Tab·작업 공간 이동으로 포커스가 간 메모가 다른 창에 가려지지 않는다
        on_top = self.note.get("pinned", False) or self.get_application().peeking or self.is_focused()
        if on_top:
            self.set_keep_below(False)
            self.set_keep_above(True)
        else:
            self.set_keep_above(False)
            self.set_keep_below(True)
        context = self.pin_button.get_style_context()
        if self.note.get("pinned", False):
            context.add_class("active")
        else:
            context.remove_class("active")
        self._update_status()

    def apply_theme(self, theme):
        # 테마 파일이 잠깐 없거나 깨져도 메모에 적힌 테마는 그대로 두고 기본 테마로만 보여 준다
        themes = self.get_application().themes
        self.note["theme"] = theme
        self.theme = theme if theme in themes else DEFAULT_THEME
        context = self.get_style_context()
        for name in context.list_classes():
            if name.startswith("theme-"):
                context.remove_class(name)
        context.add_class(f"theme-{self.theme}")
        dim = Gdk.RGBA()
        dim.parse(themes[self.theme][0])
        dim.alpha = 0.45
        self._done_tag.props.foreground_rgba = dim
        self._update_status()

    def _apply_font_size(self, size):
        size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))
        self._font_css.load_from_data(f"textview, textview text {{ font-size: {size}pt; }}".encode())
        self.note["font_size"] = size
        return size

    def flush_text(self):
        if self._text_dirty:
            self.note["text"] = self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), False)
            self._text_dirty = False

    def _line(self, start):
        """start 가 있는 줄의 끝 위치와 글자. 빈 줄에서 forward_to_line_end 를 부르면 다음 줄로 넘어가므로 확인한다."""
        end = start.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        return end, self.buffer.get_text(start, end, False)

    def _highlight_lines(self, first, last):
        start = self.buffer.get_iter_at_line(first)
        for _number in range(first, last + 1):
            end, line = self._line(start)
            self.buffer.remove_all_tags(start, end)
            tag = line_tag(line)
            if tag:
                self.buffer.apply_tag_by_name(tag, start, end)
            if not start.forward_line():
                break

    def _update_title(self):
        start = self.buffer.get_start_iter()
        while True:
            _end, line = self._line(start)
            if line.strip() or not start.forward_line():
                break
        name = note_filename(line)
        self.set_title(name)
        self.title_label.set_markup(f'<span alpha="55%">~/notes/</span>{GLib.markup_escape_text(name)}')

    def _update_status(self):
        if self._confirm_source:
            self.mode_label.set_text("rm")
            self.info_label.set_text(tr("rm: remove '{}'? [y/N]").format(self.get_title()))
            return
        if self.note.get("pinned", False):
            mode = "PIN"
        elif self.get_application().peeking:
            mode = "PEEK"
        else:
            mode = "DESK"
        self.mode_label.set_text(mode)
        if self._flash_message:
            self.info_label.set_text(self._flash_message)
            return
        chars = self.buffer.get_char_count()
        lines = self.buffer.get_line_count() if chars else 0
        updated = time.strftime("%m-%d %H:%M", time.localtime(self.note["updated"])) if "updated" in self.note else "--:--"
        self.info_label.set_text(f"{self.theme} │ {lines}L {chars}C │ {updated}")

    def _flash(self, message):
        # vim 처럼 상태줄에 잠깐 메시지를 띄운다
        if self._flash_source:
            GLib.source_remove(self._flash_source)
        self._flash_message = message
        self._flash_source = GLib.timeout_add(1500, self._end_flash)
        self._update_status()

    def _end_flash(self):
        self._flash_source = 0
        self._flash_message = ""
        self._update_status()
        return GLib.SOURCE_REMOVE

    def _undo(self):
        if self.history.undo():
            self.text_view.scroll_mark_onscreen(self.buffer.get_insert())
        else:
            self._flash("Already at oldest change")

    def _redo(self):
        if self.history.redo():
            self.text_view.scroll_mark_onscreen(self.buffer.get_insert())
        else:
            self._flash("Already at newest change")

    def _set_font_size(self, size):
        self._flash(f"font {self._apply_font_size(size)}pt")
        self.get_application().schedule_save()

    def _cycle_theme(self):
        names = list(self.get_application().themes)
        self._set_theme(names[(names.index(self.theme) + 1) % len(names)])

    def _set_theme(self, theme):
        self.apply_theme(theme)
        self.get_application().schedule_save()

    def _show_theme_menu(self):
        app = self.get_application()
        # 테마 파일을 새로 넣거나 고쳤으면 메뉴를 열 때 반영된다
        app.reload_themes()
        if self._theme_menu:
            self._theme_menu.destroy()
        self._theme_menu = menu = Gtk.Menu()
        menu.attach_to_widget(self.theme_button, None)
        for name, (fg, bg, _crt) in app.themes.items():
            item = Gtk.CheckMenuItem(draw_as_radio=True, active=name == self.theme)
            label = Gtk.Label(xalign=0)
            label.set_markup(f'<span font_family="monospace" background="{bg}" foreground="{fg}"> Aa </span>  {name}')
            item.add(label)
            item.connect("activate", lambda _item, name=name: self._set_theme(name))
            menu.append(item)
        menu.append(Gtk.SeparatorMenuItem())
        folder = Gtk.MenuItem(label=tr("Open themes folder"))
        folder.connect("activate", lambda _item: self._open_themes_dir())
        menu.append(folder)
        menu.show_all()
        menu.popup_at_widget(self.theme_button, Gdk.Gravity.SOUTH_EAST, Gdk.Gravity.NORTH_EAST, None)

    def _open_themes_dir(self):
        THEMES_DIR.mkdir(parents=True, exist_ok=True)
        try:
            Gio.AppInfo.launch_default_for_uri(THEMES_DIR.as_uri(), None)
        except GLib.Error:
            self._flash(str(THEMES_DIR))

    def _toggle_pin(self):
        self.note["pinned"] = not self.note.get("pinned", False)
        self.apply_layer()
        self.get_application().schedule_save()

    def _ask_delete(self):
        # 빈 메모는 바로 지우고, 내용이 있으면 rm -i 처럼 한 번 더 묻는다. [x] 를 다시 눌러도 삭제된다
        self.flush_text()
        if self._confirm_source or not self.note.get("text", "").strip():
            self._delete()
            return
        self._confirm_source = GLib.timeout_add_seconds(5, self._stop_confirm)
        self.mode_label.get_style_context().add_class("warn")
        self._update_status()

    def _stop_confirm(self):
        if self._confirm_source:
            GLib.source_remove(self._confirm_source)
            self._confirm_source = 0
        self.mode_label.get_style_context().remove_class("warn")
        self._update_status()
        return GLib.SOURCE_REMOVE

    def _delete(self):
        for source in (self._confirm_source, self._flash_source):
            if source:
                GLib.source_remove(source)
        self._confirm_source = self._flash_source = 0
        self.get_application().remove_note(self.note)
        self.destroy()

    def _on_realize(self, _window):
        # 최대화·최소화를 빼 두면 화면 가장자리로 끌어도 타일링되지 않는다
        self.get_window().set_functions(Gdk.WMFunction.MOVE | Gdk.WMFunction.RESIZE | Gdk.WMFunction.CLOSE)

    def is_focused(self):
        # GTK 의 is-active 는 우클릭 메뉴가 키보드를 잡기만 해도 꺼지므로 창 관리자가 알려 주는 포커스를 본다
        window = self.get_window()
        return bool(window and window.get_state() & Gdk.WindowState.FOCUSED)

    def _on_window_state(self, _window, event):
        if event.changed_mask & Gdk.WindowState.FOCUSED:
            self.apply_layer()
            self.get_application().on_focus_changed()

    def _on_titlebar_pressed(self, _widget, event):
        # 두 번 눌러 최대화하는 기본 동작은 메모에 어울리지 않아 직접 옮기기만 한다
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
            self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
        return True

    def _on_grip_pressed(self, _widget, event):
        if event.button == 1:
            self.begin_resize_drag(
                Gdk.WindowEdge.SOUTH_EAST, event.button, int(event.x_root), int(event.y_root), event.time
            )
        return True

    def _on_text_changed(self, _buffer):
        self._text_dirty = True
        self.note["updated"] = time.time()
        self._update_title()
        self._update_status()
        self.get_application().schedule_save()

    def _on_text_inserted(self, _buffer, end, text, _length):
        # 기본 처리기가 끝나면 end 는 삽입된 글자 바로 뒤를 가리킨다
        last = end.get_line()
        self._highlight_lines(last - text.count("\n"), last)

    def _on_range_deleted(self, _buffer, start, _end):
        self._highlight_lines(start.get_line(), start.get_line())

    def _on_scroll(self, _view, event):
        # 터미널처럼 Ctrl+스크롤로 글자 크기를 바꾼다
        if not event.state & Gdk.ModifierType.CONTROL_MASK:
            return False
        if event.direction == Gdk.ScrollDirection.UP:
            steps = 1
        elif event.direction == Gdk.ScrollDirection.DOWN:
            steps = -1
        else:
            # 터치패드는 잘게 나뉜 값이 오므로 한 칸이 모일 때마다 바꾼다
            self._zoom_scroll -= event.delta_y
            steps = int(self._zoom_scroll)
            self._zoom_scroll -= steps
        if steps:
            self._set_font_size(self.note["font_size"] + steps)
        return True

    def _on_text_clicked(self, view, event):
        # 체크박스의 [ ] 를 누르면 [x] 로, [x] 를 누르면 [ ] 로 바꾼다
        if event.button != 1 or self.buffer.get_has_selection():
            return False
        x, y = view.window_to_buffer_coords(Gtk.TextWindowType.TEXT, int(event.x), int(event.y))
        over_text, clicked = view.get_iter_at_location(x, y)
        if not over_text:
            return False
        number = clicked.get_line()
        _end, line = self._line(self.buffer.get_iter_at_line(number))
        task = TASK.match(line)
        if not task or not task.start(2) - 1 <= clicked.get_line_offset() <= task.end(2):
            return False
        start = self.buffer.get_iter_at_line_offset(number, task.start(2))
        end = start.copy()
        end.forward_char()
        self.buffer.begin_user_action()
        self.buffer.delete(start, end)
        self.buffer.insert(start, " " if task.group(2) in "xX" else "x")
        self.buffer.end_user_action()
        return False

    def _on_configure(self, _window, _event):
        x, y = self.get_position()
        width, height = self.get_size()
        geometry = {"x": x, "y": y, "width": width, "height": height}
        if any(self.note.get(key) != value for key, value in geometry.items()):
            self.note.update(geometry)
            self.get_application().schedule_save()
        return False

    def _on_key_press(self, _window, event):
        if not self._confirm_source or event.is_modifier:
            return False
        if event.keyval in (Gdk.KEY_y, Gdk.KEY_Y):
            self._delete()
        else:
            self._stop_confirm()
        return True

    def _on_delete_event(self, *_args):
        # Alt+F4 로 닫아도 메모는 남는다. 앱을 다시 실행하면 돌아온다
        self.get_application().save_now()
        return False


class StickyNotesApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.notes = []
        self.themes = {}
        self.peeking = False
        self._save_source = 0
        self._focus_source = 0

    def do_startup(self):
        Gtk.Application.do_startup(self)
        settings = Gtk.Settings.get_default()
        # 툴팁·스크롤바 같은 테마 요소도 어두운 메모에 맞춘다
        settings.props.gtk_application_prefer_dark_theme = True
        # 반투명 창에 서브픽셀 안티앨리어싱을 쓰면 글자 옆에 색이 번진다
        settings.props.gtk_xft_rgba = "none"
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._theme_provider = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), self._theme_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.reload_themes()

        new_note_action = Gio.SimpleAction.new("new-note", None)
        new_note_action.connect("activate", lambda *_: self.new_note(near=self.get_active_window()))
        self.add_action(new_note_action)
        for action_name, accels in ACCELS.items():
            self.set_accels_for_action(action_name, accels)

        self.notes = load_notes()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if "--quit" in args:
            # 업데이트한 뒤 새 코드로 다시 띄울 수 있도록 저장하고 끝낸다 (install.sh 가 쓴다)
            self.quit()
        elif "--new" in args:
            # 다른 창에 가려져 있어도 보이도록 메모들을 앞으로 꺼낸 뒤 새 메모를 연다
            self._show_hidden_notes()
            self.set_peek(True)
            self.new_note()
        else:
            self.activate()
        return 0

    def do_activate(self):
        # 처음 실행이면 저장된 메모를 바탕화면에 깔고, 이미 다 떠 있으면 다른 창 위로 꺼내거나 다시 내린다
        if self._show_hidden_notes():
            return
        if not self.notes:
            self.new_note()
            return
        self.set_peek(not self.peeking)
        if self.peeking:
            self.note_windows()[-1].present()

    def do_shutdown(self):
        if self._save_source:
            self.save_now()
        Gtk.Application.do_shutdown(self)

    def reload_themes(self):
        themes = load_themes()
        if themes == self.themes:
            return
        self.themes = themes
        css = "".join(_theme_css(name, *theme) for name, theme in themes.items())
        self._theme_provider.load_from_data(css.encode())
        for window in self.note_windows():
            window.apply_theme(window.note["theme"])

    def note_windows(self):
        return [window for window in self.get_windows() if isinstance(window, NoteWindow)]

    def _show_hidden_notes(self):
        open_ids = {window.note["id"] for window in self.note_windows()}
        hidden = [note for note in self.notes if note["id"] not in open_ids]
        for note in hidden:
            NoteWindow(self, note).show_all()
        return bool(hidden)

    def new_note(self, near=None):
        note = {"id": uuid.uuid4().hex, "text": "", "theme": DEFAULT_THEME}
        if isinstance(near, NoteWindow):
            x, y = near.get_position()
            note.update(x=x + 32, y=y + 32, theme=near.note["theme"])
        self.notes.append(note)
        self.schedule_save()
        window = NoteWindow(self, note)
        window.show_all()
        window.present()

    def remove_note(self, note):
        self.notes.remove(note)
        self.save_now()

    def set_peek(self, peeking):
        self.peeking = peeking
        for window in self.note_windows():
            window.apply_layer()

    def on_focus_changed(self):
        # 꺼내 보던 중 메모 밖을 누르면 다시 바탕화면으로 내린다.
        # 메모끼리 오갈 때는 잠깐 아무 메모도 활성이 아니므로 조금 기다렸다가 확인한다
        if self.peeking and not self._focus_source:
            self._focus_source = GLib.timeout_add(250, self._on_focus_timeout)

    def _on_focus_timeout(self):
        self._focus_source = 0
        if self.peeking and not any(window.is_focused() for window in self.note_windows()):
            self.set_peek(False)
        return GLib.SOURCE_REMOVE

    def schedule_save(self):
        if not self._save_source:
            self._save_source = GLib.timeout_add(500, self._on_save_timeout)

    def _on_save_timeout(self):
        self._save_source = 0
        self._save()
        return GLib.SOURCE_REMOVE

    def save_now(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
            self._save_source = 0
        self._save()

    def _save(self):
        for window in self.note_windows():
            window.flush_text()
        save_notes(self.notes)


if __name__ == "__main__":
    sys.exit(StickyNotesApp().run(sys.argv))
