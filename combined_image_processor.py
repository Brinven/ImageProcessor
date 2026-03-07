# combined_image_processor.py
# This is a full Python script combining the metadata stripper, adder, and image sorter into one GUI app.
# It uses Tkinter (built-in), tkinterdnd2 for drag-and-drop (pip install tkinterdnd2),
# Pillow for image processing (pip install pillow),
# piexif for JPG metadata handling (pip install piexif),
# portalocker for JSON file locking (pip install portalocker).
# Run it with: py -3.12 combined_image_processor.py (from Command Prompt in the script's folder).
# Drop images onto the app: it will (optionally) strip metadata, (optionally) add fixed metadata ("Website: axly.com", "Copyright: © 2025 axly.com"),
# then rename and move to the target folder based on the sorter logic.
# Checkboxes for "Remove Metadata" and "Add Metadata" default to ON, but you can toggle them off.
# Handles JPG/JPEG/PNG; skips non-images gracefully.
# Preserves JPG quality by avoiding re-compression where possible (uses piexif for strip/add).

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import tkinterdnd2 as tkdnd  # For drag-and-drop
from PIL import Image, PngImagePlugin  # For image processing and PNG metadata
import os
import shutil
import glob
import json
import re
import portalocker  # For file locking
import piexif  # For JPG metadata

class ImageProcessorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Image Processor Elf - Drop 'em like it's hot!")
        self.root.geometry("175x700")  # A bit taller for new checkboxes

        # Load or initialize JSON data (with lock)
        self.json_file = "image_sorter.json"  # Keeping the name for compatibility
        self.data = self.load_json()

        # Fixed metadata values
        self.website_value = "axly.com"
        self.copyright_value = "© 2025 axly.com"

        # UI Elements
        self.create_ui()

        # Update the status label initially
        self.update_status_label()

        # Bind changes to comboboxes to update label
        self.genre_combo.bind("<<ComboboxSelected>>", self.update_status_label)
        self.subgenre_combo.bind("<<ComboboxSelected>>", self.update_status_label)
        self.desc_combo.bind("<<ComboboxSelected>>", self.update_status_label)
        self.tag_combo.bind("<<ComboboxSelected>>", self.update_status_label)
        self.genre_combo.bind("<KeyRelease>", self.update_status_label)
        self.subgenre_combo.bind("<KeyRelease>", self.update_status_label)
        self.desc_combo.bind("<KeyRelease>", self.update_status_label)
        self.tag_combo.bind("<KeyRelease>", self.update_status_label)

        # Make the whole window a drop target
        self.root.drop_target_register(tkdnd.DND_FILES)
        self.root.dnd_bind('<<Drop>>', self.on_drop)

    def load_json(self):
        if os.path.exists(self.json_file):
            with open(self.json_file, 'r') as f:
                portalocker.lock(f, portalocker.LOCK_SH)  # Shared lock for reading
                data = json.load(f)
                portalocker.unlock(f)
                return data
        else:
            return {
                "presets": [],
                "genres": [],
                "subgenres": [],
                "descs": ["fe", "M", "Ob"],
                "tags": ["N", "S", "WC", "OP", "Photo"]
            }

    def save_json(self):
        with open(self.json_file, 'w') as f:
            portalocker.lock(f, portalocker.LOCK_EX)  # Exclusive lock for writing
            json.dump(self.data, f, indent=4)
            f.flush()  # Ensure it's written
            os.fsync(f.fileno())  # Force to disk
            portalocker.unlock(f)

    def create_ui(self):
        # Dedicated drag area at the top (approx top third)
        self.drag_frame = tk.Frame(self.root, height=216, bg="lightgray")
        self.drag_frame.pack(fill=tk.X)
        drag_label = tk.Label(self.drag_frame, text="Drag here to move", bg="lightgray", font=("Arial", 12), anchor="center")
        drag_label.pack(fill=tk.BOTH, expand=True)
        drag_label.bind("<Button-1>", self.start_move)
        drag_label.bind("<B1-Motion>", self.do_move)

        # Genre (Combobox for editable list)
        tk.Label(self.root, text="Genre (e.g., Modern):").pack(pady=5)
        self.genre_combo = ttk.Combobox(self.root, values=sorted(self.data["genres"]))
        self.genre_combo.pack()
        add_genre_btn = tk.Button(self.root, text="Add Genre to List", command=self.add_genre)
        add_genre_btn.pack()

        # Subgenre (Combobox for editable list)
        tk.Label(self.root, text="Subgenre (e.g., elf):").pack(pady=5)
        self.subgenre_combo = ttk.Combobox(self.root, values=sorted(self.data["subgenres"]))
        self.subgenre_combo.pack()
        add_subgenre_btn = tk.Button(self.root, text="Add Subgenre to List", command=self.add_subgenre)
        add_subgenre_btn.pack()

        # Desc (Combobox for editable list)
        tk.Label(self.root, text="Desc (e.g., fe, M, Ob):").pack(pady=5)
        self.desc_combo = ttk.Combobox(self.root, values=sorted(self.data["descs"]))
        self.desc_combo.pack()
        add_desc_btn = tk.Button(self.root, text="Add Desc to List", command=self.add_desc)
        add_desc_btn.pack()

        # Tag (Combobox for editable list)
        tk.Label(self.root, text="Tag (e.g., S, N, WC):").pack(pady=5)
        self.tag_combo = ttk.Combobox(self.root, values=sorted(self.data["tags"]))
        self.tag_combo.pack()
        add_tag_btn = tk.Button(self.root, text="Add Tag to List", command=self.add_tag)
        add_tag_btn.pack()

        # Metadata checkboxes
        self.remove_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.root, text="Remove Metadata?", variable=self.remove_var).pack()
        self.add_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.root, text="Add Metadata?", variable=self.add_var).pack()

        # Folder
        tk.Label(self.root, text="Target Folder:").pack(pady=5)
        self.folder_entry = tk.Entry(self.root)
        self.folder_entry.pack()
        browse_btn = tk.Button(self.root, text="Browse Folder", command=self.browse_folder)
        browse_btn.pack()

        # Presets
        tk.Label(self.root, text="Presets:").pack(pady=5)
        self.preset_combo = ttk.Combobox(self.root, values=self.get_sorted_preset_names())
        self.preset_combo.pack()
        load_btn = tk.Button(self.root, text="Load Preset", command=self.load_preset)
        load_btn.pack()
        save_btn = tk.Button(self.root, text="Save New Preset", command=self.save_preset)
        save_btn.pack()

        # Refresh button to reload JSON (in case of desync)
        refresh_btn = tk.Button(self.root, text="Refresh from JSON", command=self.refresh_from_json)
        refresh_btn.pack()

        # Status label for non-intrusive messages
        self.status_label = tk.Label(self.root, text="", font=("Arial", 12), fg="green")
        self.status_label.pack(pady=5)

        # Drop area label (for fun)
        self.drop_label = tk.Label(self.root, text="Drag & Drop Images Here!", font=("Arial", 16, "bold"), bg="lightblue", height=5, wraplength=150)
        self.drop_label.pack(fill=tk.BOTH, expand=True)

    def get_sorted_preset_names(self):
        sorted_presets = sorted(self.data["presets"], key=lambda p: (p.get("genre", "").lower(), p.get("subgenre", "").lower(), p.get("desc", "").lower(), p.get("tag", "").lower()))
        return [p["name"] for p in sorted_presets]

    def start_move(self, event):
        self.root._offsetx = event.x
        self.root._offsety = event.y

    def do_move(self, event):
        x = self.root.winfo_pointerx() - self.root._offsetx
        y = self.root.winfo_pointery() - self.root._offsety
        self.root.geometry(f"+{x}+{y}")

    def add_genre(self):
        self.data = self.load_json()  # Reload fresh before modify
        genre = self.genre_combo.get().strip()
        if genre and genre not in self.data["genres"]:
            self.data["genres"].append(genre)
            self.data["genres"].sort()
            self.genre_combo['values'] = self.data["genres"]
            self.save_json()
            self.status_label.config(text=f"Added genre: {genre}", fg="green")
            self.root.after(3000, lambda: self.status_label.config(text=""))

    def add_subgenre(self):
        self.data = self.load_json()  # Reload fresh before modify
        subgenre = self.subgenre_combo.get().strip()
        if subgenre and subgenre not in self.data["subgenres"]:
            self.data["subgenres"].append(subgenre)
            self.data["subgenres"].sort()
            self.subgenre_combo['values'] = self.data["subgenres"]
            self.save_json()
            self.status_label.config(text=f"Added subgenre: {subgenre}", fg="green")
            self.root.after(3000, lambda: self.status_label.config(text=""))

    def add_desc(self):
        self.data = self.load_json()  # Reload fresh before modify
        desc = self.desc_combo.get().strip()
        if desc and desc not in self.data["descs"]:
            self.data["descs"].append(desc)
            self.data["descs"].sort()
            self.desc_combo['values'] = self.data["descs"]
            self.save_json()
            self.status_label.config(text=f"Added desc: {desc}", fg="green")
            self.root.after(3000, lambda: self.status_label.config(text=""))

    def add_tag(self):
        self.data = self.load_json()  # Reload fresh before modify
        tag = self.tag_combo.get().strip()
        if tag and tag not in self.data["tags"]:
            self.data["tags"].append(tag)
            self.data["tags"].sort()
            self.tag_combo['values'] = self.data["tags"]
            self.save_json()
            self.status_label.config(text=f"Added tag: {tag}", fg="green")
            self.root.after(3000, lambda: self.status_label.config(text=""))

    def refresh_from_json(self):
        self.data = self.load_json()
        self.genre_combo['values'] = sorted(self.data["genres"])
        self.subgenre_combo['values'] = sorted(self.data["subgenres"])
        self.desc_combo['values'] = sorted(self.data["descs"])
        self.tag_combo['values'] = sorted(self.data["tags"])
        self.preset_combo['values'] = self.get_sorted_preset_names()
        self.status_label.config(text="Refreshed from JSON!", fg="green")
        self.root.after(3000, lambda: self.status_label.config(text=""))

    def update_status_label(self, event=None):
        genre = self.genre_combo.get().strip()
        subgenre = self.subgenre_combo.get().strip()
        desc = self.desc_combo.get().strip()
        tag = self.tag_combo.get().strip()
        if all([genre, subgenre, desc, tag]):
            self.drop_label.config(text=f"{genre}.{subgenre}.{desc}.{tag}\nDrag & Drop Here!", fg="black")
        else:
            self.drop_label.config(text="Drag & Drop Images Here!\n(Fill fields first)", fg="red")

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, folder)

    def load_preset(self):
        self.data = self.load_json()  # Reload fresh for latest presets
        name = self.preset_combo.get()
        if not name:
            return
        for preset in self.data["presets"]:
            if preset["name"] == name:
                self.genre_combo.set(preset["genre"])
                self.subgenre_combo.set(preset["subgenre"])
                self.desc_combo.set(preset["desc"])
                self.tag_combo.set(preset["tag"])
                self.folder_entry.delete(0, tk.END)
                self.folder_entry.insert(0, preset["folder"])
                self.update_status_label()
                break

    def save_preset(self):
        self.data = self.load_json()  # Reload fresh before modify
        genre = self.genre_combo.get().strip()
        subgenre = self.subgenre_combo.get().strip()
        desc = self.desc_combo.get().strip()
        tag = self.tag_combo.get().strip()
        default_name = f"{genre}.{subgenre}.{desc}.{tag}" if all([genre, subgenre, desc, tag]) else ""
        name = simpledialog.askstring("Preset Name", "Enter a name for this preset:", initialvalue=default_name)
        if not name:
            return
        # Check for duplicate names and prompt to overwrite or append
        existing = [p for p in self.data["presets"] if p["name"] == name]
        if existing:
            if messagebox.askyesno("Duplicate Preset", "Preset with this name exists. Overwrite? (No = Append new)"):
                self.data["presets"] = [p for p in self.data["presets"] if p["name"] != name]
            # Else append anyway
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
        self.data = self.load_json()  # Reload after save for sync
        self.preset_combo['values'] = self.get_sorted_preset_names()
        self.preset_combo.set(name)
        self.status_label.config(text=f"Saved preset: {name}", fg="green")
        self.root.after(3000, lambda: self.status_label.config(text=""))

    def on_drop(self, event):
        # Parse dropped files (handles paths with spaces)
        raw_data = event.data
        files = []
        # Regex to match either {path} or plain path
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

        if not all([genre, subgenre, desc, tag, folder]):
            messagebox.showerror("Hold up!", "Please fill in all fields before dropping images.")
            return

        self.data = self.load_json()  # Reload fresh before any auto-adds

        added = False
        # Auto-add new genre if not in list
        if genre not in self.data["genres"]:
            self.data["genres"].append(genre)
            self.data["genres"].sort()
            self.genre_combo['values'] = self.data["genres"]
            added = True

        # Auto-add new subgenre if not in list
        if subgenre not in self.data["subgenres"]:
            self.data["subgenres"].append(subgenre)
            self.data["subgenres"].sort()
            self.subgenre_combo['values'] = self.data["subgenres"]
            added = True

        # Auto-add new desc if not in list
        if desc not in self.data["descs"]:
            self.data["descs"].append(desc)
            self.data["descs"].sort()
            self.desc_combo['values'] = self.data["descs"]
            added = True

        # Auto-add new tag if not in list
        if tag not in self.data["tags"]:
            self.data["tags"].append(tag)
            self.data["tags"].sort()
            self.tag_combo['values'] = self.data["tags"]
            added = True

        if added:
            self.save_json()

        # Create folder if it doesn't exist
        os.makedirs(folder, exist_ok=True)

        remove_meta = self.remove_var.get()
        add_meta = self.add_var.get()

        for file_path in files:
            self.process_image(file_path, genre, subgenre, desc, tag, folder, remove_meta, add_meta)

        # Display success in GUI status label (clears after 5 seconds)
        self.status_label.config(text=f"Processed {len(files)} images. Check {folder}!", fg="green")
        self.root.after(5000, lambda: self.status_label.config(text=""))

    def process_image(self, file_path, genre, subgenre, desc, tag, folder, remove_meta, add_meta):
        if not os.path.exists(file_path):
            messagebox.showerror("Error", f"File not found: {file_path}")
            return

        try:
            # Get extension
            base, ext = os.path.splitext(file_path)
            ext_lower = ext.lower()
            if ext_lower not in ('.jpg', '.jpeg', '.png'):
                messagebox.showinfo("Skipped", f"Unsupported file type: {ext}. Only JPG/JPEG/PNG supported.")
                return

            # Get image size
            with Image.open(file_path) as img:
                width, height = img.size
                size_str = f"{width}x{height}"

            # Find next index
            pattern = f"{genre}.{subgenre}.*.{desc}.{tag}.*.*"
            existing_files = glob.glob(os.path.join(folder, pattern))
            max_index = 0
            for f in existing_files:
                basename = os.path.basename(f)
                parts = basename.split('.')
                if len(parts) >= 7:  # genre.subgenre.size.desc.tag.index.ext
                    try:
                        idx = int(parts[5])
                        max_index = max(max_index, idx)
                    except ValueError:
                        pass

            next_index = max_index + 1
            index_str = str(next_index).zfill(3)  # Pads to at least 3 digits

            # Build new name
            new_name = f"{genre}.{subgenre}.{size_str}.{desc}.{tag}.{index_str}{ext_lower}"
            new_path = os.path.join(folder, new_name)

            # Handle potential dups (race condition)
            while os.path.exists(new_path):
                next_index += 1
                index_str = str(next_index).zfill(3)
                new_name = f"{genre}.{subgenre}.{size_str}.{desc}.{tag}.{index_str}{ext_lower}"
                new_path = os.path.join(folder, new_name)

            # Now process metadata and save/move
            if not remove_meta and not add_meta:
                # Just move
                shutil.move(file_path, new_path)
            else:
                if remove_meta:
                    # Strip metadata
                    self.strip_metadata(file_path, new_path, ext_lower)
                else:
                    # Copy original to new_path
                    shutil.copy(file_path, new_path)

                if add_meta:
                    # Add metadata to new_path
                    self.add_metadata(new_path, ext_lower)

                # Original file remains; if you want to delete it, uncomment: os.remove(file_path)
                # But since sorter moves, and we processed to new, delete original to mimic move
                os.remove(file_path)

        except Exception as e:
            messagebox.showerror("Oops!", f"Failed to process {file_path}: {str(e)}")
            if os.path.exists(new_path):
                os.remove(new_path)  # Clean up

    def strip_metadata(self, input_path, output_path, ext):
        """Strips metadata without quality loss where possible."""
        if ext == '.png':
            # For PNG: Open and save without info (lossless, but re-compresses)
            with Image.open(input_path) as img:
                img.save(output_path)
        elif ext in ('.jpg', '.jpeg'):
            # For JPG: Copy and remove EXIF without re-encoding
            shutil.copy(input_path, output_path)
            try:
                piexif.remove(output_path)
            except piexif.InvalidImageDataError:
                pass  # No EXIF to remove

    def add_metadata(self, file_path, ext):
        """Adds fixed metadata without quality loss."""
        if ext == '.png':
            # For PNG: Add text chunks
            with Image.open(file_path) as img:
                info = PngImagePlugin.PngInfo()
                info.add_text("Website", self.website_value)
                info.add_text("Copyright", self.copyright_value)
                img.save(file_path, pnginfo=info)
        elif ext in ('.jpg', '.jpeg'):
            # For JPG: Add EXIF tags without re-encoding
            exif_dict = piexif.load(file_path) if os.path.getsize(file_path) > 0 else {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
            exif_dict['0th'][piexif.ImageIFD.ImageDescription] = f"Website: {self.website_value}".encode('utf-8')
            exif_dict['0th'][piexif.ImageIFD.Copyright] = self.copyright_value.encode('utf-8')
            exif_bytes = piexif.dump(exif_dict)
            piexif.insert(exif_bytes, file_path)

if __name__ == "__main__":
    root = tkdnd.Tk()
    app = ImageProcessorApp(root)
    root.mainloop()