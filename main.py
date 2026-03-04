"""PDF 分割アプリケーション - エントリーポイント。

MVP アーキテクチャに基づき、Model / View / Presenter を組み立てて起動する。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from view.main_window import MainWindow
from presenter.main_presenter import MainPresenter


SPLASH_MIN_SECONDS = 1.0
SPLASH_ICON_SIZE = 256


def _resource_path(filename: str) -> Path:
    """開発実行と PyInstaller 実行の両方で使えるリソースパスを返す。"""
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_dir / filename


def _center_geometry(width: int, height: int, root: ctk.CTk) -> str:
    """画面中央配置用の geometry 文字列を返す。"""
    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x_pos = (screen_width - width) // 2
    y_pos = (screen_height - height) // 2
    return f"{width}x{height}+{x_pos}+{y_pos}"


def _show_startup_splash(root: MainWindow, icon_path: Path) -> ctk.CTkToplevel:
    """アイコン画像のみの最小スプラッシュを表示する。"""
    splash = ctk.CTkToplevel(root)
    splash.overrideredirect(True)
    splash.attributes("-topmost", True)

    if icon_path.exists():
        splash.iconbitmap(str(icon_path))
        icon_image = ctk.CTkImage(
            light_image=Image.open(icon_path),
            dark_image=Image.open(icon_path),
            size=(SPLASH_ICON_SIZE, SPLASH_ICON_SIZE),
        )
        icon_label = ctk.CTkLabel(splash, text="", image=icon_image)
        icon_label.pack(padx=0, pady=0)
    else:
        fallback_label = ctk.CTkLabel(splash, text="PDF Splitter")
        fallback_label.pack(padx=24, pady=24)

    splash.geometry(_center_geometry(SPLASH_ICON_SIZE, SPLASH_ICON_SIZE, root))
    splash.lift()
    splash.focus_force()
    return splash


def main() -> None:
    startup_started_at = time.perf_counter()

    view = MainWindow()
    icon_path = _resource_path("pdf_splitter_icon.ico")
    if icon_path.exists():
        view.iconbitmap(str(icon_path))

    view.withdraw()
    splash = _show_startup_splash(view, icon_path)

    _presenter = MainPresenter(view)  # noqa: F841  -- View が参照を保持する

    elapsed_seconds = time.perf_counter() - startup_started_at
    remaining_ms = max(0, int((SPLASH_MIN_SECONDS - elapsed_seconds) * 1000))

    def close_splash() -> None:
        if splash.winfo_exists():
            splash.destroy()
        view.deiconify()
        view.lift()
        view.focus_force()

    if remaining_ms > 0:
        view.after(remaining_ms, close_splash)
    else:
        close_splash()

    view.mainloop()


if __name__ == "__main__":
    main()
