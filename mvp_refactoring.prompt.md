# **役割と目的**

あなたは優秀なPython / GUIアプリケーションエンジニアです。

提供された単一ファイルのGUIアプリケーション（main.py）を、MVP（Model-View-Presenter）アーキテクチャに基づいてリファクタリングしてください。

# **コンテキストと課題**

現在のコードはCustomTkinterとPyMuPDF(fitz)を使用したPDF分割アプリですが、「UIの構築」「状態管理」「PDF操作ロジック」「非同期処理」がすべて App クラスに密結合する「Fat GUI」になっています。

今後の拡張（バッチ処理やアルゴリズムの追加など）に備え、各責務を分離し、テストしやすく保守性の高いコードベースに再構築することが目標です。

# **アーキテクチャ方針 (MVP)**

以下の原則に従ってモジュールを分割してください。

ただし、Tkinterの性質上、ViewとPresenter間のイベント伝達を厳密にしすぎるとボイラープレートが過剰になるため、「Viewは描画とユーザー入力の検知に徹し、処理はPresenterのメソッドを直接呼ぶ」という実用的なアプローチ（Passive Viewに近い形）を採用してください。

* **Model**: UIを一切知らない純粋なPythonクラス。PyMuPDFへの依存もこの層に閉じ込める。  
  * 状態管理（ページ番号、分割点、セクション情報）  
  * PDF画像の生成とキャッシュ  
  * 非同期でのファイル分割処理  
* **View**: CustomTkinter / Tkinterへの依存をここに閉じ込める。ドメインロジックや状態（現在ページなど）を自前で保持せず、Presenterから渡されたデータ（ViewModel等）に基づいてUIを更新する。  
* **Presenter**: Viewからの入力イベントを受け取り、Modelを操作し、Modelの最新状態を取得してViewに描画指示を出す。

# **目標とするディレクトリ構成**

pdf\_splitter/  
├── main.py  
├── model/  
│   ├── pdf\_document.py     (PDF読み込み・画像生成)  
│   ├── split\_session.py    (分割点・セクション状態管理)  
│   └── pdf\_processor.py    (非同期でのPDF分割・保存処理)  
├── view/  
│   ├── main\_window.py      (全体のレイアウト構築)  
│   └── components/  
│       ├── split\_bar.py    (カスタムプログレスバー)  
│       ├── preview.py      (画像プレビュー領域)  
│       └── controls.py     (各種ボタン・入力エリア)  
└── presenter/  
    └── main\_presenter.py   (ModelとViewの調停)

# **指示（ステップバイステップでの実行）**

一度に全コードを出力するとコンテキスト上限やバグの特定が難しくなるため、以下のステップで**段階的**にコードを出力してください。

今回は **【Step 1】** のみを実行して、出力を提示してください。（私が「次へ」と指示したらStep 2に進んでください）

### **【Step 1】 Model層の実装**

現在の main.py から、ビジネスロジックと状態管理を抽出し、以下の3つのファイルを作成してください。UIに関するコード（Tkinter等）は絶対に含めないでください。

1. model/split\_session.py  
   * current\_page\_idx, split\_points, sections\_data の管理。  
   * add\_split\_point, \_rebuild\_sections\_data などの純粋なロジック。  
2. model/pdf\_document.py  
   * PyMuPDFのラップ。ファイルを開く、ページ数を取得する。  
   * 現在の App にある preview\_render\_cache のロジックをここに移植し、指定ページの画像（PIL Image等）を返すメソッドを実装する。  
3. model/pdf\_processor.py  
   * threading と queue による非同期ファイル分割・保存ロジック（現在の \_split\_worker に相当）。

### **【Step 2】 View層の構築 (※今回は実行しない)**

Model層に依存せず、UIの構築とイベントのバインディング用のインターフェースを持つViewコンポーネント群を作成。

### **【Step 3】 Presenterとエントリーポイントの実装 (※今回は実行しない)**

ModelとViewを繋ぎ合わせる main\_presenter.py と、アプリケーションを起動する main.py を作成。

# **元コード (main.py)**

\[ここに元のmain.pyのコード全体を貼り付けます\]