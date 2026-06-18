"""
ui/dialogs.py
-------------
Диалоговые окна отчётов, списания, заказов, планограммы, возвратов.

Все диалоги получают зависимости (db, reports, slc, …) через конструктор
и не содержат бизнес-логики — только отображение. Для отчётов используется
ttk.Treeview — нормальная таблица с заголовками, а не моноширинный текст.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import customtkinter as ctk
from CTkMessagebox import CTkMessagebox

from modules import (
    AutoOrder,
    Planogram,
    Reports,
    Returns,
    ShelfLifeControl,
    WriteOff,
    save_excel_report,
    save_text_report,
)
from modules.database import Database
from ui.notify import play_alert, play_warning


# ---------- общие стили ----------
COLOR_BG       = "#F5F5F5"
COLOR_ACCENT   = "#1B5E20"     # тёмно-зелёный
COLOR_DANGER   = "#C62828"     # красный
COLOR_WARN     = "#E65100"     # оранжевый
COLOR_OK       = "#2E7D32"     # зелёный
COLOR_INFO_BG  = "#E3F2FD"     # светло-синий
COLOR_WARN_BG  = "#FFF3E0"     # светло-оранжевый
COLOR_OK_BG    = "#E8F5E9"     # светло-зелёный


def _title(window: ctk.CTk, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        window,
        text=text,
        font=ctk.CTkFont(size=20, weight="bold"),
        text_color=COLOR_ACCENT,
    )


# ---------- таблица на ttk.Treeview ----------
def _make_table(parent: ctk.CTk, headers: list[str], widths: list[int],
                height: int = 380) -> ttk.Treeview:
    """Создаёт Treeview с заголовками внутри CTkFrame."""
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Treeview",
        background="white",
        fieldbackground="white",
        foreground="#222",
        rowheight=28,
        font=("Segoe UI", 11),
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        background=COLOR_ACCENT,
        foreground="white",
        font=("Segoe UI", 11, "bold"),
        relief="flat",
    )
    style.map(
        "Treeview.Heading",
        background=[("active", "#0D3B0D")],
    )
    style.map(
        "Treeview",
        background=[("selected", "#A5D6A7")],
        foreground=[("selected", "#000")],
    )

    frame = ctk.CTkFrame(parent, fg_color="white",
                         border_width=1, border_color=COLOR_ACCENT,
                         corner_radius=6)
    frame.pack(padx=15, pady=10, fill="both", expand=True)

    tree = ttk.Treeview(frame, columns=headers, show="headings", height=height)
    for h, w in zip(headers, widths):
        anchor = "center" if h in ("Остаток", "Кол-во", "Цена", "Срок", "Позиция",
                                    "Min", "Max", "Дней", "Статус", "Qty",
                                    "TotalItems", "Position") else "w"
        tree.heading(h, text=h, anchor=anchor)
        tree.column(h, width=w, anchor=anchor)
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    tree.pack(side="left", fill="both", expand=True, padx=2, pady=2)
    vsb.pack(side="right", fill="y")
    return tree


def _fill_table(tree: ttk.Treeview, rows: list[list]) -> None:
    for r in tree.get_children():
        tree.delete(r)
    for row in rows:
        tree.insert("", "end", values=row)


def _row_to_list(row: dict, keys: list[str], formatters: dict | None = None) -> list:
    """Превращает dict из БД в список значений в порядке `keys` с опциональными
    форматтерами (callable)."""
    fmt = formatters or {}
    out = []
    for k in keys:
        v = row.get(k)
        if k in fmt:
            v = fmt[k](v) if callable(fmt[k]) else fmt[k]
        out.append(v)
    return out


# ---------- экспорт ----------
def _add_export_buttons(window: ctk.CTk, table, default_name: str) -> ctk.CTkFrame:
    frame = ctk.CTkFrame(window, fg_color="transparent")
    frame.pack(pady=10)
    ctk.CTkButton(
        frame, text="📄 Сохранить в TXT", width=160, height=38,
        fg_color=COLOR_ACCENT, hover_color="#0D3B0D",
        command=lambda: _save_text(table, default_name),
    ).pack(side="left", padx=10)
    ctk.CTkButton(
        frame, text="📊 Сохранить в Excel", width=160, height=38,
        fg_color=COLOR_DANGER, hover_color="#B71C1C",
        command=lambda: _save_excel(table, default_name),
    ).pack(side="left", padx=10)
    return frame


def _save_text(table, name: str) -> None:
    path = save_text_report(table, name)
    if path:
        CTkMessagebox(title="Успех", message=f"Отчёт сохранён:\n{path}", icon="check")


def _save_excel(table, name: str) -> None:
    path = save_excel_report(table, name)
    if path:
        CTkMessagebox(title="Успех", message=f"Отчёт сохранён:\n{path}", icon="check")


# ==================== ДИАЛОГИ ====================
class AllProductsDialog(ctk.CTkToplevel):
    def __init__(self, master, reports: Reports):
        super().__init__(master)
        self.title("Все товары в базе")
        self.geometry("820x580")
        _title(self, "Список всех товаров в базе данных (FEFO)").pack(pady=10)
        rows = reports.db.get_all_active_batches_with_stock()
        data = [[r["ProductName"], r["ExpirationDate"],
                 f"{int(r.get('StockQty') or 0)} шт"]
                for r in rows]
        headers = ["Название товара", "Срок годности", "Остаток"]
        widths = [420, 140, 100]
        self.tree = _make_table(self, headers, widths, height=20)
        _fill_table(self.tree, data)
        # экспорт: используем ReportTable
        table = reports.all_products()
        _add_export_buttons(self, table, "all_products")


class SalesHistoryDialog(ctk.CTkToplevel):
    def __init__(self, master, reports: Reports, limit: int = 50):
        super().__init__(master)
        self.title("История продаж")
        self.geometry("820x580")
        _title(self, f"История продаж (последние {limit})").pack(pady=10)
        rows = reports.db.get_recent_sales(limit)
        data = [[str(r["SaleDate"])[:19], r["ProductName"],
                 f"{int(r['Quantity'])} шт"] for r in rows]
        headers = ["Дата и время", "Товар", "Кол-во"]
        widths = [220, 420, 100]
        self.tree = _make_table(self, headers, widths, height=20)
        _fill_table(self.tree, data)
        table = reports.sales_history(limit)
        _add_export_buttons(self, table, "sales_history")


class LossesDialog(ctk.CTkToplevel):
    def __init__(self, master, reports: Reports, days: int = 7):
        super().__init__(master)
        self.title("Потери от просрочки")
        self.geometry("900x620")
        _title(self, f"Потери от просрочки за последние {days} дней").pack(pady=15)
        rows = reports.db.get_losses_in_window(days)
        total_loss = 0.0
        data = []
        for r in rows:
            qty = int(r.get("StockQty") or 0)
            price = float(r.get("PurchasePrice") or 0)
            loss = qty * price
            total_loss += loss
            data.append([r["ProductName"], r["ExpirationDate"],
                         f"{qty} шт", f"{price:.2f}", f"{loss:.2f} BYN"])
        headers = ["Товар", "Срок истёк", "Остаток", "Цена", "Сумма потерь"]
        widths = [340, 120, 100, 100, 140]
        self.tree = _make_table(self, headers, widths, height=18)
        _fill_table(self.tree, data)
        ctk.CTkLabel(
            self, text=f"ИТОГО ПОТЕРЬ ЗА НЕДЕЛЮ: {total_loss:.2f} BYN",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=COLOR_DANGER,
        ).pack(pady=(0, 6))
        table = reports.losses(days)
        _add_export_buttons(self, table, "losses_report")


class MyOrdersDialog(ctk.CTkToplevel):
    def __init__(self, master, reports: Reports, db: Database):
        super().__init__(master)
        self.title("Мои заказы")
        self.geometry("820x540")
        self.db = db
        self.reports = reports
        _title(self, "Сохранённые интеллектуальные авто-заказы").pack(pady=10)
        rows = db.list_orders()
        data = [[r["OrderID"], str(r["CreationDate"])[:19],
                 r["TotalItems"], r["Status"]] for r in rows]
        headers = ["№ заказа", "Дата создания", "Позиций", "Статус"]
        widths = [100, 220, 100, 140]
        self.tree = _make_table(self, headers, widths, height=14)
        _fill_table(self.tree, data)
        ctk.CTkButton(
            self, text="Показать детали выбранного заказа",
            command=self._show_details, height=40,
            fg_color="#1565C0", hover_color="#0D47A1",
        ).pack(pady=10)

    def _show_details(self) -> None:
        sel = self.tree.selection()
        if not sel:
            CTkMessagebox(title="Ошибка",
                          message="Выберите заказ в таблице!",
                          icon="cancel")
            return
        try:
            order_id = int(self.tree.item(sel[0])["values"][0])
        except (ValueError, IndexError):
            CTkMessagebox(title="Ошибка",
                          message="Не удалось прочитать номер заказа.",
                          icon="cancel")
            return
        details = self.reports.order_details(order_id)
        w = ctk.CTkToplevel(self)
        w.title(f"Детали заказа №{order_id}")
        w.geometry("780x440")
        _title(w, f"Состав заказа №{order_id}").pack(pady=10)
        rows = self.db.get_order_items(order_id)
        data = [[r["ProductName"], r["RecommendedQuantity"], r.get("Reason", "")]
                for r in rows]
        headers = ["Товар", "Кол-во", "Причина"]
        widths = [340, 100, 280]
        tree2 = _make_table(w, headers, widths, height=14)
        _fill_table(tree2, data)


class WriteOffExpiredDialog(ctk.CTkToplevel):
    def __init__(self, master, write_off: WriteOff, on_done_callback=None):
        super().__init__(master)
        self.title("Списать просроченные товары")
        self.geometry("820x560")
        self.write_off = write_off
        self.on_done_callback = on_done_callback
        _title(self, "Просроченные товары (срок истёк)").pack(pady=10)
        self.expired = write_off.list_expired()

        if self.expired:
            data = [[r["ProductName"], r["ExpirationDate"],
                     f"{int(r.get('StockQty') or 0)} шт",
                     f"{float(r.get('PurchasePrice') or 0):.2f}"]
                    for r in self.expired]
            headers = ["Товар", "Срок истёк", "Остаток", "Цена"]
            widths = [340, 120, 100, 100]
            self.tree = _make_table(self, headers, widths, height=14)
            _fill_table(self.tree, data)
            # звуковой сигнал
            try:
                play_warning()
            except Exception:
                pass
            ctk.CTkButton(
                self, text="🗑️ Списать все просроченные товары",
                command=self._confirm_write_off, height=44,
                fg_color=COLOR_DANGER, hover_color="#B71C1C",
            ).pack(pady=12)
        else:
            ctk.CTkLabel(
                self, text="Просроченных товаров нет.",
                font=ctk.CTkFont(size=14), text_color="#555",
            ).pack(pady=30)

    def _confirm_write_off(self) -> None:
        if not self.expired:
            return
        total_qty = sum(int(r.get("StockQty") or 0) for r in self.expired)
        total_loss = sum(
            int(r.get("StockQty") or 0) * float(r.get("PurchasePrice") or 0)
            for r in self.expired
        )
        result = CTkMessagebox(
            title="Подтверждение",
            message=(
                "Списать все просроченные товары?\n\n"
                f"Количество: {total_qty} шт\n"
                f"Сумма потерь: {total_loss:.2f} BYN"
            ),
            icon="warning", option_1="Да, списать", option_2="Отмена",
        )
        if result.get() == "Да, списать":
            res = self.write_off.write_off_all_expired()
            if res:
                CTkMessagebox(
                    title="Готово",
                    message=(
                        f"Списано {res.total_items} шт на сумму "
                        f"{res.total_loss:.2f} BYN\n"
                        f"Акт №: {res.act_number}"
                    ),
                    icon="check",
                )
                if self.on_done_callback:
                    self.on_done_callback()
                self.destroy()


class WriteOffsHistoryDialog(ctk.CTkToplevel):
    def __init__(self, master, reports: Reports):
        super().__init__(master)
        self.title("История списаний")
        self.geometry("900x580")
        _title(self, "История списаний просроченных товаров").pack(pady=10)
        rows = reports.db.get_writeoffs(200)
        total_qty = 0
        data = []
        for r in rows:
            qty = int(r.get("Quantity") or 0)
            total_qty += qty
            data.append([r.get("WriteOffDate"), r.get("ProductName"),
                         f"{qty} шт", r.get("Reason", ""),
                         r.get("ActNumber", "")])
        headers = ["Дата", "Товар", "Кол-во", "Причина", "Акт"]
        widths = [120, 280, 90, 140, 200]
        self.tree = _make_table(self, headers, widths, height=16)
        _fill_table(self.tree, data)
        ctk.CTkLabel(
            self, text=f"ИТОГО СПИСАНО: {total_qty} шт",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_DANGER,
        ).pack(pady=(0, 4))
        ctk.CTkButton(
            self, text="📄 Сохранить в TXT",
            command=lambda: _save_text(reports.writeoffs(200), "writeoffs_history"),
            fg_color=COLOR_ACCENT, hover_color="#0D3B0D",
        ).pack(pady=8)


class SmartOrderDialog(ctk.CTkToplevel):
    """Окно интеллектуального авто-заказа."""
    def __init__(self, master, auto_order: AutoOrder, reports: Reports,
                 on_save_callback=None):
        super().__init__(master)
        self.title("Интеллектуальный авто-заказ")
        self.geometry("1000x640")
        self.auto_order = auto_order
        self.reports = reports
        self.on_save_callback = on_save_callback
        self.recs = auto_order.generate_for_all()
        _title(self, "Рекомендуемый интеллектуальный авто-заказ").pack(pady=12)
        data = [[r.product_name, r.current_stock, r.avg_daily_sales,
                 r.recommended_qty, r.reason] for r in self.recs]
        headers = ["Товар", "Остаток", "Ср. продажи/день", "Рекомендация", "Причина"]
        widths = [320, 80, 130, 130, 280]
        self.tree = _make_table(self, headers, widths, height=18)
        _fill_table(self.tree, data)
        ctk.CTkButton(
            self, text="💾 Сохранить заказ в базу",
            command=self._save, height=42,
            fg_color=COLOR_DANGER, hover_color="#B71C1C",
        ).pack(pady=10)

    def _save(self) -> None:
        if not any(r.recommended_qty > 0 for r in self.recs):
            CTkMessagebox(title="Ошибка",
                          message="Нет позиций для сохранения!", icon="cancel")
            return
        order_id = self.auto_order.save_draft(self.recs)
        if order_id:
            CTkMessagebox(
                title="Успех",
                message=f"Авто-заказ №{order_id} успешно сохранён!",
                icon="check",
            )
            if self.on_save_callback:
                self.on_save_callback()
            self.destroy()
        else:
            CTkMessagebox(title="Ошибка", message="Не удалось сохранить заказ.",
                          icon="cancel")


class ActionLogDialog(ctk.CTkToplevel):
    """Просмотр журнала аудита (ActionLog) — для старшего оператора."""
    def __init__(self, master, audit):
        super().__init__(master)
        self.title("Журнал действий (ActionLog)")
        self.geometry("1100x620")
        _title(self, "Журнал аудита (Audit Trail)").pack(pady=10)
        rows = audit.get_recent(300)
        data = [[str(r["DateTime"])[:19], str(r.get("User", ""))[:14],
                 r["Action"], r["TableName"],
                 str(r.get("NewValues", ""))[:80]] for r in rows]
        headers = ["Дата/время", "Пользователь", "Действие", "Объект", "Детали"]
        widths = [180, 140, 160, 140, 380]
        self.tree = _make_table(self, headers, widths, height=18)
        _fill_table(self.tree, data)
        ctk.CTkButton(
            self, text="Закрыть", command=self.destroy,
            fg_color=COLOR_ACCENT, hover_color="#0D3B0D",
            width=120,
        ).pack(pady=8)


# ==================== НОВЫЕ ДИАЛОГИ ====================
class PlanogramDialog(ctk.CTkToplevel):
    """Управление планограммой — справочник полок и товаров."""
    def __init__(self, master, db: Database):
        super().__init__(master)
        self.title("Планограмма торгового зала")
        self.geometry("920x600")
        self.db = db
        _title(self, "Планограмма (размещение товаров на полках)").pack(pady=10)
        rows = db.list_planogram()
        data = [[r["ShelfCode"], r["Position"], r["ProductName"],
                 r.get("Category", ""), r["MinStock"], r["MaxStock"]]
                for r in rows]
        headers = ["Полка", "Поз.", "Товар", "Категория", "Min", "Max"]
        widths = [120, 60, 320, 160, 80, 80]
        self.tree = _make_table(self, headers, widths, height=18)
        _fill_table(self.tree, data)
        ctk.CTkLabel(
            self,
            text=("Планограмма используется модулем AutoOrder для расчёта "
                  "целевого остатка (TargetStock) и контроля размещения товаров."),
            font=ctk.CTkFont(size=12), text_color="#555",
        ).pack(pady=4)
        ctk.CTkButton(
            self, text="Закрыть", command=self.destroy,
            fg_color=COLOR_ACCENT, hover_color="#0D3B0D",
            width=120,
        ).pack(pady=6)


class ReturnsDialog(ctk.CTkToplevel):
    """Оформление возврата партии поставщику."""
    def __init__(self, master, db: Database, returns: Returns | None = None):
        super().__init__(master)
        self.title("Возврат поставщику")
        self.geometry("1000x620")
        self.db = db
        # если не передали — создаём из db
        from modules.audit_log import AuditAndLog
        from modules.returns import Returns as _Returns
        self.returns = returns or _Returns(db, AuditAndLog(db, default_user="SeniorOperator"))
        _title(self, "Кандидаты на возврат (срок истекает ≤ 14 дней)").pack(pady=10)
        self.candidates = self.returns.list_critical_batches(days=14)
        if self.candidates:
            data = [[r["BatchID"], r["ProductName"],
                     r["ExpirationDate"],
                     f"{int(r.get('StockQty') or 0)} шт",
                     r.get("Supplier") or "—"]
                    for r in self.candidates]
            headers = ["Batch", "Товар", "Срок", "Остаток", "Поставщик"]
            widths = [70, 320, 110, 90, 200]
            self.tree = _make_table(self, headers, widths, height=14)
            _fill_table(self.tree, data)
            try:
                play_warning()
            except Exception:
                pass

            # Поля ввода для оформления возврата
            form = ctk.CTkFrame(self, fg_color="transparent")
            form.pack(pady=8)
            ctk.CTkLabel(form, text="Batch ID:").grid(row=0, column=0, padx=5)
            self.entry_batch = ctk.CTkEntry(form, width=80)
            self.entry_batch.grid(row=0, column=1, padx=5)
            ctk.CTkLabel(form, text="Кол-во:").grid(row=0, column=2, padx=5)
            self.entry_qty = ctk.CTkEntry(form, width=80)
            self.entry_qty.grid(row=0, column=3, padx=5)
            ctk.CTkLabel(form, text="Причина:").grid(row=0, column=4, padx=5)
            self.entry_reason = ctk.CTkEntry(form, width=240,
                                              placeholder_text="Напр. Истекает срок")
            self.entry_reason.grid(row=0, column=5, padx=5)

            ctk.CTkButton(
                form, text="↩ Оформить возврат",
                command=self._do_return,
                fg_color=COLOR_WARN, hover_color="#BF360C",
                height=36, width=200,
            ).grid(row=0, column=6, padx=10)

            # история возвратов
            ctk.CTkLabel(self, text="История возвратов (последние 50)",
                         font=ctk.CTkFont(size=14, weight="bold"),
                         text_color=COLOR_ACCENT).pack(pady=(10, 0))
            self._fill_history()
        else:
            ctk.CTkLabel(
                self, text="Партий с истекающим сроком нет — возвраты не требуются.",
                font=ctk.CTkFont(size=14), text_color="#555",
            ).pack(pady=30)

    def _fill_history(self) -> None:
        rows = self.db.list_returns(50)
        data = [[r["ReturnID"], r["ProductName"], r["ReturnDate"],
                 f"{r['Quantity']} шт", r.get("Reason", ""),
                 r.get("ActNumber", "")]
                for r in rows]
        headers = ["№", "Товар", "Дата", "Кол-во", "Причина", "Акт"]
        widths = [60, 280, 110, 80, 200, 220]
        self.tree_h = _make_table(self, headers, widths, height=10)
        _fill_table(self.tree_h, data)

    def _do_return(self) -> None:
        try:
            batch_id = int(self.entry_batch.get().strip())
            qty = int(self.entry_qty.get().strip())
        except ValueError:
            CTkMessagebox(title="Ошибка",
                          message="Batch ID и Кол-во должны быть числами.",
                          icon="cancel")
            return
        reason = self.entry_reason.get().strip() or "Истекает срок"
        # определить поставщика из партии
        batch = self.db.get_batch(batch_id)
        if not batch:
            CTkMessagebox(title="Ошибка",
                          message=f"Партия #{batch_id} не найдена.",
                          icon="cancel")
            return
        supplier = batch.get("Supplier")
        stock = self.db.get_stock(batch_id)
        if stock < qty:
            CTkMessagebox(title="Ошибка",
                          message=f"На партии #{batch_id} только {stock} шт.",
                          icon="cancel")
            return
        result = self.returns.perform_return(batch_id, qty, reason, supplier)
        if result:
            CTkMessagebox(
                title="Готово",
                message=(f"Возврат оформлен!\n"
                         f"Акт: {result.act_number}\n"
                         f"Кол-во: {result.quantity} шт"),
                icon="check",
            )
            self.entry_batch.delete(0, "end")
            self.entry_qty.delete(0, "end")
            self.entry_reason.delete(0, "end")
            # обновляем списки
            self.candidates = self.returns.list_critical_batches(days=14)
            if self.candidates:
                data = [[r["BatchID"], r["ProductName"],
                         r["ExpirationDate"],
                         f"{int(r.get('StockQty') or 0)} шт",
                         r.get("Supplier") or "—"]
                        for r in self.candidates]
                _fill_table(self.tree, data)
            self._fill_history()
        else:
            CTkMessagebox(title="Ошибка",
                          message="Не удалось оформить возврат.",
                          icon="cancel")
