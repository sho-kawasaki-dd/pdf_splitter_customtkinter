"""PDF 分割アプリケーション - エントリーポイント。

MVP アーキテクチャに基づき、Model / View / Presenter を組み立てて起動する。
"""

from view.main_window import MainWindow
from presenter.main_presenter import MainPresenter


def main() -> None:
    view = MainWindow()
    _presenter = MainPresenter(view)  # noqa: F841  -- View が参照を保持する
    view.mainloop()


if __name__ == "__main__":
    main()
