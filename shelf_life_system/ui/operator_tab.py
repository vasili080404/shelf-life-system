"""
ui/operator_tab.py
------------------
Вкладка «Оператор (Касса)».

Реализует экран кассира (рис. 3.2 дипломной работы) с поддержкой:
  • поиска по имени или штрих-коду с автодополнением;
  • FEFO-индикации (красный/оранжевый/зелёный — Expired / Critical / Normal);
  • автоматического расчёта скидки;
  • запрета продажи просроченного товара;
  • горячей клавиши Enter для быстрого добавления в чек.
"""
from __future__ import annotations

import customtkinter as ctk
from CTkMessagebox import CTkMessagebox
from tkinter import StringVar

from modules import ShelfLifeControl
from modules.shelf_life_control import BatchInfo, BatchStatus
from ui.dialogs import (
    COLOR_ACCENT,
    COLOR_DANGER,
    COLOR_OK,
    COLOR_WARN,
    AllProductsDialog,
    SalesHistoryDialog,
)


class OperatorTab:
    """Вкладка кассира. Получает готовые сервисы через конструктор."""

    def __init__(self, parent: ctk.CTk, slc: ShelfLifeControl,
                 reports, on_sale_callback=None) -> None:
        self.parent = parent
        self.slc = slc
        self.reports = reports
        self.on_sale_callback = on_sale_callback
        self._current_batch: BatchInfo | None = None
        self._suggestion_box: ctk.CTkFrame | None = None
        self._suggestion_buttons: list[ctk.CTkButton] = []
        self._build()
        self._products_cache: list[dict] = self.slc.db.list_products()
        self._wire_autocomplete()

    # ---------------- UI ----------------
    def _build(self) -> None:
        frame = ctk.CTkFrame(self.parent, fg_color="#F5F5F5")
        frame.pack(padx=15, pady=15, fill="both", expand=True)

        ctk.CTkLabel(
            frame, text="Режим Оператора (Касса)",
            font=ctk.CTkFont(size=22, weight="bold"), text_color=COLOR_ACCENT,
        ).pack(pady=10)

        ctk.CTkLabel(
            frame,
            text="Введите название товара или штрих-код (Barcode) и нажмите Enter",
            font=ctk.CTkFont(size=12), text_color="#555",
        ).pack()

        # Поиск с автодополнением — оборачиваем в Frame, чтобы позиционировать список
        self.search_container = ctk.CTkFrame(frame, fg_color="transparent",
                                             width=420, height=40)
        self.search_container.pack(pady=(5, 5))
        self.search_container.pack_propagate(False)

        self.search_var = StringVar()
        self.search_entry = ctk.CTkEntry(
            self.search_container, textvariable=self.search_var,
            placeholder_text="Название или штрих-код",
            width=420, height=40, font=ctk.CTkFont(size=14),
        )
        self.search_entry.pack()
        self.search_entry.bind("<Return>", lambda _e: self._on_search())
        self.search_entry.bind("<Down>", lambda _e: self._focus_first_suggestion())
        self.search_entry.bind("<Escape>", lambda _e: self._hide_suggestions())

        # Кнопки
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(pady=5)

        ctk.CTkButton(
            btn_frame, text="🔍 Найти товар", command=self._on_search,
            width=160, height=40, fg_color=COLOR_ACCENT, hover_color="#0D3B0D",
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame, text="🛒 Добавить в чек", command=self._on_add_to_cart,
            width=170, height=40, fg_color=COLOR_DANGER, hover_color="#B71C1C",
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame, text="📋 Все товары", command=self._open_all_products,
            width=160, height=40, fg_color=COLOR_ACCENT, hover_color="#0D3B0D",
        ).pack(side="left", padx=5)
        ctk.CTkButton(
            btn_frame, text="📜 История", command=self._open_sales_history,
            width=140, height=40, fg_color=COLOR_WARN, hover_color="#BF360C",
        ).pack(side="left", padx=5)

        # Информационная карточка — компактный формат, как на скрине диплома
        self.info_frame = ctk.CTkFrame(
            frame, fg_color="white",
            border_width=2, border_color=COLOR_ACCENT, corner_radius=10,
        )
        self.info_frame.pack(pady=15, fill="x", padx=20)

        self.product_label = ctk.CTkLabel(
            self.info_frame, text="Товар не выбран",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.product_label.pack(pady=(14, 4))

        self.stock_label = ctk.CTkLabel(
            self.info_frame, text="", font=ctk.CTkFont(size=14),
        )
        self.stock_label.pack(pady=2)

        self.status_label = ctk.CTkLabel(
            self.info_frame, text="",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        self.status_label.pack(pady=6)

        self.expiration_label = ctk.CTkLabel(
            self.info_frame, text="", font=ctk.CTkFont(size=13),
            text_color="#555",
        )
        self.expiration_label.pack(pady=(0, 14))

    # ---------------- autocomplete ----------------
    def _wire_autocomplete(self) -> None:
        self.search_var.trace_add("write", lambda *_: self._on_text_change())

    def _on_text_change(self) -> None:
        text = self.search_var.get().strip()
        if not text or len(text) < 1:
            self._hide_suggestions()
            return
        matches = []
        text_low = text.lower()
        for p in self._products_cache:
            if text_low in p["Name"].lower() or text in (p.get("Barcode") or ""):
                matches.append(p)
        matches = matches[:6]
        if not matches:
            self._hide_suggestions()
            return
        self._show_suggestions(matches)

    def _show_suggestions(self, products) -> None:
        self._hide_suggestions()
        # создаём оверлей-фрейм поверх родительского фрейма
        self._suggestion_box = ctk.CTkFrame(
            self.search_container, fg_color="white",
            border_width=1, border_color=COLOR_ACCENT, corner_radius=6,
        )
        self._suggestion_box.place(x=0, y=42, relwidth=1.0)
        self._suggestion_buttons = []
        for p in products:
            b = ctk.CTkButton(
                self._suggestion_box, text=p["Name"],
                anchor="w",
                fg_color="white", text_color="#222",
                hover_color="#E8F5E9",
                height=28,
                command=lambda prod=p: self._pick_suggestion(prod),
            )
            b.pack(fill="x", padx=2, pady=1)
            self._suggestion_buttons.append(b)

    def _hide_suggestions(self) -> None:
        if self._suggestion_box is not None:
            self._suggestion_box.destroy()
            self._suggestion_box = None
        self._suggestion_buttons = []

    def _focus_first_suggestion(self) -> None:
        if self._suggestion_buttons:
            self._suggestion_buttons[0].focus_set()

    def _pick_suggestion(self, product: dict) -> None:
        self.search_var.set(product["Name"])
        self._hide_suggestions()
        self._on_search()

    # ---------------- handlers ----------------
    def _on_search(self) -> None:
        self._hide_suggestions()
        query = self.search_var.get().strip()
        if not query:
            return
        result = self.slc.find_product_for_sale(query)
        if not result:
            self._clear_card("Товар не найден")
            self._current_batch = None
            return

        product = result["product"]
        batch: BatchInfo | None = result["batch"]
        if not batch:
            # товар есть, но все партии просрочены
            self._clear_card(
                f"Товар: {product['Name']}\nВсе партии просрочены!"
            )
            self._current_batch = None
            return

        self._current_batch = batch
        # Компактный формат, как на скрине диплома (рис. 3.2)
        self.product_label.configure(text=f"Товар: {product['Name']}")
        self.stock_label.configure(
            text=(
                f"Остаток: {batch.quantity} шт   •   "
                f"Партия: {batch.batch_id}   •   "
                f"Поставщик: {batch.supplier or '—'}"
            )
        )
        if batch.status is BatchStatus.EXPIRED:
            status_text = (
                f"⛔ ПРОСРОЧЕНО — осталось {batch.days_remaining} дн "
                f"(продажа запрещена)"
            )
        elif batch.status is BatchStatus.CRITICAL:
            status_text = (
                f"⚠ СКИДКА {batch.discount_percent}% — "
                f"осталось {batch.days_remaining} дн"
            )
        elif batch.discount_percent > 0:
            status_text = (
                f"СКИДКА {batch.discount_percent}% — "
                f"осталось {batch.days_remaining} дн"
            )
        else:
            status_text = f"Срок годности: {batch.expiration_date.isoformat()}"
        self.status_label.configure(text=status_text, text_color=batch.status.color)
        self.expiration_label.configure(
            text=(
                f"Срок истёк: {batch.expiration_date.isoformat()}   |   "
                f"Партия FEFO-выбрана автоматически"
            )
        )

    def _on_add_to_cart(self) -> None:
        if not self._current_batch:
            CTkMessagebox(title="Ошибка", message="Сначала найдите товар!",
                          icon="cancel")
            return
        batch = self._current_batch
        if batch.blocked:
            CTkMessagebox(
                title="Запрет продажи",
                message=(
                    f"Товар «{batch.product_name}» ПРОСРОЧЕН!\n"
                    "Продажа запрещена согласно политике FEFO."
                ),
                icon="cancel",
            )
            return
        try:
            ok = self.slc.perform_sale(batch, qty=1, sale_price=5.0)
        except Exception as e:
            CTkMessagebox(title="Ошибка", message=str(e), icon="cancel")
            return
        if not ok:
            CTkMessagebox(title="Ошибка", message="Не удалось списать товар.",
                          icon="cancel")
            return
        CTkMessagebox(
            title="Успех",
            message=f"Товар «{batch.product_name}» добавлен в чек!\n"
                    f"Остаток в партии: {batch.quantity} шт",
            icon="check",
        )
        self._clear_card("Товар не выбран")
        self._current_batch = None
        self.search_var.set("")
        if self.on_sale_callback:
            self.on_sale_callback()

    def _open_all_products(self) -> None:
        self._hide_suggestions()
        AllProductsDialog(self.parent, self.reports)

    def _open_sales_history(self) -> None:
        self._hide_suggestions()
        SalesHistoryDialog(self.parent, self.reports)

    def _clear_card(self, text: str) -> None:
        self.product_label.configure(text=text)
        self.stock_label.configure(text="")
        self.status_label.configure(text="", text_color=COLOR_OK)
        self.expiration_label.configure(text="")
