import os
import shutil
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

# ---------------- Configuration ----------------
DEFAULT_FRAME_SIZE = 768
ZOOM_STEP = 1.12
MIN_SCALE = 0.02
MAX_SCALE = 30.0
SUGGEST_THRESHOLD = 2                 # show suggestions when a part is used >= 2 times
HISTORY_FILE = "suggest_history.txt"  # semicolon-separated: tag;count
GLOBAL_WORDS_FILE = "global_words.txt"
SNAP_TOL = 10                         # px; snap edges to frame when dragging

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


# ---------------- Viewport (canvas + interactions) ----------------
class ImageViewport(ttk.Frame):
    def __init__(self, master, frame_size_getter, no_image_click_callback=None):
        super().__init__(master)
        self.get_frame_size = frame_size_getter
        self.no_image_click_callback = no_image_click_callback

        self.canvas = tk.Canvas(self, bg="#111", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # Image state
        self.img_pil = None
        self.img_disp = None
        self.tk_img = None
        self.img_id = None

        # Transform (scale + translation)
        self.S = 1.0
        self.dx = 0.0
        self.dy = 0.0

        # Dragging
        self._dragging = False
        self._drag_start = (0, 0)
        self._start_dxdy = (0.0, 0.0)

        # Overlay
        self.overlay_ids = []

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", self._on_configure)

        # Cross-platform mouse wheel binding
        self._bind_wheel_events()

    # ---- Helpers ----
    def _canvas_size(self):
        w = max(50, int(self.canvas.winfo_width()))
        h = max(50, int(self.canvas.winfo_height()))
        return w, h

    def _frame_rect(self):
        frame_size = self.get_frame_size()
        cw, ch = self._canvas_size()
        L = (cw - frame_size) / 2
        T = (ch - frame_size) / 2
        return L, T, L + frame_size, T + frame_size

    # ---- Image handling ----
    def set_image(self, pil_image):
        self.img_pil = pil_image.convert("RGBA")
        iw, ih = self.img_pil.size
        cw, ch = self._canvas_size()
        fit = min(cw / iw, ch / ih)
        fit = max(MIN_SCALE, min(MAX_SCALE, fit))
        self.S = fit
        self.dx = (cw - iw * self.S) / 2.0
        self.dy = (ch - ih * self.S) / 2.0
        self._render_image()
        self._draw_overlay()

    def _render_image(self):
        if self.img_pil is None:
            return
        disp_w = max(1, int(round(self.img_pil.width * self.S)))
        disp_h = max(1, int(round(self.img_pil.height * self.S)))
        self.img_disp = self.img_pil.resize((disp_w, disp_h), Image.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(self.img_disp)
        if self.img_id is None:
            self.img_id = self.canvas.create_image(self.dx, self.dy, image=self.tk_img, anchor="nw", tags="image")
        else:
            self.canvas.itemconfigure(self.img_id, image=self.tk_img)
            self.canvas.coords(self.img_id, self.dx, self.dy)
        for oid in self.overlay_ids:
            self.canvas.tag_raise(oid)

    def _draw_overlay(self):
        # Clear old overlay
        for oid in self.overlay_ids:
            self.canvas.delete(oid)
        self.overlay_ids = []

        L, T, R, B = self._frame_rect()
        cw, ch = self._canvas_size()

        # Dim outside the frame using stippled rectangles (≈50% opacity)
        self.overlay_ids.append(
            self.canvas.create_rectangle(0, 0, cw, T, fill="#000000", outline="", stipple="gray50")
        )
        self.overlay_ids.append(
            self.canvas.create_rectangle(0, T, L, B, fill="#000000", outline="", stipple="gray50")
        )
        self.overlay_ids.append(
            self.canvas.create_rectangle(R, T, cw, B, fill="#000000", outline="", stipple="gray50")
        )
        self.overlay_ids.append(
            self.canvas.create_rectangle(0, B, cw, ch, fill="#000000", outline="", stipple="gray50")
        )

        # Frame outline
        self.overlay_ids.append(self.canvas.create_rectangle(L, T, R, B, outline="#6aa3ff", width=2))

        # Corner ticks
        tick = 18
        for (x, y, dx, dy) in [
            (L, T, +tick, 0), (L, T, 0, +tick),
            (R, T, -tick, 0), (R, T, 0, +tick),
            (L, B, +tick, 0), (L, B, 0, -tick),
            (R, B, -tick, 0), (R, B, 0, -tick),
        ]:
            self.overlay_ids.append(self.canvas.create_line(x, y, x + dx, y + dy, fill="#6aa3ff", width=2))

    # ---- Mouse interactions ----
    def _on_press(self, event):
        if self.img_pil is None:
            if callable(self.no_image_click_callback):
                self.no_image_click_callback()
            return
        self._dragging = True
        self._drag_start = (event.x, event.y)
        self._start_dxdy = (self.dx, self.dy)
        self.canvas.focus_set()

    def _on_drag(self, event):
        if not self._dragging:
            return
        sx, sy = self._drag_start
        self.dx = self._start_dxdy[0] + (event.x - sx)
        self.dy = self._start_dxdy[1] + (event.y - sy)
        self._apply_snap_to_frame()
        self._render_image()

    def _on_release(self, _):
        self._dragging = False

    # ---- Cross-platform wheel bindings ----
    def _bind_wheel_events(self):
        plat = sys.platform
        if plat == "darwin":
            self.canvas.bind("<MouseWheel>", self._on_wheel_darwin)
        elif plat.startswith("linux"):
            self.canvas.bind("<Button-4>", lambda e: self._on_wheel_linux(+1, e))
            self.canvas.bind("<Button-5>", lambda e: self._on_wheel_linux(-1, e))
        else:
            self.canvas.bind("<MouseWheel>", self._on_wheel_windows)

    def _ctrl_held(self, event):
        return (event.state & 0x0004) != 0

    def _on_wheel_windows(self, event):
        if self.img_pil is None:
            return
        steps = event.delta / 120.0
        if steps == 0:
            return
        base = ZOOM_STEP ** (0.25 if self._ctrl_held(event) else 1.0)
        self.zoom_at(event.x, event.y, base ** steps)

    def _on_wheel_darwin(self, event):
        if self.img_pil is None:
            return
        steps = 1 if event.delta > 0 else -1
        base = ZOOM_STEP ** (0.25 if self._ctrl_held(event) else 1.0)
        self.zoom_at(event.x, event.y, base ** steps)

    def _on_wheel_linux(self, direction, event):
        if self.img_pil is None:
            return
        steps = direction  # +1 up, -1 down
        base = ZOOM_STEP ** (0.25 if self._ctrl_held(event) else 1.0)
        self.zoom_at(event.x, event.y, base ** steps)

    # ---- Public controls ----
    def zoom_in(self, fine=False):
        cw, ch = self._canvas_size()
        factor = ZOOM_STEP ** (0.25 if fine else 1.0)
        self.zoom_at(cw / 2, ch / 2, factor)

    def zoom_out(self, fine=False):
        cw, ch = self._canvas_size()
        factor = ZOOM_STEP ** (0.25 if fine else 1.0)
        self.zoom_at(cw / 2, ch / 2, 1.0 / factor)

    def fit_full(self):
        """Fit the entire image inside the square frame (not the window)."""
        if self.img_pil is None:
            return
        iw, ih = self.img_pil.size
        frame_size = self.get_frame_size()
        fit = min(frame_size / iw, frame_size / ih)
        fit = max(MIN_SCALE, min(MAX_SCALE, fit))
        self.S = fit
        fL, fT, fR, fB = self._frame_rect()
        fCx = (fL + fR) / 2.0
        fCy = (fT + fB) / 2.0
        self.dx = fCx - (iw * self.S) / 2.0
        self.dy = fCy - (ih * self.S) / 2.0
        self._render_image()

    def fit_cover_frame(self):
        """Scale so the frame is fully covered by the image (may crop)."""
        if self.img_pil is None:
            return
        frame_size = self.get_frame_size()
        iw, ih = self.img_pil.size
        cover = max(frame_size / iw, frame_size / ih)
        self.S = max(MIN_SCALE, min(MAX_SCALE, cover))
        fL, fT, fR, fB = self._frame_rect()
        fCx = (fL + fR) / 2.0
        fCy = (fT + fB) / 2.0
        self.dx = fCx - (iw * self.S) / 2.0
        self.dy = fCy - (ih * self.S) / 2.0
        self._render_image()

    def zoom_at(self, cx, cy, factor):
        if self.img_pil is None:
            return
        old_S = self.S
        new_S = max(MIN_SCALE, min(MAX_SCALE, old_S * factor))
        factor = new_S / old_S
        if abs(factor - 1.0) < 1e-6:
            return
        u = (cx - self.dx) / old_S
        v = (cy - self.dy) / old_S
        self.S = new_S
        self.dx = cx - u * self.S
        self.dy = cy - v * self.S
        self._render_image()

    def move_image(self, dx, dy):
        self.dx += dx
        self.dy += dy
        self._render_image()

    # ---- Configure/Redraw ----
    def _on_configure(self, event):
        self._redraw()

    def _redraw(self):
        self._draw_overlay()
        self._render_image()

    # ---- Drag snapping helper ----
    def _apply_snap_to_frame(self):
        if self.img_pil is None:
            return
        L, T, R, B = self._frame_rect()
        w = self.img_pil.width * self.S
        h = self.img_pil.height * self.S
        left = self.dx
        top = self.dy
        right = self.dx + w
        bottom = self.dy + h
        if abs(left - L) <= SNAP_TOL:
            self.dx = L
        if abs(right - R) <= SNAP_TOL:
            self.dx = R - w
        if abs(top - T) <= SNAP_TOL:
            self.dy = T
        if abs(bottom - B) <= SNAP_TOL:
            self.dy = B - h

    # ---- Crop result (RGB) ----
    def get_crop_result_rgb(self):
        """
        Return an RGB PIL.Image of size (frame_size, frame_size) where the
        area of the source image that falls within the frame is pasted.
        Any area outside the source image becomes black.
        """
        if self.img_pil is None:
            return None

        frame_size = self.get_frame_size()
        fL, fT, fR, fB = self._frame_rect()

        left_img   = (fL - self.dx) / self.S
        top_img    = (fT - self.dy) / self.S
        right_img  = (fR - self.dx) / self.S
        bottom_img = (fB - self.dy) / self.S

        iw, ih = self.img_pil.size
        inter_left   = max(0, left_img)
        inter_top    = max(0, top_img)
        inter_right  = min(iw, right_img)
        inter_bottom = min(ih, bottom_img)

        out = Image.new("RGB", (frame_size, frame_size), (0, 0, 0))

        if inter_right > inter_left and inter_bottom > inter_top:
            crop = self.img_pil.crop((
                int(inter_left),
                int(inter_top),
                int(inter_right),
                int(inter_bottom)
            )).convert("RGB")

            interL_canvas = inter_left * self.S + self.dx
            interT_canvas = inter_top * self.S + self.dy

            dest_x = int(round(interL_canvas - fL))
            dest_y = int(round(interT_canvas - fT))

            inter_w_canvas = (inter_right - inter_left) * self.S
            inter_h_canvas = (inter_bottom - inter_top) * self.S
            target_w = max(1, int(round(inter_w_canvas)))
            target_h = max(1, int(round(inter_h_canvas)))

            if crop.size != (target_w, target_h):
                crop = crop.resize((target_w, target_h), Image.LANCZOS)

            out.paste(crop, (dest_x, dest_y))

        return out


# ---------------- Main app ----------------
class ImageCropperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Square Cropper — Selectable Frame Size")
        self.geometry(f"{DEFAULT_FRAME_SIZE + 900}x{DEFAULT_FRAME_SIZE + 520}")
        self.minsize(DEFAULT_FRAME_SIZE + 650, DEFAULT_FRAME_SIZE + 380)

        # State
        self.images = []
        self.idx = -1
        self.frame_size_var = tk.IntVar(value=DEFAULT_FRAME_SIZE)
        self.tag_counts = {}

        # Paths
        self.app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.history_path = os.path.join(self.app_dir, HISTORY_FILE)
        self.global_words_path = os.path.join(self.app_dir, GLOBAL_WORDS_FILE)

        # Paned layout (reliable 67/33 split)
        self.panes = tk.PanedWindow(self, orient="horizontal", sashrelief="flat", sashwidth=6)
        self.panes.pack(fill="both", expand=True)

        self.left_wrap = ttk.Frame(self.panes)
        self.right_wrap = ttk.Frame(self.panes)
        self.panes.add(self.left_wrap)
        self.panes.add(self.right_wrap)
        try:
            self.panes.paneconfigure(self.left_wrap, minsize=400)
            self.panes.paneconfigure(self.right_wrap, minsize=260)
        except Exception:
            pass

        # Left: viewport
        self.left_wrap.rowconfigure(0, weight=1)
        self.left_wrap.columnconfigure(0, weight=1)
        self.viewport = ImageViewport(
            self.left_wrap,
            self.get_frame_size,
            no_image_click_callback=self.choose_files
        )
        self.viewport.grid(row=0, column=0, sticky="nsew", padx=(14, 10), pady=(14, 8))

        # Bind arrow keys to the CANVAS only (so Text fields keep their arrows)
        self.viewport.canvas.bind("<Left>",  lambda e: self.viewport.move_image(-1, 0))
        self.viewport.canvas.bind("<Right>", lambda e: self.viewport.move_image(1, 0))
        self.viewport.canvas.bind("<Up>",    lambda e: self.viewport.move_image(0, -1))
        self.viewport.canvas.bind("<Down>",  lambda e: self.viewport.move_image(0, 1))

        # Right: sidebar
        side = ttk.Frame(self.right_wrap)
        side.pack(fill="both", expand=True, padx=(0, 14), pady=(14, 8))
        side.columnconfigure(0, weight=1)

        ttk.Label(side, text="Frame size").grid(row=0, column=0, sticky="w")
        size_menu = ttk.OptionMenu(side, self.frame_size_var, DEFAULT_FRAME_SIZE, 512, 768, 1024,
                                   command=lambda _: self.viewport._draw_overlay())
        size_menu.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ttk.Button(side, text="Open Images…", command=self.choose_files).grid(row=2, column=0, sticky="ew")
        self.file_label = ttk.Label(side, text="No files loaded", wraplength=320)
        self.file_label.grid(row=3, column=0, sticky="w", pady=(6, 10))

        ttk.Button(side, text="Fit full", command=self.viewport.fit_full).grid(row=4, column=0, sticky="ew")
        ttk.Button(side, text="Cover frame", command=self.viewport.fit_cover_frame).grid(row=5, column=0, sticky="ew")

        # --- Global words (prefix) ---
        ttk.Separator(side, orient="horizontal").grid(row=6, column=0, sticky="ew", pady=8)
        ttk.Label(side, text="Global words (prefixed to each .txt)").grid(row=7, column=0, sticky="w")
        global_wrap = ttk.Frame(side)
        global_wrap.grid(row=8, column=0, sticky="ew")
        self.global_text = tk.Text(global_wrap, height=3, wrap="word")
        self.global_text.pack(side="left", fill="x", expand=True)
        global_scroll = ttk.Scrollbar(global_wrap, orient="vertical", command=self.global_text.yview)
        global_scroll.pack(side="right", fill="y")
        self.global_text.configure(yscrollcommand=global_scroll.set)

        # --- Notes (per image) ---
        ttk.Separator(side, orient="horizontal").grid(row=9, column=0, sticky="ew", pady=8)
        ttk.Label(side, text="Notes per image (saved as .txt)").grid(row=10, column=0, sticky="w")
        notes_wrap = ttk.Frame(side)
        notes_wrap.grid(row=11, column=0, sticky="nsew")
        side.rowconfigure(11, weight=1)
        self.note_text = tk.Text(notes_wrap, height=6, wrap="word")
        self.note_text.pack(side="left", fill="both", expand=True)
        notes_scroll = ttk.Scrollbar(notes_wrap, orient="vertical", command=self.note_text.yview)
        notes_scroll.pack(side="right", fill="y")
        self.note_text.configure(yscrollcommand=notes_scroll.set)

        # Suggestions
        self.suggest_wrap = ttk.Frame(side)
        self.suggest_wrap.grid(row=12, column=0, sticky="ew", pady=(6, 0))
        header = ttk.Frame(self.suggest_wrap)
        header.pack(fill="x")
        self.suggest_caption = ttk.Label(header, text="", foreground="#666")
        self.suggest_caption.pack(side="left", anchor="w")
        ttk.Button(header, text="Clear history", command=self.clear_history).pack(side="right")
        self.suggest_items_frame = ttk.Frame(self.suggest_wrap)
        self.suggest_items_frame.pack(fill="x", expand=True)

        ttk.Separator(side, orient="horizontal").grid(row=13, column=0, sticky="ew", pady=8)
        ttk.Button(side, text="Save & Next", command=self.save_and_next).grid(row=14, column=0, sticky="ew")
        ttk.Button(side, text="Skip", command=self.skip).grid(row=15, column=0, sticky="ew", pady=(4, 0))

        self.progress_label = ttk.Label(side, text="—")
        self.progress_label.grid(row=16, column=0, sticky="w", pady=(8, 0))

        # Init data: history + global words
        self._load_history()
        self._load_global_words()
        self._refresh_suggestions()

        # Set/enforce split
        self.after(80, self._set_initial_split)
        self.panes.bind("<Configure>", self._enforce_split)

        # Shortcuts
        self.bind_all("<Control-s>", lambda e: self.save_and_next())
        self.bind_all("<Control-plus>", lambda e: self.viewport.zoom_in(fine=True))
        self.bind_all("<Control-minus>", lambda e: self.viewport.zoom_out(fine=True))
        self.bind_all("<Control-Right>", self._ctrl_right_guard)
        self.bind_all("<Return>", self._enter_open_if_empty)

        # Save globals on close too
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- Guard: ignore Ctrl+Right if a Text/Entry is focused ---
    def _focused_in_text(self):
        try:
            w = self.focus_get()
            if w is None:
                return False
            cls = w.winfo_class()
            return isinstance(w, tk.Text) or cls in ("Text", "Entry", "TEntry", "Spinbox", "TSpinbox")
        except Exception:
            return False

    def _ctrl_right_guard(self, event=None):
        if self._focused_in_text():
            return
        self.next_image()
        return "break"

    # ---- Layout helpers ----
    def _set_initial_split(self):
        try:
            self.update_idletasks()
            total_w = self.panes.winfo_width()
            if total_w <= 0:
                self.after(80, self._set_initial_split)
                return
            left_w = int(total_w * 0.67)
            self.panes.sash_place(0, left_w, 0)
        except Exception:
            pass

    def _enforce_split(self, event=None):
        try:
            total_w = self.panes.winfo_width()
            if total_w <= 0:
                return
            right_target = int(total_w * 0.33)
            left_w = max(200, total_w - right_target)
            self.panes.sash_place(0, left_w, 0)
        except Exception:
            pass

    # ---- Frame size ----
    def get_frame_size(self):
        return self.frame_size_var.get()

    # ---- Text parsing helpers (unique parts) ----
    def _parts_from_text(self, raw_text: str):
        """
        Returns a list of unique, trimmed parts split on commas/newlines,
        preserving the first-seen order.
        """
        if not raw_text:
            return []
        t = raw_text.replace("\r", "").replace("\n", ",")
        parts = [p.strip() for p in t.split(",")]
        seen = set()
        unique = []
        for p in parts:
            if not p:
                continue
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return unique

    # ---- File handling ----
    def choose_files(self):
        paths = filedialog.askopenfilenames(
            filetypes=[
                ("Image files", "*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.webp"),
                ("All files", "*.*"),
            ]
        )
        if not paths:
            return
        files = [os.path.abspath(p) for p in paths if os.path.splitext(p)[1].lower() in SUPPORTED_EXTS]
        if not files:
            return
        self.images = files
        self.idx = 0
        self.clear_notes()
        self.load_current()
        self.update_status()

    def _enter_open_if_empty(self, event=None):
        if not self.images:
            self.choose_files()
            return "break"

    def load_current(self):
        if not self.images or self.idx < 0 or self.idx >= len(self.images):
            self.viewport.set_image(Image.new("RGBA", (self.get_frame_size(), self.get_frame_size()), (20, 20, 20, 255)))
            self.file_label.config(text="No files loaded")
            return
        path = self.images[self.idx]
        try:
            pil = Image.open(path)
        except Exception:
            self.skip(move_current=False)
            return
        self.viewport.set_image(pil)
        self.file_label.config(text=os.path.basename(path))

    def update_status(self):
        if not self.images:
            self.progress_label.config(text="—")
        else:
            self.progress_label.config(text=f"Image {self.idx + 1} of {len(self.images)}")

    # ---- Suggestions / history ----
    def _process_text_for_counts(self, raw_text: str):
        parts = self._parts_from_text(raw_text)  # unique parts only
        for p in parts:
            self.tag_counts[p] = self.tag_counts.get(p, 0) + 1
        self._save_history()
        self._refresh_suggestions()

    def _refresh_suggestions(self):
        for child in self.suggest_items_frame.winfo_children():
            child.destroy()

        items = [(p, c) for p, c in self.tag_counts.items() if c >= SUGGEST_THRESHOLD]
        if not items:
            self.suggest_caption.configure(text="")
            try:
                self.note_text.configure(height=6)
            except Exception:
                pass
            return

        try:
            self.note_text.configure(height=4)
        except Exception:
            pass

        items.sort(key=lambda t: t[0].lower())
        self.suggest_caption.configure(text="Frequently used (A–Z): click to insert")

        max_cols = 6
        for idx, (p, _c) in enumerate(items[:120]):
            r, c = divmod(idx, max_cols)
            lbl = ttk.Label(self.suggest_items_frame, text=p, cursor="hand2")
            try:
                lbl.configure(font=("Segoe UI", 8))
            except Exception:
                pass
            lbl.grid(row=r, column=c, padx=(0, 8), pady=(2, 2), sticky="w")
            lbl.bind("<Button-1>", lambda e, part=p: self._insert_suggestion(part))

        for col in range(max_cols):
            try:
                self.suggest_items_frame.grid_columnconfigure(col, weight=1)
            except Exception:
                pass

    def _insert_suggestion(self, part: str):
        current = self.note_text.get("1.0", "end-1c")
        if current and not current.endswith("\n"):
            current = current + "\n"
        new_text = (current or "") + part + "\n"
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", new_text)
        self.note_text.mark_set("insert", "end-1c")
        self.note_text.see("end")

    def _load_history(self):
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or ";" not in line:
                        continue
                    tag, cnt = line.split(";", 1)
                    try:
                        self.tag_counts[tag] = max(self.tag_counts.get(tag, 0), int(cnt))
                    except ValueError:
                        pass
        except FileNotFoundError:
            self.tag_counts = getattr(self, "tag_counts", {})
        except Exception:
            pass

    def _save_history(self):
        try:
            items = sorted(self.tag_counts.items(), key=lambda t: t[0].lower())
            with open(self.history_path, "w", encoding="utf-8") as f:
                for tag, cnt in items:
                    f.write(f"{tag};{cnt}\n")
        except Exception:
            pass

    # ---- Global words persistence ----
    def _load_global_words(self):
        try:
            with open(self.global_words_path, "r", encoding="utf-8") as f:
                text = f.read()
            self.global_text.delete("1.0", "end")
            self.global_text.insert("1.0", text)
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def _save_global_words(self):
        try:
            text = self.global_text.get("1.0", "end-1c")
            with open(self.global_words_path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass

    def clear_history(self):
        if not messagebox.askyesno("Clear history", "Delete your frequently used words history? This cannot be undone."):
            return
        try:
            self.tag_counts.clear()
            if os.path.exists(self.history_path):
                os.remove(self.history_path)
        except Exception:
            pass
        self._refresh_suggestions()

    # ---- Navigation ----
    def next_image(self):
        if not self.images:
            return
        if self.idx < len(self.images) - 1:
            self.idx += 1
            self.clear_notes()
            self.load_current()
            self.update_status()
        else:
            # Clear image & status when no more images
            self.images = []
            self.idx = -1
            self.viewport.set_image(
                Image.new("RGBA", (self.get_frame_size(), self.get_frame_size()), (20, 20, 20, 255))
            )
            self.file_label.config(text="No files loaded")
            self.progress_label.config(text="—")
            self.clear_notes()
            messagebox.showinfo("Done", "No more images.")

    def skip(self, move_current=True):
        txt = self.note_text.get("1.0", "end-1c")
        if txt.strip():
            self._process_text_for_counts(txt)
        if move_current and self.images and 0 <= self.idx < len(self.images):
            self._move_current_to_processed()
        self._save_global_words()
        self.clear_notes()
        self.next_image()

    # ---- Save ----
    def save_and_next(self):
        if not self.images:
            return
        path = self.images[self.idx]
        try:
            out_img = self.viewport.get_crop_result_rgb()
            if out_img is None:
                return
            base_dir = os.path.dirname(path)
            out_dir = os.path.join(base_dir, "output")
            os.makedirs(out_dir, exist_ok=True)
            stem, _ = os.path.splitext(os.path.basename(path))

            # Save JPEG with same base name
            img_out_path = self._unique_path(os.path.join(out_dir, f"{stem}.jpg"))
            out_img.save(img_out_path, format="JPEG", quality=95, subsampling=1, optimize=True)

            # Build unique parts for text: global first, then notes, order preserved
            global_parts = self._parts_from_text(self.global_text.get("1.0", "end-1c"))
            notes_parts = self._parts_from_text(self.note_text.get("1.0", "end-1c"))

            # Combine and dedupe preserving order
            seen = set()
            combined = []
            for p in (global_parts + notes_parts):
                if p not in seen:
                    seen.add(p)
                    combined.append(p)

            combined_txt = ", ".join(combined).rstrip(", ")

            txt_out_path = os.path.join(out_dir, f"{stem}.txt")
            with open(txt_out_path, "w", encoding="utf-8") as f:
                f.write(combined_txt)

            # Only count unique per-image notes in history
            if notes_parts:
                self._process_text_for_counts(", ".join(notes_parts))

            # Move original to 'processed'
            self._move_current_to_processed()

            # Persist current global words on each save
            self._save_global_words()
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to save or move file.\n\n{e}")
            return

        self.clear_notes()
        self.next_image()

    def _move_current_to_processed(self):
        try:
            src = self.images[self.idx]
            base_dir = os.path.dirname(src)
            proc_dir = os.path.join(base_dir, "processed")
            os.makedirs(proc_dir, exist_ok=True)
            dest = os.path.join(proc_dir, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dest):
                if os.path.exists(dest):
                    dest = self._unique_path(dest)
                shutil.move(src, dest)
                self.images[self.idx] = dest
        except Exception as e:
            messagebox.showwarning("Move warning", f"Could not move original to 'processed':\n{e}")

    def clear_notes(self):
        if hasattr(self, "note_text"):
            self.note_text.delete("1.0", "end")

    def on_close(self):
        self._save_global_words()
        self.destroy()

    @staticmethod
    def _unique_path(path):
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        n = 1
        while True:
            candidate = f"{base} ({n}){ext}"
            if not os.path.exists(candidate):
                return candidate
            n += 1


def main():
    app = ImageCropperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
