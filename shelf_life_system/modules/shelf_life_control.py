"""
modules/shelf_life_control.py
-----------------------------
Модуль ShelfLifeControl — компонент архитектуры прототипа (рис. 2.15).

Реализует алгоритм AutomaticShelfLifeControl (раздел 2.5 дипломной работы):
  • вычисляет DaysRemaining для каждой активной партии;
  • присваивает статус (Normal / Critical / Expired);
  • автоматически блокирует просрочку в UI;
  • подсвечивает критические партии жёлтым;
  • обеспечивает принцип FEFO при выборе партии на продажу.

Содержит также логику автоматических скидок на основе таблицы DiscountRules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from modules.audit_log import AuditAndLog
from modules.database import Database


class BatchStatus(str, Enum):
    NORMAL = "Normal"
    CRITICAL = "Critical"   # <= 3 дней
    EXPIRED = "Expired"     # < 0 дней

    @property
    def color(self) -> str:
        return {
            BatchStatus.NORMAL:   "#1B5E20",   # зелёный
            BatchStatus.CRITICAL: "#E65100",   # оранжевый
            BatchStatus.EXPIRED:  "#B71C1C",   # красный
        }[self]

    @property
    def label_ru(self) -> str:
        return {
            BatchStatus.NORMAL:   "Нормальный",
            BatchStatus.CRITICAL: "Критический",
            BatchStatus.EXPIRED:  "Просрочен",
        }[self]


@dataclass
class BatchInfo:
    """Агрегированная информация о партии для UI."""
    batch_id: int
    product_id: int
    product_name: str
    expiration_date: date
    days_remaining: int
    quantity: int
    status: BatchStatus
    discount_percent: int
    blocked: bool
    purchase_price: float | None = None
    supplier: str | None = None

    @property
    def status_text(self) -> str:
        if self.status is BatchStatus.EXPIRED:
            return f"ПРОСРОЧЕНО — осталось {self.days_remaining} дн (продажа запрещена)"
        if self.status is BatchStatus.CRITICAL:
            return f"⚠ СКИДКА {self.discount_percent}% — осталось {self.days_remaining} дн"
        if self.discount_percent > 0:
            return f"СКИДКА {self.discount_percent}% — осталось {self.days_remaining} дн"
        return f"Срок годности: {self.expiration_date.isoformat()}"


class ShelfLifeControl:
    """
    Ядро системы контроля сроков годности.

    Соответствует псевдокоду из раздела 2.5 дипломной работы:
        PROCEDURE AutomaticShelfLifeControl(ProductID)
    """

    CRITICAL_DAYS_THRESHOLD = 3
    SALE_BLOCK_HOURS_BEFORE_EXPIRY = 0   # 0 = блокируем в день истечения и позже

    def __init__(self, db: Database, audit: AuditAndLog) -> None:
        self.db = db
        self.audit = audit
        self._rules: list[dict[str, Any]] | None = None

    # ---------------- helpers ----------------
    def _rules_cache(self) -> list[dict[str, Any]]:
        if self._rules is None:
            self._rules = self.db.get_discount_rules()
        return self._rules

    def refresh_rules(self) -> None:
        self._rules = None

    @staticmethod
    def calculate_days_remaining(expiration: str | date, today: date | None = None) -> int:
        if today is None:
            today = date.today()
        if isinstance(expiration, str):
            expiration = datetime.strptime(expiration, "%Y-%m-%d").date()
        return (expiration - today).days

    def determine_status(self, days_remaining: int) -> BatchStatus:
        if days_remaining < self.SALE_BLOCK_HOURS_BEFORE_EXPIRY:
            return BatchStatus.EXPIRED
        if days_remaining <= self.CRITICAL_DAYS_THRESHOLD:
            return BatchStatus.CRITICAL
        return BatchStatus.NORMAL

    def determine_discount(self, days_remaining: int) -> int:
        """Скидка в % по таблице DiscountRules (максимальная из подходящих)."""
        for rule in self._rules_cache():
            if days_remaining <= rule["DaysBeforeExpire"]:
                return int(rule["DiscountPercent"])
        return 0

    # ---------------- core algorithm ----------------
    def control_for_product(self, product_id: int) -> list[BatchInfo]:
        """Выполняет AutomaticShelfLifeControl для всех активных партий товара."""
        today = date.today()
        batches = self.db.get_active_batches(product_id)
        result: list[BatchInfo] = []
        for b in batches:
            stock = self.db.get_stock(b["BatchID"])
            if stock <= 0:
                continue
            days_rem = self.calculate_days_remaining(b["ExpirationDate"], today)
            status = self.determine_status(days_rem)
            discount = self.determine_discount(days_rem) if status is not BatchStatus.EXPIRED else 0
            blocked = status is BatchStatus.EXPIRED
            info = BatchInfo(
                batch_id=b["BatchID"],
                product_id=b["ProductID"],
                product_name="",  # заполнит вызывающий код
                expiration_date=b["ExpirationDate"],
                days_remaining=days_rem,
                quantity=stock,
                status=status,
                discount_percent=discount,
                blocked=blocked,
                purchase_price=b.get("PurchasePrice"),
                supplier=b.get("Supplier"),
            )
            result.append(info)
            # логируем критические / просроченные
            if status is BatchStatus.EXPIRED:
                self.audit.log_blocked_batch(b["BatchID"], "", days_rem)
            elif status is BatchStatus.CRITICAL:
                self.audit.log_critical_alert(b["BatchID"], "", days_rem)
        return result

    def find_sale_batch(self, product_id: int) -> BatchInfo | None:
        """FEFO: вернёт подходящую для продажи партию (исключая просрочку)."""
        candidates = self.control_for_product(product_id)
        for info in candidates:
            if not info.blocked and info.quantity > 0:
                return info
        return None

    def find_product_for_sale(self, search_text: str) -> dict[str, Any] | None:
        """Поиск товара по имени или штрих-коду. Возвращает dict с Product + BatchInfo."""
        search_text = (search_text or "").strip()
        if not search_text:
            return None
        product = None
        # сначала по точному штрих-коду
        product = self.db.get_product_by_barcode(search_text)
        if not product:
            # по началу имени
            with self.db.cursor() as cur:
                cur.execute(
                    "SELECT * FROM Products WHERE LOWER(Name) LIKE LOWER(?) "
                    "ORDER BY Name LIMIT 1",
                    (f"%{search_text}%",),
                )
                row = cur.fetchone()
                if row:
                    product = dict(row)
        if not product:
            return None
        info = self.find_sale_batch(product["ProductID"])
        if info:
            info.product_name = product["Name"]
        return {
            "product": product,
            "batch": info,
        }

    # ---------------- sale operations ----------------
    def perform_sale(self, batch_info: BatchInfo, qty: int = 1,
                     sale_price: float | None = None) -> bool:
        """Совершить продажу. Возвращает True при успехе. Блокирует просрочку."""
        if batch_info.blocked:
            return False
        if batch_info.quantity < qty:
            return False
        new_qty = self.db.decrement_stock(batch_info.batch_id, qty)
        self.db.record_sale(batch_info.batch_id, qty, sale_price)
        self.audit.log_sale(
            batch_info.batch_id,
            batch_info.product_name,
            qty,
        )
        # обновляем AvgDailySales14Days для рекомендаций
        avg = self.db.get_avg_daily_sales(batch_info.product_id, days=14)
        self.db.update_avg_sales(batch_info.product_id, avg)
        batch_info.quantity = new_qty
        return True

    # ---------------- dashboard ----------------
    def summary(self) -> dict[str, Any]:
        return {
            "expiring_7d": self.db.count_expiring_within(7),
            "sold_7d": self.db.sum_sales_in_window(7),
            "fefo_efficiency": self.db.calculate_fefo_efficiency(),
        }
