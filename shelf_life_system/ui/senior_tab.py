"""
ui/senior_tab.py
----------------
Вкладка «Старший оператор».

Содержит:
  • шесть кнопок действий, расположенных в 2 ряда по 3 (рис. 3.7 дипломной работы):
      — Сформировать авто-заказ      — Мои заказы          — История продаж
      — Потери от просрочки (7 дней) — Списать просрочку   — История списаний
  • мини-ссылку «Журнал действий» в правом верхнем углу;
  • дашборд с тремя KPI-карточками:
      — Товары с истекающим сроком (7 дней)
      — Продано за неделю
      — Эффективность FEFO
"""
from __future__ import annotations

import customtkinter as ctk
from CTkMessagebox import CTkMessagebox

from modules import (
    AuditAndLog,
    AutoOrder,
    Reports,
    ShelfLifeControl,
    WriteOff,
)
from ui.dialogs import (
    COLOR_ACCENT,
    COLOR_DANGER,
    COLOR_OK,
    COLOR_WARN,
    ActionLogDialog,
    LossesDialog,
    MyOrdersDialog,
    PlanogramDialog,
    ReturnsDialog,
    SalesHistoryDialog,
    SmartOrderDialog,
    WriteOffExpiredDialog,
    WriteOffsHistoryDialog,
)


