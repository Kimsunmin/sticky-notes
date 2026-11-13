#!/usr/bin/env python3
"""바탕화면에 붙여 두는 터미널 감성 스티커 메모."""

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

# 이름: (글자색, 배경색)
THEMES = {
    "green": ("#3df07c", "#06130b"),
    "amber": ("#ffb547", "#150e02"),
    "cyan": ("#56d8ff", "#03121b"),
    "magenta": ("#ff6ad5", "#16071a"),
    "red": ("#ff6b5e", "#190706"),
    "white": ("#e2e2e2", "#121212"),
}
DEFAULT_THEME = "green"
FONT = '"Ubuntu Sans Mono", "Noto Sans Mono CJK KR", monospace'

# (글자, 툴팁, 액션)
TITLE_BUTTONS = (
    ("[+]", "새 메모 (Ctrl+N)", "app.new-note"),
    ("[~]", "테마 바꾸기 (Ctrl+T)", "win.cycle-theme"),
    ("[^]", "다른 창 위에 고정 (Ctrl+P)", "win.toggle-pin"),
    ("[x]", "메모 삭제 (Ctrl+W)", "win.delete"),
)
ACCELS = {
    "app.new-note": "<Control>n",
    "win.cycle-theme": "<Control>t",
    "win.toggle-pin": "<Control>p",
    "win.delete": "<Control>w",
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
.note-body textview, .note-body textview text {{ background-color: transparent; font-size: 12pt; }}
.note-body textview {{ -GtkWidget-cursor-aspect-ratio: 0.1; }}
.statusline {{ padding: 0 2px 3px 6px; }}
.statusline label {{ font-size: 9pt; }}
.statusline .mode {{ padding: 0 6px; font-weight: bold; }}
.statusline .grip {{ background: none; padding: 0 4px; }}
"""


def _theme_css(name, fg, bg):
    scope = f"window.note.theme-{name}"
    return f"""
{scope} .note-frame {{ border-color: alpha({fg}, 0.35); }}
{scope}:backdrop .note-frame {{ border-color: alpha({fg}, 0.2); }}
{scope} .note-titlebar {{ background-color: alpha(mix({bg}, {fg}, 0.14), 0.95); color: alpha({fg}, 0.8); }}
{scope} .note-body {{ background-color: alpha({bg}, 0.9);
    background-image: repeating-linear-gradient(to bottom, alpha({fg}, 0.035), alpha({fg}, 0.035) 1px,
                                                transparent 1px, transparent 3px); }}
{scope} label {{ text-shadow: 0 0 5px alpha({fg}, 0.45); }}
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


CSS += "".join(_theme_css(name, fg, bg) for name, (fg, bg) in THEMES.items())


def note_filename(text):
    """첫 줄로 터미널 파일 이름처럼 보이는 제목을 만든다."""
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    slug = re.sub(r"[\s/]+", "-", TITLE_PREFIX.sub("", first_line).strip().lower()).strip("-.")
    return f"{slug[:24] or 'untitled'}.txt"


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
        print(f"메모 파일을 읽지 못해 {backup} 로 옮겼습니다.", file=sys.stderr)
        return []


def save_notes(notes):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"notes": notes}, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, DATA_FILE)


