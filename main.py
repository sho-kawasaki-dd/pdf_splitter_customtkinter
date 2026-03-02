import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import threading
import re
import queue
from collections import OrderedDict
import customtkinter as ctk
import fitz  # PyMuPDF
from PIL import Image, ImageTk

# CustomTkinterの全体設定
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class CustomSplitBar(tk.Canvas):
    """
    標準のtkinter.Canvasを使って、色分けされたバーを描画するクラス
    """
    def __init__(self, master, on_page_click=None, **kwargs):
        # 背景色をCustomTkinterの背景に馴染ませるための処理
        bg_color = master.cget("fg_color")
        if isinstance(bg_color, tuple) or isinstance(bg_color, list):
            # ライトモード/ダークモードに応じて色を選択 (簡易的な対応)
            mode = ctk.get_appearance_mode()
            bg_color = bg_color[0] if mode == "Light" else bg_color[1]
            
        super().__init__(master, height=30, bg=bg_color, highlightthickness=0, **kwargs)
        
        self.total_pages = 0
        self.current_page = 0
        self.split_points = []
        self.active_section_index = -1  # アクティブセクションのハイライト用
        self.on_page_click = on_page_click
        
        self.colors = ["#3498db", "#e74c3c", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c"]
        
        # ウィンドウリサイズ時に再描画するためのバインド
        self.bind("<Configure>", self.on_resize)
        self.bind("<Button-1>", self.on_click)
        self.bind("<B1-Motion>", self.on_drag)

    def on_resize(self, event):
        self.draw()

    def _event_to_page(self, event):
        if self.total_pages <= 0:
            return None

        width = self.winfo_width()
        if width <= 1:
            return None

        x_pos = min(max(event.x, 0), width - 1)
        target_page = int((x_pos / width) * self.total_pages)
        return min(max(target_page, 0), self.total_pages - 1)

    def on_click(self, event):
        target_page = self._event_to_page(event)
        if target_page is None:
            return

        if self.on_page_click:
            self.on_page_click(target_page)

    def on_drag(self, event):
        target_page = self._event_to_page(event)
        if target_page is None:
            return

        if self.on_page_click:
            self.on_page_click(target_page)

    def update_state(self, total, current, splits, active_section_index=-1):
        self.total_pages = total
        self.current_page = current
        self.split_points = sorted(splits)
        self.active_section_index = active_section_index
        self.draw()

    def draw(self):
        self.delete("all")  # キャンバスをクリア
        if self.total_pages <= 0:
            return

        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1: return # 初期化前対策

        page_width = width / self.total_pages
        
        # --- 1. 分割範囲ごとの色分け描画 ---
        start_page = 0
        color_idx = 0
        points = self.split_points + [self.total_pages]
        
        for point in points:
            if point <= start_page: continue
            
            x_start = start_page * page_width
            x_end = point * page_width
            
            color = self.colors[color_idx % len(self.colors)]
            self.create_rectangle(x_start, 0, x_end, height, fill=color, outline="")
            
            start_page = point
            color_idx += 1

        # --- 2. 分割線の描画 ---
        for point in self.split_points:
            x_pos = point * page_width
            self.create_line(x_pos, 0, x_pos, height, fill="black", width=2)

        # --- 3. アクティブセクションの白枠ハイライト ---
        if self.active_section_index >= 0:
            boundaries = [0] + self.split_points + [self.total_pages]
            if self.active_section_index < len(boundaries) - 1:
                sec_start = boundaries[self.active_section_index]
                sec_end = boundaries[self.active_section_index + 1]
                x_start = sec_start * page_width
                x_end = sec_end * page_width
                self.create_rectangle(
                    x_start + 1, 1, x_end - 1, height - 1,
                    fill="", outline="white", width=2
                )

        # --- 4. 現在位置のインジケーター（逆三角形） ---
        current_x = (self.current_page + 0.5) * page_width
        self.create_polygon(
            current_x - 6, 0,
            current_x + 6, 0,
            current_x, 10,
            fill="white", outline="black"
        )


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF 分割アプリケーション (CustomTkinter)")
        self.geometry("1000x700")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.doc = None
        self.current_page_idx = 0
        self.split_points = []
        self.sections_data = []  # データモデル: [{'start', 'end', 'filename', 'is_custom_name'}, ...]
        self.preview_zoom = 1.0
        self.preview_zoom_min = 0.5
        self.preview_zoom_max = 3.0
        self.preview_zoom_step = 0.1
        self.preview_image_tk = None
        self.preview_render_cache = OrderedDict()
        self.preview_render_cache_limit = 10
        self.preview_can_pan = False
        self.is_splitting = False
        self.source_pdf_path = None
        self.split_result_queue = queue.Queue()
        self.split_queue_poll_job = None

        self.grid_columnconfigure(0, weight=7)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        self.init_left_frame()
        self.init_right_frame()

        self.bind_all("<Shift-Return>", self.on_shift_enter_execute_key)
        self.bind_all("<Shift-KP_Enter>", self.on_shift_enter_execute_key)
        self.bind_all("<Control-Up>", self.on_ctrl_up_section_key)
        self.bind_all("<Control-Down>", self.on_ctrl_down_section_key)
        self.bind_all("<Control-KP_Up>", self.on_ctrl_up_section_key)
        self.bind_all("<Control-KP_Down>", self.on_ctrl_down_section_key)

    def init_left_frame(self):
        left_frame = ctk.CTkFrame(self)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        # PDFプレビュー領域
        self.preview_frame = ctk.CTkFrame(left_frame)
        self.preview_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.preview_frame.grid_rowconfigure(0, weight=1)
        self.preview_frame.grid_columnconfigure(0, weight=1)

        self.preview_canvas = tk.Canvas(self.preview_frame, highlightthickness=0, takefocus=1)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<Button-1>", self.on_preview_mouse_down)
        self.preview_canvas.bind("<B1-Motion>", self.on_preview_mouse_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self.on_preview_mouse_up)
        self.preview_canvas.bind("<Enter>", self.on_preview_mouse_enter)
        self.preview_canvas.bind("<Leave>", self.on_preview_mouse_leave)
        self.preview_canvas.bind("<FocusIn>", self.on_preview_focus_in)
        self.preview_canvas.bind("<FocusOut>", self.on_preview_focus_out)
        self.preview_canvas.bind("<Home>", self.on_preview_home_key)
        self.preview_canvas.bind("<End>", self.on_preview_end_key)
        self.preview_canvas.bind("<Prior>", self.on_preview_pageup_key)
        self.preview_canvas.bind("<Next>", self.on_preview_pagedown_key)
        self.preview_canvas.bind("<Control-Prior>", self.on_preview_ctrl_pageup_key)
        self.preview_canvas.bind("<Control-Next>", self.on_preview_ctrl_pagedown_key)
        self.preview_canvas.bind("<Return>", self.on_preview_enter_key)
        self.preview_canvas.bind("<KP_Enter>", self.on_preview_enter_key)
        self.preview_canvas.bind("<Delete>", self.on_preview_delete_key)
        self.preview_canvas.bind("<Shift-Return>", self.on_shift_enter_execute_key)
        self.preview_canvas.bind("<Shift-KP_Enter>", self.on_shift_enter_execute_key)
        self.preview_canvas.bind("<z>", self.on_preview_zoom_in_key)
        self.preview_canvas.bind("<Z>", self.on_preview_zoom_out_key)
        self.preview_canvas.bind("<d>", self.on_preview_zoom_reset_key)

        self.preview_message = self.preview_canvas.create_text(
            250, 300,
            text="PDFを開いてください",
            fill="#808080",
            font=("Segoe UI", 16)
        )

        # カスタム色分けプログレスバー (tk.CanvasをCTkFrameに配置)
        self.split_bar = CustomSplitBar(left_frame, on_page_click=self.go_to_page)
        self.split_bar.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        # ナビゲーション領域
        nav_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        nav_frame.grid(row=2, column=0, sticky="ew")
        nav_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.btn_prev_10 = ctk.CTkButton(nav_frame, text="<< -10", width=80, command=self.prev_10_pages, state="disabled")
        self.btn_prev_10.grid(row=0, column=0, padx=5)

        self.btn_prev = ctk.CTkButton(nav_frame, text="< 前のページ", command=self.prev_page, state="disabled")
        self.btn_prev.grid(row=0, column=1, padx=5)

        self.lbl_page_info = ctk.CTkLabel(nav_frame, text="0 / 0")
        self.lbl_page_info.grid(row=0, column=2)

        self.btn_next = ctk.CTkButton(nav_frame, text="次のページ >", command=self.next_page, state="disabled")
        self.btn_next.grid(row=0, column=3, padx=5)

        self.btn_next_10 = ctk.CTkButton(nav_frame, text="+10 >>", width=80, command=self.next_10_pages, state="disabled")
        self.btn_next_10.grid(row=0, column=4, padx=5)

        add_split_container = ctk.CTkFrame(left_frame, fg_color="transparent")
        add_split_container.grid(row=3, column=0, sticky="ew", pady=(10, 10))
        add_split_container.grid_columnconfigure(0, weight=1)
        add_split_container.grid_columnconfigure(1, weight=1, uniform="split_action", minsize=260)
        add_split_container.grid_columnconfigure(2, weight=1, uniform="split_action", minsize=260)
        add_split_container.grid_columnconfigure(3, weight=1)

        self.btn_add_split = ctk.CTkButton(
            add_split_container,
            text="現在のページに分割点を設定する",
            command=self.add_split_point,
            width=280,
            fg_color="#f39c12",
            hover_color="#d68910",
            text_color="#111111",
            text_color_disabled="#666666",
            state="disabled"
        )
        self.btn_add_split.grid(row=0, column=1, sticky="ew", padx=(0, 5))

        self.btn_remove_split = ctk.CTkButton(
            add_split_container,
            text="現在のページの分割点を消去",
            command=self.remove_split_point,
            width=280,
            fg_color="gray",
            hover_color="darkgray",
            state="disabled"
        )
        self.btn_remove_split.grid(row=0, column=2, sticky="ew")

        self.lbl_zoom_info = ctk.CTkLabel(add_split_container, text="倍率: 100%", anchor="w")
        self.lbl_zoom_info.grid(row=0, column=0, sticky="w", padx=(5, 10))

    def init_right_frame(self):
        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        right_frame.grid_columnconfigure(0, weight=1)

        self.btn_open = ctk.CTkButton(right_frame, text="PDFを開く", command=self.open_pdf)
        self.btn_open.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        self.btn_clear_split = ctk.CTkButton(right_frame, text="すべての分割点をリセット", 
                                             command=self.clear_split_points, fg_color="gray", hover_color="darkgray",
                                             state="disabled")
        self.btn_clear_split.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.btn_split_every_page = ctk.CTkButton(
            right_frame,
            text="全体を1ページずつ分割する",
            command=self.split_every_page,
            fg_color="#b04a4a",
            hover_color="#953f3f",
            state="disabled"
        )
        self.btn_split_every_page.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

        # --- アクティブセクション表示エリア ---
        section_area = ctk.CTkFrame(right_frame)
        section_area.grid(row=4, column=0, sticky="nsew", padx=10, pady=(10, 5))
        section_area.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(4, weight=1)

        lbl_section_title = ctk.CTkLabel(section_area, text="現在のセクション:", anchor="w")
        lbl_section_title.grid(row=0, column=0, sticky="w", padx=5, pady=(5, 0))

        # セクション番号 / 総セクション数 + ページ範囲 + 色マーカー
        section_info_frame = ctk.CTkFrame(section_area, fg_color="transparent")
        section_info_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        section_info_frame.grid_columnconfigure(1, weight=1)

        self.section_color_marker = tk.Canvas(section_info_frame, width=20, height=20, highlightthickness=0)
        self.section_color_marker.grid(row=0, column=0, padx=(0, 8))

        self.lbl_section_info = ctk.CTkLabel(section_info_frame, text="- / -", anchor="w", font=ctk.CTkFont(size=14))
        self.lbl_section_info.grid(row=0, column=1, sticky="w")

        self.lbl_section_range = ctk.CTkLabel(section_area, text="ページ範囲: -", anchor="w")
        self.lbl_section_range.grid(row=2, column=0, sticky="w", padx=5, pady=(0, 5))

        # ファイル名入力
        lbl_filename = ctk.CTkLabel(section_area, text="出力ファイル名:", anchor="w")
        lbl_filename.grid(row=3, column=0, sticky="w", padx=5)

        self.txt_section_filename = ctk.CTkEntry(section_area, placeholder_text="ファイル名を入力")
        self.txt_section_filename.grid(row=4, column=0, sticky="ew", padx=5, pady=(0, 5))
        self.txt_section_filename.bind("<Tab>", self._on_section_entry_tab)
        self.txt_section_filename.bind("<Return>", self._on_section_entry_return)
        self.txt_section_filename.bind("<KP_Enter>", self._on_section_entry_return)
        self.txt_section_filename.bind("<Delete>", self._on_section_entry_delete)
        self.txt_section_filename.bind("<Shift-Return>", self.on_shift_enter_execute_key)
        self.txt_section_filename.bind("<Shift-KP_Enter>", self.on_shift_enter_execute_key)
        self.txt_section_filename.bind("<FocusOut>", self._on_section_entry_focus_out)

        # セクション間ナビゲーションボタン
        section_nav_frame = ctk.CTkFrame(section_area, fg_color="transparent")
        section_nav_frame.grid(row=5, column=0, sticky="ew", padx=5, pady=5)
        section_nav_frame.grid_columnconfigure((0, 1), weight=1)

        self.btn_prev_section = ctk.CTkButton(
            section_nav_frame, text="< 前のセクション",
            command=self.prev_section, state="disabled"
        )
        self.btn_prev_section.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self.btn_next_section = ctk.CTkButton(
            section_nav_frame, text="次のセクション >",
            command=self.next_section, state="disabled"
        )
        self.btn_next_section.grid(row=0, column=1, sticky="ew", padx=(3, 0))

        self.btn_remove_active_section_split = ctk.CTkButton(
            section_area,
            text="このセクションの開始分割点を消去",
            command=self.remove_active_section_split_point,
            fg_color="gray",
            hover_color="darkgray",
            state="disabled"
        )
        self.btn_remove_active_section_split.grid(row=6, column=0, sticky="ew", padx=5, pady=(12, 5))

        self.btn_execute = ctk.CTkButton(right_frame, text="分割を実行", command=self.execute_split, 
                                         fg_color="#2ecc71", hover_color="#27ae60", text_color="white",
                                         state="disabled")
        self.btn_execute.grid(row=6, column=0, sticky="ew", padx=10, pady=10)

    def open_pdf(self):
        if self.is_splitting:
            messagebox.showinfo("実行中", "分割処理の実行中はPDFを開けません。")
            return

        file_path = filedialog.askopenfilename(title="PDFファイルを選択", filetypes=[("PDF Files", "*.pdf")])
        if file_path:
            if self.doc:
                self.doc.close()
            self.doc = fitz.open(file_path)
            self.source_pdf_path = file_path
            self.current_page_idx = 0
            self.split_points = []
            self.sections_data = []
            self.preview_zoom = 1.0
            self.preview_render_cache.clear()
            self._rebuild_sections_data()
            self.render_page()

    def on_closing(self):
        if self.split_queue_poll_job is not None:
            try:
                self.after_cancel(self.split_queue_poll_job)
            except Exception:
                pass
            self.split_queue_poll_job = None

        if self.doc:
            self.doc.close()
            self.doc = None

        self.preview_render_cache.clear()
        self.destroy()

    # ------------------------------------------------------------------
    # データモデル管理
    # ------------------------------------------------------------------

    def _rebuild_sections_data(self):
        """分割点から sections_data を再構築する。
        開始ページをキーにして、ユーザーが手入力したカスタムファイル名を引き継ぐ。
        """
        if not self.doc:
            self.sections_data = []
            return

        # 旧データを開始ページで索引化 (カスタム名の引き継ぎ用)
        old_by_start = {}
        for sec in self.sections_data:
            old_by_start[sec['start']] = sec

        points = [0] + sorted(self.split_points) + [len(self.doc)]
        new_data = []
        for i in range(len(points) - 1):
            start = points[i]
            end = points[i + 1] - 1
            default_name = f"output_part{i + 1}.pdf"

            old = old_by_start.get(start)
            if old and old.get('is_custom_name'):
                filename = old['filename']
                is_custom = True
            else:
                filename = default_name
                is_custom = False

            new_data.append({
                'start': start,
                'end': end,
                'filename': filename,
                'is_custom_name': is_custom,
            })

        self.sections_data = new_data

    def _get_active_section_index(self):
        """現在表示中のページが属するセクションのインデックスを返す。"""
        for i, sec in enumerate(self.sections_data):
            if sec['start'] <= self.current_page_idx <= sec['end']:
                return i
        return 0 if self.sections_data else -1

    def _save_active_section_filename(self):
        """UIのテキストボックスの内容をデータモデルに反映する。"""
        idx = self._get_active_section_index()
        if idx < 0 or idx >= len(self.sections_data):
            return

        text = self.txt_section_filename.get().strip()
        sec = self.sections_data[idx]
        default_name = f"output_part{idx + 1}.pdf"
        reserved_names = {
            "con", "prn", "aux", "nul",
            "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
            "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
        }

        sanitized = re.sub(r'[\\/*?:"<>|]', '_', text)
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        if sanitized.lower().endswith('.pdf'):
            sanitized = sanitized[:-4]
        sanitized = sanitized.strip(' ._')
        sanitized = re.sub(r'_+', '_', sanitized)

        is_invalid = (
            not sanitized
            or sanitized.lower() in reserved_names
            or re.fullmatch(r'_+', sanitized) is not None
        )

        if is_invalid:
            sec['filename'] = default_name
            sec['is_custom_name'] = False
            return

        candidate = f"{sanitized}.pdf"
        if candidate == default_name:
            sec['filename'] = default_name
            sec['is_custom_name'] = False
        else:
            sec['filename'] = candidate
            sec['is_custom_name'] = True

    def _update_active_section_ui(self):
        """アクティブセクション表示を更新する。"""
        idx = self._get_active_section_index()
        total = len(self.sections_data)

        if idx < 0 or total == 0:
            self.lbl_section_info.configure(text="- / -")
            self.lbl_section_range.configure(text="ページ範囲: -")
            self.txt_section_filename.delete(0, "end")
            self.section_color_marker.configure(bg="gray")
            return

        sec = self.sections_data[idx]
        color = self.split_bar.colors[idx % len(self.split_bar.colors)]

        self.lbl_section_info.configure(text=f"セクション {idx + 1} / {total}")
        self.lbl_section_range.configure(text=f"ページ範囲: P.{sec['start'] + 1} - P.{sec['end'] + 1}")
        self.section_color_marker.configure(bg=color)

        # テキストボックスの内容を更新 (フォーカスがある場合はユーザー入力を尊重)
        current_text = self.txt_section_filename.get()
        if current_text != sec['filename']:
            self.txt_section_filename.delete(0, "end")
            self.txt_section_filename.insert(0, sec['filename'])

    def render_page(self):
        if not self.doc: return

        page = self.doc.load_page(self.current_page_idx)
        page_rect = page.rect

        frame_width = self.preview_canvas.winfo_width()
        frame_height = self.preview_canvas.winfo_height()

        # 初回レンダリング時などサイズが取得できない場合のフォールバック
        if frame_width <= 1 or frame_height <= 1:
            frame_width, frame_height = 500, 600

        cache_key = (self.current_page_idx, round(self.preview_zoom, 2), frame_width, frame_height)
        cached_image = self.preview_render_cache.get(cache_key)
        if cached_image is not None:
            self.preview_render_cache.move_to_end(cache_key)
            self.preview_image_tk = cached_image
            target_width = cached_image.width()
            target_height = cached_image.height()
        else:
            fit_ratio = min(frame_width / page_rect.width, frame_height / page_rect.height)
            final_scale = max(0.01, fit_ratio * self.preview_zoom)
            pix = page.get_pixmap(matrix=fitz.Matrix(final_scale, final_scale))
            mode = "RGBA" if pix.alpha else "RGB"
            img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
            target_width = img.width
            target_height = img.height

            self.preview_image_tk = ImageTk.PhotoImage(img)
            self.preview_render_cache[cache_key] = self.preview_image_tk
            self.preview_render_cache.move_to_end(cache_key)

            while len(self.preview_render_cache) > self.preview_render_cache_limit:
                _, old_image = self.preview_render_cache.popitem(last=False)
                del old_image

        self.preview_canvas.delete("all")

        image_x = max((frame_width - target_width) // 2, 0)
        image_y = max((frame_height - target_height) // 2, 0)
        self.preview_canvas.create_image(image_x, image_y, anchor="nw", image=self.preview_image_tk)

        scroll_width = max(frame_width, target_width)
        scroll_height = max(frame_height, target_height)
        self.preview_canvas.configure(scrollregion=(0, 0, scroll_width, scroll_height))
        self.preview_canvas.xview_moveto(0)
        self.preview_canvas.yview_moveto(0)
        self.preview_can_pan = target_width > frame_width or target_height > frame_height
        self.update_preview_cursor()
        self.lbl_zoom_info.configure(text=f"倍率: {int(self.preview_zoom * 100)}%")
        
        self.update_ui_state()

    def set_preview_zoom(self, value):
        if not self.doc:
            return

        clamped_zoom = max(self.preview_zoom_min, min(self.preview_zoom_max, value))
        snapped_zoom = round(clamped_zoom, 2)
        if snapped_zoom == self.preview_zoom:
            return

        self.preview_zoom = snapped_zoom
        self.render_page()

    def zoom_in(self):
        self.set_preview_zoom(self.preview_zoom + self.preview_zoom_step)

    def zoom_out(self):
        self.set_preview_zoom(self.preview_zoom - self.preview_zoom_step)

    def reset_zoom(self):
        self.set_preview_zoom(1.0)

    def on_preview_zoom_in_key(self, event):
        self.zoom_in()
        return "break"

    def on_preview_zoom_out_key(self, event):
        self.zoom_out()
        return "break"

    def on_preview_zoom_reset_key(self, event):
        self.reset_zoom()
        return "break"

    def on_preview_mouse_down(self, event):
        self.preview_canvas.focus_set()
        if self.preview_can_pan:
            self.preview_canvas.scan_mark(event.x, event.y)
            self.preview_canvas.configure(cursor="fleur")

    def on_preview_mouse_drag(self, event):
        if not self.doc:
            return "break"

        if self.preview_can_pan:
            self.preview_canvas.scan_dragto(event.x, event.y, gain=1)
        return "break"

    def on_preview_mouse_up(self, event):
        self.update_preview_cursor()

    def on_preview_mouse_enter(self, event):
        self.update_preview_cursor()

    def on_preview_mouse_leave(self, event):
        self.preview_canvas.configure(cursor="")

    def on_preview_focus_in(self, event):
        self.preview_canvas.configure(
            highlightthickness=1,
            highlightbackground="#3b82f6",
            highlightcolor="#3b82f6",
        )

    def on_preview_focus_out(self, event):
        self.preview_canvas.configure(highlightthickness=0)

    def update_preview_cursor(self):
        cursor = "hand2" if self.preview_can_pan else ""
        self.preview_canvas.configure(cursor=cursor)

    def prev_page(self):
        if self.doc and self.current_page_idx > 0:
            self.current_page_idx -= 1
            self.render_page()

    def next_page(self):
        if self.doc and self.current_page_idx < len(self.doc) - 1:
            self.current_page_idx += 1
            self.render_page()

    def prev_10_pages(self):
        if self.doc and self.current_page_idx > 0:
            self.current_page_idx = max(0, self.current_page_idx - 10)
            self.render_page()

    def next_10_pages(self):
        if self.doc and self.current_page_idx < len(self.doc) - 1:
            self.current_page_idx = min(len(self.doc) - 1, self.current_page_idx + 10)
            self.render_page()

    def on_preview_pageup_key(self, event):
        self.prev_page()
        return "break"

    def on_preview_pagedown_key(self, event):
        self.next_page()
        return "break"

    def on_preview_ctrl_pageup_key(self, event):
        self.prev_10_pages()
        return "break"

    def on_preview_ctrl_pagedown_key(self, event):
        self.next_10_pages()
        return "break"

    def on_ctrl_up_section_key(self, event):
        self.prev_section()
        return "break"

    def on_ctrl_down_section_key(self, event):
        self.next_section()
        return "break"

    def on_preview_home_key(self, event):
        self.go_to_page(0)
        return "break"

    def on_preview_end_key(self, event):
        if self.doc:
            self.go_to_page(len(self.doc) - 1)
        return "break"

    def on_preview_enter_key(self, event):
        if event.state & 0x0001:
            return self.on_shift_enter_execute_key(event)

        self.add_split_point()
        return "break"

    def on_preview_delete_key(self, event):
        self.remove_split_point()
        return "break"

    def on_shift_enter_execute_key(self, event):
        if not self.doc or self.is_splitting or self.btn_execute.cget("state") != "normal":
            return "break"

        self.execute_split()
        return "break"

    def go_to_page(self, page_idx):
        if not self.doc:
            return

        if 0 <= page_idx < len(self.doc) and page_idx != self.current_page_idx:
            self._save_active_section_filename()
            self.current_page_idx = page_idx
            self.render_page()

    # ------------------------------------------------------------------
    # セクション間ナビゲーション
    # ------------------------------------------------------------------

    def prev_section(self):
        idx = self._get_active_section_index()
        if idx > 0:
            self._save_active_section_filename()
            self.current_page_idx = self.sections_data[idx - 1]['start']
            self.render_page()

    def next_section(self):
        idx = self._get_active_section_index()
        if idx < len(self.sections_data) - 1:
            self._save_active_section_filename()
            self.current_page_idx = self.sections_data[idx + 1]['start']
            self.render_page()

    def remove_active_section_split_point(self):
        idx = self._get_active_section_index()
        if idx <= 0 or idx >= len(self.sections_data):
            return

        split_point = self.sections_data[idx]['start']
        if split_point in self.split_points:
            self._save_active_section_filename()
            self.split_points.remove(split_point)
            self._rebuild_sections_data()
            self.update_ui_state()

    def _on_section_entry_tab(self, event):
        """Tab押下: 保存 → 次セクションへ → テキスト全選択"""
        self._save_active_section_filename()
        idx = self._get_active_section_index()
        if idx < len(self.sections_data) - 1:
            self.current_page_idx = self.sections_data[idx + 1]['start']
            self.render_page()
        self.after(10, self._focus_and_select_entry)
        return "break"

    def _focus_and_select_entry(self):
        self.txt_section_filename.focus_set()
        self.txt_section_filename.select_range(0, "end")
        self.txt_section_filename.icursor("end")

    def _on_section_entry_return(self, event):
        """Enter押下: Shift+Enterでなければ Tab と同じ挙動"""
        if event.state & 0x0001:
            return self.on_shift_enter_execute_key(event)
        return self._on_section_entry_tab(event)

    def _on_section_entry_focus_out(self, event):
        """テキストボックスからフォーカスが外れたら保存"""
        self._save_active_section_filename()

    def _on_section_entry_delete(self, event):
        """Delete押下: 現在セクションの開始分割点を削除"""
        self.remove_active_section_split_point()
        return "break"

    # ------------------------------------------------------------------
    # 分割点操作
    # ------------------------------------------------------------------

    def add_split_point(self):
        if not self.doc: return
        if self.current_page_idx > 0 and self.current_page_idx not in self.split_points:
            self._save_active_section_filename()
            self.split_points.append(self.current_page_idx)
            self.split_points.sort()
            self._rebuild_sections_data()
            self.update_ui_state()

    def remove_split_point(self):
        if not self.doc:
            return

        if self.current_page_idx in self.split_points:
            self._save_active_section_filename()
            self.split_points.remove(self.current_page_idx)
            self._rebuild_sections_data()
            self.update_ui_state()

    def clear_split_points(self):
        answer = messagebox.askyesno(
            "確認",
            "現在の分割点をすべてリセットします。\n実行しますか？"
        )
        if not answer:
            return

        self.split_points = []
        self._rebuild_sections_data()
        self.update_ui_state()

    def split_every_page(self):
        if not self.doc:
            return

        answer = messagebox.askyesno(
            "確認",
            "分割点を1ページごとに一括設定します。現在の分割点は上書きされます。\n実行しますか？"
        )
        if not answer:
            return

        total_pages = len(self.doc)
        if total_pages <= 1:
            self.split_points = []
        else:
            self.split_points = list(range(1, total_pages))

        self._rebuild_sections_data()
        self.update_ui_state()

    # ------------------------------------------------------------------
    # UI状態の一括更新
    # ------------------------------------------------------------------

    def update_ui_state(self):
        if self.doc:
            total = len(self.doc)
            active_idx = self._get_active_section_index()
            self.lbl_page_info.configure(text=f"{self.current_page_idx + 1} / {total}")
            self.split_bar.update_state(total, self.current_page_idx, self.split_points, active_idx)
            self.lbl_zoom_info.configure(text=f"倍率: {int(self.preview_zoom * 100)}%")
        else:
            self.lbl_zoom_info.configure(text="倍率: 100%")
            active_idx = -1
        
        state_prev = "normal" if self.doc and self.current_page_idx > 0 else "disabled"
        state_next = "normal" if self.doc and self.current_page_idx < (len(self.doc)-1 if self.doc else 0) else "disabled"
        state_add = "normal" if self.doc and self.current_page_idx > 0 and self.current_page_idx not in self.split_points else "disabled"
        state_remove = "normal" if self.doc and self.current_page_idx in self.split_points else "disabled"
        state_clear_split = "normal" if self.doc else "disabled"
        state_split_every_page = "normal" if self.doc and len(self.doc) > 1 else "disabled"
        state_exec = "normal" if self.doc else "disabled"
        state_prev_sec = "normal" if self.doc and active_idx > 0 else "disabled"
        state_next_sec = "normal" if self.doc and active_idx < len(self.sections_data) - 1 else "disabled"
        state_remove_active_section_split = "normal" if (
            self.doc
            and active_idx > 0
            and active_idx < len(self.sections_data)
            and self.sections_data[active_idx]['start'] in self.split_points
        ) else "disabled"

        if self.is_splitting:
            state_prev = "disabled"
            state_next = "disabled"
            state_add = "disabled"
            state_remove = "disabled"
            state_clear_split = "disabled"
            state_split_every_page = "disabled"
            state_exec = "disabled"
            state_prev_sec = "disabled"
            state_next_sec = "disabled"
            state_remove_active_section_split = "disabled"

        self.btn_open.configure(state="disabled" if self.is_splitting else "normal")
        self.btn_prev.configure(state=state_prev)
        self.btn_prev_10.configure(state=state_prev)
        self.btn_next.configure(state=state_next)
        self.btn_next_10.configure(state=state_next)
        self.btn_add_split.configure(state=state_add)
        self.btn_remove_split.configure(state=state_remove)
        self.btn_clear_split.configure(state=state_clear_split)
        self.btn_split_every_page.configure(state=state_split_every_page)
        self.btn_execute.configure(state=state_exec)
        self.btn_prev_section.configure(state=state_prev_sec)
        self.btn_next_section.configure(state=state_next_sec)
        self.btn_remove_active_section_split.configure(state=state_remove_active_section_split)
        self.txt_section_filename.configure(state="normal" if self.doc and not self.is_splitting else "disabled")

        # アクティブセクション表示を更新
        self._update_active_section_ui()

    # ------------------------------------------------------------------
    # 分割実行
    # ------------------------------------------------------------------

    def _ensure_unique_output_path(self, output_dir, filename):
        target_path = output_dir / filename
        stem = target_path.stem
        suffix = target_path.suffix
        counter = 1

        while target_path.exists():
            target_path = output_dir / f"{stem} ({counter}){suffix}"
            counter += 1

        return target_path

    def _collect_split_jobs(self):
        """データモデル (sections_data) から分割ジョブを生成する。"""
        jobs = []

        for i, sec in enumerate(self.sections_data):
            filename = sec['filename'].strip()
            if not filename:
                filename = f"output_part{i + 1}.pdf"
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"

            jobs.append({
                'index': i + 1,
                'start': sec['start'],
                'end': sec['end'],
                'filename': filename,
            })

        return jobs

    def _set_split_running(self, is_running):
        self.is_splitting = is_running
        self.update_ui_state()

    def _on_split_success(self, file_count):
        self._set_split_running(False)
        messagebox.showinfo("完了", f"PDFの分割が完了しました。\n作成ファイル数: {file_count}")

    def _on_split_error(self, error_message):
        self._set_split_running(False)
        messagebox.showerror("保存エラー", error_message)

    def _poll_split_result_queue(self):
        while True:
            try:
                result = self.split_result_queue.get_nowait()
            except queue.Empty:
                break

            result_type = result.get('type')
            if result_type == 'success':
                self._on_split_success(result.get('file_count', 0))
            elif result_type == 'error':
                self._on_split_error(result.get('message', '不明なエラーが発生しました。'))

        if self.is_splitting:
            self.split_queue_poll_job = self.after(100, self._poll_split_result_queue)
        else:
            self.split_queue_poll_job = None

    def _split_worker(self, source_pdf_path, out_dir, jobs):
        output_dir = Path(out_dir)
        current_job_desc = "(初期化中)"

        try:
            with fitz.open(source_pdf_path) as source_doc:
                for job in jobs:
                    current_job_desc = f"{job['index']}番目のセクション（{job['filename']}）"
                    out_path = self._ensure_unique_output_path(output_dir, job['filename'])

                    with fitz.open() as new_doc:
                        new_doc.insert_pdf(source_doc, from_page=job['start'], to_page=job['end'])
                        try:
                            new_doc.save(str(out_path))
                        except PermissionError as e:
                            self.split_result_queue.put({
                                'type': 'error',
                                'message': (
                                    "保存先ファイルが他のアプリで使用中のため保存できませんでした。\n"
                                    f"対象ファイル: {out_path}\n"
                                    f"詳細: {e}"
                                ),
                            })
                            return

        except Exception as e:
            desc = current_job_desc
            err = str(e)
            self.split_result_queue.put({
                'type': 'error',
                'message': f"{desc}の保存中にエラーが発生しました:\n{err}",
            })
            return

        self.split_result_queue.put({'type': 'success', 'file_count': len(jobs)})

    def execute_split(self):
        if not self.doc or self.is_splitting:
            return

        # 実行前にアクティブセクションの入力を保存
        self._save_active_section_filename()

        out_dir = filedialog.askdirectory(title="保存先フォルダを選択")
        if not out_dir:
            return

        if not self.source_pdf_path:
            messagebox.showerror("エラー", "元PDFのパスが取得できませんでした。PDFを開き直してください。")
            return

        jobs = self._collect_split_jobs()
        if not jobs:
            messagebox.showerror("エラー", "分割対象のセクションがありません。")
            return

        while True:
            try:
                self.split_result_queue.get_nowait()
            except queue.Empty:
                break

        self._set_split_running(True)
        if self.split_queue_poll_job is None:
            self.split_queue_poll_job = self.after(100, self._poll_split_result_queue)

        worker = threading.Thread(
            target=self._split_worker,
            args=(self.source_pdf_path, out_dir, jobs),
            daemon=True,
        )
        worker.start()

if __name__ == "__main__":
    app = App()
    app.mainloop()