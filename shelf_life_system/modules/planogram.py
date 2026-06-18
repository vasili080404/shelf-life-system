"""
modules/planogram.py
--------------------
Модуль «Планограмма» — компонент архитектуры прототипа (рис. 2.15).

Реализует требование F5 (Functionality) дипломной работы:
  «Maintenance of a digital shelf inspection log with automatic control
   of planogram compliance».

Планограмма — это привязка товаров к полкам с указанием минимального
(MinStock) и максимального (MaxStock) остатка. Используется:
  • в модуле AutoOrder для расчёта TargetStock (приоритет над Products.MinStock);
  • в UI как справочник для старшего оператора.
"""
from __future__ import annotations

from typing import Any

from modules.audit_log import AuditAndLog
from modules.database import Database


class Planogram:
    """Управление планограммой торгового зала."""

    def __init__(self, db: Database, audit: AuditAndLog) -> None:
        self.db = db
        self.audit = audit

    def list_all(self) -> list[dict[str, Any]]:
        return self.db.list_planogram()

    def get_min_stock(self, product_id: int) -> int:
        """MinStock из планограммы или fallback на Products.MinStock."""
        v = self.db.get_planogram_min_for_product(product_id)
        if v is not None:
            return v
        product = self.db.get_product_by_name("")  # не используется
        # fallback: ищем продукт напрямую
        with self.db.cursor() as cur:
            cur.execute("SELECT MinStock FROM Products WHERE ProductID = ?",
                        (product_id,))
            row = cur.fetchone()
            return int(row["MinStock"]) if row and row["MinStock"] is not None else 10

    def upsert(self, shelf_code: str, position: int, product_id: int,
               min_stock: int, max_stock: int) -> int:
        pid = self.db.upsert_planogram(
            shelf_code, position, product_id, min_stock, max_stock,
        )
        self.audit.log(
            action="PLANOGRAM_UPSERT",
            table="Planogram",
            new=f"shelf={shelf_code} pos={position} product={product_id} "
                f"min={min_stock} max={max_stock}",
        )
        return pid

    def delete(self, planogram_id: int) -> None:
        self.db.delete_planogram(planogram_id)
        self.audit.log(
            action="PLANOGRAM_DELETE",
            table="Planogram",
            new=f"id={planogram_id}",
        )
