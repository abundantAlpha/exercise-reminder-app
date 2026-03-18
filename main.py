import random
import threading
import time

import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw

TIMER_SECONDS = 15 * 60

DEFAULT_EXERCISES = [
    "30 Push-ups",
    "20 Squats",
    "15 Lunges (each leg)",
    "30 sec Plank",
    "20 Jumping Jacks",
    "10 Burpees",
    "20 Mountain Climbers",
    "15 Tricep Dips",
    "20 Calf Raises",
    "10 Pull-ups",
]


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------

class ExerciseDialog(ctk.CTkToplevel):
    """Modal dialog for adding or editing a single exercise."""

    def __init__(self, parent, title="Exercise", initial_value=""):
        super().__init__(parent)
        self.title(title)
        self.geometry("320x150")
        self.resizable(False, False)
        self.grab_set()
        self.result = None

        ctk.CTkLabel(self, text="Exercise:").pack(pady=(20, 4), padx=20, anchor="w")

        self.entry = ctk.CTkEntry(self, width=280, placeholder_text="e.g. 30 Push-ups")
        self.entry.pack(padx=20)
        if initial_value:
            self.entry.insert(0, initial_value)
        self.entry.focus()

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=15)
        ctk.CTkButton(btn_frame, text="Save", width=110, command=self._save).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_frame, text="Cancel", width=110,
            fg_color="gray40", hover_color="gray30",
            command=self.destroy,
        ).pack(side="left", padx=6)

        self.entry.bind("<Return>", lambda _e: self._save())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _save(self):
        value = self.entry.get().strip()
        if value:
            self.result = value
            self.destroy()


