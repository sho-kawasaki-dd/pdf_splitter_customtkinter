import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
import fitz  # PyMuPDF
from PIL import Image

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

    def update_state(self, total, current, splits):
        self.total_pages = total
        self.current_page = current
        self.split_points = sorted(splits)
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

        # --- 3. 現在位置のインジケーター（逆三角形） ---
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

        self.doc = None
        self.current_page_idx = 0
        self.split_points = []
        self.section_widgets = [] # スクロールフレーム内のウィジェット管理用

        self.grid_columnconfigure(0, weight=7)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        self.init_left_frame()
        self.init_right_frame()

    def init_left_frame(self):
        left_frame = ctk.CTkFrame(self)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        left_frame.grid_rowconfigure(0, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        # PDFプレビュー領域
        self.pdf_label = ctk.CTkLabel(left_frame, text="PDFを開いてください", takefocus=True)
        self.pdf_label.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.pdf_label.bind("<Button-1>", lambda event: self.pdf_label.focus_set())
        self.pdf_label.bind("<Left>", self.on_preview_left_key)
        self.pdf_label.bind("<Right>", self.on_preview_right_key)
        self.pdf_label.bind("<Home>", self.on_preview_home_key)
        self.pdf_label.bind("<End>", self.on_preview_end_key)
        self.pdf_label.bind("<Prior>", self.on_preview_pageup_key)
        self.pdf_label.bind("<Next>", self.on_preview_pagedown_key)
        self.pdf_label.bind("<Return>", self.on_preview_enter_key)
        self.pdf_label.bind("<KP_Enter>", self.on_preview_enter_key)

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
        add_split_container.grid_columnconfigure(0, weight=3)
        add_split_container.grid_columnconfigure(1, weight=4)
        add_split_container.grid_columnconfigure(2, weight=3)

        self.btn_add_split = ctk.CTkButton(
            add_split_container,
            text="現在のページを分割点の始点にする",
            command=self.add_split_point,
            fg_color="#f39c12",
            hover_color="#d68910",
            text_color="#111111",
            text_color_disabled="#666666",
            state="disabled"
        )
        self.btn_add_split.grid(row=0, column=1, sticky="ew")

    def init_right_frame(self):
        right_frame = ctk.CTkFrame(self)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        right_frame.grid_columnconfigure(0, weight=1)

        self.btn_open = ctk.CTkButton(right_frame, text="PDFを開く", command=self.open_pdf)
        self.btn_open.grid(row=0, column=0, sticky="ew", padx=10, pady=10)

        self.btn_clear_split = ctk.CTkButton(right_frame, text="分割点をリセット", 
                                             command=self.clear_split_points, fg_color="gray", hover_color="darkgray",
                                             state="disabled")
        self.btn_clear_split.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.btn_split_every_page = ctk.CTkButton(
            right_frame,
            text="全体を1ページずつ分割する",
            command=self.split_every_page,
            state="disabled"
        )
        self.btn_split_every_page.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

        lbl_section = ctk.CTkLabel(right_frame, text="分割セクションと出力ファイル名:")
        lbl_section.grid(row=4, column=0, sticky="w", padx=10, pady=(10, 0))

        # 分割セクションのリスト表示領域
        self.scroll_frame = ctk.CTkScrollableFrame(right_frame)
        self.scroll_frame.grid(row=5, column=0, sticky="nsew", padx=10, pady=5)
        right_frame.grid_rowconfigure(5, weight=1)

        self.btn_execute = ctk.CTkButton(right_frame, text="分割を実行", command=self.execute_split, 
                                         fg_color="#2ecc71", hover_color="#27ae60", text_color="white",
                                         state="disabled")
        self.btn_execute.grid(row=6, column=0, sticky="ew", padx=10, pady=10)

    def open_pdf(self):
        file_path = filedialog.askopenfilename(title="PDFファイルを選択", filetypes=[("PDF Files", "*.pdf")])
        if file_path:
            if self.doc:
                self.doc.close()
            self.doc = fitz.open(file_path)
            self.current_page_idx = 0
            self.split_points = []
            self.render_page()
            self.update_sections_ui()

    def render_page(self):
        if not self.doc: return

        page = self.doc.load_page(self.current_page_idx)
        # 画像化 (解像度調整)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
        mode = "RGBA" if pix.alpha else "RGB"
        img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

        # 表示領域に合わせて画像をリサイズしつつアスペクト比を維持
        frame_width = self.pdf_label.winfo_width()
        frame_height = self.pdf_label.winfo_height()
        
        # 初回レンダリング時などサイズが取得できない場合のフォールバック
        if frame_width <= 1 or frame_height <= 1:
            frame_width, frame_height = 500, 600

        img.thumbnail((frame_width, frame_height), Image.Resampling.LANCZOS)
        
        # CTkImageに変換して表示
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(img.width, img.height))
        self.pdf_label.configure(image=ctk_img, text="")
        
        self.update_ui_state()

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

    def on_preview_left_key(self, event):
        self.prev_page()

    def on_preview_right_key(self, event):
        self.next_page()
        return "break"

    def on_preview_pageup_key(self, event):
        self.prev_10_pages()
        return "break"

    def on_preview_pagedown_key(self, event):
        self.next_10_pages()
        return "break"

    def on_preview_home_key(self, event):
        self.go_to_page(0)
        return "break"

    def on_preview_end_key(self, event):
        if self.doc:
            self.go_to_page(len(self.doc) - 1)
        return "break"

    def on_preview_enter_key(self, event):
        self.add_split_point()
        return "break"

    def go_to_page(self, page_idx):
        if not self.doc:
            return

        if 0 <= page_idx < len(self.doc) and page_idx != self.current_page_idx:
            self.current_page_idx = page_idx
            self.render_page()

    def on_section_click(self, start_page):
        self.go_to_page(start_page)

    def add_split_point(self):
        if not self.doc: return
        if self.current_page_idx > 0 and self.current_page_idx not in self.split_points:
            self.split_points.append(self.current_page_idx)
            self.split_points.sort()
            self.update_sections_ui()
            self.update_ui_state()

    def clear_split_points(self):
        answer = messagebox.askyesno(
            "確認",
            "現在の分割点をすべてリセットします。\n実行しますか？"
        )
        if not answer:
            return

        self.split_points = []
        self.update_sections_ui()
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

        self.update_sections_ui()
        self.update_ui_state()

    def update_sections_ui(self):
        # 既存のウィジェットを削除
        for widget_dict in self.section_widgets:
            widget_dict['frame'].destroy()
        self.section_widgets.clear()

        if not self.doc: return

        points = [0] + self.split_points + [len(self.doc)]
        for i in range(len(points) - 1):
            start = points[i]
            end = points[i+1] - 1
            
            # 各セクションを包むフレーム
            item_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            item_frame.pack(fill="x", pady=2)
            item_frame.grid_columnconfigure(2, weight=1)

            # 色マーカー (tk.Canvasを使用)
            color = self.split_bar.colors[i % len(self.split_bar.colors)]
            marker = tk.Canvas(item_frame, width=15, height=15, bg=color, highlightthickness=0)
            marker.grid(row=0, column=0, padx=(0, 5))

            lbl_range = ctk.CTkLabel(item_frame, text=f"P.{start+1} - P.{end+1}", width=80, anchor="w")
            lbl_range.grid(row=0, column=1, padx=5)

            txt_filename = ctk.CTkEntry(item_frame, placeholder_text=f"output_part{i+1}.pdf")
            txt_filename.grid(row=0, column=2, sticky="ew")

            clickable_widgets = [item_frame, marker, lbl_range]
            for widget in clickable_widgets:
                widget.bind("<Button-1>", lambda event, s=start: self.on_section_click(s))

            self.section_widgets.append({
                'frame': item_frame,
                'entry': txt_filename,
                'start': start,
                'end': end
            })

    def update_ui_state(self):
        if self.doc:
            total = len(self.doc)
            self.lbl_page_info.configure(text=f"{self.current_page_idx + 1} / {total}")
            self.split_bar.update_state(total, self.current_page_idx, self.split_points)
        
        state_prev = "normal" if self.doc and self.current_page_idx > 0 else "disabled"
        state_next = "normal" if self.doc and self.current_page_idx < (len(self.doc)-1 if self.doc else 0) else "disabled"
        state_add = "normal" if self.doc and self.current_page_idx > 0 else "disabled"
        state_clear_split = "normal" if self.doc else "disabled"
        state_split_every_page = "normal" if self.doc and len(self.doc) > 1 else "disabled"
        state_exec = "normal" if self.doc else "disabled"

        self.btn_prev.configure(state=state_prev)
        self.btn_prev_10.configure(state=state_prev)
        self.btn_next.configure(state=state_next)
        self.btn_next_10.configure(state=state_next)
        self.btn_add_split.configure(state=state_add)
        self.btn_clear_split.configure(state=state_clear_split)
        self.btn_split_every_page.configure(state=state_split_every_page)
        self.btn_execute.configure(state=state_exec)

    def execute_split(self):
        if not self.doc: return

        out_dir = filedialog.askdirectory(title="保存先フォルダを選択")
        if not out_dir: return

        for i, widget_dict in enumerate(self.section_widgets):
            start = widget_dict['start']
            end = widget_dict['end']
            entry = widget_dict['entry']
            
            filename = entry.get().strip()
            if not filename:
                # CTkEntryのcgetでplaceholder_textを取得
                filename = entry.cget("placeholder_text")
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"
                
            out_path = f"{out_dir}/{filename}"
            
            new_doc = fitz.open()
            new_doc.insert_pdf(self.doc, from_page=start, to_page=end)
            new_doc.save(out_path)
            new_doc.close()
            
        messagebox.showinfo("完了", "PDFの分割が完了しました。")

if __name__ == "__main__":
    app = App()
    app.mainloop()