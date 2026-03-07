# combined_image_processorv3.py
# Modern UI rewrite using CustomTkinter with dark/light mode toggle.
# Dependencies: customtkinter, tkinterdnd2, pillow, piexif, portalocker
# Install: pip install customtkinter tkinterdnd2 pillow piexif portalocker
# Run: pythonw combined_image_processorv3.py

import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinterdnd2 as tkdnd
from PIL import Image, PngImagePlugin
import os
import shutil
import glob
import json
import re
import portalocker
import piexif


class DnDCTk(ctk.CTk, tkdnd.TkinterDnD.DnDWrapper):
    """CTk window with drag-and-drop support."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = tkdnd.TkinterDnD._require(self)


class ImageProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Processor Elf")
        self.root.geometry("300x750")
        self.root.minsize(260, 620)

        ctk.set_default_color_theme("blue")
        ctk.set_appearance_mode("dark")
        self.is_dark = True

        self.json_file = "image_sorter.json"
        self.data = self.load_json()

        self.website_value = "axly.com"
        self.copyright_value = "\u00a9 2025 axly.com"

        # Watermark path — loaded from settings
        self.watermark_path = ""
        self._wm_ctk_image = None

        # Field toggle vars (which naming components are active)
        self.use_genre = ctk.BooleanVar(value=True)
        self.use_subgenre = ctk.BooleanVar(value=True)
        self.use_size = ctk.BooleanVar(value=True)
        self.use_desc = ctk.BooleanVar(value=True)
        self.use_tag = ctk.BooleanVar(value=True)
        self._load_settings()

        self.create_ui()
        self._update_field_states()
        self.update_drop_label()
        self._load_watermark_preview()

        self.root.drop_target_register(tkdnd.DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.on_drop)

    # ── JSON persistence ──────────────────────────────────────────────

    def load_json(self):
        if os.path.exists(self.json_file):
            with open(self.json_file, 'r') as f:
                portalocker.lock(f, portalocker.LOCK_SH)
                data = json.load(f)
                portalocker.unlock(f)
                return data
        return {
            "presets": [],
            "genres": [],
            "subgenres": [],
            "descs": ["fe", "M", "Ob"],
            "tags": ["N", "S", "WC", "OP", "Photo"]
        }

    def save_json(self):
        with open(self.json_file, 'w') as f:
            portalocker.lock(f, portalocker.LOCK_EX)
            json.dump(self.data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
            portalocker.unlock(f)

    # ── Settings persistence ──────────────────────────────────────────

    def _load_settings(self):
        settings = self.data.get("settings", {})
        self.use_genre.set(settings.get("use_genre", True))
        self.use_subgenre.set(settings.get("use_subgenre", True))
        self.use_size.set(settings.get("use_size", True))
        self.use_desc.set(settings.get("use_desc", True))
        self.use_tag.set(settings.get("use_tag", True))
        self.watermark_path = settings.get("watermark_path", "")

    def _save_settings(self):
        self.data = self.load_json()
        self.data["settings"] = {
            "use_genre": self.use_genre.get(),
            "use_subgenre": self.use_subgenre.get(),
            "use_size": self.use_size.get(),
            "use_desc": self.use_desc.get(),
            "use_tag": self.use_tag.get(),
            "watermark_path": self.watermark_path,
        }
        self.save_json()

    # ── UI construction ───────────────────────────────────────────────

    def create_ui(self):
        container = ctk.CTkFrame(self.root, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=8, pady=8)

        # ── Header ──
        header = ctk.CTkFrame(container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            header, text="Image Processor Elf",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(side="left")

        self.mode_btn = ctk.CTkButton(
            header, text="\u2600", width=32, height=32,
            font=ctk.CTkFont(size=16), command=self.toggle_mode
        )
        self.mode_btn.pack(side="right")

        ctk.CTkButton(
            header, text="\u2699", width=32, height=32,
            font=ctk.CTkFont(size=16), command=self._open_settings
        ).pack(side="right", padx=(0, 4))

        # ── Naming section ──
        naming = ctk.CTkFrame(container)
        naming.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            naming, text="Naming",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=8, pady=(6, 2))

        self.genre_combo, self.genre_btn = self._combo_row(naming, "Genre", sorted(self.data["genres"]), self.add_genre)
        self.subgenre_combo, self.subgenre_btn = self._combo_row(naming, "Subgenre", sorted(self.data["subgenres"]), self.add_subgenre)
        self.desc_combo, self.desc_btn = self._combo_row(naming, "Desc", sorted(self.data["descs"]), self.add_desc)
        self.tag_combo, self.tag_btn = self._combo_row(naming, "Tag", sorted(self.data["tags"]), self.add_tag)

        # ── Options section ──
        options = ctk.CTkFrame(container)
        options.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            options, text="Options",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=8, pady=(6, 2))

        self.remove_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(options, text="Remove Metadata", variable=self.remove_var).pack(anchor="w", padx=12, pady=2)

        self.add_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(options, text="Add Metadata", variable=self.add_var).pack(anchor="w", padx=12, pady=2)

        # Watermark row: checkbox on left, preview on right
        wm_row = ctk.CTkFrame(options, fg_color="transparent")
        wm_row.pack(fill="x", padx=12, pady=(2, 8))

        self.watermark_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(wm_row, text="Add Watermark", variable=self.watermark_var).pack(side="left")

        # Watermark preview — click or drop to set
        self.wm_drop_frame = ctk.CTkFrame(
            wm_row, width=64, height=64,
            corner_radius=8, border_width=1,
            border_color="#3B8ED0"
        )
        self.wm_drop_frame.pack(side="right", padx=(8, 0))
        self.wm_drop_frame.pack_propagate(False)

        self.wm_preview_label = ctk.CTkLabel(
            self.wm_drop_frame, text="Drop or\nclick",
            font=ctk.CTkFont(size=9), cursor="hand2"
        )
        self.wm_preview_label.pack(fill="both", expand=True)
        self.wm_preview_label.bind("<Button-1>", lambda _e: self._browse_watermark())
        self.wm_drop_frame.bind("<Button-1>", lambda _e: self._browse_watermark())

        # ── Target folder section ──
        folder_sec = ctk.CTkFrame(container)
        folder_sec.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            folder_sec, text="Target Folder",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=8, pady=(6, 2))

        folder_row = ctk.CTkFrame(folder_sec, fg_color="transparent")
        folder_row.pack(fill="x", padx=8, pady=(0, 8))

        self.folder_entry = ctk.CTkEntry(folder_row, placeholder_text="Select folder...")
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            folder_row, text="Browse", width=60, command=self.browse_folder
        ).pack(side="right")

        # ── Presets section ──
        presets_sec = ctk.CTkFrame(container)
        presets_sec.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(
            presets_sec, text="Presets",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=8, pady=(6, 2))

        self.preset_combo = ctk.CTkComboBox(presets_sec, values=self.get_sorted_preset_names())
        self.preset_combo.pack(fill="x", padx=8, pady=(0, 4))
        self.preset_combo.set("")

        btn_row = ctk.CTkFrame(presets_sec, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(0, 8))

        ctk.CTkButton(btn_row, text="Load", width=65, command=self.load_preset).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="Save", width=65, command=self.save_preset).pack(side="left", padx=(0, 4))
        ctk.CTkButton(btn_row, text="Refresh", width=65, command=self.refresh_from_json).pack(side="left")

        # ── Status label ──
        self.status_label = ctk.CTkLabel(
            container, text="", font=ctk.CTkFont(size=11),
            text_color="#4CAF50"
        )
        self.status_label.pack(pady=(0, 4))

        # ── Drop zone ──
        self.drop_frame = ctk.CTkFrame(
            container, corner_radius=12,
            border_width=2, border_color="#3B8ED0"
        )
        self.drop_frame.pack(fill="both", expand=True, pady=(0, 2))

        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="Drag & Drop\nImages Here!",
            font=ctk.CTkFont(size=16, weight="bold"),
            wraplength=220
        )
        self.drop_label.pack(fill="both", expand=True, padx=10, pady=20)

    def _combo_row(self, parent, label_text, values, add_cmd):
        """Label + ComboBox + '+' button row. Returns (combo, btn)."""
        ctk.CTkLabel(
            parent, text=label_text, font=ctk.CTkFont(size=11)
        ).pack(anchor="w", padx=10, pady=(4, 0))

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 2))

        combo = ctk.CTkComboBox(
            row, values=values,
            command=lambda _v: self.update_drop_label()
        )
        combo.pack(side="left", fill="x", expand=True, padx=(0, 4))
        combo.set("")
        combo.bind("<KeyRelease>", lambda _e: self.update_drop_label())

        btn = ctk.CTkButton(row, text="+", width=28, height=28, command=add_cmd)
        btn.pack(side="right")

        return combo, btn

    # ── Watermark management ──────────────────────────────────────────

    def _browse_watermark(self):
        path = filedialog.askopenfilename(
            title="Select Watermark Image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All files", "*.*")]
        )
        if path:
            self.watermark_path = path
            self._save_settings()
            self._load_watermark_preview()
            self._show_status("Watermark set!")

    def _load_watermark_preview(self):
        if self.watermark_path and os.path.exists(self.watermark_path):
            try:
                pil_img = Image.open(self.watermark_path)
                pil_img.thumbnail((56, 56), Image.Resampling.LANCZOS)
                self._wm_ctk_image = ctk.CTkImage(
                    light_image=pil_img, dark_image=pil_img,
                    size=pil_img.size
                )
                self.wm_preview_label.configure(image=self._wm_ctk_image, text="")
            except Exception:
                self._wm_ctk_image = None
                self.wm_preview_label.configure(image=None, text="Invalid\nimage")
        else:
            self._wm_ctk_image = None
            self.wm_preview_label.configure(image=None, text="Drop or\nclick")

    def _is_over_widget(self, widget):
        """Check if the mouse pointer is over the widget or any of its children."""
        x = self.root.winfo_pointerx()
        y = self.root.winfo_pointery()
        target = self.root.winfo_containing(x, y)
        if target is None:
            return False
        # Walk up the widget hierarchy to see if we're inside the target widget
        w = target
        while w is not None:
            if w is widget:
                return True
            try:
                w = w.master
            except AttributeError:
                break
        return False

    def _handle_watermark_drop(self, event):
        """Handle an image dropped on the watermark preview area."""
        files = []
        matches = re.findall(r'(?:\{([^\}]*)\}|([^\s]+))', event.data)
        for m in matches:
            path = m[0] or m[1]
            if path:
                files.append(path)

        if not files:
            return

        path = files[0]
        ext = os.path.splitext(path)[1].lower()
        if ext in ('.png', '.jpg', '.jpeg', '.gif', '.bmp'):
            self.watermark_path = path
            self._save_settings()
            self._load_watermark_preview()
            self._show_status("Watermark set!")
        else:
            self._show_status("Not an image file", color="#E74C3C")

    # ── Settings dialog ───────────────────────────────────────────────

    def _open_settings(self):
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Settings")
        dialog.geometry("300x280")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.transient(self.root)

        ctk.CTkLabel(
            dialog, text="Filename Components",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(pady=(15, 10))

        preview_label = ctk.CTkLabel(
            dialog, text="", font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60")
        )

        def on_change():
            self._update_field_states()
            update_preview()

        ctk.CTkCheckBox(dialog, text="Genre", variable=self.use_genre, command=on_change).pack(anchor="w", padx=20, pady=3)
        ctk.CTkCheckBox(dialog, text="Subgenre", variable=self.use_subgenre, command=on_change).pack(anchor="w", padx=20, pady=3)
        ctk.CTkCheckBox(dialog, text="Size  (auto-detected)", variable=self.use_size, command=on_change).pack(anchor="w", padx=20, pady=3)
        ctk.CTkCheckBox(dialog, text="Desc", variable=self.use_desc, command=on_change).pack(anchor="w", padx=20, pady=3)
        ctk.CTkCheckBox(dialog, text="Tag", variable=self.use_tag, command=on_change).pack(anchor="w", padx=20, pady=3)

        preview_label.pack(pady=(12, 5))

        def update_preview():
            parts = []
            if self.use_genre.get():
                parts.append("Genre")
            if self.use_subgenre.get():
                parts.append("Sub")
            if self.use_size.get():
                parts.append("WxH")
            if self.use_desc.get():
                parts.append("Desc")
            if self.use_tag.get():
                parts.append("Tag")
            parts.append("001")
            preview_label.configure(text="Preview:  " + ".".join(parts) + ".jpg")

        update_preview()

        def on_close():
            self._save_settings()
            dialog.destroy()

        ctk.CTkButton(dialog, text="Close", width=100, command=on_close).pack(pady=10)
        dialog.protocol("WM_DELETE_WINDOW", on_close)

    def _update_field_states(self):
        """Enable/disable combo rows based on settings toggles."""
        fields = [
            (self.genre_combo, self.genre_btn, self.use_genre),
            (self.subgenre_combo, self.subgenre_btn, self.use_subgenre),
            (self.desc_combo, self.desc_btn, self.use_desc),
            (self.tag_combo, self.tag_btn, self.use_tag),
        ]
        for combo, btn, var in fields:
            state = "normal" if var.get() else "disabled"
            combo.configure(state=state)
            btn.configure(state=state)
        self.update_drop_label()

    # ── Dark / light toggle ───────────────────────────────────────────

    def toggle_mode(self):
        self.is_dark = not self.is_dark
        ctk.set_appearance_mode("dark" if self.is_dark else "light")
        self.mode_btn.configure(text="\u2600" if self.is_dark else "\U0001f319")

    # ── Status helper ─────────────────────────────────────────────────

    def _show_status(self, text, color="#4CAF50", duration=3000):
        self.status_label.configure(text=text, text_color=color)
        self.root.after(duration, lambda: self.status_label.configure(text=""))

    # ── Add-to-list handlers ──────────────────────────────────────────

    def add_genre(self):
        self.data = self.load_json()
        genre = self.genre_combo.get().strip()
        if genre and genre not in self.data["genres"]:
            self.data["genres"].append(genre)
            self.data["genres"].sort()
            self.genre_combo.configure(values=sorted(self.data["genres"]))
            self.save_json()
            self._show_status(f"Added genre: {genre}")

    def add_subgenre(self):
        self.data = self.load_json()
        subgenre = self.subgenre_combo.get().strip()
        if subgenre and subgenre not in self.data["subgenres"]:
            self.data["subgenres"].append(subgenre)
            self.data["subgenres"].sort()
            self.subgenre_combo.configure(values=sorted(self.data["subgenres"]))
            self.save_json()
            self._show_status(f"Added subgenre: {subgenre}")

    def add_desc(self):
        self.data = self.load_json()
        desc = self.desc_combo.get().strip()
        if desc and desc not in self.data["descs"]:
            self.data["descs"].append(desc)
            self.data["descs"].sort()
            self.desc_combo.configure(values=sorted(self.data["descs"]))
            self.save_json()
            self._show_status(f"Added desc: {desc}")

    def add_tag(self):
        self.data = self.load_json()
        tag = self.tag_combo.get().strip()
        if tag and tag not in self.data["tags"]:
            self.data["tags"].append(tag)
            self.data["tags"].sort()
            self.tag_combo.configure(values=sorted(self.data["tags"]))
            self.save_json()
            self._show_status(f"Added tag: {tag}")

    # ── Refresh / presets ─────────────────────────────────────────────

    def refresh_from_json(self):
        self.data = self.load_json()
        self.genre_combo.configure(values=sorted(self.data["genres"]))
        self.subgenre_combo.configure(values=sorted(self.data["subgenres"]))
        self.desc_combo.configure(values=sorted(self.data["descs"]))
        self.tag_combo.configure(values=sorted(self.data["tags"]))
        self.preset_combo.configure(values=self.get_sorted_preset_names())
        self._load_settings()
        self._update_field_states()
        self._load_watermark_preview()
        self._show_status("Refreshed from JSON!")

    def get_sorted_preset_names(self):
        sorted_presets = sorted(
            self.data["presets"],
            key=lambda p: (
                p.get("genre", "").lower(),
                p.get("subgenre", "").lower(),
                p.get("desc", "").lower(),
                p.get("tag", "").lower()
            )
        )
        return [p["name"] for p in sorted_presets]

    def update_drop_label(self):
        parts = []
        all_filled = True

        if self.use_genre.get():
            val = self.genre_combo.get().strip()
            parts.append(val if val else "Genre")
            if not val:
                all_filled = False
        if self.use_subgenre.get():
            val = self.subgenre_combo.get().strip()
            parts.append(val if val else "Sub")
            if not val:
                all_filled = False
        if self.use_desc.get():
            val = self.desc_combo.get().strip()
            parts.append(val if val else "Desc")
            if not val:
                all_filled = False
        if self.use_tag.get():
            val = self.tag_combo.get().strip()
            parts.append(val if val else "Tag")
            if not val:
                all_filled = False

        if not parts:
            self.drop_label.configure(
                text="001.ext\nDrag & Drop Here!",
                text_color=("gray10", "gray90")
            )
        elif all_filled:
            self.drop_label.configure(
                text=f"{'.'.join(parts)}\nDrag & Drop Here!",
                text_color=("gray10", "gray90")
            )
        else:
            self.drop_label.configure(
                text="Drag & Drop Images Here!\n(Fill enabled fields first)",
                text_color="#E74C3C"
            )

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, folder)

    def load_preset(self):
        self.data = self.load_json()
        name = self.preset_combo.get()
        if not name:
            return
        for preset in self.data["presets"]:
            if preset["name"] == name:
                self.genre_combo.set(preset["genre"])
                self.subgenre_combo.set(preset["subgenre"])
                self.desc_combo.set(preset["desc"])
                self.tag_combo.set(preset["tag"])
                self.folder_entry.delete(0, "end")
                self.folder_entry.insert(0, preset["folder"])
                self.update_drop_label()
                break

    def save_preset(self):
        self.data = self.load_json()
        genre = self.genre_combo.get().strip()
        subgenre = self.subgenre_combo.get().strip()
        desc = self.desc_combo.get().strip()
        tag = self.tag_combo.get().strip()
        default_name = f"{genre}.{subgenre}.{desc}.{tag}" if all([genre, subgenre, desc, tag]) else ""

        name = self._ask_preset_name(default_name)
        if not name:
            return

        existing = [p for p in self.data["presets"] if p["name"] == name]
        if existing:
            if messagebox.askyesno("Duplicate Preset", "Preset with this name exists. Overwrite? (No = Append new)"):
                self.data["presets"] = [p for p in self.data["presets"] if p["name"] != name]

        preset = {
            "name": name,
            "genre": genre,
            "subgenre": subgenre,
            "desc": desc,
            "tag": tag,
            "folder": self.folder_entry.get()
        }
        self.data["presets"].append(preset)
        self.save_json()
        self.data = self.load_json()
        self.preset_combo.configure(values=self.get_sorted_preset_names())
        self.preset_combo.set(name)
        self._show_status(f"Saved preset: {name}")

    def _ask_preset_name(self, default_name=""):
        """CTk-styled input dialog with initial value support."""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Preset Name")
        dialog.geometry("320x150")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.transient(self.root)

        result = [None]

        ctk.CTkLabel(dialog, text="Enter a name for this preset:").pack(pady=(20, 5))
        entry = ctk.CTkEntry(dialog, width=280)
        entry.pack(pady=5)
        entry.insert(0, default_name)
        entry.select_range(0, "end")
        entry.focus()

        def on_ok():
            val = entry.get().strip()
            if val:
                result[0] = val
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="OK", width=80, command=on_ok).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="Cancel", width=80, command=on_cancel).pack(side="left", padx=5)

        entry.bind("<Return>", lambda _e: on_ok())
        entry.bind("<Escape>", lambda _e: on_cancel())

        dialog.wait_window()
        return result[0]

    # ── Drag-and-drop handler ─────────────────────────────────────────

    def on_drop(self, event):
        # Route to watermark handler if dropped on the preview area
        if self._is_over_widget(self.wm_drop_frame):
            self._handle_watermark_drop(event)
            return

        raw_data = event.data
        files = []
        matches = re.findall(r'(?:\{([^\}]*)\}|([^\s]+))', raw_data)
        for m in matches:
            path = m[0] or m[1]
            if path:
                files.append(path)

        if not files:
            messagebox.showerror("Oops!", "No files dropped?")
            return

        genre = self.genre_combo.get().strip()
        subgenre = self.subgenre_combo.get().strip()
        desc = self.desc_combo.get().strip()
        tag = self.tag_combo.get().strip()
        folder = self.folder_entry.get().strip()

        # Only validate enabled fields + folder
        required = [folder]
        if self.use_genre.get():
            required.append(genre)
        if self.use_subgenre.get():
            required.append(subgenre)
        if self.use_desc.get():
            required.append(desc)
        if self.use_tag.get():
            required.append(tag)

        if not all(required):
            messagebox.showerror("Hold up!", "Please fill in all enabled fields and target folder before dropping images.")
            return

        self.data = self.load_json()

        # Auto-add new values for enabled fields
        added = False
        if self.use_genre.get() and genre and genre not in self.data["genres"]:
            self.data["genres"].append(genre)
            self.data["genres"].sort()
            self.genre_combo.configure(values=sorted(self.data["genres"]))
            added = True
        if self.use_subgenre.get() and subgenre and subgenre not in self.data["subgenres"]:
            self.data["subgenres"].append(subgenre)
            self.data["subgenres"].sort()
            self.subgenre_combo.configure(values=sorted(self.data["subgenres"]))
            added = True
        if self.use_desc.get() and desc and desc not in self.data["descs"]:
            self.data["descs"].append(desc)
            self.data["descs"].sort()
            self.desc_combo.configure(values=sorted(self.data["descs"]))
            added = True
        if self.use_tag.get() and tag and tag not in self.data["tags"]:
            self.data["tags"].append(tag)
            self.data["tags"].sort()
            self.tag_combo.configure(values=sorted(self.data["tags"]))
            added = True
        if added:
            self.save_json()

        os.makedirs(folder, exist_ok=True)

        remove_meta = self.remove_var.get()
        add_meta = self.add_var.get()
        add_wm = self.watermark_var.get()

        for file_path in files:
            self.process_image(file_path, genre, subgenre, desc, tag, folder, remove_meta, add_meta, add_wm)

        self._show_status(f"Processed {len(files)} image(s)!", duration=5000)

    # ── Image processing ──────────────────────────────────────────────

    def _build_name_parts(self, genre, subgenre, size_str, desc, tag):
        """Build the list of filename components based on enabled fields."""
        parts = []
        if self.use_genre.get():
            parts.append(genre)
        if self.use_subgenre.get():
            parts.append(subgenre)
        if self.use_size.get():
            parts.append(size_str)
        if self.use_desc.get():
            parts.append(desc)
        if self.use_tag.get():
            parts.append(tag)
        return parts

    def _build_glob_pattern(self, genre, subgenre, desc, tag):
        """Build a glob pattern for finding existing files with matching fields."""
        parts = []
        if self.use_genre.get():
            parts.append(genre)
        if self.use_subgenre.get():
            parts.append(subgenre)
        if self.use_size.get():
            parts.append("*")
        if self.use_desc.get():
            parts.append(desc)
        if self.use_tag.get():
            parts.append(tag)
        parts.append("*")  # index
        return ".".join(parts) + ".*"

    def process_image(self, file_path, genre, subgenre, desc, tag, folder, remove_meta, add_meta, add_watermark):
        if not os.path.exists(file_path):
            messagebox.showerror("Error", f"File not found: {file_path}")
            return

        new_path = None
        try:
            base, ext = os.path.splitext(file_path)
            ext_lower = ext.lower()
            if ext_lower not in ('.jpg', '.jpeg', '.png'):
                messagebox.showinfo("Skipped", f"Unsupported file type: {ext}. Only JPG/JPEG/PNG supported.")
                return

            with Image.open(file_path) as img:
                width, height = img.size
                size_str = f"{width}x{height}"

            # Find next index — index is always the last component before extension
            pattern = self._build_glob_pattern(genre, subgenre, desc, tag)
            existing_files = glob.glob(os.path.join(folder, pattern))
            max_index = 0
            for f in existing_files:
                basename = os.path.basename(f)
                name_no_ext = os.path.splitext(basename)[0]
                name_parts = name_no_ext.split('.')
                if name_parts:
                    try:
                        idx = int(name_parts[-1])
                        max_index = max(max_index, idx)
                    except ValueError:
                        pass

            next_index = max_index + 1
            index_str = str(next_index).zfill(3)

            # Build filename from enabled components + index
            name_parts = self._build_name_parts(genre, subgenre, size_str, desc, tag)
            name_parts.append(index_str)
            new_name = ".".join(name_parts) + ext_lower
            new_path = os.path.join(folder, new_name)

            # Handle potential dups
            while os.path.exists(new_path):
                next_index += 1
                index_str = str(next_index).zfill(3)
                name_parts[-1] = index_str
                new_name = ".".join(name_parts) + ext_lower
                new_path = os.path.join(folder, new_name)

            if not remove_meta and not add_meta and not add_watermark:
                shutil.move(file_path, new_path)
            else:
                with Image.open(file_path).convert("RGBA") as img:
                    if remove_meta:
                        self.strip_metadata(img, new_path, ext_lower)
                    else:
                        out = img.convert("RGB") if ext_lower in ('.jpg', '.jpeg') else img
                        out.save(new_path, quality=95)

                    if add_meta:
                        self.add_metadata(new_path, ext_lower)

                    if add_watermark and self.watermark_path and os.path.exists(self.watermark_path):
                        watermark = Image.open(self.watermark_path).convert("RGBA")
                        scale_factor = 0.1
                        new_width = int(img.width * scale_factor)
                        ratio = new_width / watermark.width
                        new_height = int(watermark.height * ratio)
                        watermark = watermark.resize((new_width, new_height), Image.Resampling.LANCZOS)
                        alpha = watermark.split()[3]
                        alpha = alpha.point(lambda p: int(p * 0.3))
                        watermark.putalpha(alpha)
                        x = img.width - watermark.width - 10
                        y = img.height - watermark.height - 10
                        img.paste(watermark, (x, y), watermark)
                        out = img.convert("RGB") if ext_lower in ('.jpg', '.jpeg') else img
                        out.save(new_path, quality=95)

                os.remove(file_path)

        except Exception as e:
            messagebox.showerror("Oops!", f"Failed to process {file_path}: {str(e)}")
            if new_path and os.path.exists(new_path):
                os.remove(new_path)

    def strip_metadata(self, img, output_path, ext):
        if ext == '.png':
            img.save(output_path)
        elif ext in ('.jpg', '.jpeg'):
            img.convert("RGB").save(output_path, quality=95)

    def add_metadata(self, file_path, ext):
        if ext == '.png':
            with Image.open(file_path) as img:
                info = PngImagePlugin.PngInfo()
                info.add_text("Website", self.website_value)
                info.add_text("Copyright", self.copyright_value)
                img.save(file_path, pnginfo=info)
        elif ext in ('.jpg', '.jpeg'):
            exif_dict = piexif.load(file_path) if os.path.getsize(file_path) > 0 else {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
            exif_dict['0th'][piexif.ImageIFD.ImageDescription] = f"Website: {self.website_value}".encode('utf-8')
            exif_dict['0th'][piexif.ImageIFD.Copyright] = self.copyright_value.encode('utf-8')
            exif_bytes = piexif.dump(exif_dict)
            piexif.insert(exif_bytes, file_path)


if __name__ == "__main__":
    root = DnDCTk()
    app = ImageProcessorApp(root)
    root.mainloop()