class PopupWindow(ctk.CTkToplevel):
    """Exercise reminder popup — stays until user clicks Done."""

    def __init__(self, parent, exercise: str, on_done):
        super().__init__(parent)
        self.title("Time to Exercise!")
        self.geometry("340x210")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.grab_set()
        self._on_done = on_done

        ctk.CTkLabel(
            self, text="Time to exercise!",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(30, 8))

        ctk.CTkLabel(
            self, text=exercise,
            font=ctk.CTkFont(size=24),
            wraplength=300,
        ).pack(pady=8)

        ctk.CTkButton(self, text="Done", width=130, command=self._done).pack(pady=20)
        self.protocol("WM_DELETE_WINDOW", self._done)

    def _done(self):
        self._on_done()
        self.destroy()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class ExerciseReminderApp:

    def __init__(self):
        self.exercises: list[str] = list(DEFAULT_EXERCISES)
        self._shuffle_queue: list[str] = []
        self._popup_open = False

        # Timer state (guarded by _lock)
        self._lock = threading.Lock()
        self._timer_paused = False
        self._timer_seconds = TIMER_SECONDS
        self._running = True

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Exercise Reminder")
        self.root.geometry("420x540")
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._minimize_to_tray)

        self._build_ui()
        self._setup_tray()
        self._start_timer()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        ctk.CTkLabel(
            self.root, text="Exercise Reminder",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(20, 8))

        # Scrollable exercise list
        self._list_frame = ctk.CTkScrollableFrame(self.root, width=360, height=290)
        self._list_frame.pack(padx=20, pady=4, fill="both", expand=True)
        self._selected_index: int | None = None
        self._list_buttons: list[ctk.CTkButton] = []
        self._refresh_list()

        # Add / Edit / Delete buttons
        btn_row = ctk.CTkFrame(self.root, fg_color="transparent")
        btn_row.pack(pady=8)
        ctk.CTkButton(btn_row, text="Add",    width=95, command=self._add).pack(side="left", padx=5)
        ctk.CTkButton(btn_row, text="Edit",   width=95, command=self._edit).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_row, text="Delete", width=95,
            fg_color="#c0392b", hover_color="#922b21",
            command=self._delete,
        ).pack(side="left", padx=5)

        # Timer section
        timer_card = ctk.CTkFrame(self.root)
        timer_card.pack(padx=20, pady=(4, 20), fill="x")

        self._timer_label = ctk.CTkLabel(
            timer_card, text="15:00",
            font=ctk.CTkFont(size=34, weight="bold"),
        )
        self._timer_label.pack(pady=(12, 4))

        self._pause_btn = ctk.CTkButton(
            timer_card, text="Pause", width=110, command=self._toggle_pause,
        )
        self._pause_btn.pack(pady=(0, 12))

    # ------------------------------------------------------------------
    # Exercise list helpers
    # ------------------------------------------------------------------

    def _refresh_list(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._list_buttons = []
        self._selected_index = None

        for i, exercise in enumerate(self.exercises):
            btn = ctk.CTkButton(
                self._list_frame,
                text=exercise,
                anchor="w",
                fg_color="transparent",
                text_color=("gray10", "gray90"),
                hover_color=("gray80", "gray30"),
                height=36,
                command=lambda idx=i: self._select(idx),
            )
            btn.pack(fill="x", pady=2, padx=4)
            self._list_buttons.append(btn)

    def _select(self, index: int):
        if self._selected_index is not None and self._selected_index < len(self._list_buttons):
            self._list_buttons[self._selected_index].configure(fg_color="transparent")
        self._selected_index = index
        self._list_buttons[index].configure(fg_color=("gray75", "gray25"))

    # ------------------------------------------------------------------
    # Add / Edit / Delete
    # ------------------------------------------------------------------

    def _add(self):
        dlg = ExerciseDialog(self.root, title="Add Exercise")
        self.root.wait_window(dlg)
        if dlg.result:
            self.exercises.append(dlg.result)
            self._refresh_list()

    def _edit(self):
        if self._selected_index is None:
            return
        idx = self._selected_index
        dlg = ExerciseDialog(self.root, title="Edit Exercise", initial_value=self.exercises[idx])
        self.root.wait_window(dlg)
        if dlg.result:
            self.exercises[idx] = dlg.result
            self._refresh_list()

    def _delete(self):
        if self._selected_index is None or not self.exercises:
            return
        self.exercises.pop(self._selected_index)
        self._refresh_list()

    # ------------------------------------------------------------------
    # Timer
    # ------------------------------------------------------------------

    def _start_timer(self):
        t = threading.Thread(target=self._timer_loop, daemon=True)
        t.start()
        self._update_timer_label()

    def _timer_loop(self):
        while self._running:
            time.sleep(1)
            with self._lock:
                if not self._timer_paused and not self._popup_open:
                    self._timer_seconds -= 1
                    if self._timer_seconds <= 0:
                        self._timer_seconds = TIMER_SECONDS
                        self.root.after(0, self._show_popup)
            self.root.after(0, self._update_timer_label)

    def _update_timer_label(self):
        with self._lock:
            secs = self._timer_seconds
        mins, s = divmod(secs, 60)
        self._timer_label.configure(text=f"{mins:02d}:{s:02d}")

    def _toggle_pause(self):
        with self._lock:
            self._timer_paused = not self._timer_paused
        self._pause_btn.configure(text="Resume" if self._timer_paused else "Pause")

    # ------------------------------------------------------------------
    # Popup
    # ------------------------------------------------------------------

    def _next_exercise(self) -> str:
        if not self.exercises:
            return "No exercises configured!"
        if not self._shuffle_queue:
            self._shuffle_queue = list(self.exercises)
            random.shuffle(self._shuffle_queue)
        return self._shuffle_queue.pop()

    def _show_popup(self):
        if self._popup_open or not self.exercises:
            return
        self._popup_open = True
        exercise = self._next_exercise()
        self.root.deiconify()
        popup = PopupWindow(self.root, exercise, on_done=self._on_popup_done)
        self.root.update_idletasks()
        px = self.root.winfo_x() + (self.root.winfo_width()  - 340) // 2
        py = self.root.winfo_y() + (self.root.winfo_height() - 210) // 2
        popup.geometry(f"340x210+{px}+{py}")

    def _on_popup_done(self):
        self._popup_open = False
        with self._lock:
            self._timer_seconds = TIMER_SECONDS

    # ------------------------------------------------------------------
    # System tray
    # ------------------------------------------------------------------

    def _make_tray_image(self) -> Image.Image:
        img = Image.new("RGB", (64, 64), (30, 30, 30))
        draw = ImageDraw.Draw(img)
        draw.ellipse([6, 6, 58, 58], fill=(52, 152, 219))
        draw.text((16, 18), "EX", fill="white")
        return img

    def _setup_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Open",  self._tray_open, default=True),
            pystray.MenuItem("Quit",  self._tray_quit),
        )
        self._tray = pystray.Icon(
            "ExerciseReminder", self._make_tray_image(),
            "Exercise Reminder", menu,
        )
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _minimize_to_tray(self):
        self.root.withdraw()

    def _tray_open(self):
        self.root.after(0, self.root.deiconify)

    def _tray_quit(self):
        self._running = False
        self._tray.stop()
        self.root.after(0, self.root.destroy)

    # ------------------------------------------------------------------

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = ExerciseReminderApp()
    app.run()
