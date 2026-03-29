# watermark_studio.py
# Standalone watermark designer — companion to Image Processor Elf (v3+)
# Previews your watermark live on a test image; saves settings to image_sorter.json
# so the main app picks them up automatically.
#
# Dependencies: customtkinter, tkinterdnd2, pillow
# Install:      pip install customtkinter tkinterdnd2 pillow
# Run:          pythonw watermark_studio.py

import customtkinter as ctk
from tkinter import filedialog
import tkinterdnd2 as tkdnd
from PIL import Image, ImageChops, ImageOps
import os
import json
import re

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_FILE = os.path.join(_SCRIPT_DIR, "image_sorter.json")


# ── Drag-and-drop enabled root ─────────────────────────────────────────────────

class DnDCTk(ctk.CTk, tkdnd.TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = tkdnd.TkinterDnD._require(self)


# ── Main app ───────────────────────────────────────────────────────────────────

class WatermarkStudio:
    def __init__(self, root):
        self.root = root
        self.root.title("Watermark Studio")
        self.root.geometry("920x600")
        self.root.minsize(780, 500)

        ctk.set_default_color_theme("blue")
        ctk.set_appearance_mode("dark")

        # Internal state
        self.wm_path     = ""
        self.wm_neg_path = ""
        self.test_path   = ""
        self.wm_img      = None   # PIL RGBA — current (after bg removal)
        self._wm_original = None  # PIL RGBA — as loaded, before bg removal
        self.wm_neg_img  = None   # PIL RGBA — negative variant
        self.test_img    = None   # PIL RGBA — never mutated after load
        self.position    = "BR"

        self._preview_job       = None
        self._preview_ctk_img   = None
        self._opacity_val       = 0.30   # 0.0 – 1.0
        self._scale_val         = 0.10   # fraction of image width
        self._padding_val       = 10     # pixels from edge
        self._bg_tolerance_val  = 0      # 0 = off, 1-100 = active

        self._load_settings()
        self._build_ui()
        self._schedule_preview()

        # DnD — whole window is the target; we route by drop location
        self.root.drop_target_register(tkdnd.DND_FILES)
        self.root.dnd_bind('<<Drop>>', self._on_drop)

    # ── JSON helpers ───────────────────────────────────────────────────────────

    def _read_json(self):
        if os.path.exists(JSON_FILE):
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _write_json(self, data):
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())

    def _load_settings(self):
        s = self._read_json().get("settings", {})
        self.wm_path       = s.get("watermark_path",       "")
        self.wm_neg_path   = s.get("watermark_path_negative", "")
        self._opacity_val  = float(s.get("watermark_opacity",  0.30))
        self._scale_val    = float(s.get("watermark_scale",    0.10))
        self._padding_val  = int(s.get("watermark_padding",   10))
        self._bg_tolerance_val = int(s.get("watermark_bg_tolerance", 0))
        self.position      = s.get("watermark_position",   "BR")
        self.test_path     = s.get("watermark_test_image", "")

        if self.wm_path and os.path.exists(self.wm_path):
            try:
                self._wm_original = Image.open(self.wm_path).convert("RGBA")
                self.wm_img = self._wm_original.copy()
                if self._bg_tolerance_val > 0:
                    self._apply_bg_removal()
            except Exception:
                self._wm_original = None
                self.wm_img = None

        if self.wm_neg_path and os.path.exists(self.wm_neg_path):
            try:
                self.wm_neg_img = Image.open(self.wm_neg_path).convert("RGBA")
            except Exception:
                self.wm_neg_img = None

        if self.test_path and os.path.exists(self.test_path):
            try:
                self.test_img = Image.open(self.test_path).convert("RGBA")
            except Exception:
                self.test_img = None

    def _save_settings(self):
        data = self._read_json()
        s = data.get("settings", {})
        s.update({
            "watermark_path":           self.wm_path,
            "watermark_path_negative":  self.wm_neg_path,
            "watermark_opacity":        round(self._opacity_val, 4),
            "watermark_scale":          round(self._scale_val,   4),
            "watermark_padding":        int(self._padding_val),
            "watermark_bg_tolerance":   int(self._bg_tolerance_val),
            "watermark_position":       self.position,
            "watermark_test_image":     self.test_path,
        })
        data["settings"] = s
        self._write_json(data)

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=0)

        self._build_left_panel()
        self._build_right_panel()
        self._build_status_bar()

        self.root.bind("<Configure>", self._on_resize)

    # ── Left control panel ─────────────────────────────────────────────────────

    def _build_left_panel(self):
        left = ctk.CTkFrame(self.root, width=268, corner_radius=0,
                            fg_color=("gray90", "gray13"))
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)

        inner = ctk.CTkScrollableFrame(left, fg_color="transparent")
        inner.pack(fill="both", expand=True)

        # App title
        ctk.CTkLabel(
            inner, text="WATERMARK STUDIO",
            font=ctk.CTkFont(family="Courier New", size=13, weight="bold"),
            text_color=("#F5A623", "#F5A623")
        ).pack(anchor="w", padx=14, pady=(14, 12))

        # Watermark file — dedicated drop zone
        self._section_label(inner, "WATERMARK FILE")
        self.wm_drop_zone = ctk.CTkFrame(
            inner, height=48, corner_radius=8,
            border_width=2, border_color=("#F5A623", "#F5A623"),
            fg_color=("gray82", "gray18")
        )
        self.wm_drop_zone.pack(fill="x", padx=10, pady=(2, 2))
        self.wm_drop_zone.pack_propagate(False)
        self.wm_path_label = ctk.CTkLabel(
            self.wm_drop_zone,
            text=self._fmt_path(self.wm_path) or "Drop watermark here",
            font=ctk.CTkFont(family="Courier New", size=9),
            text_color=("gray40", "gray60"),
            wraplength=220, justify="center"
        )
        self.wm_path_label.pack(fill="both", expand=True)

        wm_btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        wm_btn_row.pack(fill="x", padx=10, pady=(2, 10))
        ctk.CTkButton(wm_btn_row, text="Browse", width=66, height=26,
                      command=self._browse_wm).pack(side="left")
        ctk.CTkButton(wm_btn_row, text="✕ Clear", width=66, height=26,
                      fg_color=("gray70", "gray30"),
                      hover_color=("gray60", "gray40"),
                      command=self._clear_wm).pack(side="right")

        # Test image — dedicated drop zone
        self._section_label(inner, "TEST IMAGE")
        self.test_drop_zone = ctk.CTkFrame(
            inner, height=48, corner_radius=8,
            border_width=2, border_color=("#3B8ED0", "#3B8ED0"),
            fg_color=("gray82", "gray18")
        )
        self.test_drop_zone.pack(fill="x", padx=10, pady=(2, 2))
        self.test_drop_zone.pack_propagate(False)
        self.test_path_label = ctk.CTkLabel(
            self.test_drop_zone,
            text=self._fmt_path(self.test_path) or "Drop test image here",
            font=ctk.CTkFont(family="Courier New", size=9),
            text_color=("gray40", "gray60"),
            wraplength=220, justify="center"
        )
        self.test_path_label.pack(fill="both", expand=True)

        test_btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        test_btn_row.pack(fill="x", padx=10, pady=(2, 10))
        ctk.CTkButton(test_btn_row, text="Browse", width=66, height=26,
                      command=self._browse_test).pack(side="left")
        ctk.CTkButton(test_btn_row, text="✕ Clear", width=66, height=26,
                      fg_color=("gray70", "gray30"),
                      hover_color=("gray60", "gray40"),
                      command=self._clear_test).pack(side="right")

        # Opacity slider
        self._section_label(inner, "OPACITY")
        self.opacity_lbl = self._val_label(inner, f"{int(self._opacity_val * 100)}%")
        self.opacity_slider = ctk.CTkSlider(inner, from_=0, to=100,
                                            command=self._on_opacity)
        self.opacity_slider.pack(fill="x", padx=10, pady=(0, 10))
        self.opacity_slider.set(self._opacity_val * 100)

        # Scale slider
        self._section_label(inner, "SCALE  (% of image width)")
        self.scale_lbl = self._val_label(inner, f"{int(self._scale_val * 100)}%")
        self.scale_slider = ctk.CTkSlider(inner, from_=1, to=40,
                                          command=self._on_scale)
        self.scale_slider.pack(fill="x", padx=10, pady=(0, 10))
        self.scale_slider.set(self._scale_val * 100)

        # Padding slider
        self._section_label(inner, "EDGE PADDING  (px)")
        self.pad_lbl = self._val_label(inner, f"{int(self._padding_val)}px")
        self.pad_slider = ctk.CTkSlider(inner, from_=0, to=120,
                                        command=self._on_padding)
        self.pad_slider.pack(fill="x", padx=10, pady=(0, 10))
        self.pad_slider.set(self._padding_val)

        # Position picker (2×2 grid of corner buttons)
        self._section_label(inner, "POSITION")
        pos_grid = ctk.CTkFrame(inner, fg_color="transparent")
        pos_grid.pack(padx=10, pady=(4, 10))
        self._pos_btns = {}
        for key, r, c in [("TL", 0, 0), ("TR", 0, 1), ("BL", 1, 0), ("BR", 1, 1)]:
            selected = (key == self.position)
            btn = ctk.CTkButton(
                pos_grid, text=key, width=56, height=38,
                font=ctk.CTkFont(family="Courier New", size=12, weight="bold"),
                fg_color=("#F5A623", "#F5A623") if selected else ("gray75", "gray25"),
                text_color="gray10" if selected else ("gray20", "gray80"),
                hover_color=("#D4891E", "#D4891E") if selected else ("gray65", "gray35"),
                command=lambda k=key: self._set_position(k)
            )
            btn.grid(row=r, column=c, padx=4, pady=4)
            self._pos_btns[key] = btn

        # ── Background removal ──
        self._section_label(inner, "BACKGROUND REMOVAL")
        self.bg_tol_lbl = self._val_label(
            inner, f"{int(self._bg_tolerance_val)}%" if self._bg_tolerance_val > 0 else "off")
        self.bg_tol_slider = ctk.CTkSlider(inner, from_=0, to=100,
                                           command=self._on_bg_tolerance)
        self.bg_tol_slider.pack(fill="x", padx=10, pady=(0, 4))
        self.bg_tol_slider.set(self._bg_tolerance_val)

        ctk.CTkButton(
            inner, text="Save Cleaned PNG", height=28,
            font=ctk.CTkFont(size=11),
            command=self._save_cleaned_wm
        ).pack(fill="x", padx=10, pady=(0, 10))

        # ── Negative variant ──
        self._section_label(inner, "NEGATIVE VARIANT")
        self.neg_path_label = ctk.CTkLabel(
            inner,
            text=self._fmt_path(self.wm_neg_path) or "Not generated yet",
            font=ctk.CTkFont(family="Courier New", size=9),
            text_color=("gray40", "gray60"),
            wraplength=220, justify="left", anchor="w"
        )
        self.neg_path_label.pack(anchor="w", padx=14, pady=(2, 4))

        neg_btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        neg_btn_row.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(neg_btn_row, text="Generate", width=90, height=26,
                      command=self._generate_negative).pack(side="left")
        ctk.CTkButton(neg_btn_row, text="✕ Clear", width=66, height=26,
                      fg_color=("gray70", "gray30"),
                      hover_color=("gray60", "gray40"),
                      command=self._clear_negative).pack(side="right")

        # Divider
        ctk.CTkFrame(inner, height=1,
                     fg_color=("gray70", "gray30")).pack(fill="x", padx=10, pady=(6, 12))

        # Save button (primary)
        ctk.CTkButton(
            inner, text="💾  Save to JSON",
            height=38,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=("#F5A623", "#F5A623"),
            text_color="gray10",
            hover_color=("#D4891E", "#D4891E"),
            command=self._save_and_confirm
        ).pack(fill="x", padx=10, pady=(0, 6))

        # Export button (secondary)
        ctk.CTkButton(
            inner, text="📤  Export Test Render",
            height=32,
            font=ctk.CTkFont(size=11),
            command=self._export_render
        ).pack(fill="x", padx=10, pady=(0, 14))

    def _section_label(self, parent, text):
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(family="Courier New", size=9, weight="bold"),
            text_color=("gray50", "gray50")
        ).pack(anchor="w", padx=14, pady=(8, 2))

    def _val_label(self, parent, text):
        """Right-aligned amber value readout above a slider."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(0, 2))
        lbl = ctk.CTkLabel(
            row, text=text,
            font=ctk.CTkFont(family="Courier New", size=13, weight="bold"),
            text_color=("#F5A623", "#F5A623")
        )
        lbl.pack(side="right")
        return lbl

    # ── Right preview panel ────────────────────────────────────────────────────

    def _build_right_panel(self):
        right = ctk.CTkFrame(self.root, corner_radius=0,
                             fg_color=("gray85", "gray10"))
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=0)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # Header bar
        hdr = ctk.CTkFrame(right, height=38, corner_radius=0,
                           fg_color=("gray80", "gray16"))
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="LIVE PREVIEW",
                     font=ctk.CTkFont(family="Courier New", size=11, weight="bold"),
                     text_color=("gray40", "gray55")
        ).pack(side="left", padx=14, pady=0)
        self.info_label = ctk.CTkLabel(
            hdr, text="",
            font=ctk.CTkFont(family="Courier New", size=9),
            text_color=("gray50", "gray50")
        )
        self.info_label.pack(side="right", padx=14)

        # Preview image label (fills remaining space)
        self.preview_label = ctk.CTkLabel(
            right,
            text="Load a watermark and a test image to begin\n\n"
                 "Browse using the panel on the left,\nor drop files anywhere on this window.",
            font=ctk.CTkFont(family="Courier New", size=12),
            text_color=("gray55", "gray45"),
            corner_radius=0,
            fg_color=("gray78", "gray17")
        )
        self.preview_label.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

    def _build_status_bar(self):
        self.status_bar = ctk.CTkLabel(
            self.root, text="",
            font=ctk.CTkFont(family="Courier New", size=10),
            text_color=("#4CAF50", "#4CAF50"),
            height=26, anchor="w"
        )
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 4))

    # ── Slider callbacks ───────────────────────────────────────────────────────

    def _on_opacity(self, val):
        self._opacity_val = float(val) / 100.0
        self.opacity_lbl.configure(text=f"{int(val)}%")
        self._schedule_preview()

    def _on_scale(self, val):
        self._scale_val = float(val) / 100.0
        self.scale_lbl.configure(text=f"{int(val)}%")
        self._schedule_preview()

    def _on_padding(self, val):
        self._padding_val = int(val)
        self.pad_lbl.configure(text=f"{int(val)}px")
        self._schedule_preview()

    def _set_position(self, key):
        self.position = key
        for k, btn in self._pos_btns.items():
            if k == key:
                btn.configure(
                    fg_color=("#F5A623", "#F5A623"),
                    text_color="gray10",
                    hover_color=("#D4891E", "#D4891E")
                )
            else:
                btn.configure(
                    fg_color=("gray75", "gray25"),
                    text_color=("gray20", "gray80"),
                    hover_color=("gray65", "gray35")
                )
        self._schedule_preview()

    def _on_resize(self, event):
        if event.widget is self.root:
            self._schedule_preview()

    # ── Browse / load helpers ──────────────────────────────────────────────────

    def _browse_wm(self):
        path = filedialog.askopenfilename(
            title="Select Watermark Image",
            filetypes=[("PNG images", "*.png"),
                       ("All images", "*.png *.jpg *.jpeg *.bmp *.gif"),
                       ("All files", "*.*")]
        )
        if path:
            self._load_wm(path)

    def _browse_test(self):
        path = filedialog.askopenfilename(
            title="Select Test Image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp"),
                       ("All files", "*.*")]
        )
        if path:
            self._load_test(path)

    def _clear_wm(self):
        self.wm_img = None
        self._wm_original = None
        self.wm_neg_img = None
        self.wm_path = ""
        self.wm_neg_path = ""
        self.wm_path_label.configure(text="Drop watermark here")
        if hasattr(self, 'neg_path_label'):
            self.neg_path_label.configure(text="Not generated yet")
        self._schedule_preview()
        self._status("Watermark cleared")

    def _clear_test(self):
        self.test_img = None
        self.test_path = ""
        self.test_path_label.configure(text="Drop test image here")
        self._schedule_preview()
        self._status("Test image cleared")

    # ── Background removal ────────────────────────────────────────────────────

    def _on_bg_tolerance(self, val):
        self._bg_tolerance_val = int(val)
        label = f"{int(val)}%" if val > 0 else "off"
        self.bg_tol_lbl.configure(text=label)
        if self._wm_original:
            self.wm_img = self._wm_original.copy()
            if self._bg_tolerance_val > 0:
                self._apply_bg_removal()
        self._schedule_preview()

    def _apply_bg_removal(self):
        """Remove background from wm_img based on corner-sampled color."""
        if self._wm_original is None:
            return
        img = self._wm_original.copy()
        px = img.load()
        w, h = img.size

        # Sample corners (and one pixel inward) to detect background color
        samples = []
        for sx, sy in [(0, 0), (w-1, 0), (0, h-1), (w-1, h-1),
                        (1, 1), (w-2, 1), (1, h-2), (w-2, h-2)]:
            if 0 <= sx < w and 0 <= sy < h:
                samples.append(px[sx, sy][:3])
        bg_r = sum(s[0] for s in samples) // len(samples)
        bg_g = sum(s[1] for s in samples) // len(samples)
        bg_b = sum(s[2] for s in samples) // len(samples)

        # Use PIL channel operations for speed
        bg_flat = Image.new('RGB', img.size, (bg_r, bg_g, bg_b))
        diff = ImageChops.difference(img.convert('RGB'), bg_flat)
        # Max channel difference as distance metric
        r_ch, g_ch, b_ch = diff.split()
        dist = ImageChops.lighter(ImageChops.lighter(r_ch, g_ch), b_ch)

        # Build alpha: transparent where close to bg, gradient at edges
        tol = self._bg_tolerance_val * 2.55          # map 0-100 → 0-255
        outer = min(tol * 1.5, 255)
        span = max(outer - tol, 1)

        new_alpha = dist.point(lambda d: 0 if d <= tol else
                               (int((d - tol) / span * 255) if d < outer else 255))

        # Combine with original alpha (preserve existing transparency)
        orig_alpha = img.split()[3]
        final_alpha = ImageChops.darker(orig_alpha, new_alpha)

        r, g, b, _ = img.split()
        self.wm_img = Image.merge('RGBA', (r, g, b, final_alpha))

    def _save_cleaned_wm(self):
        """Save the bg-removed watermark to a new PNG file."""
        if not self.wm_img:
            self._status("Load a watermark first.", error=True)
            return
        init_name = (os.path.splitext(os.path.basename(self.wm_path))[0] + "_clean.png"
                     if self.wm_path else "watermark_clean.png")
        path = filedialog.asksaveasfilename(
            title="Save Cleaned Watermark",
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialfile=init_name
        )
        if not path:
            return
        try:
            self.wm_img.save(path)
            # Point at the cleaned file going forward
            self.wm_path = path
            self._wm_original = self.wm_img.copy()
            self._bg_tolerance_val = 0
            self.bg_tol_slider.set(0)
            self.bg_tol_lbl.configure(text="off")
            self.wm_path_label.configure(text=self._fmt_path(path))
            self._status(f"Saved cleaned watermark: {os.path.basename(path)}")
        except Exception as e:
            self._status(f"Save failed: {e}", error=True)

    # ── Negative variant ──────────────────────────────────────────────────────

    def _generate_negative(self):
        """Invert RGB channels of current watermark, keep alpha. Save to disk."""
        if not self.wm_img:
            self._status("Load a watermark first.", error=True)
            return

        # Invert RGB, preserve alpha
        r, g, b, a = self.wm_img.split()
        rgb_inv = ImageOps.invert(Image.merge('RGB', (r, g, b)))
        self.wm_neg_img = Image.merge('RGBA', (*rgb_inv.split(), a))

        # Auto-generate save path next to current watermark
        if self.wm_path:
            base, _ = os.path.splitext(self.wm_path)
            neg_path = base + "_negative.png"
        else:
            neg_path = os.path.join(_SCRIPT_DIR, "watermark_negative.png")

        try:
            self.wm_neg_img.save(neg_path)
            self.wm_neg_path = neg_path
            self.neg_path_label.configure(text=self._fmt_path(neg_path))
            self._schedule_preview()
            self._status(f"Negative saved: {os.path.basename(neg_path)}")
        except Exception as e:
            self._status(f"Failed to save negative: {e}", error=True)

    def _clear_negative(self):
        self.wm_neg_img = None
        self.wm_neg_path = ""
        self.neg_path_label.configure(text="Not generated yet")
        self._schedule_preview()
        self._status("Negative variant cleared")

    # ── Region luminance helper ───────────────────────────────────────────────

    def _region_luminance(self, base_img):
        """Mean luminance (0-255) of the region where the watermark would land."""
        w, h = base_img.size
        new_wm_w = max(1, int(w * self._scale_val))
        ratio = new_wm_w / self.wm_img.width
        new_wm_h = max(1, int(self.wm_img.height * ratio))

        pad = int(self._padding_val)
        x, y = {
            "TL": (pad, pad),
            "TR": (w - new_wm_w - pad, pad),
            "BL": (pad, h - new_wm_h - pad),
            "BR": (w - new_wm_w - pad, h - new_wm_h - pad),
        }[self.position]

        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w, x + new_wm_w), min(h, y + new_wm_h)
        region = base_img.crop((x1, y1, x2, y2)).convert("L")
        data = region.tobytes()
        return sum(data) / len(data) if data else 128

    def _load_wm(self, path):
        try:
            self._wm_original = Image.open(path).convert("RGBA")
            self.wm_img = self._wm_original.copy()
            self.wm_path = path
            # Reset negative when loading a new watermark
            self.wm_neg_img = None
            self.wm_neg_path = ""
            if hasattr(self, 'neg_path_label'):
                self.neg_path_label.configure(text="Not generated yet")
            # Apply bg removal if tolerance is set
            if self._bg_tolerance_val > 0:
                self._apply_bg_removal()
            self.wm_path_label.configure(text=self._fmt_path(path))
            self._schedule_preview()
            self._status(f"Watermark loaded — {os.path.basename(path)}")
        except Exception as e:
            self._status(f"Could not load watermark: {e}", error=True)

    def _load_test(self, path):
        try:
            self.test_img  = Image.open(path).convert("RGBA")
            self.test_path = path
            self.test_path_label.configure(text=self._fmt_path(path))
            self._schedule_preview()
            self._status(f"Test image loaded — {os.path.basename(path)}")
        except Exception as e:
            self._status(f"Could not load image: {e}", error=True)

    # ── Drag-and-drop handler ──────────────────────────────────────────────────

    def _is_over_widget(self, widget):
        """Check if the mouse pointer is over the widget or any of its children."""
        x = self.root.winfo_pointerx()
        y = self.root.winfo_pointery()
        target = self.root.winfo_containing(x, y)
        if target is None:
            return False
        w = target
        while w is not None:
            if w is widget:
                return True
            try:
                w = w.master
            except AttributeError:
                break
        return False

    def _on_drop(self, event):
        files = []
        for m in re.findall(r'(?:\{([^\}]*)\}|([^\s]+))', event.data):
            p = m[0] or m[1]
            if p:
                files.append(p)

        # Filter to image files
        images = [p for p in files
                  if os.path.splitext(p)[1].lower() in ('.png', '.jpg', '.jpeg', '.bmp', '.gif')]
        if not images:
            return

        # Route based on drop location (first image file only)
        path = images[0]
        if self._is_over_widget(self.wm_drop_zone):
            self._load_wm(path)
        elif self._is_over_widget(self.test_drop_zone):
            self._load_test(path)
        else:
            # Anywhere else (including preview area) → test image
            self._load_test(path)

    # ── Preview compositing ────────────────────────────────────────────────────

    def _schedule_preview(self):
        """Debounce: only refresh 80 ms after the last change."""
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(80, self._refresh_preview)

    def _refresh_preview(self):
        self._preview_job = None

        if not self.test_img:
            self.preview_label.configure(
                image=None,
                text="Load a watermark and a test image to begin\n\n"
                     "Browse or drop files into the\ncolored zones on the left panel."
            )
            self._preview_ctk_img = None
            self.info_label.configure(text="")
            return

        # Auto-select watermark variant if both exist
        chosen_wm = self.wm_img
        variant_tag = ""
        if self.wm_img and self.wm_neg_img:
            lum = self._region_luminance(self.test_img)
            if lum > 128:
                chosen_wm = self.wm_img
                variant_tag = "  ·  auto: dark wm"
            else:
                chosen_wm = self.wm_neg_img
                variant_tag = "  ·  auto: light wm"

        composited = self._composite(self.test_img, chosen_wm)

        # Scale to fit the preview label widget
        pw = max(self.preview_label.winfo_width(),  100)
        ph = max(self.preview_label.winfo_height(), 100)
        iw, ih = composited.size
        ratio   = min(pw / iw, ph / ih, 1.0)
        dw = max(1, int(iw * ratio))
        dh = max(1, int(ih * ratio))
        display = composited.resize((dw, dh), Image.Resampling.LANCZOS)

        self._preview_ctk_img = ctk.CTkImage(
            light_image=display, dark_image=display, size=(dw, dh)
        )
        self.preview_label.configure(image=self._preview_ctk_img, text="")

        wm_label = f"no watermark" if not self.wm_img else \
                   f"scale {int(self._scale_val * 100)}%  ·  opacity {int(self._opacity_val * 100)}%  ·  {self.position}  ·  pad {int(self._padding_val)}px{variant_tag}"
        self.info_label.configure(text=f"{iw}×{ih}  ·  {wm_label}")

    def _composite(self, base_img, wm_img):
        """Composite watermark onto base. Returns new PIL image; never mutates originals."""
        result = base_img.copy().convert("RGBA")
        if wm_img is None:
            return result

        w, h = result.size

        # Scale watermark to target width
        new_wm_w = max(1, int(w * self._scale_val))
        ratio    = new_wm_w / wm_img.width
        new_wm_h = max(1, int(wm_img.height * ratio))
        wm = wm_img.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)

        # Apply opacity — multiply alpha channel by the opacity fraction
        r, g, b, a = wm.split()
        a = a.point(lambda p: int(p * self._opacity_val))
        wm = Image.merge("RGBA", (r, g, b, a))

        # Resolve corner position
        pad = int(self._padding_val)
        x, y = {
            "TL": (pad,                       pad),
            "TR": (w - wm.width - pad,        pad),
            "BL": (pad,                       h - wm.height - pad),
            "BR": (w - wm.width - pad,        h - wm.height - pad),
        }[self.position]

        result.paste(wm, (x, y), wm)
        return result

    # ── Save / export ──────────────────────────────────────────────────────────

    def _save_and_confirm(self):
        try:
            self._save_settings()
            self._status(
                f"Saved → opacity {int(self._opacity_val * 100)}%  "
                f"scale {int(self._scale_val * 100)}%  "
                f"pos {self.position}  "
                f"pad {int(self._padding_val)}px  ·  "
                f"Image Processor Elf will use these settings automatically."
            )
        except Exception as e:
            self._status(f"Save failed: {e}", error=True)

    def _export_render(self):
        if not self.test_img:
            self._status("Load a test image first.", error=True)
            return

        path = filedialog.asksaveasfilename(
            title="Save Test Render",
            defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg")]
        )
        if not path:
            return

        try:
            composited = self._composite(self.test_img, self.wm_img)
            ext = os.path.splitext(path)[1].lower()
            if ext in ('.jpg', '.jpeg'):
                composited.convert("RGB").save(path, quality=95)
            else:
                composited.save(path)
            self._status(f"Exported: {os.path.basename(path)}")
        except Exception as e:
            self._status(f"Export failed: {e}", error=True)

    # ── Utilities ──────────────────────────────────────────────────────────────

    def _fmt_path(self, path):
        if not path:
            return ""
        return ("…" + path[-27:]) if len(path) > 30 else path

    def _status(self, msg, error=False):
        color = "#E74C3C" if error else "#4CAF50"
        self.status_bar.configure(text=msg, text_color=color)
        self.root.after(8000, lambda: self.status_bar.configure(text=""))


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = DnDCTk()
    app  = WatermarkStudio(root)
    root.mainloop()
