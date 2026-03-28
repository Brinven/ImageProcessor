# v3_patch.md — What to update in combined_image_processorv3.py
#
# After using Watermark Studio to dial in your settings and hitting "Save to JSON",
# the main app needs to READ those settings instead of using hardcoded values.
# Three lines need updating inside process_image(), in the watermark block.
#
# ─────────────────────────────────────────────────────────────────────────────
# FIND this block (around line 728-843):
# ─────────────────────────────────────────────────────────────────────────────
#
#   # Pre-load watermark image once
#   wm_img = None
#   if add_wm and self.watermark_path and os.path.exists(self.watermark_path):
#       try:
#           wm_img = Image.open(self.watermark_path).convert("RGBA")
#       except Exception:
#           wm_img = None
#
# ─────────────────────────────────────────────────────────────────────────────
# REPLACE WITH:
# ─────────────────────────────────────────────────────────────────────────────
#
#   # Pre-load watermark image once
#   wm_img = None
#   if add_wm and self.watermark_path and os.path.exists(self.watermark_path):
#       try:
#           wm_img = Image.open(self.watermark_path).convert("RGBA")
#       except Exception:
#           wm_img = None
#
#   # Read studio settings (with safe fallbacks to original hardcoded values)
#   wm_settings  = self.data.get("settings", {})
#   wm_opacity   = float(wm_settings.get("watermark_opacity",  0.30))
#   wm_scale     = float(wm_settings.get("watermark_scale",    0.10))
#   wm_padding   = int(wm_settings.get("watermark_padding",    10))
#   wm_position  = wm_settings.get("watermark_position", "BR")
#
# ─────────────────────────────────────────────────────────────────────────────
# FIND this block (inside process_image, the watermark resize + paste section):
# ─────────────────────────────────────────────────────────────────────────────
#
#   if wm_img:
#       if width not in wm_cache:
#           new_wm_w = max(1, int(width * 0.1))
#           ratio = new_wm_w / wm_img.width
#           new_wm_h = max(1, int(wm_img.height * ratio))
#           wm_resized = wm_img.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)
#           alpha = wm_resized.split()[3].point(lambda p: int(p * 0.3))
#           wm_resized.putalpha(alpha)
#           wm_cache[width] = wm_resized
#       wm = wm_cache[width]
#       img.paste(wm, (width - wm.width - 10, height - wm.height - 10), wm)
#
# ─────────────────────────────────────────────────────────────────────────────
# REPLACE WITH:
# ─────────────────────────────────────────────────────────────────────────────
#
#   if wm_img:
#       cache_key = (width, wm_scale, wm_opacity)
#       if cache_key not in wm_cache:
#           new_wm_w = max(1, int(width * wm_scale))
#           ratio    = new_wm_w / wm_img.width
#           new_wm_h = max(1, int(wm_img.height * ratio))
#           wm_resized = wm_img.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)
#           r, g, b, a = wm_resized.split()
#           a = a.point(lambda p: int(p * wm_opacity))
#           wm_resized = Image.merge("RGBA", (r, g, b, a))
#           wm_cache[cache_key] = wm_resized
#       wm = wm_cache[cache_key]
#       pad = wm_padding
#       x, y = {
#           "TL": (pad,               pad),
#           "TR": (width  - wm.width  - pad, pad),
#           "BL": (pad,               height - wm.height - pad),
#           "BR": (width  - wm.width  - pad, height - wm.height - pad),
#       }[wm_position]
#       img.paste(wm, (x, y), wm)
#
# ─────────────────────────────────────────────────────────────────────────────
# NOTE: The cache key was changed from `width` to `(width, wm_scale, wm_opacity)`
# because the scale and opacity are now variable. This is a correct fix — the old
# single-key cache would have returned a stale cached watermark if you changed
# settings mid-session.
# ─────────────────────────────────────────────────────────────────────────────
