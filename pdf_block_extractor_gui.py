#!/usr/bin/env python3
"""
pdf_block_extractor_gui.py

Features:
- Load PDF (first page by default)
- Render preview that supports zoom and pan
- Detect rectangles from vector drawings (page.get_drawings())
- Allow selecting topmost rectangle (handles nested)
- Export each selected rectangle as a true SVG (vector) using page.get_svg_image(clip=...)
"""

import fitz  # PyMuPDF
import io
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import filedialog, messagebox
import os

# --- Utility functions -----------------------------------------------------
def fitz_rect_to_tuple(r):
    """Return (x0,y0,x1,y1) for a fitz.Rect-like object or tuple."""
    if hasattr(r, "x0"):
        return (float(r.x0), float(r.y0), float(r.x1), float(r.y1))
    return tuple(map(float, r))

# --- GUI App ---------------------------------------------------------------
class PDFBlockExtractorGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Block Extractor — Vector-accurate")
        self.geometry("1200x800")

        # PDF & rendering state
        self.pdf_path = None
        self.doc = None
        self.page = None
        self.page_number = 0
        self.zoom = 1.0  # PDF user units -> pixels scale multiplier (matrix)
        self.min_zoom = 0.1
        self.max_zoom = 4.0

        # image objects
        self.pix = None
        self.pil_img = None
        self.tk_img = None

        # detected rectangles: list of dicts: {"bbox":(x0,y0,x1,y1), "canvas_id":id}
        self.rects = []
        self.selected_rects = set()  # indices into self.rects

        # UI layout
        self.create_ui()
        self.bind_events()

    def create_ui(self):
        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=6, pady=6)

        btn_load = tk.Button(top, text="Load PDF", command=self.load_pdf)
        btn_load.pack(side=tk.LEFT, padx=4)

        tk.Label(top, text="Page:").pack(side=tk.LEFT, padx=(10,2))
        self.page_spin = tk.Spinbox(top, from_=1, to=999, width=4, command=self.on_page_change)
        self.page_spin.delete(0, "end")
        self.page_spin.insert(0, "1")
        self.page_spin.pack(side=tk.LEFT)

        tk.Label(top, text="Zoom:").pack(side=tk.LEFT, padx=(10,2))
        self.zoom_var = tk.StringVar(value=f"{self.zoom:.2f}")
        self.zoom_label = tk.Label(top, textvariable=self.zoom_var)
        self.zoom_label.pack(side=tk.LEFT)

        btn_detect = tk.Button(top, text="Detect Rectangles", command=self.detect_rects)
        btn_detect.pack(side=tk.LEFT, padx=8)

        btn_export = tk.Button(top, text="Export Selected SVGs", command=self.export_selected_svgs)
        btn_export.pack(side=tk.RIGHT, padx=4)

        # Canvas + scrollbars
        frame = tk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True)

        self.hbar = tk.Scrollbar(frame, orient=tk.HORIZONTAL)
        self.vbar = tk.Scrollbar(frame, orient=tk.VERTICAL)
        self.canvas = tk.Canvas(frame, bg="#222222",
                                xscrollcommand=self.hbar.set,
                                yscrollcommand=self.vbar.set)
        self.hbar.config(command=self.canvas.xview)
        self.vbar.config(command=self.canvas.yview)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")

        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        # Info bar
        self.info_var = tk.StringVar(value="Load a PDF and click 'Detect Rectangles'. Zoom with mouse wheel. Pan with right mouse drag.")
        info = tk.Label(self, textvariable=self.info_var, anchor="w")
        info.pack(fill=tk.X, padx=6, pady=(0,6))

    def bind_events(self):
        # left click: selection
        self.canvas.bind("<Button-1>", self.on_left_click)
        # mouse wheel: zoom (Windows/Mac have different events)
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)          # Windows / Mac
        self.canvas.bind("<Button-4>", self.on_mousewheel)            # some Linux
        self.canvas.bind("<Button-5>", self.on_mousewheel)            # some Linux
        # right-click drag for pan
        self.canvas.bind("<ButtonPress-3>", self.on_right_press)
        self.canvas.bind("<B3-Motion>", self.on_right_drag)

        # handle window resize to keep scrollregion
        self.bind("<Configure>", lambda e: self.update_canvas_scrollregion())

    # --------------------------
    # PDF loading & rendering
    # --------------------------
    def load_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        try:
            if self.doc:
                try:
                    self.doc.close()
                except Exception:
                    pass
            self.doc = fitz.open(path)
            self.pdf_path = path
            self.page_number = 0
            self.page_spin.delete(0, "end")
            self.page_spin.insert(0, "1")
            self.page = self.doc.load_page(self.page_number)
            self.zoom = 1.0
            self.render_page()
            self.info_var.set(f"Loaded: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Load error", f"Failed to open PDF: {e}")

    def on_page_change(self):
        try:
            p = int(self.page_spin.get()) - 1
            if p < 0:
                return
            if not self.doc:
                return
            if p >= len(self.doc):
                return
            self.page_number = p
            self.page = self.doc.load_page(self.page_number)
            self.render_page()
        except Exception:
            pass

    def render_page(self, preserve_view_center=True):
        """
        Render page at current self.zoom (fitz.Matrix(self.zoom, self.zoom)).
        If preserve_view_center is True, attempt to keep the visible center roughly the same after re-render.
        """
        if self.page is None:
            return

        # attempt to preserve view center
        try:
            # visible box in canvas coords before re-render
            canvas_w = self.canvas.winfo_width() or 1
            canvas_h = self.canvas.winfo_height() or 1
            # view center in canvas coordinates
            x0, y0, x1, y1 = self.canvas.xview(), self.canvas.yview(), None, None
        except Exception:
            pass

        try:
            mat = fitz.Matrix(self.zoom, self.zoom)
            self.pix = self.page.get_pixmap(matrix=mat, alpha=False)
            mode = "RGB"
            img = Image.frombytes(mode, [self.pix.width, self.pix.height], self.pix.samples)
            self.pil_img = img
            self.tk_img = ImageTk.PhotoImage(img)

            # clear canvas and display
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img, tags=("pdf_img",))
            self.canvas.config(scrollregion=(0, 0, self.pix.width, self.pix.height))
            self.draw_rectangles_on_canvas()  # redraw overlays if any
            self.zoom_var.set(f"{self.zoom:.2f}")
        except Exception as e:
            messagebox.showerror("Render error", f"Failed to render page: {e}")

    def update_canvas_scrollregion(self):
        if self.pil_img:
            self.canvas.config(scrollregion=(0, 0, self.pil_img.width, self.pil_img.height))

    # --------------------------
    # Rectangle detection
    # --------------------------
    def detect_rects(self):
        """Detect rectangular drawing elements, skipping text outlines."""
        if self.page is None:
            messagebox.showwarning("No PDF", "Load a PDF first.")
            return

        rects = []
        for d in self.page.get_drawings():
            # Ignore text outlines (very thin or no width)
            width = d.get("width") or 0
            if width < 0.2 and not d.get("fill"):
                continue

            r = d.get("rect")
            if r and not r.is_empty:
                bbox = fitz_rect_to_tuple(r)
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]

                # ✅ Optional filter to ignore extreme aspect ratios (very thin lines)
                aspect = max(w / h, h / w)
                if aspect > 20:
                    continue

                if w > 3 and h > 3:
                    rects.append(bbox)
                continue

            # infer from points if no direct rect
            pts = []
            for item in d.get("items", []):
                if isinstance(item, list) and len(item) >= 2:
                    pts.extend([(p[0], p[1]) for p in item if isinstance(p, (list, tuple)) and len(p) == 2])
            if pts:
                xs, ys = zip(*pts)
                bbox = (min(xs), min(ys), max(xs), max(ys))
                w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]

                # ✅ again apply aspect filter here too
                aspect = max(w / h, h / w)
                if aspect > 20:
                    continue

                if w > 3 and h > 3:
                    rects.append(bbox)

        # remove near-duplicates
        filtered = []
        for b in rects:
            if not any(self._bbox_almost_equal(b, e, tol=2.0) for e in filtered):
                filtered.append(b)

        self.rects = [{"bbox": b, "canvas_id": None} for b in filtered]
        self.selected_rects = set()
        self.draw_rectangles_on_canvas()
        self.info_var.set(f"Detected {len(self.rects)} likely box shapes (filtered).")

    def export_selected_svgs(self):
        if not self.selected_rects:
            messagebox.showwarning("No selection", "Select at least one rectangle first.")
            return

        out_dir = filedialog.askdirectory(title="Select output folder")
        if not out_dir:
            return

        saved = 0
        page = self.page
        if not page:
            return

        for idx in sorted(self.selected_rects):
            bbox = self.rects[idx]["bbox"]
            clip = fitz.Rect(bbox)

            try:
                drawings = [
                    d for d in page.get_drawings()
                    if "rect" in d and d["rect"] and clip.intersects(d["rect"])
                ]

                svg_parts = [
                    '<?xml version="1.0" encoding="UTF-8"?>',
                    f'<svg xmlns="http://www.w3.org/2000/svg" '
                    f'viewBox="{clip.x0} {clip.y0} {clip.width} {clip.height}">'
                ]

                for d in drawings:
                    # Skip invalid or empty items
                    if not d:
                        continue

                    path = d.get("path")
                    stroke = d.get("color") or (0, 0, 0)
                    fill = d.get("fill")
                    stroke_color = f"rgb({int(stroke[0]*255)}, {int(stroke[1]*255)}, {int(stroke[2]*255)})"
                    fill_attr = (
                        f'fill="rgb({int(fill[0]*255)}, {int(fill[1]*255)}, {int(fill[2]*255)})"'
                        if fill else 'fill="none"'
                    )
                    stroke_attr = f'stroke="{stroke_color}" stroke-width="{d.get("width",1)}"'

                    if path:
                        cmds = []
                        for item in path:
                            op = item[0]
                            pts = item[1] if len(item) > 1 else []
                            if not pts:
                                continue
                            pts_str = " ".join([f"{p[0]},{p[1]}" for p in pts])
                            cmds.append(f"{op} {pts_str}")
                        if cmds:
                            svg_parts.append(f'<path d="{" ".join(cmds)}" {stroke_attr} {fill_attr}/>')
                    elif "rect" in d and d["rect"]:
                        r = d["rect"]
                        svg_parts.append(
                            f'<rect x="{r.x0}" y="{r.y0}" width="{r.width}" height="{r.height}" '
                            f'{stroke_attr} {fill_attr}/>'
                        )

                svg_parts.append("</svg>")
                svg_data = "\n".join(svg_parts)

                out_path = os.path.join(out_dir, f"block_{idx+1}.svg")
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(svg_data)
                saved += 1

            except Exception as e:
                print(f"[warn] Export {idx} failed: {e}")

        messagebox.showinfo("Export done", f"Saved {saved} SVG(s) to:\n{out_dir}")


    def _bbox_almost_equal(self, a, b, tol=2.0):
        return all(abs(a[i] - b[i]) <= tol for i in range(4))

    # --------------------------
    # Drawing rectangle overlays
    # --------------------------
    def draw_rectangles_on_canvas(self):
        """Draw overlays corresponding to self.rects. Coordinates in PDF units -> pixels via zoom."""
        # remove previous overlays
        # preserve the pdf image (tagged "pdf_img") by deleting other items
        self.canvas.delete("overlay")
        # draw each rectangle (scaled by zoom)
        for idx, info in enumerate(self.rects):
            x0, y0, x1, y1 = info["bbox"]
            px0 = x0 * self.zoom
            py0 = y0 * self.zoom
            px1 = x1 * self.zoom
            py1 = y1 * self.zoom
            color = "green" if idx in self.selected_rects else "red"
            # create rectangle overlay, tag with overlay and index
            cid = self.canvas.create_rectangle(px0, py0, px1, py1,
                                               outline=color, width=2,
                                               tags=("overlay", f"rect_{idx}"))
            # store canvas id
            info["canvas_id"] = cid

    # --------------------------
    # Input handling (selection)
    # --------------------------
    def on_left_click(self, event):
        """Select the innermost rectangle under the click (smallest-area containing bbox)."""
        if not self.rects:
            return

        # convert canvas coords -> page coords
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        page_x = canvas_x / self.zoom
        page_y = canvas_y / self.zoom

        # collect indices of rects that contain the point
        hits = []
        for idx, info in enumerate(self.rects):
            x0, y0, x1, y1 = info["bbox"]
            if x0 <= page_x <= x1 and y0 <= page_y <= y1:
                area = (x1 - x0) * (y1 - y0)
                hits.append((area, idx))

        if not hits:
            return

        # pick smallest area (innermost)
        hits.sort(key=lambda t: t[0])
        _, chosen_idx = hits[0]

        # toggle selection
        if chosen_idx in self.selected_rects:
            self.selected_rects.remove(chosen_idx)
        else:
            self.selected_rects.add(chosen_idx)

        # redraw overlays
        self.draw_rectangles_on_canvas()


    # --------------------------
    # Zoom & pan
    # --------------------------
    def on_mousewheel(self, event):
        """Zoom centered at mouse pointer. Re-render page at new zoom to keep accuracy."""
        # wheel up: event.delta > 0 (Windows). On Linux, use Button-4/5
        delta = 0
        if hasattr(event, "delta") and event.delta:
            delta = event.delta
        elif event.num == 4:
            delta = 120
        elif event.num == 5:
            delta = -120

        factor = 1.1 if delta > 0 else 0.9
        new_zoom = self.zoom * factor
        # clamp
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))
        if abs(new_zoom - self.zoom) < 1e-6:
            return

        # compute page coords of the mouse point before zoom, to keep it roughly at the same view
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        page_x_before = canvas_x / self.zoom
        page_y_before = canvas_y / self.zoom

        # update zoom and re-render
        self.zoom = new_zoom
        self.render_page(preserve_view_center=False)

        # after re-render, compute new canvas coords of same page point and scroll to center there
        new_canvas_x = page_x_before * self.zoom
        new_canvas_y = page_y_before * self.zoom

        # compute new scroll offsets to put that point near where the mouse was
        # We center the view such that new_canvas_x, new_canvas_y appears at same canvas pixel pos
        # Compute fraction positions for xview/yview
        canvas_w = self.canvas.winfo_width() or 1
        canvas_h = self.canvas.winfo_height() or 1
        # desired top-left so that new_canvas_x is at event.x
        new_left = new_canvas_x - event.x
        new_top = new_canvas_y - event.y
        # clamp
        max_w = max(1, int(self.pil_img.width * self.zoom))
        max_h = max(1, int(self.pil_img.height * self.zoom))
        new_left = max(0, min(new_left, max_w - canvas_w))
        new_top = max(0, min(new_top, max_h - canvas_h))

        self.canvas.xview_moveto(new_left / max_w)
        self.canvas.yview_moveto(new_top / max_h)

    def on_right_press(self, event):
        # start panning
        self.canvas.scan_mark(event.x, event.y)

    def on_right_drag(self, event):
        self.canvas.scan_dragto(event.x, event.y, gain=1)


# --- Entry point -----------------------------------------------------------
def main():
    app = PDFBlockExtractorGUI()
    app.mainloop()

if __name__ == "__main__":
    main()
