"""
app.py — точка входа приложения «Система контроля сроков годности».

Архитектура — модульная, согласно рис. 2.15 дипломной работы:
  • Presentation Layer (ui/*)
  • Business Logic Layer (modules/*)
  • Data Access Layer (modules/database.py)

Сборка зависимостей и компоновка вкладок делается здесь. Логики здесь нет —
только инициализация и связывание.

CLI-режим (для автоматических скриншотов в дипломе):
  python app.py --tab=senior
  python app.py --tab=operator --product=Шоколад
  python app.py --tab=senior --open=planogram --screenshots=D:\shots
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

import customtkinter as ctk

# делаем пакеты доступными при запуске файла напрямую
sys.path.insert(0, str(Path(__file__).parent))

from modules import (
    AuditAndLog,
    AutoOrder,
    Database,
    Planogram,
    Reports,
    Returns,
    ShelfLifeControl,
    WriteOff,
)
from ui.dialogs import (
    ActionLogDialog,
    AllProductsDialog,
    LossesDialog,
    MyOrdersDialog,
    PlanogramDialog,
    ReturnsDialog,
    SalesHistoryDialog,
    SmartOrderDialog,
    WriteOffExpiredDialog,
    WriteOffsHistoryDialog,
)
from ui.operator_tab import OperatorTab
from ui.senior_tab import SeniorTab

DB_PATH = "database.db"
APP_TITLE = "Система контроля сроков годности"
APP_SUBTITLE = "АЗС №16 — Поколюбичи"
APP_SIZE = "1080x720"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--tab", choices=("operator", "senior"), default="operator")
    p.add_argument("--open", default=None,
                   help="Какой диалог открыть при старте: all_products | "
                        "smart_order | planogram | returns | sales_history | "
                        "losses | my_orders | writeoff | writeoff_history | action_log")
    p.add_argument("--product", default=None,
                   help="Сразу найти товар по имени/штрих-коду (только на вкладке оператора)")
    p.add_argument("--product-file", default=None,
                   help="Файл с именем товара для предзаполнения (обход проблем с UTF-8 в argv)")
    p.add_argument("--screenshots", default=None,
                   help="Папка для сохранения скриншотов диалогов (через PowerShell)")
    p.add_argument("--delay", type=int, default=600,
                   help="Задержка в мс перед открытием диалога/скриншота")
    p.add_argument("--size", default=APP_SIZE,
                   help="Размер окна WIDTHxHEIGHT (например 1280x820)")
    p.add_argument("--fixed", action="store_true",
                   help="Запретить ресайз окна (по умолчанию ресайз разрешён)")
    args = p.parse_known_args()[0]
    if args.product_file and Path(args.product_file).is_file():
        args.product = Path(args.product_file).read_text(encoding="utf-8").strip()
    return args


def _save_screenshot(out_dir: str, name: str, bbox=None) -> None:
    """
    Save a screenshot of a specific screen region using PIL.ImageGrab.

    bbox: (x0, y0, x1, y1) in physical pixels; if None — grab the full primary screen.
    Runs in a daemon thread so the UI loop isn't blocked.
    """
    from PIL import ImageGrab  # imported lazily to avoid hard dep on GUI-only hosts
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"

    def _runner() -> None:
        try:
            if bbox is None:
                img = ImageGrab.grab()
            else:
                # Cap bbox to actual screen bounds; otherwise grab fails.
                full = ImageGrab.grab()
                sw, sh = full.size
                x0, y0, x1, y1 = bbox
                x0 = max(0, min(int(x0), sw))
                y0 = max(0, min(int(y0), sh))
                x1 = max(0, min(int(x1), sw))
                y1 = max(0, min(int(y1), sh))
                if x1 <= x0 or y1 <= y0:
                    print(f"Empty bbox for {name}: {bbox} (screen {sw}x{sh})")
                    return
                img = ImageGrab.grab(bbox=(x0, y0, x1, y1))
            img.save(str(path), "PNG")
            print(f"  saved: {path}  size={img.size}")
        except Exception as e:
            print(f"Screenshot thread exception: {e}")

    threading.Thread(target=_runner, daemon=True).start()


def _window_bbox(window) -> tuple[int, int, int, int]:
    """Return (x0, y0, x1, y1) screen bbox of a Tk/CTk window in physical pixels."""
    window.update_idletasks()
    x = window.winfo_rootx()
    y = window.winfo_rooty()
    w = window.winfo_width()
    h = window.winfo_height()
    return (x, y, x + w, y + h)


class ShelfLifeApp(ctk.CTk):
    """Главное окно приложения."""

    # Default size used in screenshot mode — wider so dialogs fit
    CLI_SCREENSHOT_SIZE = "1600x1000"

    def __init__(self, args: argparse.Namespace | None = None) -> None:
        super().__init__()
        self.args = args or _parse_args()

        ctk.set_appearance_mode("Light")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)
        # In screenshot mode, force window to (0,0) with a wider size
        # so dialogs fit and the bbox is predictable.
        if self.args.screenshots:
            self.geometry(f"{self.CLI_SCREENSHOT_SIZE}+0+0")
        else:
            self.geometry(self.args.size)
        self.resizable(not self.args.fixed, not self.args.fixed)
        # в CLI-режиме держим окно поверх всего (для корректных скриншотов)
        if self.args.screenshots:
            try:
                self.attributes("-topmost", True)
                self.lift()
                self.focus_force()
            except Exception:
                pass

        # ---- сборка зависимостей ----
        self.db = Database(DB_PATH)
        self.db.connect()
        self.audit = AuditAndLog(self.db)
        self.planogram = Planogram(self.db, self.audit)
        self.shelf_life = ShelfLifeControl(self.db, self.audit)
        self.auto_order = AutoOrder(self.db, self.audit, self.planogram)
        self.returns = Returns(self.db, self.audit)
        self.write_off = WriteOff(self.db, self.audit)
        self.reports = Reports(self.db)

        # ---- header ----
        self._build_header()

        # ---- вкладки ----
        self.tabview = ctk.CTkTabview(
            self,
            width=1240, height=720,
            segmented_button_fg_color="#1B5E20",
            segmented_button_selected_color="#C62828",
            segmented_button_selected_hover_color="#B71C1C",
        )
        self.tabview.pack(padx=20, pady=15, fill="both", expand=True)

        tab_op = self.tabview.add("Оператор (Касса)")
        tab_sr = self.tabview.add("Старший оператор")

        self.operator_tab = OperatorTab(
            tab_op, self.shelf_life, self.reports,
            on_sale_callback=self._on_sale,
        )
        self.senior_tab = SeniorTab(
            tab_sr, self.db, self.shelf_life, self.auto_order,
            self.write_off, self.reports, self.audit,
            self.planogram, self.returns,
        )

        # Проверим, что БД не пустая
        if not self.db.list_products():
            self.after(500, self._show_init_hint)

        # ---- CLI: переключение вкладки, открытие диалога, префилл товара ----
        self._schedule_cli_actions()

    # ---------------- UI ----------------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="#1B5E20", height=80)
        header.pack(fill="x", pady=0)
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="СИСТЕМА КОНТРОЛЯ СРОКОВ ГОДНОСТИ",
            font=ctk.CTkFont(size=24, weight="bold"), text_color="white",
        ).pack(side="left", padx=30, pady=20)

        ctk.CTkLabel(
            header, text=APP_SUBTITLE,
            font=ctk.CTkFont(size=14), text_color="#FFEB3B",
        ).pack(side="right", padx=30, pady=20)

    # ---------------- CLI actions ----------------
    def _schedule_cli_actions(self) -> None:
        delay = self.args.delay
        # 1) переключаем вкладку
        if self.args.tab == "senior":
            self.after(delay, lambda: self.tabview.set("Старший оператор"))
        else:
            self.after(delay, lambda: self.tabview.set("Оператор (Касса)"))
        # 2) ищем товар
        if self.args.product:
            self.after(
                delay + 200,
                lambda: self._prefill_product(self.args.product),
            )
        # 3) открываем диалог
        if self.args.open:
            self.after(delay + 400, lambda: self._open_dialog(self.args.open))
        # 4.5) auto-close the app once screenshots are done
        if self.args.screenshots:
            # dialog path: delay+400 (open) + 1800 (capture) + 200 (settle) + 800 (thread buffer)
            # main path:  delay+1500 (capture) + 200 (settle) + 800 (thread buffer)
            settle = 200
            close_at = (delay + 400 + 1800 + settle + 800) if self.args.open else (delay + 1500 + settle + 800)
            self.after(close_at, self.on_close)
        # 4) скрин главного окна (если --open не задан, делаем снимок самого приложения)
        if self.args.screenshots and not self.args.open:
            name = f"{self.args.tab}_main"
            if self.args.product:
                import hashlib
                tag = hashlib.md5(
                    self.args.product.encode("utf-8")
                ).hexdigest()[:8]
                name = f"{self.args.tab}__prefill__{tag}"
            # Force focus + small settle delay right before the capture, so the
            # window is guaranteed on top even if the user clicked away.
            self.after(delay + 1500, self._capture_main_with_focus, name)

    def _prefill_product(self, query: str) -> None:
        try:
            self.operator_tab.search_var.set(query)
            self.operator_tab._on_search()
        except Exception:
            pass

    def _open_dialog(self, kind: str) -> None:
        dlg = None
        try:
            if kind == "all_products":
                dlg = AllProductsDialog(self, self.reports)
            elif kind == "smart_order":
                dlg = SmartOrderDialog(self, self.auto_order, self.reports)
            elif kind == "planogram":
                dlg = PlanogramDialog(self, self.db)
            elif kind == "returns":
                dlg = ReturnsDialog(self, self.db, self.returns)
            elif kind == "sales_history":
                dlg = SalesHistoryDialog(self, self.reports)
            elif kind == "losses":
                dlg = LossesDialog(self, self.reports, days=7)
            elif kind == "my_orders":
                dlg = MyOrdersDialog(self, self.reports, self.db)
            elif kind == "writeoff":
                dlg = WriteOffExpiredDialog(self, self.write_off)
            elif kind == "writeoff_history":
                dlg = WriteOffsHistoryDialog(self, self.reports)
            elif kind == "action_log":
                dlg = ActionLogDialog(self, self.audit)
        except Exception as e:
            import traceback
            print(f"Dialog open error [{kind}]: {e}")
            traceback.print_exc()
            return
        # делаем окно поверх главного
        if dlg is not None:
            try:
                dlg.lift()
                dlg.attributes("-topmost", True)
                dlg.focus_force()
            except Exception:
                pass
        if dlg is not None and self.args.screenshots:
            name = f"{self.args.tab}__{kind}"
            if self.args.product:
                import hashlib
                tag = hashlib.md5(
                    self.args.product.encode("utf-8")
                ).hexdigest()[:8]
                name = f"{self.args.tab}__{kind}__{tag}"
            # даём окну появиться и зафиксировать свою позицию
            self.after(
                1800,
                self._capture_dialog_after,
            )

        # Stash dialog for the screenshot callback
        self._pending_dialog = dlg
        self._pending_dialog_name = name if (dlg is not None and self.args.screenshots) else None

    def _capture_dialog_after(self) -> None:
        """Grab the pending dialog's actual screen bbox and save a screenshot."""
        dlg = getattr(self, "_pending_dialog", None)
        name = getattr(self, "_pending_dialog_name", None)
        if dlg is None or name is None:
            return
        # Re-apply focus on BOTH the main window and the dialog, then capture
        # the dialog's bbox. The small settle delay lets the OS process the
        # z-order change before the screen capture fires.
        try:
            self.attributes("-topmost", True)
            self.lift()
            dlg.attributes("-topmost", True)
            dlg.lift()
            dlg.focus_force()
            self.update()
        except Exception:
            pass
        self.after(200, self._do_capture_dialog, dlg, name)

    def _do_capture_dialog(self, dlg, name: str) -> None:
        try:
            dlg.update_idletasks()
            bbox = _window_bbox(dlg)
            _save_screenshot(self.args.screenshots, name, bbox=bbox)
        except Exception as e:
            print(f"Dialog capture error: {e}")

    def _capture_main_with_focus(self, name: str) -> None:
        """Re-apply topmost + focus on the main window, then capture its bbox."""
        try:
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
            self.update()
        except Exception:
            pass
        self.after(200, self._do_capture_main, name)

    def _do_capture_main(self, name: str) -> None:
        try:
            self.update_idletasks()
            bbox = _window_bbox(self)
            _save_screenshot(self.args.screenshots, name, bbox=bbox)
        except Exception as e:
            print(f"Main capture error: {e}")

    # ---------------- handlers ----------------
    def _on_sale(self) -> None:
        """После продажи обновляем дашборд старшего оператора."""
        if hasattr(self, "senior_tab"):
            self.senior_tab.refresh_dashboard()

    def _show_init_hint(self) -> None:
        from CTkMessagebox import CTkMessagebox
        CTkMessagebox(
            title="База данных пуста",
            message=(
                "В базе нет товаров. Запустите:\n\n"
                "python init_db.py\n\n"
                "для создания демо-данных."
            ),
            icon="info",
        )

    def on_close(self) -> None:
        try:
            self.db.close()
        finally:
            self.destroy()


if __name__ == "__main__":
    args = _parse_args()
    app = ShelfLifeApp(args)
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