class SeniorTab:
    def __init__(self, parent: ctk.CTk, db, slc: ShelfLifeControl,
                 auto_order: AutoOrder, write_off: WriteOff,
                 reports: Reports, audit: AuditAndLog,
                 planogram=None, returns=None) -> None:
        self.parent = parent
        self.db = db
        self.slc = slc
        self.auto_order = auto_order
        self.write_off = write_off
        self.reports = reports
        self.audit = audit
        self.planogram = planogram
        self.returns = returns
        self._build()
        self.refresh_dashboard()

    # ---------------- UI ----------------
    def _build(self) -> None:
        frame = ctk.CTkFrame(self.parent, fg_color="#F5F5F5")
        frame.pack(padx=15, pady=15, fill="both", expand=True)

        # Заголовок и мини-ссылка «Журнал действий»
        header_row = ctk.CTkFrame(frame, fg_color="transparent")
        header_row.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(
            header_row, text="Режим Старшего оператора",
            font=ctk.CTkFont(size=22, weight="bold"), text_color=COLOR_ACCENT,
        ).pack(side="left", padx=20)
        ctk.CTkButton(
            header_row, text="🛡 Журнал действий",
            command=self._open_action_log,
            width=180, height=32,
            fg_color="transparent",
            text_color=COLOR_ACCENT,
            hover_color="#E0E0E0",
            border_width=1, border_color=COLOR_ACCENT,
        ).pack(side="right", padx=20)

        # Кнопки действий — 2 ряда по 3
        btn_box = ctk.CTkFrame(frame, fg_color="transparent")
        btn_box.pack(pady=14)

        row1 = ctk.CTkFrame(btn_box, fg_color="transparent")
        row1.pack(pady=6)
        row2 = ctk.CTkFrame(btn_box, fg_color="transparent")
        row2.pack(pady=6)
        row3 = ctk.CTkFrame(btn_box, fg_color="transparent")
        row3.pack(pady=6)

        # Ряд 1 — оперативные действия
        self._add_btn(row1, "📦 Сформировать авто-заказ", self._open_smart_order, 230)
        self._add_btn(row1, "📋 Мои заказы", self._open_my_orders, 150)
        self._add_btn(row1, "📜 История продаж", self._open_sales, 170)

        # Ряд 2 — отчётность и списания
        self._add_btn(row2, "📉 Потери от просрочки (7 дней)", self._open_losses, 240)
        self._add_btn(row2, "🗑️ Списать просрочку", self._open_writeoff_expired, 190)
        self._add_btn(row2, "📋 История списаний", self._open_writeoff_history, 180)

        # Ряд 3 — доп. функции (планограмма, возврат, обновить)
        self._add_btn(row3, "🗂 Планограмма", self._open_planogram, 150)
        self._add_btn(row3, "↩ Возврат поставщику", self._open_returns, 190)
        self._add_btn(row3, "🔄 Обновить показатели", self.refresh_dashboard, 200,
                      fg_color=COLOR_WARN, hover_color="#BF360C")

        # Дашборд
        dash = ctk.CTkFrame(
            frame, fg_color="white",
            border_width=2, border_color=COLOR_ACCENT, corner_radius=12,
        )
        dash.pack(pady=18, fill="x", padx=15)
        ctk.CTkLabel(
            dash, text="Быстрые показатели",
            font=ctk.CTkFont(size=18, weight="bold"), text_color=COLOR_ACCENT,
        ).pack(pady=10)

        cards = ctk.CTkFrame(dash, fg_color="transparent")
        cards.pack(fill="x", padx=20, pady=10)

        # Карточка 1 — Товары с истекающим сроком
        card1 = self._make_card(cards, "⏰", "Товары с истекающим сроком",
                                COLOR_WARN, "#FFF3E0", "#FF9800")
        card1.pack(side="left", padx=10, fill="both", expand=True)
        self.expiring_label = self._make_card_value(card1)

        # Карточка 2 — Продано за неделю
        card2 = self._make_card(cards, "📦", "Продано за неделю",
                                "#1565C0", "#E3F2FD", "#2196F3")
        card2.pack(side="left", padx=10, fill="both", expand=True)
        self.sold_label = self._make_card_value(card2)

        # Карточка 3 — Эффективность FEFO
        card3 = self._make_card(cards, "✅", "Эффективность FEFO",
                                COLOR_OK, "#E8F5E9", "#4CAF50")
        card3.pack(side="left", padx=10, fill="both", expand=True)
        self.fefo_label = self._make_card_value(card3, default="...")

    @staticmethod
    def _add_btn(parent, text, command, width, fg_color=None, hover_color=None):
        ctk.CTkButton(
            parent, text=text, command=command,
            width=width, height=42,
            fg_color=fg_color or COLOR_ACCENT,
            hover_color=hover_color or "#0D3B0D",
        ).pack(side="left", padx=6)

    @staticmethod
    def _make_card(parent, icon, title, value_color, bg, border):
        card = ctk.CTkFrame(parent, fg_color=bg, border_width=2,
                            border_color=border, corner_radius=10)
        ctk.CTkLabel(card, text=icon, font=ctk.CTkFont(size=32)).pack(pady=(10, 0))
        ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=value_color).pack(pady=5)
        return card

    @staticmethod
    def _make_card_value(card, default="..."):
        lbl = ctk.CTkLabel(card, text=default,
                           font=ctk.CTkFont(size=28, weight="bold"),
                           text_color=card.winfo_children()[1].cget("text_color"))
        lbl.pack(pady=(0, 10))
        return lbl

    # ---------------- actions ----------------
    def _open_smart_order(self):
        SmartOrderDialog(self.parent, self.auto_order, self.reports,
                         on_save_callback=self.refresh_dashboard)

    def _open_my_orders(self):
        MyOrdersDialog(self.parent, self.reports, self.db)

    def _open_sales(self):
        SalesHistoryDialog(self.parent, self.reports)

    def _open_losses(self):
        LossesDialog(self.parent, self.reports, days=7)

    def _open_writeoff_expired(self):
        WriteOffExpiredDialog(self.parent, self.write_off,
                              on_done_callback=self.refresh_dashboard)

    def _open_writeoff_history(self):
        WriteOffsHistoryDialog(self.parent, self.reports)

    def _open_action_log(self):
        ActionLogDialog(self.parent, self.audit)

    def _open_planogram(self):
        PlanogramDialog(self.parent, self.db)

    def _open_returns(self):
        ReturnsDialog(self.parent, self.db)

    def refresh_dashboard(self):
        s = self.slc.summary()
        self.expiring_label.configure(text=f"{s['expiring_7d']}")
        self.sold_label.configure(text=f"{s['sold_7d']}")
        self.fefo_label.configure(text=f"{s['fefo_efficiency']}%")
