"""
modules/returns.py
------------------
Модуль «Возврат поставщику» — компонент архитектуры прототипа.

Реализует требование F8 (Functionality) и упоминание в разделе 1.4 дипломной
работы: «automatic generation of write-off and return acts within the
established loss norms».

Позволяет оформить возврат партии поставщику (например, товар с критическим
сроком, который не успели продать) с формированием акта.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from modules.audit_log import AuditAndLog
from modules.database import Database


@dataclass
class ReturnResult:
    return_id: int
    batch_id: int
    quantity: int
    act_number: str
    supplier: str | None


class Returns:
    """Оформление возврата партии поставщику."""

    def __init__(self, db: Database, audit: AuditAndLog) -> None:
        self.db = db
        self.audit = audit

    @staticmethod
    def generate_act_number() -> str:
        return f"ВЗВ-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    def list_critical_batches(self, days: int = 14) -> list[dict[str, Any]]:
        """Партии, у которых срок истекает в ближайшие N дней — кандидаты на возврат."""
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT b.BatchID, b.ProductID, b.ExpirationDate, "
                "       b.CurrentQuantity, b.Supplier, "
                "       s.Quantity AS StockQty, "
                "       p.Name AS ProductName "
                "FROM Batches b "
                "JOIN Products p ON p.ProductID = b.ProductID "
                "LEFT JOIN Stock s ON s.BatchID = b.BatchID "
                "WHERE b.ExpirationDate BETWEEN date('now') AND "
                "      date('now', '+' || ? || ' days') "
                "AND b.IsActive = 1 AND COALESCE(s.Quantity, 0) > 0 "
                "ORDER BY b.ExpirationDate ASC",
                (days,),
            )
            return self.db.rows_to_dicts(cur.fetchall())

    def perform_return(self, batch_id: int, qty: int, reason: str,
                       supplier: str | None = None) -> ReturnResult | None:
        """Оформить возврат `qty` единиц партии `batch_id` поставщику."""
        # проверим остаток
        stock_qty = self.db.get_stock(batch_id)
        if stock_qty < qty:
            return None
        act = self.generate_act_number()
        rid = self.db.create_return(
            batch_id=batch_id,
            qty=qty,
            reason=reason,
            act_number=act,
            supplier=supplier,
        )
        # списываем со склада
        self.db.decrement_stock(batch_id, qty)
        # если остаток = 0, деактивируем партию
        if self.db.get_stock(batch_id) <= 0:
            self.db.set_batch_inactive(batch_id)
        self.audit.log(
            action="RETURN_TO_SUPPLIER",
            table="Returns",
            new=(
                f"batch={batch_id} qty={qty} reason='{reason}' "
                f"supplier='{supplier or ''}' act={act}"
            ),
        )
        # получаем имя продукта для записи в лог
        batch = self.db.get_batch(batch_id)
        product_name = ""
        if batch:
            with self.db.cursor() as cur:
                cur.execute("SELECT Name FROM Products WHERE ProductID = ?",
                            (batch["ProductID"],))
                row = cur.fetchone()
                if row:
                    product_name = row["Name"]
        return ReturnResult(
            return_id=rid,
            batch_id=batch_id,
            quantity=qty,
            act_number=act,
            supplier=supplier,
        )
