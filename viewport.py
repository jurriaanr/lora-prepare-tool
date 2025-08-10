import sys
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

ZOOM_STEP = 1.12
MIN_SCALE = 0.02
MAX_SCALE = 30.0
SNAP_TOL = 10  # px; snap to frame edges while mouse-dragging

class ImageViewport(ttk.Frame):
    """
    Canvas viewport that displays an image with zoom/pan and a square frame overlay.
    Provides get_crop_result_rgb() to render the frame area as an RGB square image.
    """
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

        # Track canvas size to maintain image offset relative to frame on resize
        self._last_canvas_size = None

        # Bindings
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", self._on_configure)

        self._bind_wheel_events()

    # ---- Sizes / frame ----
    def _canvas_size(self):
        w = max(50, int(self.canvas.winfo_width()))
        h = max(50, int(self.canvas.winfo_height()))
        return w, h

    def _frame_rect_for(self, cw, ch):
        frame = self.get_frame_size()
        L = (cw - frame) / 2
        T = (ch - frame) / 2
        return L, T, L + frame, T + frame

    def _frame_rect(self):
        return self._frame_rect_for(*self._canvas_size())

    # ---- Public API ----
    def set_image(self, pil_image):
        """Set a PIL image (RGBA converted). If None, clears the canvas."""
        if pil_image is None:
            self.clear()
            return
        self.img_pil = pil_image.convert("RGBA")
        iw, ih = self.img_pil.size
        cw, ch = self._canvas_size()
        self._last_canvas_size = (cw, ch)

        fit = min(cw / iw, ch / ih)
        fit = max(MIN_SCALE, min(MAX_SCALE, fit))
        self.S = fit

        # center inside frame
        L, T, R, B = self._frame_rect()
        fCx, fCy = (L + R) / 2, (T + B) / 2
        self.dx = fCx - (iw * self.S) / 2
        self.dy = fCy - (ih * self.S) / 2

        self._render_image()
        self._draw_overlay()

    def clear(self):
        self.img_pil = None
        self.img_disp = None
        self.tk_img = None
        if self.img_id is not None:
            self.canvas.delete(self.img_id)
            self.img_id = None
        for oid in self.overlay_ids:
            self.canvas.delete(oid)
        self.overlay_ids = []

    def zoom_in(self, fine=False):
        cw, ch = self._canvas_size()
        factor = ZOOM_STEP ** (0.25 if fine else 1.0)
        self.zoom_at(cw / 2, ch / 2, factor)

    def zoom_out(self, fine=False):
        cw, ch = self._canvas_size()
        factor = ZOOM_STEP ** (0.25 if fine else 1.0)
        self.zoom_at(cw / 2, ch / 2, 1.0 / factor)

    def fit_full(self):
        if self.img_pil is None:
            return
        iw, ih = self.img_pil.size
        frame = self.get_frame_size()
        fit = max(MIN_SCALE, min(MAX_SCALE, min(frame / iw, frame / ih)))
        self.S = fit
        L, T, R, B = self._frame_rect()
        fCx, fCy = (L + R) / 2, (T + B) / 2
        self.dx = fCx - (iw * self.S) / 2.0
        self.dy = fCy - (ih * self.S) / 2.0
        self._render_image()

    def fit_cover_frame(self):
        if self.img_pil is None:
            return
        iw, ih = self.img_pil.size
        frame = self.get_frame_size()
        cover = max(frame / iw, frame / ih)
        self.S = max(MIN_SCALE, min(MAX_SCALE, cover))
        L, T, R, B = self._frame_rect()
        fCx, fCy = (L + R) / 2, (T + B) / 2
        self.dx = fCx - (iw * self.S) / 2.0
        self.dy = fCy - (ih * self.S) / 2.0
        self._render_image()

    def move_image(self, dx, dy):
        self.dx += dx
        self.dy += dy
        self._render_image()

    def get_crop_result_rgb(self):
        """Return an RGB square image of size (frame, frame) from the frame area (letterbox black)."""
        if self.img_pil is None:
            return None
        frame = self.get_frame_size()
        L, T, R, B = self._frame_rect()

        left_img   = (L - self.dx) / self.S
        top_img    = (T - self.dy) / self.S
        right_img  = (R - self.dx) / self.S
        bottom_img = (B - self.dy) / self.S

        iw, ih = self.img_pil.size
        inter_left   = max(0, left_img)
        inter_top    = max(0, top_img)
        inter_right  = min(iw, right_img)
        inter_bottom = min(ih, bottom_img)

        out = Image.new("RGB", (frame, frame), (0, 0, 0))
        if inter_right > inter_left and inter_bottom > inter_top:
            crop = self.img_pil.crop((
                int(inter_left), int(inter_top), int(inter_right), int(inter_bottom)
            )).convert("RGB")

            interL_canvas = inter_left * self.S + self.dx
            interT_canvas = inter_top  * self.S + self.dy
            dest_x = int(round(interL_canvas - L))
            dest_y = int(round(interT_canvas - T))

            inter_w_canvas = (inter_right - inter_left) * self.S
            inter_h_canvas = (inter_bottom - inter_top) * self.S
            target_w = max(1, int(round(inter_w_canvas)))
            target_h = max(1, int(round(inter_h_canvas)))
            if crop.size != (target_w, target_h):
                crop = crop.resize((target_w, target_h), Image.LANCZOS)

            out.paste(crop, (dest_x, dest_y))
        return out

    # ---- Internals ----
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
        for oid in self.overlay_ids:
            self.canvas.delete(oid)
        self.overlay_ids = []
        if self.img_pil is None:
            return

        L, T, R, B = self._frame_rect()
        cw, ch = self._canvas_size()

        # Dim outside frame (stipple ≈ 50% opacity)
        self.overlay_ids.append(self.canvas.create_rectangle(0, 0, cw, T, fill="#000", outline="", stipple="gray50"))
        self.overlay_ids.append(self.canvas.create_rectangle(0, T, L, B, fill="#000", outline="", stipple="gray50"))
        self.overlay_ids.append(self.canvas.create_rectangle(R, T, cw, B, fill="#000", outline="", stipple="gray50"))
        self.overlay_ids.append(self.canvas.create_rectangle(0, B, cw, ch, fill="#000", outline="", stipple="gray50"))

        # Frame outline + ticks
        self.overlay_ids.append(self.canvas.create_rectangle(L, T, R, B, outline="#6aa3ff", width=2))
        tick = 18
        for (x, y, dx, dy) in [
            (L, T, +tick, 0), (L, T, 0, +tick),
            (R, T, -tick, 0), (R, T, 0, +tick),
            (L, B, +tick, 0), (L, B, 0, -tick),
            (R, B, -tick, 0), (R, B, 0, -tick),
        ]:
            self.overlay_ids.append(self.canvas.create_line(x, y, x + dx, y + dy, fill="#6aa3ff", width=2))

    # ---- Events ----
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
        steps = direction
        base = ZOOM_STEP ** (0.25 if self._ctrl_held(event) else 1.0)
        self.zoom_at(event.x, event.y, base ** steps)

    def _on_configure(self, event):
        new_cw, new_ch = int(event.width), int(event.height)
        old = self._last_canvas_size
        self._last_canvas_size = (new_cw, new_ch)
        if self.img_pil is not None and old is not None and (new_cw, new_ch) != old:
            oldL, oldT, _, _ = self._frame_rect_for(*old)
            rel_dx = self.dx - oldL
            rel_dy = self.dy - oldT
            newL, newT, _, _ = self._frame_rect_for(new_cw, new_ch)
            self.dx = newL + rel_dx
            self.dy = newT + rel_dy
        self._redraw()

    def _redraw(self):
        self._draw_overlay()
        self._render_image()

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