class NoteWindow(Gtk.ApplicationWindow):
    def __init__(self, app, note, focus=True):
        super().__init__(application=app, show_menubar=False)
        self.note = note
        self._confirm_source = 0
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
        # 바탕화면 위젯처럼 둔다: 모든 작업 공간에 보이고, 독·Alt+Tab·개요에는 나오지 않는다
        self.stick()
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_focus_on_map(focus)

        for name, callback in (
            ("cycle-theme", self._cycle_theme),
            ("toggle-pin", self._toggle_pin),
            ("delete", self._ask_delete),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _action, _param, callback=callback: callback())
            self.add_action(action)

        frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.get_style_context().add_class("note-frame")
        frame.pack_start(self._build_titlebar(), False, False, 0)
        frame.pack_start(self._build_body(), True, True, 0)
        self.add(frame)

        self._apply_theme(note.get("theme", DEFAULT_THEME))
        self.apply_layer()
        self._refresh()
        self.connect("realize", self._on_realize)
        self.connect("configure-event", self._on_configure)
        self.connect("key-press-event", self._on_key_press)
        self.connect("notify::is-active", lambda *_: app.on_focus_changed())
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

        # 배경은 안쪽 상자가 그리고, 이벤트 상자는 끌어서 옮기기 입력만 받는다
        titlebar = Gtk.EventBox(child=box, visible_window=False)
        titlebar.connect("button-press-event", self._on_titlebar_pressed)
        return titlebar

    def _build_body(self):
        self.buffer = Gtk.TextBuffer(text=self.note.get("text", ""))
        self.buffer.create_tag("heading", weight=Pango.Weight.BOLD)
        self._done_tag = self.buffer.create_tag("done", strikethrough=True)
        self.buffer.connect("changed", self._on_text_changed)
        text_view = Gtk.TextView(
            buffer=self.buffer,
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            left_margin=12,
            right_margin=12,
            top_margin=8,
            bottom_margin=8,
        )
        text_view.connect("button-release-event", self._on_text_clicked)
        scrolled = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        scrolled.add(text_view)

        self.mode_label = Gtk.Label()
        self.mode_label.get_style_context().add_class("mode")
        self.info_label = Gtk.Label(xalign=1, ellipsize=Pango.EllipsizeMode.START)
        grip = Gtk.EventBox(child=Gtk.Label(label="◢"), tooltip_text="크기 조절")
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
        # 평소에는 다른 창 아래(바탕화면), 고정했거나 잠깐 꺼내 볼 때만 위로 올린다
        on_top = self.note.get("pinned", False) or self.get_application().peeking
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

    def _apply_theme(self, theme):
        if theme not in THEMES:
            theme = DEFAULT_THEME
        context = self.get_style_context()
        for name in THEMES:
            context.remove_class(f"theme-{name}")
        context.add_class(f"theme-{theme}")
        dim = Gdk.RGBA()
        dim.parse(THEMES[theme][0])
        dim.alpha = 0.45
        self._done_tag.props.foreground_rgba = dim
        self.note["theme"] = theme

    def _refresh(self):
        name = note_filename(self.note.get("text", ""))
        self.set_title(name)
        self.title_label.set_markup(f'<span alpha="55%">~/notes/</span>{GLib.markup_escape_text(name)}')
        self._highlight()
        self._update_status()

    def _highlight(self):
        self.buffer.remove_all_tags(self.buffer.get_start_iter(), self.buffer.get_end_iter())
        for number, line in enumerate(self.note.get("text", "").split("\n")):
            task = TASK.match(line)
            if line.lstrip().startswith("#"):
                tag = "heading"
            elif task and task.group(2) in "xX":
                tag = "done"
            else:
                continue
            start = self.buffer.get_iter_at_line(number)
            end = start.copy()
            end.forward_to_line_end()
            self.buffer.apply_tag_by_name(tag, start, end)

    def _update_status(self):
        if self._confirm_source:
            self.mode_label.set_text("rm")
            self.info_label.set_text(f"'{self.get_title()}' 삭제할까요? [y/N]")
            return
        if self.note.get("pinned", False):
            mode = "PIN"
        elif self.get_application().peeking:
            mode = "PEEK"
        else:
            mode = "DESK"
        text = self.note.get("text", "")
        lines = text.count("\n") + 1 if text else 0
        updated = time.strftime("%m-%d %H:%M", time.localtime(self.note["updated"])) if "updated" in self.note else "--:--"
        self.mode_label.set_text(mode)
        self.info_label.set_text(f"{self.note['theme']} │ {lines}L {len(text)}C │ {updated}")

    def _cycle_theme(self):
        names = list(THEMES)
        self._apply_theme(names[(names.index(self.note["theme"]) + 1) % len(names)])
        self._update_status()
        self.get_application().schedule_save()

    def _toggle_pin(self):
        self.note["pinned"] = not self.note.get("pinned", False)
        self.apply_layer()
        self.get_application().schedule_save()

    def _ask_delete(self):
        # 빈 메모는 바로 지우고, 내용이 있으면 rm -i 처럼 한 번 더 묻는다. [x] 를 다시 눌러도 삭제된다
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
        if self._confirm_source:
            GLib.source_remove(self._confirm_source)
            self._confirm_source = 0
        self.get_application().remove_note(self.note)
        self.destroy()

    def _on_realize(self, _window):
        # 최대화·최소화를 빼 두면 화면 가장자리로 끌어도 타일링되지 않는다
        self.get_window().set_functions(Gdk.WMFunction.MOVE | Gdk.WMFunction.RESIZE | Gdk.WMFunction.CLOSE)

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

    def _on_text_changed(self, buffer):
        self.note["text"] = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        self.note["updated"] = time.time()
        self._refresh()
        self.get_application().schedule_save()

    def _on_text_clicked(self, view, event):
        # 체크박스의 [ ] 를 누르면 [x] 로, [x] 를 누르면 [ ] 로 바꾼다
        if event.button != 1 or self.buffer.get_has_selection():
            return False
        x, y = view.window_to_buffer_coords(Gtk.TextWindowType.TEXT, int(event.x), int(event.y))
        over_text, clicked = view.get_iter_at_location(x, y)
        if not over_text:
            return False
        number = clicked.get_line()
        task = TASK.match(self.note.get("text", "").split("\n")[number])
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

        new_note_action = Gio.SimpleAction.new("new-note", None)
        new_note_action.connect("activate", lambda *_: self.new_note(near=self.get_active_window()))
        self.add_action(new_note_action)
        for action_name, accel in ACCELS.items():
            self.set_accels_for_action(action_name, [accel])

        self.notes = load_notes()

    def do_command_line(self, command_line):
        if "--new" in command_line.get_arguments()[1:]:
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

    def note_windows(self):
        return [window for window in self.get_windows() if isinstance(window, NoteWindow)]

    def _show_hidden_notes(self):
        open_ids = {window.note["id"] for window in self.note_windows()}
        hidden = [note for note in self.notes if note["id"] not in open_ids]
        for note in hidden:
            NoteWindow(self, note, focus=False).show_all()
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
        if self.peeking and not any(window.is_active() for window in self.note_windows()):
            self.set_peek(False)
        return GLib.SOURCE_REMOVE

    def schedule_save(self):
        if not self._save_source:
            self._save_source = GLib.timeout_add(500, self._on_save_timeout)

    def _on_save_timeout(self):
        self._save_source = 0
        save_notes(self.notes)
        return GLib.SOURCE_REMOVE

    def save_now(self):
        if self._save_source:
            GLib.source_remove(self._save_source)
            self._save_source = 0
        save_notes(self.notes)


if __name__ == "__main__":
    sys.exit(StickyNotesApp().run(sys.argv))
