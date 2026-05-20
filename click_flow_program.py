import ctypes
import json
import os
import threading
import time
from ctypes import wintypes
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from keyboard_simulator import (
    ActionCancelled,
    ClickRecorder,
    VK_F6,
    activate_window,
    list_visible_windows,
    mouse_click_at,
    raise_if_cancelled,
    recorded_value_from_tk_event,
    resolve_key_spec,
    run_click_flow,
    sleep_with_cancel,
    user32,
)

BTN_COLOR = {"left": "#2471a3", "right": "#7d3c98", "middle": "#1e8449"}
KEY_PRESSED_MASK = 0x8000

user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
user32.GetCursorPos.restype = wintypes.BOOL


# ─── Tooltip ────────────────────────────────────────────────────────────────

class Tooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._w = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _=None) -> None:
        if self._tip:
            return
        x = self._w.winfo_rootx() + 10
        y = self._w.winfo_rooty() + self._w.winfo_height() + 4
        self._tip = tw = tk.Toplevel(self._w)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self._text, bg="#ffffcc", relief="solid", bd=1,
                 font=("Segoe UI", 9), wraplength=320, justify="left",
                 padx=6, pady=4).pack()

    def _hide(self, _=None) -> None:
        if self._tip:
            self._tip.destroy()
            self._tip = None


# ─── Step Card ──────────────────────────────────────────────────────────────

class StepCard(ttk.Frame):
    """One step block. Each card owns its entry widgets and pushes
    changes back to the parent app in real time."""

    def __init__(self, parent: tk.Widget, index: int, click: dict,
                 app: "ClickFlowApp", loop_key: str, on_wheel) -> None:
        super().__init__(parent, relief="groove", borderwidth=2, padding=(8, 5))
        self._index = index
        self._app = app
        self._loop_key = loop_key
        self._suppress = False

        # ── header row ──────────────────────────────────────────────
        hdr = ttk.Frame(self)
        hdr.pack(fill="x")

        color = BTN_COLOR.get(str(click.get("button", "left")), "#2471a3")
        self._badge = tk.Label(hdr, text=f" {index + 1} ",
                               bg=color, fg="white",
                               font=("Segoe UI", 8, "bold"), padx=2, pady=1)
        self._badge.pack(side="left")

        self._lbl = ttk.Label(hdr, text=f" 步骤 {index + 1}",
                              font=("Segoe UI", 8, "bold"))
        self._lbl.pack(side="left")

        ttk.Button(hdr, text="✕", width=2,
                   command=lambda: self._app.delete_step(self._loop_key, self._index)
                   ).pack(side="right", padx=(2, 0))
        ttk.Button(hdr, text="▼", width=2,
                   command=lambda: self._app.move_step(self._loop_key, self._index, 1)
                   ).pack(side="right", padx=(2, 0))
        ttk.Button(hdr, text="▲", width=2,
                   command=lambda: self._app.move_step(self._loop_key, self._index, -1)
                   ).pack(side="right")

        # ── fields row ──────────────────────────────────────────────
        row = ttk.Frame(self)
        row.pack(fill="x", pady=(5, 0))

        ttk.Label(row, text="X", font=("Segoe UI", 8)).pack(side="left")
        self._x_var = tk.StringVar(value=str(int(click.get("x", 0))))
        x_entry = ttk.Entry(row, textvariable=self._x_var, width=5)
        x_entry.pack(side="left", padx=(3, 8))

        ttk.Label(row, text="Y", font=("Segoe UI", 8)).pack(side="left")
        self._y_var = tk.StringVar(value=str(int(click.get("y", 0))))
        y_entry = ttk.Entry(row, textvariable=self._y_var, width=5)
        y_entry.pack(side="left", padx=(3, 8))

        ttk.Label(row, text="按键", font=("Segoe UI", 8)).pack(side="left")
        self._btn_var = tk.StringVar(value=str(click.get("button", "left")))
        self._btn_cmb = ttk.Combobox(row, textvariable=self._btn_var,
                                      values=("left", "right", "middle"),
                                      state="readonly", width=5)
        self._btn_cmb.pack(side="left", padx=(3, 8))

        ttk.Label(row, text="延迟", font=("Segoe UI", 8)).pack(side="left")
        self._d_var = tk.StringVar(value=f"{float(click.get('delay', 0)):.2f}")
        d_entry = ttk.Entry(row, textvariable=self._d_var, width=5)
        d_entry.pack(side="left", padx=(3, 2))
        ttk.Label(row, text="秒", font=("Segoe UI", 8)).pack(side="left")

        for var in (self._btn_var, self._x_var, self._y_var, self._d_var):
            var.trace_add("write", self._push)

        # Bind mouse wheel
        for w in [self, hdr, row, self._badge, self._lbl,
                  self._btn_cmb, x_entry, y_entry, d_entry]:
            w.bind("<MouseWheel>", on_wheel)

    def _push(self, *_) -> None:
        if self._suppress:
            return
        try:
            data = self._read()
            data = self._app.normalize_step_data(data)
            self._badge.config(bg=BTN_COLOR.get(data["button"], "#2471a3"))
            self._app.update_step_data(self._loop_key, self._index, data)
            self._app.clear_step_error(self._loop_key, self._index)
        except (ValueError, KeyError) as e:
            self._app.set_step_error(self._loop_key, self._index, str(e))

    def _read(self) -> dict:
        data = {
            "x":      int(self._x_var.get().strip() or "0"),
            "y":      int(self._y_var.get().strip() or "0"),
            "button": self._btn_var.get().strip().lower(),
            "delay":  round(float(self._d_var.get().strip() or "0"), 3),
        }
        if data["button"] not in BTN_COLOR:
            raise ValueError("按键必须是 left / right / middle。")
        if data["delay"] < 0:
            raise ValueError("延迟不能为负数。")
        return data

    def read_data(self) -> dict:
        return self._read()

    def pull(self, click: dict, new_index: int) -> None:
        """Receive updated data from app without triggering _push."""
        self._suppress = True
        try:
            self._index = new_index
            self._lbl.config(text=f" 步骤 {new_index + 1}")
            self._badge.config(
                text=f" {new_index + 1} ",
                bg=BTN_COLOR.get(str(click.get("button", "left")), "#2471a3"),
            )
            self._btn_var.set(str(click.get("button", "left")))
            self._x_var.set(str(int(click.get("x", 0))))
            self._y_var.set(str(int(click.get("y", 0))))
            self._d_var.set(f"{float(click.get('delay', 0)):.2f}")
        finally:
            self._suppress = False


# ─── Main Application ────────────────────────────────────────────────────────

class ClickFlowApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Click Flow - 嵌套循环")
        self.root.resizable(True, True)
        self.root.minsize(900, 700)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # ── vars ─────────────────────────────────────────────────────
        self.delay_var = tk.StringVar(value="3")
        self.countdown_var = tk.StringVar(value="3")
        self.minimize_var = tk.BooleanVar(value=True)
        self.use_selected_window_var = tk.BooleanVar(value=False)
        self.target_window_var = tk.StringVar(value="")
        self.autoclick_count_var = tk.StringVar(value="100")
        self.autoclick_interval_var = tk.StringVar(value="0.05")
        self.autoclick_status_var = tk.StringVar(value="就绪 — 鼠标放到目标位置后启动连点。")
        self.autoclick_start_hotkey_var = tk.StringVar(value="开始快捷键: F7")
        self.autoclick_stop_hotkey_var = tk.StringVar(value="结束快捷键: F8")

        # 小循环1控制变量
        self.loop1_repeat_var = tk.StringVar(value="1")
        self.loop1_interval_var = tk.StringVar(value="0.5")

        # 小循环2控制变量
        self.loop2_repeat_var = tk.StringVar(value="1")
        self.loop2_interval_var = tk.StringVar(value="0.5")

        # 大循环控制变量
        self.big_loop_count_var = tk.StringVar(value="1")
        self.exec_order_var = tk.StringVar(value="1→2")  # 执行顺序
        self.exec_mode_var = tk.StringVar(value="sequential")  # 执行模式: sequential/alternate
        self.switch_interval_var = tk.StringVar(value="0")  # 循环间切换间隔

        self.status_var = tk.StringVar(value="就绪 — 录制点击步骤，然后按开始运行。")

        # ── state ────────────────────────────────────────────────────
        self.click_recorder = ClickRecorder()
        self.flows: dict[str, list[dict]] = {"loop1": [], "loop2": []}
        self.active_recording_loop: str | None = None
        self.window_targets: list[dict] = []
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self._recording_prefix: list[dict] = []
        self._recording_append = False
        self._recording_overlay: tk.Toplevel | None = None
        self._recording_count_var: tk.StringVar | None = None
        self._countdown_window: tk.Toplevel | None = None
        self._recording_cancelled = False
        self._recording_original_flow: list[dict] = []
        self._stop_hotkey_monitor = threading.Event()
        self._stop_hotkey_thread: threading.Thread | None = None
        self._stop_hotkey_armed = False
        self.autoclick_worker: threading.Thread | None = None
        self.autoclick_stop_event = threading.Event()
        self._autoclick_hotkey_monitor = threading.Event()
        self._autoclick_hotkey_thread: threading.Thread | None = None
        self._autoclick_start_key = "f7"
        self._autoclick_stop_key = "f8"
        self._autoclick_start_vk = resolve_key_spec(self._autoclick_start_key)[-1]
        self._autoclick_stop_vk = resolve_key_spec(self._autoclick_stop_key)[-1]
        self._autoclick_start_armed = False
        self._autoclick_stop_armed = False
        self._capturing_autoclick_hotkey: str | None = None

        # 两个循环的步骤卡片列表
        self._step_cards: dict[str, list[StepCard]] = {"loop1": [], "loop2": []}
        self._step_errors: dict[str, dict[int, str]] = {"loop1": {}, "loop2": {}}
        self._add_btns: dict[str, tk.Widget] = {}
        self._steps_canvases: dict[str, tk.Canvas] = {}
        self._steps_inners: dict[str, ttk.Frame] = {}
        self._canvas_wins: dict[str, int] = {}

        self.build_ui()
        self.refresh_window_list()

        self.root.bind("<Control-s>", lambda _: self.save_click_flow("loop1"))
        self.root.bind("<Control-o>", lambda _: self.load_click_flow("loop1"))
        self.root.bind("<F6>", self._handle_stop_hotkey)
        self._start_autoclick_hotkey_monitor()

    # ─── helpers ────────────────────────────────────────────────────────────

    def _btn_state(self, btn: tk.Widget, enabled: bool) -> None:
        if isinstance(btn, ttk.Button):
            btn.state(["!disabled"] if enabled else ["disabled"])
        else:
            btn.config(state="normal" if enabled else "disabled")

    def _handle_stop_hotkey(self, _=None):
        if self.worker and self.worker.is_alive() and not self.click_recorder.is_recording:
            self.stop_action()
            return "break"
        return None

    def _start_stop_hotkey_monitor(self) -> None:
        self._stop_hotkey_monitor.set()
        self._stop_hotkey_armed = bool(user32.GetAsyncKeyState(VK_F6) & KEY_PRESSED_MASK)
        self._stop_hotkey_thread = threading.Thread(
            target=self._watch_stop_hotkey,
            daemon=True,
        )
        self._stop_hotkey_thread.start()

    def _stop_stop_hotkey_monitor(self) -> None:
        self._stop_hotkey_monitor.clear()

    def _watch_stop_hotkey(self) -> None:
        while self._stop_hotkey_monitor.is_set():
            pressed = bool(user32.GetAsyncKeyState(VK_F6) & KEY_PRESSED_MASK)
            if pressed and not self._stop_hotkey_armed:
                self.root.after(0, self._handle_stop_hotkey)
                self._stop_hotkey_monitor.clear()
                return
            self._stop_hotkey_armed = pressed
            time.sleep(0.03)

    def normalize_step_data(self, data: dict) -> dict:
        return self._normalize(data)

    def set_step_error(self, loop_key: str, index: int, message: str) -> None:
        if loop_key in self._step_errors:
            self._step_errors[loop_key][index] = message
        label = "小循环1" if loop_key == "loop1" else "小循环2"
        self.status_var.set(f"{label} 步骤 {index + 1} 输入无效：{message}")

    def clear_step_error(self, loop_key: str, index: int) -> None:
        if loop_key in self._step_errors:
            self._step_errors[loop_key].pop(index, None)

    def _validated_flow(self, loop_key: str) -> list[dict]:
        cards = self._step_cards[loop_key]
        label = "小循环1" if loop_key == "loop1" else "小循环2"
        validated: list[dict] = []
        errors: dict[int, str] = {}

        for idx, card in enumerate(cards):
            try:
                validated.append(self._normalize(card.read_data()))
            except ValueError as e:
                errors[idx] = str(e)

        self._step_errors[loop_key] = errors
        if errors:
            first_idx = min(errors)
            raise ValueError(f"{label} 步骤 {first_idx + 1} 输入无效：{errors[first_idx]}")

        self.flows[loop_key] = validated
        return [dict(c) for c in validated]

    # ─── UI construction ────────────────────────────────────────────────────

    def build_ui(self) -> None:
        root = self.root
        notebook = ttk.Notebook(root)
        notebook.grid(sticky="nsew")
        loop_tab = ttk.Frame(notebook)
        autoclick_tab = ttk.Frame(notebook)
        notebook.add(loop_tab, text="点击流程")
        notebook.add(autoclick_tab, text="鼠标连点器")
        loop_tab.columnconfigure(0, weight=1)
        loop_tab.rowconfigure(0, weight=1)
        autoclick_tab.columnconfigure(0, weight=1)
        autoclick_tab.rowconfigure(0, weight=1)

        outer = ttk.Frame(loop_tab, padding=10)
        outer.grid(sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)  # 顶部步骤区域扩展

        # ══════════════════════════════════════════════════════════════════════
        # 顶部：两栏步骤列表
        # ══════════════════════════════════════════════════════════════════════
        top_frame = ttk.Frame(outer)
        top_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        top_frame.columnconfigure(0, weight=1)
        top_frame.columnconfigure(1, weight=1)
        top_frame.rowconfigure(0, weight=1)

        # 小循环1步骤列表
        self._build_loop_panel(top_frame, "loop1", "小循环 1", 0)
        # 小循环2步骤列表
        self._build_loop_panel(top_frame, "loop2", "小循环 2", 1)

        # ══════════════════════════════════════════════════════════════════════
        # 底部：循环控制板（融合小循环和大循环设置）
        # ══════════════════════════════════════════════════════════════════════
        ctrl_frame = ttk.LabelFrame(outer, text="循环控制板", padding=10)
        ctrl_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        # 第一行：小循环设置
        loop_row = ttk.Frame(ctrl_frame)
        loop_row.pack(fill="x", pady=(0, 8))

        # 小循环1设置
        ttk.Label(loop_row, text="小循环1:", font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Label(loop_row, text="运行").pack(side="left", padx=(4, 0))
        r1 = ttk.Entry(loop_row, textvariable=self.loop1_repeat_var, width=4)
        r1.pack(side="left", padx=(2, 0))
        ttk.Label(loop_row, text="次").pack(side="left")
        ttk.Label(loop_row, text="间隔").pack(side="left", padx=(8, 0))
        i1 = ttk.Entry(loop_row, textvariable=self.loop1_interval_var, width=4)
        i1.pack(side="left", padx=(2, 0))
        ttk.Label(loop_row, text="秒").pack(side="left")
        Tooltip(r1, "小循环1执行多少次")
        Tooltip(i1, "小循环1每次重复之间的间隔（仅当运行次数>1时生效）")

        ttk.Separator(loop_row, orient="vertical").pack(side="left", fill="y", padx=12)

        # 小循环2设置
        ttk.Label(loop_row, text="小循环2:", font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Label(loop_row, text="运行").pack(side="left", padx=(4, 0))
        r2 = ttk.Entry(loop_row, textvariable=self.loop2_repeat_var, width=4)
        r2.pack(side="left", padx=(2, 0))
        ttk.Label(loop_row, text="次").pack(side="left")
        ttk.Label(loop_row, text="间隔").pack(side="left", padx=(8, 0))
        i2 = ttk.Entry(loop_row, textvariable=self.loop2_interval_var, width=4)
        i2.pack(side="left", padx=(2, 0))
        ttk.Label(loop_row, text="秒").pack(side="left")
        Tooltip(r2, "小循环2执行多少次")
        Tooltip(i2, "小循环2每次重复之间的间隔（仅当运行次数>1时生效）")

        ttk.Separator(loop_row, orient="vertical").pack(side="left", fill="y", padx=12)

        # 切换间隔
        ttk.Label(loop_row, text="切换间隔:").pack(side="left")
        si = ttk.Entry(loop_row, textvariable=self.switch_interval_var, width=4)
        si.pack(side="left", padx=(2, 0))
        ttk.Label(loop_row, text="秒").pack(side="left")
        Tooltip(si, "小循环1和小循环2之间切换时的等待时间")

        # 第二行：执行顺序和模式
        order_row = ttk.Frame(ctrl_frame)
        order_row.pack(fill="x", pady=(0, 8))

        ttk.Label(order_row, text="执行顺序:").pack(side="left")
        order_combo = ttk.Combobox(order_row, textvariable=self.exec_order_var,
                                    values=("1→2", "2→1", "仅1", "仅2"),
                                    state="readonly", width=6)
        order_combo.pack(side="left", padx=(4, 16))
        Tooltip(order_combo, "1→2: 先小循环1后小循环2\n2→1: 先小循环2后小循环1\n仅1: 只执行小循环1\n仅2: 只执行小循环2")

        ttk.Label(order_row, text="执行模式:").pack(side="left")
        ttk.Radiobutton(order_row, text="顺序", value="sequential",
                        variable=self.exec_mode_var).pack(side="left", padx=(4, 0))
        ttk.Radiobutton(order_row, text="交替", value="alternate",
                        variable=self.exec_mode_var).pack(side="left", padx=(8, 0))
        Tooltip(order_row, "顺序: 小循环1全部完成 → 小循环2全部完成\n交替: 小循环1执行1次 → 小循环2执行1次 → 循环")

        ttk.Separator(order_row, orient="vertical").pack(side="left", fill="y", padx=12)

        ttk.Label(order_row, text="大循环次数:").pack(side="left")
        blc = ttk.Entry(order_row, textvariable=self.big_loop_count_var, width=4)
        blc.pack(side="left", padx=(4, 0))
        Tooltip(blc, "整个（小循环1→小循环2）执行多少轮")

        # 第三行：通用设置和按钮
        action_row = ttk.Frame(ctrl_frame)
        action_row.pack(fill="x")

        ttk.Label(action_row, text="开始延迟:").pack(side="left")
        de = ttk.Entry(action_row, textvariable=self.delay_var, width=4)
        de.pack(side="left", padx=(2, 0))
        ttk.Label(action_row, text="秒").pack(side="left")
        Tooltip(de, "按下开始后等待多少秒再执行")

        ttk.Checkbutton(action_row, text="最小化",
                        variable=self.minimize_var).pack(side="left", padx=(12, 0))

        ttk.Checkbutton(action_row, text="激活窗口:",
                        variable=self.use_selected_window_var).pack(side="left", padx=(8, 0))
        self._target_combo = ttk.Combobox(action_row, textvariable=self.target_window_var,
                                           state="readonly", width=28)
        self._target_combo.pack(side="left", padx=(4, 0))
        self._target_combo.bind("<<ComboboxSelected>>", self._on_target_selected)
        ttk.Button(action_row, text="⟳", width=2,
                   command=self.refresh_window_list).pack(side="left", padx=(2, 0))

        ttk.Separator(action_row, orient="vertical").pack(side="left", fill="y", padx=10)

        self._run_btn = tk.Button(
            action_row, text="▶ 开始", font=("Segoe UI", 10, "bold"),
            bg="#27ae60", fg="white", relief="flat", padx=12, pady=4,
            activebackground="#1e8449", activeforeground="white",
            command=self.start_action, cursor="hand2",
        )
        self._run_btn.pack(side="left", padx=(0, 6))

        self._stop_btn = tk.Button(
            action_row, text="■ 停止", font=("Segoe UI", 10),
            bg="#e67e22", fg="white", relief="flat", padx=12, pady=4,
            activebackground="#ca6f1e", activeforeground="white",
            command=self.stop_action, cursor="hand2", state="disabled",
        )
        self._stop_btn.pack(side="left")
        Tooltip(self._stop_btn, "运行中按 F6 可停止循环（窗口最小化时也可用）。")

        # ══════════════════════════════════════════════════════════════════════
        # 状态栏
        # ══════════════════════════════════════════════════════════════════════
        sb = tk.Frame(outer, bg="#ececec", relief="sunken", bd=1)
        sb.grid(row=2, column=0, sticky="ew")
        tk.Label(sb, textvariable=self.status_var, bg="#ececec",
                 anchor="w", font=("Segoe UI", 9), padx=8, pady=5).pack(fill="x")

        self._build_autoclick_tab(autoclick_tab)

    def _build_loop_panel(self, parent: ttk.Frame, loop_key: str, title: str, col: int) -> None:
        """Build a step list panel for one loop."""
        frame = ttk.LabelFrame(parent, text=title, padding=6)
        frame.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 4, 4 if col == 0 else 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        # 工具栏
        tb = ttk.Frame(frame)
        tb.pack(fill="x", pady=(0, 6))

        rec_btn = tk.Button(
            tb, text="⏺ 录制", font=("Segoe UI", 9, "bold"),
            bg="#c0392b", fg="white", relief="flat", padx=8, pady=3,
            activebackground="#a93226", activeforeground="white",
            command=lambda: self.start_click_recording(loop_key, append=False), cursor="hand2",
        )
        rec_btn.pack(side="left")
        Tooltip(rec_btn, f"录制新的点击步骤到{title}。按 F6 或 Esc 停止。")

        app_btn = tk.Button(
            tb, text="＋追加", font=("Segoe UI", 9),
            bg="#2471a3", fg="white", relief="flat", padx=8, pady=3,
            activebackground="#1a5276", activeforeground="white",
            command=lambda: self.start_click_recording(loop_key, append=True), cursor="hand2",
        )
        app_btn.pack(side="left", padx=(6, 0))
        Tooltip(app_btn, f"追加更多点击步骤到{title}。")

        ttk.Button(tb, text="保存", command=lambda: self.save_click_flow(loop_key)).pack(side="left", padx=(10, 0))
        ttk.Button(tb, text="加载", command=lambda: self.load_click_flow(loop_key)).pack(side="left", padx=(4, 0))
        ttk.Button(tb, text="清空", command=lambda: self.clear_flow(loop_key)).pack(side="left", padx=(4, 0))

        ttk.Label(tb, text="倒计时:", font=("Segoe UI", 8)).pack(side="left", padx=(10, 0))
        cd = ttk.Entry(tb, textvariable=self.countdown_var, width=3)
        cd.pack(side="left", padx=(2, 0))
        ttk.Label(tb, text="秒", font=("Segoe UI", 8)).pack(side="left")

        # 步骤列表（可滚动）
        canvas = tk.Canvas(frame, highlightthickness=0, bg="#f9f9f9")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        inner = ttk.Frame(canvas)
        canvas_win = canvas.create_window((0, 0), window=inner, anchor="nw")

        self._steps_canvases[loop_key] = canvas
        self._steps_inners[loop_key] = inner
        self._canvas_wins[loop_key] = canvas_win

        def _on_inner_resize(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_resize(e):
            canvas.itemconfig(canvas_win, width=e.width)

        inner.bind("<Configure>", _on_inner_resize)
        canvas.bind("<Configure>", _on_canvas_resize)

        on_wheel = lambda e, c=canvas: c.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", on_wheel)
        inner.bind("<MouseWheel>", on_wheel)

        # "添加步骤" 按钮
        add_btn = ttk.Button(
            inner, text="＋ 添加步骤",
            command=lambda: self.add_step_at(loop_key, len(self.flows[loop_key])),
        )
        add_btn.pack(pady=10, padx=10, fill="x")
        add_btn.bind("<MouseWheel>", on_wheel)
        self._add_btns[loop_key] = add_btn

    def _build_autoclick_tab(self, parent: ttk.Frame) -> None:
        outer = ttk.Frame(parent, padding=16)
        outer.grid(sticky="nsew")
        outer.columnconfigure(0, weight=1)

        settings = ttk.LabelFrame(outer, text="连点设置", padding=12)
        settings.grid(row=0, column=0, sticky="ew")

        ttk.Label(settings, text="点击次数:").grid(row=0, column=0, sticky="w")
        count_entry = ttk.Entry(settings, textvariable=self.autoclick_count_var, width=12)
        count_entry.grid(row=0, column=1, sticky="w", padx=(6, 18))
        Tooltip(count_entry, "总共点击多少次。")

        ttk.Label(settings, text="点击间隔(秒):").grid(row=0, column=2, sticky="w")
        interval_entry = ttk.Entry(settings, textvariable=self.autoclick_interval_var, width=12)
        interval_entry.grid(row=0, column=3, sticky="w", padx=(6, 0))
        Tooltip(interval_entry, "每次点击之间等待多久；数值越小速度越快。")

        hotkeys = ttk.LabelFrame(outer, text="快捷键", padding=12)
        hotkeys.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        self._autoclick_start_hotkey_btn = tk.Button(
            hotkeys, textvariable=self.autoclick_start_hotkey_var,
            font=("Segoe UI", 10), bg="#2471a3", fg="white",
            activebackground="#1f618d", activeforeground="white",
            relief="flat", padx=12, pady=5,
            command=lambda: self._begin_autoclick_hotkey_capture("start"),
            cursor="hand2",
        )
        self._autoclick_start_hotkey_btn.pack(side="left")

        self._autoclick_stop_hotkey_btn = tk.Button(
            hotkeys, textvariable=self.autoclick_stop_hotkey_var,
            font=("Segoe UI", 10), bg="#b03a2e", fg="white",
            activebackground="#943126", activeforeground="white",
            relief="flat", padx=12, pady=5,
            command=lambda: self._begin_autoclick_hotkey_capture("stop"),
            cursor="hand2",
        )
        self._autoclick_stop_hotkey_btn.pack(side="left", padx=(8, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))

        self._autoclick_start_btn = tk.Button(
            actions, text="▶ 开始连点", font=("Segoe UI", 11, "bold"),
            bg="#27ae60", fg="white", activebackground="#1e8449",
            activeforeground="white", relief="flat", padx=16, pady=6,
            command=self.start_autoclick, cursor="hand2",
        )
        self._autoclick_start_btn.pack(side="left")

        self._autoclick_stop_btn = tk.Button(
            actions, text="■ 停止连点", font=("Segoe UI", 11),
            bg="#e67e22", fg="white", activebackground="#ca6f1e",
            activeforeground="white", relief="flat", padx=16, pady=6,
            command=self.stop_autoclick, cursor="hand2", state="disabled",
        )
        self._autoclick_stop_btn.pack(side="left", padx=(8, 0))

        status = tk.Frame(outer, bg="#ececec", relief="sunken", bd=1)
        status.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        tk.Label(status, textvariable=self.autoclick_status_var, bg="#ececec",
                 anchor="w", font=("Segoe UI", 9), padx=8, pady=5).pack(fill="x")

    # ─── scroll helper ───────────────────────────────────────────────────────

    def _format_hotkey_name(self, key_name: str) -> str:
        return key_name.upper()

    def _refresh_autoclick_hotkey_labels(self) -> None:
        self.autoclick_start_hotkey_var.set(
            f"开始快捷键: {self._format_hotkey_name(self._autoclick_start_key)}"
        )
        self.autoclick_stop_hotkey_var.set(
            f"结束快捷键: {self._format_hotkey_name(self._autoclick_stop_key)}"
        )

    def _begin_autoclick_hotkey_capture(self, target: str) -> None:
        if self.autoclick_worker and self.autoclick_worker.is_alive():
            messagebox.showinfo("忙碌", "连点运行中不能修改快捷键。")
            return
        self._capturing_autoclick_hotkey = target
        if target == "start":
            self.autoclick_start_hotkey_var.set("开始快捷键: 请按键...")
        else:
            self.autoclick_stop_hotkey_var.set("结束快捷键: 请按键...")
        self.root.bind_all("<KeyPress>", self._capture_autoclick_hotkey)

    def _capture_autoclick_hotkey(self, event) -> str:
        target = self._capturing_autoclick_hotkey
        if not target:
            return "break"

        key_name = recorded_value_from_tk_event(event, combo_mode=False)
        if not key_name:
            return "break"

        try:
            vk = resolve_key_spec(key_name)[-1]
        except ValueError as e:
            self._refresh_autoclick_hotkey_labels()
            messagebox.showerror("快捷键无效", str(e))
            return "break"
        finally:
            self.root.unbind_all("<KeyPress>")
            self._capturing_autoclick_hotkey = None

        if (target == "start" and vk == self._autoclick_stop_vk) or (
            target == "stop" and vk == self._autoclick_start_vk
        ):
            self._refresh_autoclick_hotkey_labels()
            messagebox.showerror("快捷键无效", "开始和结束快捷键不能相同。")
            return "break"

        if target == "start":
            self._autoclick_start_key = key_name
            self._autoclick_start_vk = vk
            self.autoclick_start_hotkey_var.set(f"开始快捷键: {self._format_hotkey_name(key_name)}")
        else:
            self._autoclick_stop_key = key_name
            self._autoclick_stop_vk = vk
            self.autoclick_stop_hotkey_var.set(f"结束快捷键: {self._format_hotkey_name(key_name)}")
        self.autoclick_status_var.set("快捷键已更新。")
        return "break"

    def _start_autoclick_hotkey_monitor(self) -> None:
        self._autoclick_hotkey_monitor.set()
        self._autoclick_start_armed = bool(user32.GetAsyncKeyState(self._autoclick_start_vk) & KEY_PRESSED_MASK)
        self._autoclick_stop_armed = bool(user32.GetAsyncKeyState(self._autoclick_stop_vk) & KEY_PRESSED_MASK)
        self._autoclick_hotkey_thread = threading.Thread(
            target=self._watch_autoclick_hotkeys,
            daemon=True,
        )
        self._autoclick_hotkey_thread.start()

    def _watch_autoclick_hotkeys(self) -> None:
        while self._autoclick_hotkey_monitor.is_set():
            if self._capturing_autoclick_hotkey:
                time.sleep(0.03)
                continue

            start_pressed = bool(user32.GetAsyncKeyState(self._autoclick_start_vk) & KEY_PRESSED_MASK)
            stop_pressed = bool(user32.GetAsyncKeyState(self._autoclick_stop_vk) & KEY_PRESSED_MASK)

            if start_pressed and not self._autoclick_start_armed:
                self.root.after(0, self.start_autoclick)
            if stop_pressed and not self._autoclick_stop_armed:
                self.root.after(0, self.stop_autoclick)

            self._autoclick_start_armed = start_pressed
            self._autoclick_stop_armed = stop_pressed
            time.sleep(0.03)

    def _get_cursor_pos(self) -> tuple[int, int]:
        pt = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(pt.x), int(pt.y)

    def start_autoclick(self) -> None:
        if self.autoclick_worker and self.autoclick_worker.is_alive():
            self.autoclick_status_var.set("连点正在运行。")
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("忙碌", "点击流程正在运行，请先停止。")
            return
        if self.click_recorder.is_recording:
            messagebox.showinfo("忙碌", "正在录制中，请先停止录制。")
            return

        try:
            count = self._parse_int(self.autoclick_count_var.get(), "点击次数", 1)
            interval = self._parse_float(self.autoclick_interval_var.get(), "点击间隔", 0)
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
            return

        self.autoclick_stop_event = threading.Event()
        self._btn_state(self._autoclick_start_btn, False)
        self._btn_state(self._autoclick_stop_btn, True)
        self.autoclick_status_var.set("连点开始：会在当前鼠标位置点击。")
        self.autoclick_worker = threading.Thread(
            target=self._run_autoclick,
            args=(count, interval),
            daemon=True,
        )
        self.autoclick_worker.start()

    def stop_autoclick(self) -> None:
        if not (self.autoclick_worker and self.autoclick_worker.is_alive()):
            self._btn_state(self._autoclick_stop_btn, False)
            self._btn_state(self._autoclick_start_btn, True)
            self.autoclick_status_var.set("没有正在运行的连点任务。")
            return
        self.autoclick_stop_event.set()
        self._btn_state(self._autoclick_stop_btn, False)
        self.autoclick_status_var.set("正在停止连点...")

    def _run_autoclick(self, count: int, interval: float) -> None:
        started_at = time.monotonic()
        clicked = 0
        try:
            for index in range(count):
                raise_if_cancelled(self.autoclick_stop_event)
                x, y = self._get_cursor_pos()
                mouse_click_at(x, y, "left", stop_event=self.autoclick_stop_event)
                clicked += 1
                self.root.after(
                    0,
                    self.autoclick_status_var.set,
                    f"连点运行中：{clicked}/{count}，当前位置 ({x}, {y})",
                )
                if index < count - 1 and interval > 0:
                    sleep_with_cancel(interval, self.autoclick_stop_event)
        except ActionCancelled:
            self.root.after(0, self._finish_autoclick, False, clicked, count, started_at)
            return
        except Exception as e:
            self.root.after(0, self._finish_autoclick, False, clicked, count, started_at, str(e))
            return

        self.root.after(0, self._finish_autoclick, True, clicked, count, started_at)

    def _finish_autoclick(
        self,
        completed: bool,
        clicked: int,
        planned: int,
        started_at: float,
        error: str | None = None,
    ) -> None:
        self._btn_state(self._autoclick_start_btn, True)
        self._btn_state(self._autoclick_stop_btn, False)
        elapsed = max(0.0, time.monotonic() - started_at)
        if error:
            self.autoclick_status_var.set(f"连点失败：{error}；已点击 {clicked}/{planned}，耗时 {elapsed:.1f}s。")
            messagebox.showerror("连点失败", error)
        elif completed:
            self.autoclick_status_var.set(f"连点完成：已点击 {clicked}/{planned}，耗时 {elapsed:.1f}s。")
        else:
            self.autoclick_status_var.set(f"连点已停止：已点击 {clicked}/{planned}，耗时 {elapsed:.1f}s。")

    def _on_wheel(self, loop_key: str, event: tk.Event) -> None:
        self._steps_canvases[loop_key].yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ─── card management ────────────────────────────────────────────────────

    def _sync_cards(self, loop_key: str) -> None:
        """Keep StepCard list in sync with self.flows[loop_key]."""
        clicks = self.flows[loop_key]
        cards = self._step_cards[loop_key]
        inner = self._steps_inners[loop_key]
        add_btn = self._add_btns[loop_key]
        canvas = self._steps_canvases[loop_key]
        n = len(clicks)

        on_wheel = lambda e, c=canvas: c.yview_scroll(int(-1 * (e.delta / 120)), "units")

        # grow
        while len(cards) < n:
            idx = len(cards)
            card = StepCard(inner, idx, clicks[idx], self, loop_key, on_wheel=on_wheel)
            card.pack(fill="x", pady=(0, 4), before=add_btn)
            cards.append(card)

        # shrink
        while len(cards) > n:
            cards.pop().destroy()

        # refresh content
        for idx, (card, click) in enumerate(zip(cards, clicks)):
            card.pull(click, idx)

        self._step_errors[loop_key] = {}
        self._refresh_scroll(loop_key)

    def _refresh_scroll(self, loop_key: str) -> None:
        inner = self._steps_inners[loop_key]
        canvas = self._steps_canvases[loop_key]
        inner.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

    # ─── step CRUD ─────────────────────────────────────────────────────────

    def update_step_data(self, loop_key: str, index: int, data: dict) -> None:
        clicks = self.flows[loop_key]
        if 0 <= index < len(clicks):
            clicks[index] = self._normalize(data)

    def delete_step(self, loop_key: str, index: int) -> None:
        clicks = self.flows[loop_key]
        if 0 <= index < len(clicks):
            clicks.pop(index)
        self._sync_cards(loop_key)
        self.status_var.set(f"删除了步骤 {index + 1}。剩余 {len(clicks)} 个步骤。")

    def move_step(self, loop_key: str, index: int, offset: int) -> None:
        clicks = self.flows[loop_key]
        new_idx = index + offset
        if new_idx < 0 or new_idx >= len(clicks):
            return
        clicks[index], clicks[new_idx] = clicks[new_idx], clicks[index]
        self._sync_cards(loop_key)

    def add_step_at(self, loop_key: str, index: int) -> None:
        clicks = self.flows[loop_key]
        blank = {"x": 0, "y": 0, "button": "left", "delay": 0.0}
        clicks.insert(max(0, min(index, len(clicks))), blank)
        self._sync_cards(loop_key)
        canvas = self._steps_canvases[loop_key]
        self.root.after(50, lambda: canvas.yview_moveto(
            max(0.0, (index / max(len(clicks), 1)) - 0.1)
        ))
        self.status_var.set(f"添加了空白步骤 {index + 1}。")

    # ─── flow management ────────────────────────────────────────────────────

    def clear_flow(self, loop_key: str) -> None:
        if self.click_recorder.is_recording:
            if self.active_recording_loop != loop_key:
                messagebox.showinfo("忙碌", "正在录制中，请先停止当前录制。")
                return
            self._recording_cancelled = True
            self.click_recorder.stop()
        self.flows[loop_key].clear()
        self._step_errors[loop_key] = {}
        self._sync_cards(loop_key)
        label = "小循环1" if loop_key == "loop1" else "小循环2"
        self.status_var.set(f"{label} 已清空。")

    def _rebuild_loop_cards(self, loop_key: str) -> None:
        self._step_cards[loop_key].clear()
        self._step_errors[loop_key] = {}
        inner = self._steps_inners[loop_key]
        add_btn = self._add_btns[loop_key]
        for w in list(inner.winfo_children()):
            if w is not add_btn:
                w.destroy()
        self._sync_cards(loop_key)

    # ─── recording ──────────────────────────────────────────────────────────

    def start_click_recording(self, loop_key: str, append: bool = False) -> None:
        if self.click_recorder.is_recording:
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("忙碌", "正在运行中，请先停止。")
            return
        try:
            countdown = self._parse_int(self.countdown_var.get(), "倒计时", 0)
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
            return

        self.active_recording_loop = loop_key
        self._recording_append = append
        self._recording_cancelled = False
        self._recording_original_flow = list(self.flows[loop_key])
        self._recording_prefix = list(self.flows[loop_key]) if append else []
        if not append:
            self.flows[loop_key].clear()
            self._step_cards[loop_key].clear()
            self._step_errors[loop_key] = {}
            inner = self._steps_inners[loop_key]
            add_btn = self._add_btns[loop_key]
            for w in list(inner.winfo_children()):
                if w is not add_btn:
                    w.destroy()
            self._refresh_scroll(loop_key)

        self.click_recorder.recorded_clicks = self.flows[loop_key]

        self._btn_state(self._run_btn, False)
        self._btn_state(self._stop_btn, False)
        label = "小循环1" if loop_key == "loop1" else "小循环2"
        self.status_var.set(f"准备{'追加' if append else ''}录制 {label}…")
        self.root.title(f"Click Flow  —  🔴 录制中 ({label})")
        self.root.iconify()
        if countdown:
            self._show_countdown(countdown)
        else:
            self._begin_recording()

    def _show_countdown(self, remaining: int) -> None:
        if remaining <= 0:
            self._dismiss_countdown()
            self._begin_recording()
            return
        if self._countdown_window is None:
            w = tk.Toplevel(self.root)
            w.overrideredirect(True)
            w.attributes("-topmost", True)
            w.attributes("-alpha", 0.88)
            w.configure(bg="#1a1a2e")
            ww, wh = 220, 140
            sx = self.root.winfo_screenwidth() // 2 - ww // 2
            sy = self.root.winfo_screenheight() // 2 - wh // 2
            w.geometry(f"{ww}x{wh}+{sx}+{sy}")
            self._cd_lbl = tk.Label(w, text="", font=("Segoe UI", 52, "bold"),
                                    fg="#e94560", bg="#1a1a2e")
            self._cd_lbl.pack(expand=True)
            tk.Label(w, text="录制即将开始…",
                     font=("Segoe UI", 10), fg="#aaaaaa", bg="#1a1a2e"
                     ).pack(pady=(0, 10))
            self._countdown_window = w
        self._cd_lbl.configure(text=str(remaining))
        self.root.after(1000, self._show_countdown, remaining - 1)

    def _begin_recording(self) -> None:
        self._show_rec_overlay()
        self.click_recorder.start(
            on_click=lambda c: self.root.after(0, self._on_click_recorded, c),
            on_stop=lambda: self.root.after(0, self._on_recording_stopped),
            on_error=lambda m: self.root.after(0, self._on_recording_error, m),
        )

    def _show_rec_overlay(self) -> None:
        ov = tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.attributes("-alpha", 0.92)
        ov.configure(bg="#2d2d44")
        w, h = 260, 56
        x = self.root.winfo_screenwidth() - w - 16
        ov.geometry(f"{w}x{h}+{x}+16")
        top = tk.Frame(ov, bg="#2d2d44")
        top.pack(fill="x", padx=8, pady=(6, 0))
        tk.Label(top, text="⏺ 录制中", font=("Segoe UI", 11, "bold"),
                 fg="#e94560", bg="#2d2d44").pack(side="left")
        prefix_n = len(self._recording_prefix)
        self._recording_count_var = tk.StringVar(
            value=(f"  0 新 / {prefix_n} 总计"
                   if self._recording_append else "  0 点击")
        )
        tk.Label(top, textvariable=self._recording_count_var,
                 font=("Segoe UI", 10), fg="#ffffff", bg="#2d2d44"
                 ).pack(side="left", padx=(6, 0))
        tk.Label(ov, text="按 F6 或 Esc 停止录制",
                 font=("Segoe UI", 9), fg="#aaaaaa", bg="#2d2d44"
                 ).pack(anchor="w", padx=8, pady=(2, 6))
        self._recording_overlay = ov

    def _dismiss_rec_overlay(self) -> None:
        if self._recording_overlay:
            self._recording_overlay.destroy()
            self._recording_overlay = None
            self._recording_count_var = None

    def _dismiss_countdown(self) -> None:
        if self._countdown_window:
            self._countdown_window.destroy()
            self._countdown_window = None

    def _on_click_recorded(self, click: dict) -> None:
        loop_key = self.active_recording_loop
        if not loop_key:
            return

        new_n = len(self.click_recorder.recorded_clicks)
        total_idx = len(self._recording_prefix) + new_n - 1

        inner = self._steps_inners[loop_key]
        add_btn = self._add_btns[loop_key]
        canvas = self._steps_canvases[loop_key]
        on_wheel = lambda e, c=canvas: c.yview_scroll(int(-1 * (e.delta / 120)), "units")

        card = StepCard(inner, total_idx, click, self, loop_key, on_wheel=on_wheel)
        card.pack(fill="x", pady=(0, 4), before=add_btn)
        self._step_cards[loop_key].append(card)
        self._refresh_scroll(loop_key)
        canvas.yview_moveto(1.0)

        if self._recording_count_var:
            total = len(self._recording_prefix) + new_n
            if self._recording_append:
                self._recording_count_var.set(f"  {new_n} 新 / {total} 总计")
            else:
                self._recording_count_var.set(f"  {new_n} 点击")

    def _on_recording_stopped(self) -> None:
        loop_key = self.active_recording_loop
        if not loop_key:
            return

        self._dismiss_rec_overlay()
        self._dismiss_countdown()
        cancelled = self._recording_cancelled
        if cancelled:
            new_clicks: list[dict] = []
            self.click_recorder.recorded_clicks = self.flows[loop_key]
        else:
            new_clicks = [self._normalize(c) for c in self.click_recorder.recorded_clicks]
            combined = (self._recording_prefix + new_clicks
                        if self._recording_append else new_clicks)
            self.flows[loop_key] = combined
            self.click_recorder.recorded_clicks = self.flows[loop_key]

        # Full rebuild
        self._rebuild_loop_cards(loop_key)

        self._recording_prefix = []
        self._recording_append = False
        self._recording_cancelled = False
        self._recording_original_flow = []
        self.active_recording_loop = None
        self._btn_state(self._run_btn, True)
        self._btn_state(self._stop_btn, False)
        self.root.deiconify()
        self.root.lift()
        self.root.title("Click Flow - 嵌套循环")
        label = "小循环1" if loop_key == "loop1" else "小循环2"
        n = len(self.flows[loop_key])
        if cancelled:
            self.status_var.set(f"{label} 录制已取消，共 {n} 个步骤。")
        else:
            self.status_var.set(f"{label} 录制完成 — {len(new_clicks)} 新步骤，共 {n} 个。")

    def _on_recording_error(self, message: str) -> None:
        loop_key = self.active_recording_loop
        self._dismiss_rec_overlay()
        self._dismiss_countdown()
        if loop_key:
            if not self._recording_cancelled:
                self.flows[loop_key] = [dict(c) for c in self._recording_original_flow]
            self.click_recorder.recorded_clicks = self.flows[loop_key]
            self._rebuild_loop_cards(loop_key)

        self._recording_prefix = []
        self._recording_append = False
        self._recording_cancelled = False
        self._recording_original_flow = []
        self.active_recording_loop = None
        self._btn_state(self._run_btn, True)
        self._btn_state(self._stop_btn, False)
        self.root.deiconify()
        self.root.lift()
        self.root.title("Click Flow - 嵌套循环")
        self.status_var.set(f"录制失败：{message}")
        messagebox.showerror("录制失败", message)

    # ─── save / load ────────────────────────────────────────────────────────

    def save_click_flow(self, loop_key: str) -> None:
        label = "小循环1" if loop_key == "loop1" else "小循环2"
        try:
            clicks = self._validated_flow(loop_key)
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
            return
        if not clicks:
            messagebox.showinfo("无内容", f"{label} 没有步骤可保存。")
            return
        path = filedialog.asksaveasfilename(
            title=f"保存 {label}",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(clicks, fh, indent=2, ensure_ascii=False)
            self.status_var.set(f"已保存 {len(clicks)} 步骤 → {os.path.basename(path)}")
        except OSError as e:
            messagebox.showerror("保存失败", str(e))

    def load_click_flow(self, loop_key: str) -> None:
        label = "小循环1" if loop_key == "loop1" else "小循环2"
        path = filedialog.askopenfilename(
            title=f"加载 {label}",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            normalized = self._normalize_list(data)
            self.flows[loop_key] = normalized
            self._step_cards[loop_key].clear()
            self._step_errors[loop_key] = {}
            inner = self._steps_inners[loop_key]
            add_btn = self._add_btns[loop_key]
            for w in list(inner.winfo_children()):
                if w is not add_btn:
                    w.destroy()
            self._sync_cards(loop_key)
            self.status_var.set(f"已加载 {len(normalized)} 步骤 ← {os.path.basename(path)}")
        except (OSError, json.JSONDecodeError, ValueError) as e:
            messagebox.showerror("加载失败", str(e))

    # ─── normalisation ───────────────────────────────────────────────────────

    def _normalize(self, item: object) -> dict:
        if not isinstance(item, dict):
            raise ValueError("无效的步骤数据。")
        if not all(k in item for k in ("x", "y", "button", "delay")):
            raise ValueError("步骤数据缺少必要字段。")
        btn = str(item["button"]).strip().lower()
        if btn not in {"left", "right", "middle"}:
            raise ValueError("按键必须是 left / right / middle。")
        try:
            x = int(item["x"])
            y = int(item["y"])
            d = float(item["delay"])
        except (TypeError, ValueError) as e:
            raise ValueError("坐标和延迟必须是数字。") from e
        if d < 0:
            raise ValueError("延迟不能为负数。")
        return {"x": x, "y": y, "button": btn, "delay": round(d, 3)}

    def _normalize_list(self, data: object) -> list[dict]:
        if not isinstance(data, list) or not data:
            raise ValueError("文件不包含有效的步骤列表。")
        return [self._normalize(item) for item in data]

    # ─── window list ────────────────────────────────────────────────────────

    def _win_label(self, w: dict) -> str:
        return f"{w['title']} [{w['process_name']}]"

    def refresh_window_list(self) -> None:
        prev = self._get_selected_hwnd()
        windows = [
            w for w in list_visible_windows()
            if not (int(w["pid"]) == os.getpid()
                    and str(w["title"]) == self.root.title())
        ]
        self.window_targets = windows
        self._target_combo["values"] = [self._win_label(w) for w in windows]
        if not windows:
            self.target_window_var.set("")
            return
        if prev:
            for i, w in enumerate(windows):
                if int(w["hwnd"]) == prev:
                    self._target_combo.current(i)
                    return
        self.target_window_var.set("")

    def _on_target_selected(self, _=None) -> None:
        if self._target_combo.current() >= 0:
            self.use_selected_window_var.set(True)

    def _get_selected_hwnd(self) -> int | None:
        i = self._target_combo.current()
        if i < 0 or i >= len(self.window_targets):
            return None
        return int(self.window_targets[i]["hwnd"])

    # ─── parse helpers ───────────────────────────────────────────────────────

    def _parse_float(self, raw: str, name: str, minimum: float = 0.0) -> float:
        t = raw.strip()
        if not t:
            raise ValueError(f"{name} 不能为空。")
        try:
            v = float(t)
        except ValueError as e:
            raise ValueError(f"{name} 必须是数字。") from e
        if v < minimum:
            raise ValueError(f"{name} 必须 ≥ {minimum}。")
        return v

    def _parse_int(self, raw: str, name: str, minimum: int = 1) -> int:
        t = raw.strip()
        if not t:
            raise ValueError(f"{name} 不能为空。")
        try:
            v = int(t)
        except ValueError as e:
            raise ValueError(f"{name} 必须是整数。") from e
        if v < minimum:
            raise ValueError(f"{name} 必须 ≥ {minimum}。")
        return v

    # ─── run / stop ─────────────────────────────────────────────────────────

    def start_action(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("忙碌", "正在运行中。")
            return
        if self.click_recorder.is_recording:
            messagebox.showinfo("忙碌", "正在录制中。")
            return

        # 验证输入
        try:
            delay = self._parse_float(self.delay_var.get(), "开始延迟", 0)
            big_loop_count = self._parse_int(self.big_loop_count_var.get(), "大循环次数", 1)
            loop1_repeat = self._parse_int(self.loop1_repeat_var.get(), "小循环1重复次数", 1)
            loop1_interval = self._parse_float(self.loop1_interval_var.get(), "小循环1间隔", 0)
            loop2_repeat = self._parse_int(self.loop2_repeat_var.get(), "小循环2重复次数", 1)
            loop2_interval = self._parse_float(self.loop2_interval_var.get(), "小循环2间隔", 0)
            switch_interval = self._parse_float(self.switch_interval_var.get(), "切换间隔", 0)
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
            return

        exec_order = self.exec_order_var.get()
        exec_mode = self.exec_mode_var.get()

        try:
            if exec_order in ("1→2", "2→1"):
                loop1_clicks = self._validated_flow("loop1")
                loop2_clicks = self._validated_flow("loop2")
            elif exec_order == "仅1":
                loop1_clicks = self._validated_flow("loop1")
                loop2_clicks = []
            elif exec_order == "仅2":
                loop1_clicks = []
                loop2_clicks = self._validated_flow("loop2")
            else:
                raise ValueError("执行顺序无效。")
        except ValueError as e:
            messagebox.showerror("输入错误", str(e))
            return

        # 根据执行顺序验证
        if exec_order in ("1→2", "2→1"):
            if not loop1_clicks and not loop2_clicks:
                messagebox.showinfo("无步骤", "请先录制或加载至少一个小循环的步骤。")
                return
        elif exec_order == "仅1":
            if not loop1_clicks:
                messagebox.showinfo("无步骤", "请先录制或加载小循环1的步骤。")
                return
        elif exec_order == "仅2":
            if not loop2_clicks:
                messagebox.showinfo("无步骤", "请先录制或加载小循环2的步骤。")
                return

        target_hwnd = None
        if self.use_selected_window_var.get():
            target_hwnd = self._get_selected_hwnd()
            if not target_hwnd:
                messagebox.showerror("错误", "请选择目标窗口或取消勾选'激活窗口'。")
                return

        req = {
            "delay": delay,
            "minimize": self.minimize_var.get(),
            "target_hwnd": target_hwnd,
            "big_loop_count": big_loop_count,
            "loop1_clicks": [dict(c) for c in loop1_clicks],
            "loop1_repeat": loop1_repeat,
            "loop1_interval": loop1_interval,
            "loop2_clicks": [dict(c) for c in loop2_clicks],
            "loop2_repeat": loop2_repeat,
            "loop2_interval": loop2_interval,
            "exec_order": exec_order,
            "exec_mode": exec_mode,
            "switch_interval": switch_interval,
        }

        self.stop_event = threading.Event()
        self._btn_state(self._run_btn, False)
        self._btn_state(self._stop_btn, True)
        self.root.title("Click Flow  —  ▶ 运行中")
        self.status_var.set("开始运行，请切换到目标窗口。")
        if req["minimize"]:
            self.root.iconify()
        self.worker = threading.Thread(target=self._exec_big_loop, args=(req,), daemon=True)
        self._start_stop_hotkey_monitor()
        self.worker.start()

    def stop_action(self) -> None:
        if not (self.worker and self.worker.is_alive()):
            self._stop_stop_hotkey_monitor()
            self._btn_state(self._stop_btn, False)
            self.status_var.set("没有正在运行的任务。")
            return
        self.stop_event.set()
        self._stop_stop_hotkey_monitor()
        self._btn_state(self._stop_btn, False)
        self.status_var.set("正在停止…")

    # ─── worker thread ──────────────────────────────────────────────────────

    def _exec_big_loop(self, req: dict) -> None:
        stats = {
            "started_at": time.monotonic(),
            "big_loops_completed": 0,
            "big_loops_total": int(req.get("big_loop_count", 0) or 0),
            "loop_runs": {"小循环1": 0, "小循环2": 0},
            "completed_clicks": 0,
            "planned_clicks": 0,
        }
        try:
            # 开始延迟
            if req["delay"]:
                sleep_with_cancel(float(req["delay"]), self.stop_event)

            # 激活目标窗口
            hwnd = int(req.get("target_hwnd") or 0)
            if hwnd:
                raise_if_cancelled(self.stop_event)
                if not activate_window(hwnd):
                    raise ValueError("无法激活目标窗口。")
                sleep_with_cancel(0.15, self.stop_event)

            big_loop_count = int(req["big_loop_count"])
            loop1_clicks = req["loop1_clicks"]
            loop1_repeat = int(req["loop1_repeat"])
            loop1_interval = float(req["loop1_interval"])
            loop2_clicks = req["loop2_clicks"]
            loop2_repeat = int(req["loop2_repeat"])
            loop2_interval = float(req["loop2_interval"])
            exec_order = req["exec_order"]
            exec_mode = req["exec_mode"]
            switch_interval = float(req["switch_interval"])

            # 根据执行顺序确定循环列表
            if exec_order == "1→2":
                loops = [
                    ("小循环1", loop1_clicks, loop1_repeat, loop1_interval),
                    ("小循环2", loop2_clicks, loop2_repeat, loop2_interval),
                ]
            elif exec_order == "2→1":
                loops = [
                    ("小循环2", loop2_clicks, loop2_repeat, loop2_interval),
                    ("小循环1", loop1_clicks, loop1_repeat, loop1_interval),
                ]
            elif exec_order == "仅1":
                loops = [
                    ("小循环1", loop1_clicks, loop1_repeat, loop1_interval),
                ]
            elif exec_order == "仅2":
                loops = [
                    ("小循环2", loop2_clicks, loop2_repeat, loop2_interval),
                ]
            else:
                loops = []

            # 过滤掉没有步骤的循环
            loops = [(name, clicks, repeat, interval) for name, clicks, repeat, interval in loops if clicks]
            stats["planned_clicks"] = big_loop_count * sum(len(clicks) * repeat for _name, clicks, repeat, _interval in loops)

            for big_i in range(big_loop_count):
                raise_if_cancelled(self.stop_event)
                self._set_status(f"大循环 {big_i + 1}/{big_loop_count}")

                if exec_mode == "sequential":
                    # 顺序执行：每个小循环全部完成后再执行下一个
                    for loop_idx, (name, clicks, repeat, interval) in enumerate(loops):
                        for i in range(repeat):
                            raise_if_cancelled(self.stop_event)
                            self._set_status(f"大循环 {big_i + 1}/{big_loop_count} — {name} 第{i + 1}/{repeat}次")
                            run_click_flow(
                                clicks,
                                repeat=1,
                                speed=1.0,
                                use_delays=True,
                                fixed_interval=0,
                                cycle_interval=0,
                                stop_event=self.stop_event,
                            )
                            stats["completed_clicks"] += len(clicks)
                            stats["loop_runs"][name] = stats["loop_runs"].get(name, 0) + 1
                            if i < repeat - 1 and interval > 0:
                                sleep_with_cancel(interval, self.stop_event)
                        # 循环间切换间隔
                        if loop_idx < len(loops) - 1 and switch_interval > 0:
                            self._set_status(f"切换间隔等待 {switch_interval}秒...")
                            sleep_with_cancel(switch_interval, self.stop_event)

                elif exec_mode == "alternate":
                    # 交替执行：小循环1执行1次 → 小循环2执行1次 → 循环
                    if len(loops) >= 2:
                        # 构建交替执行序列
                        exec_sequence = []
                        max_repeat = max(loops[0][2], loops[1][2])
                        for i in range(max_repeat):
                            for name, clicks, repeat, interval in loops:
                                if i < repeat:
                                    exec_sequence.append((name, clicks, i + 1, repeat, interval))

                        # 执行序列
                        for seq_idx, (name, clicks, current, total, interval) in enumerate(exec_sequence):
                            raise_if_cancelled(self.stop_event)
                            self._set_status(f"大循环 {big_i + 1}/{big_loop_count} — {name} 第{current}/{total}次")
                            run_click_flow(
                                clicks,
                                repeat=1,
                                speed=1.0,
                                use_delays=True,
                                fixed_interval=0,
                                cycle_interval=0,
                                stop_event=self.stop_event,
                            )
                            stats["completed_clicks"] += len(clicks)
                            stats["loop_runs"][name] = stats["loop_runs"].get(name, 0) + 1
                            if seq_idx < len(exec_sequence) - 1:
                                next_name = exec_sequence[seq_idx + 1][0]
                                wait = switch_interval if next_name != name else interval
                                if wait > 0:
                                    sleep_with_cancel(wait, self.stop_event)
                    else:
                        # 只有一个循环时，按顺序执行
                        for name, clicks, repeat, interval in loops:
                            for i in range(repeat):
                                raise_if_cancelled(self.stop_event)
                                self._set_status(f"大循环 {big_i + 1}/{big_loop_count} — {name} 第{i + 1}/{repeat}次")
                                run_click_flow(
                                    clicks,
                                    repeat=1,
                                    speed=1.0,
                                    use_delays=True,
                                    fixed_interval=0,
                                    cycle_interval=0,
                                    stop_event=self.stop_event,
                                )
                                stats["completed_clicks"] += len(clicks)
                                stats["loop_runs"][name] = stats["loop_runs"].get(name, 0) + 1
                                if i < repeat - 1 and interval > 0:
                                    sleep_with_cancel(interval, self.stop_event)
                stats["big_loops_completed"] += 1

        except ActionCancelled as e:
            self.root.after(0, self._finish, True, str(e), False, stats)
            return
        except (ValueError, OSError) as e:
            self.root.after(0, self._finish, False, str(e), True, stats)
            return
        except Exception as e:
            self.root.after(0, self._finish, False, f"意外错误: {e}", True, stats)
            return

        self.root.after(0, self._finish, True, "全部完成！", False, stats)

    def _set_status(self, msg: str) -> None:
        self.root.after(0, self.status_var.set, msg)

    def _format_run_stats(self, message: str, stats: dict | None) -> str:
        if not stats:
            return message

        elapsed = max(0.0, time.monotonic() - float(stats.get("started_at", time.monotonic())))
        loop_runs = stats.get("loop_runs", {})
        loop1_runs = int(loop_runs.get("小循环1", 0))
        loop2_runs = int(loop_runs.get("小循环2", 0))
        completed_clicks = int(stats.get("completed_clicks", 0))
        planned_clicks = int(stats.get("planned_clicks", 0))
        big_done = int(stats.get("big_loops_completed", 0))
        big_total = int(stats.get("big_loops_total", 0))

        return (
            f"{message} 统计：耗时 {elapsed:.1f}s；"
            f"大循环 {big_done}/{big_total}；"
            f"小循环1 {loop1_runs} 次，小循环2 {loop2_runs} 次；"
            f"完成点击 {completed_clicks}/{planned_clicks}。"
        )

    def _finish(self, success: bool, message: str, show_err: bool, stats: dict | None = None) -> None:
        self._stop_stop_hotkey_monitor()
        self._btn_state(self._run_btn, True)
        self._btn_state(self._stop_btn, False)
        self.root.deiconify()
        self.root.lift()
        self.root.title("Click Flow - 嵌套循环")
        self.status_var.set(self._format_run_stats(message, stats))
        if not success and show_err:
            messagebox.showerror("执行失败", message)


# ─── entry point ─────────────────────────────────────────────────────────────

def main() -> int:
    root = tk.Tk()
    ClickFlowApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
