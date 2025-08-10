import os
import sys
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image

from viewport import ImageViewport
from config import AppConfig, HISTORY_FILE, GLOBAL_WORDS_FILE
from suggestions import SuggestionStore, parts_from_text, SUGGEST_THRESHOLD

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}

class LoraPrepareApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Lora Prepare Tool")

        # Paths & config
        self.app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.config = AppConfig(self.app_dir)
        self.history_path = os.path.join(self.app_dir, HISTORY_FILE)
        self.global_words_path = os.path.join(self.app_dir, GLOBAL_WORDS_FILE)

        # Geometry from config if available
        geom = self.config.get("geometry")
        if geom:
            try:
                self.geometry(geom)
            except Exception:
                pass
        if not geom:
            self.geometry("1400x1000")
        self.minsize(1150, 920)

        # State
        self.images = []
        self.idx = -1
        self.frame_size_var = tk.IntVar(value=int(self.config.get("frame_size", 768)))

        # Suggestions store
        self.suggest = SuggestionStore(self.history_path)

        # --- Layout: 67/33 split
        self.panes = tk.PanedWindow(self, orient="horizontal", sashrelief="flat", sashwidth=6)
        self.panes.pack(fill="both", expand=True)

        self.left_wrap = ttk.Frame(self.panes)
        self.right_wrap = ttk.Frame(self.panes)
        self.panes.add(self.left_wrap)
        self.panes.add(self.right_wrap)

        # Left: viewport
        self.left_wrap.rowconfigure(0, weight=1)
        self.left_wrap.columnconfigure(0, weight=1)
        self.viewport = ImageViewport(
            self.left_wrap,
            self.get_frame_size,
            no_image_click_callback=self.choose_files
        )
        self.viewport.grid(row=0, column=0, sticky="nsew", padx=(14, 10), pady=(14, 8))

        # Arrow keys bound ONLY to canvas
        self.viewport.canvas.bind("<Left>",  lambda e: self.viewport.move_image(-1, 0))
        self.viewport.canvas.bind("<Right>", lambda e: self.viewport.move_image(1, 0))
        self.viewport.canvas.bind("<Up>",    lambda e: self.viewport.move_image(0, -1))
        self.viewport.canvas.bind("<Down>",  lambda e: self.viewport.move_image(0, 1))

        # Right: sidebar
        side = ttk.Frame(self.right_wrap)
        side.pack(fill="both", expand=True, padx=(0, 14), pady=(14, 8))
        side.columnconfigure(0, weight=1)

        ttk.Label(side, text="Frame size").grid(row=0, column=0, sticky="w")
        size_menu = ttk.OptionMenu(
            side, self.frame_size_var, self.frame_size_var.get(), 512, 768, 1024,
            command=self._on_frame_size_changed
        )
        size_menu.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        ttk.Button(side, text="Open Images…", command=self.choose_files).grid(row=2, column=0, sticky="ew")
        self.file_label = ttk.Label(side, text="No files loaded", wraplength=320)
        self.file_label.grid(row=3, column=0, sticky="w", pady=(6, 10))

        # Export dirs (prefilled with effective defaults; no extra labels)
        ttk.Separator(side, orient="horizontal").grid(row=4, column=0, sticky="ew", pady=(6, 8))
        ttk.Label(side, text="Export folders").grid(row=5, column=0, sticky="w")

        out_row = ttk.Frame(side); out_row.grid(row=6, column=0, sticky="ew", pady=(2, 2))
        out_row.columnconfigure(0, weight=1)
        self.output_dir_var = tk.StringVar(value=self.config.get("output_dir"))
        out_entry = ttk.Entry(out_row, textvariable=self.output_dir_var); out_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(out_row, text="Browse…", command=self._browse_output_dir).grid(row=0, column=1, padx=(6, 0))

        proc_row = ttk.Frame(side); proc_row.grid(row=7, column=0, sticky="ew", pady=(2, 8))
        proc_row.columnconfigure(0, weight=1)
        self.processed_dir_var = tk.StringVar(value=self.config.get("processed_dir"))
        proc_entry = ttk.Entry(proc_row, textvariable=self.processed_dir_var); proc_entry.grid(row=0, column=0, sticky="ew")
        ttk.Button(proc_row, text="Browse…", command=self._browse_processed_dir).grid(row=0, column=1, padx=(6, 0))

        ttk.Button(side, text="Fit full", command=self.viewport.fit_full).grid(row=8, column=0, sticky="ew")
        ttk.Button(side, text="Cover frame", command=self.viewport.fit_cover_frame).grid(row=9, column=0, sticky="ew")

        # Global words
        ttk.Separator(side, orient="horizontal").grid(row=10, column=0, sticky="ew", pady=8)
        ttk.Label(side, text="Global words (prefixed to each .txt)").grid(row=11, column=0, sticky="w")
        global_wrap = ttk.Frame(side); global_wrap.grid(row=12, column=0, sticky="ew")
        self.global_text = tk.Text(global_wrap, height=3, wrap="word")
        self.global_text.pack(side="left", fill="x", expand=True)
        gscroll = ttk.Scrollbar(global_wrap, orient="vertical", command=self.global_text.yview)
        gscroll.pack(side="right", fill="y")
        self.global_text.configure(yscrollcommand=gscroll.set)

        # Notes
        ttk.Separator(side, orient="horizontal").grid(row=13, column=0, sticky="ew", pady=8)
        ttk.Label(side, text="Notes per image (saved as .txt)").grid(row=14, column=0, sticky="w")
        notes_wrap = ttk.Frame(side); notes_wrap.grid(row=15, column=0, sticky="nsew")
        side.rowconfigure(15, weight=1)
        self.note_text = tk.Text(notes_wrap, height=6, wrap="word")
        self.note_text.pack(side="left", fill="both", expand=True)
        nscroll = ttk.Scrollbar(notes_wrap, orient="vertical", command=self.note_text.yview)
        nscroll.pack(side="right", fill="y")
        self.note_text.configure(yscrollcommand=nscroll.set)

        # Suggestions
        self.suggest_wrap = ttk.Frame(side); self.suggest_wrap.grid(row=16, column=0, sticky="ew", pady=(6, 0))
        header = ttk.Frame(self.suggest_wrap); header.pack(fill="x")
        self.suggest_caption = ttk.Label(header, text="", foreground="#666"); self.suggest_caption.pack(side="left", anchor="w")
        ttk.Button(header, text="Clear history", command=self.clear_history).pack(side="right")
        self.suggest_items_frame = ttk.Frame(self.suggest_wrap); self.suggest_items_frame.pack(fill="x", expand=True)

        ttk.Separator(side, orient="horizontal").grid(row=17, column=0, sticky="ew", pady=8)
        ttk.Button(side, text="Save & Next", command=self.save_and_next).grid(row=18, column=0, sticky="ew")
        ttk.Button(side, text="Skip", command=self.skip).grid(row=19, column=0, sticky="ew", pady=(4, 0))

        self.progress_label = ttk.Label(side, text="—")
        self.progress_label.grid(row=20, column=0, sticky="w", pady=(8, 0))

        # Init data
        self._load_global_words()
        self._refresh_suggestions()

        # Split + resize behavior
        self.after(80, self._set_initial_split)
        self.panes.bind("<Configure>", self._enforce_split)

        # Shortcuts
        self.bind_all("<Control-s>", lambda e: self.save_and_next())
        self.bind_all("<Control-plus>", lambda e: self.viewport.zoom_in(fine=True))
        self.bind_all("<Control-minus>", lambda e: self.viewport.zoom_out(fine=True))
        self.bind_all("<Control-Right>", self._ctrl_right_guard)
        self.bind_all("<Return>", self._enter_open_if_empty)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if not self.images:
            self.viewport.clear()

        # Save dirs when entry loses focus
        out_entry.bind("<FocusOut>", lambda e: self._save_dirs_from_entries())
        proc_entry.bind("<FocusOut>", lambda e: self._save_dirs_from_entries())

    # ---- Helpers & config ----
    def get_frame_size(self):
        return self.frame_size_var.get()

    def _on_frame_size_changed(self, _value=None):
        self.viewport._draw_overlay()
        self.config.set("frame_size", int(self.frame_size_var.get()))
        self._save_config()

    def _save_config(self):
        self.config.set("geometry", self.geometry())
        self.config.set("output_dir", self.output_dir_var.get().strip())
        self.config.set("processed_dir", self.processed_dir_var.get().strip())
        self.config.save()

    def _browse_output_dir(self):
        initial = self.output_dir_var.get().strip() or self.app_dir
        chosen = filedialog.askdirectory(initialdir=initial, title="Select Output Folder")
        if chosen:
            self._set_out_dir(chosen)

    def _browse_processed_dir(self):
        initial = self.processed_dir_var.get().strip() or self.app_dir
        chosen = filedialog.askdirectory(initialdir=initial, title="Select Processed Folder")
        if chosen:
            self._set_proc_dir(chosen)

    def _set_out_dir(self, value: str):
        self.output_dir_var.set(value)
        self._save_dirs_from_entries()

    def _set_proc_dir(self, value: str):
        self.processed_dir_var.set(value)
        self._save_dirs_from_entries()

    def _save_dirs_from_entries(self):
        self.config.set("output_dir", self.output_dir_var.get().strip())
        self.config.set("processed_dir", self.processed_dir_var.get().strip())
        self._save_config()

    # ---- File handling ----
    def choose_files(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Image files", "*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.webp"),
                       ("All files", "*.*")]
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
            self.viewport.clear()
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
        self.progress_label.config(text="—" if not self.images else f"Image {self.idx + 1} of {len(self.images)}")

    # ---- Suggestions / history ----
    def _refresh_suggestions(self):
        for child in self.suggest_items_frame.winfo_children():
            child.destroy()

        items = self.suggest.suggestions_alpha()
        if not items:
            self.suggest_caption.configure(text="")
            try: self.note_text.configure(height=6)
            except Exception: pass
            return

        try: self.note_text.configure(height=4)
        except Exception: pass

        self.suggest_caption.configure(text="Frequently used (A–Z): click to insert")

        max_cols = 6
        for idx, (p, _c) in enumerate(items[:120]):
            r, c = divmod(idx, max_cols)
            lbl = ttk.Label(self.suggest_items_frame, text=p, cursor="hand2")
            try: lbl.configure(font=("Segoe UI", 8))
            except Exception: pass
            lbl.grid(row=r, column=c, padx=(0, 8), pady=(2, 2), sticky="w")
            lbl.bind("<Button-1>", lambda e, part=p: self._insert_suggestion(part))

        for col in range(max_cols):
            try: self.suggest_items_frame.grid_columnconfigure(col, weight=1)
            except Exception: pass

    def _insert_suggestion(self, part: str):
        current = self.note_text.get("1.0", "end-1c")
        if current and not current.endswith("\n"):
            current += "\n"
        new_text = (current or "") + part + "\n"
        self.note_text.delete("1.0", "end")
        self.note_text.insert("1.0", new_text)
        self.note_text.mark_set("insert", "end-1c")
        self.note_text.see("end")

    def clear_history(self):
        if not messagebox.askyesno("Clear history", "Delete your frequently used words history? This cannot be undone."):
            return
        self.suggest.clear()
        self._refresh_suggestions()

    # ---- Text helpers (unique parts) ----
    def _unique_combined_parts(self):
        global_parts = parts_from_text(self.global_text.get("1.0", "end-1c"))
        notes_parts  = parts_from_text(self.note_text.get("1.0", "end-1c"))
        seen, combined = set(), []
        for p in (global_parts + notes_parts):
            if p not in seen:
                seen.add(p)
                combined.append(p)
        return combined, notes_parts  # combined for file; notes_parts for counting

    # ---- Navigation ----
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

    def _set_initial_split(self):
        try:
            self.update_idletasks()
            total_w = self.panes.winfo_width()
            if total_w <= 0:
                self.after(80, self._set_initial_split); return
            left_w = int(total_w * 0.67)
            self.panes.sash_place(0, left_w, 0)
        except Exception:
            pass

    def _enforce_split(self, event=None):
        try:
            total_w = self.panes.winfo_width()
            if total_w <= 0: return
            right_target = int(total_w * 0.33)
            left_w = max(200, total_w - right_target)
            self.panes.sash_place(0, left_w, 0)
        except Exception:
            pass

    def next_image(self):
        if not self.images:
            return
        if self.idx < len(self.images) - 1:
            self.idx += 1
            self.clear_notes()
            self.load_current()
            self.update_status()
        else:
            self.images = []
            self.idx = -1
            self.viewport.clear()
            self.file_label.config(text="No files loaded")
            self.progress_label.config(text="—")
            self.clear_notes()
            messagebox.showinfo("Done", "No more images.")

    def skip(self, move_current=True):
        txt = self.note_text.get("1.0", "end-1c")
        if txt.strip():
            self.suggest.process_text_for_counts(txt)
        if move_current and self.images and 0 <= self.idx < len(self.images):
            self._move_current_to_processed()
        self._save_global_words()
        self.clear_notes()
        if self.idx < len(self.images) - 1:
            self.idx += 1
            self.load_current()
            self.update_status()
        else:
            self.images = []
            self.idx = -1
            self.viewport.clear()
            self.file_label.config(text="No files loaded")
            self.progress_label.config(text="—")
            messagebox.showinfo("Done", "No more images.")

    # ---- Save ----
    def save_and_next(self):
        if not self.images:
            return
        path = self.images[self.idx]
        try:
            out_img = self.viewport.get_crop_result_rgb()
            if out_img is None:
                return

            out_dir = self.config.effective_output_dir_for(path)
            proc_dir = self.config.effective_processed_dir_for(path)
            os.makedirs(out_dir, exist_ok=True)
            os.makedirs(proc_dir, exist_ok=True)

            stem, _ = os.path.splitext(os.path.basename(path))

            # Save JPEG
            img_out_path = self._unique_path(os.path.join(out_dir, f"{stem}.jpg"))
            out_img.save(img_out_path, format="JPEG", quality=95, subsampling=1, optimize=True)

            # Tags file
            combined, notes_parts = self._unique_combined_parts()
            combined_txt = ", ".join(combined).rstrip(", ")
            txt_out_path = os.path.join(out_dir, f"{stem}.txt")
            with open(txt_out_path, "w", encoding="utf-8") as f:
                f.write(combined_txt)

            # Update suggestions with only per-image notes
            if notes_parts:
                self.suggest.process_text_for_counts(", ".join(notes_parts))

            # Move original to 'processed'
            self._move_current_to_processed(proc_dir)

            # Persist globals + config
            self._save_global_words()
            self._save_config()
        except Exception as e:
            messagebox.showerror("Save error", f"Failed to save or move file.\n\n{e}")
            return

        self.clear_notes()
        self.next_image()

    def _move_current_to_processed(self, proc_dir=None):
        try:
            src = self.images[self.idx]
            if proc_dir is None:
                proc_dir = self.config.effective_processed_dir_for(src)
            os.makedirs(proc_dir, exist_ok=True)
            dest = os.path.join(proc_dir, os.path.basename(src))
            if os.path.abspath(src) != os.path.abspath(dest):
                if os.path.exists(dest):
                    dest = self._unique_path(dest)
                shutil.move(src, dest)
                self.images[self.idx] = dest
        except Exception as e:
            messagebox.showwarning("Move warning", f"Could not move original to 'processed':\n{e}")

    # ---- Text / globals ----
    def clear_notes(self):
        if hasattr(self, "note_text"):
            self.note_text.delete("1.0", "end")

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

    def on_close(self):
        self._save_global_words()
        self._save_config()
        self.destroy()

    @staticmethod
    def _unique_path(path):
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        n = 1
        while True:
            cand = f"{base} ({n}){ext}"
            if not os.path.exists(cand):
                return cand
            n += 1
