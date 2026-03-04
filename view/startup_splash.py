"""起動時スプラッシュ表示ユーティリティ。"""

from __future__ import annotations

from pathlib import Path

import customtkinter as ctk
from PIL import Image


SPLASH_ICON_SIZE = 256
SPLASH_PADDING = 16


def _center_geometry(width: int, height: int, root: ctk.CTk) -> str:
    """画面中央配置用の geometry 文字列を返す。"""
    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x_pos = (screen_width - width) // 2
    y_pos = (screen_height - height) // 2
    return f"{width}x{height}+{x_pos}+{y_pos}"


def show_startup_splash(root: ctk.CTk, icon_path: Path) -> ctk.CTkToplevel:
    """アイコン画像のみの最小スプラッシュを表示する。"""
    splash = ctk.CTkToplevel(root)
    splash.overrideredirect(True)
    splash.attributes("-topmost", True)
    splash.configure(fg_color="white")
    splash_size = SPLASH_ICON_SIZE + (SPLASH_PADDING * 2)

    if icon_path.exists():
        splash.iconbitmap(str(icon_path))
        raw_icon = Image.open(icon_path).convert("RGBA")
        white_bg = Image.new("RGBA", raw_icon.size, "white")
        icon_on_white = Image.alpha_composite(white_bg, raw_icon)
        icon_image = ctk.CTkImage(
            light_image=icon_on_white,
            dark_image=icon_on_white,
            size=(SPLASH_ICON_SIZE, SPLASH_ICON_SIZE),
        )
        icon_label = ctk.CTkLabel(
            splash,
            text="",
            image=icon_image,
            fg_color="white",
        )
        icon_label.pack(padx=SPLASH_PADDING, pady=SPLASH_PADDING)
    else:
        fallback_label = ctk.CTkLabel(splash, text="PDF Splitter", fg_color="white")
        fallback_label.pack(padx=24, pady=24)

    splash.geometry(_center_geometry(splash_size, splash_size, root))
    splash.lift()
    splash.focus_force()
    return splash
