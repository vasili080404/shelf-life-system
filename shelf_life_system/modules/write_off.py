"""
modules/write_off.py
--------------------
Модуль WriteOff — компонент архитектуры прототипа (рис. 2.15).

Отвечает за списание просроченных и повреждённых товаров с формированием
акта списания (таблица WriteOffs, поле ActNumber). Операция выполняется
старшим оператором и обязательно логируется в ActionLog.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from modules.audit_log import AuditAndLog
from modules.database import Database


@dataclass
class WriteOffResult:
    total_items: int
    total_loss: float
    act_number: str
    writeoff_ids: list[int]


class WriteOff:
    """Списание просроченных товаров с генерацией акта."""

    def __init__(self, db: Database, audit: AuditAndLog) -> None:
        self.db = db
        self.audit = audit

    # ---------------- helpers ----------------
    @staticmethod
    def generate_act_number() -> str:
        return f"АКТ-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    def list_expired(self) -> list[dict[str, Any]]:
        return self.db.get_expired_batches()

    def list_writeoffs(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.db.get_writeoffs(limit=limit)

    # ---------------- core operations ----------------
    def write_off_all_expired(self) -> WriteOffResult | None:
        expired = self.list_expired()
        if not expired:
            return None
        act_number = self.generate_act_number()
        total_qty = 0
        total_loss = 0.0
        writeoff_ids: list[int] = []
        for row in expired:
            qty = int(row.get("StockQty") or 0)
            price = float(row.get("PurchasePrice") or 0)
            loss = qty * price
            total_qty += qty
            total_loss += loss
            wid = self.db.create_writeoff(
                batch_id=row["BatchID"],
                qty=qty,
                reason="Просрочка",
                act_number=act_number,
            )
            writeoff_ids.append(wid)
            self.db.zero_stock(row["BatchID"])
            self.db.set_batch_inactive(row["BatchID"])
            self.audit.log_writeoff(
                batch_id=row["BatchID"],
                product_name=row.get("ProductName", ""),
                qty=qty,
                reason="Просрочка",
                act_number=act_number,
            )
        return WriteOffResult(
            total_items=total_qty,
            total_loss=round(total_loss, 2),
            act_number=act_number,
            writeoff_ids=writeoff_ids,
        )
