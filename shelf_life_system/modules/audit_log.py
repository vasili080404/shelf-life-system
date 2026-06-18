"""
modules/audit_log.py
--------------------
Модуль AuditAndLog — компонент архитектуры прототипа (рис. 2.15 дипломной работы).

Отвечает за полный аудит всех действий пользователя и изменений данных.
Обеспечивает выполнение требования R3 (Reliability):
  «Complete logging of all user actions (who, when, what changes were made)».

Все события пишутся в таблицу ActionLog. В UI реализован просмотр
журнала действий для администратора / старшего оператора.
"""
from __future__ import annotations

from typing import Any

from modules.database import Database


class AuditAndLog:
    """Тонкая обёртка над ActionLog с человекочитаемыми хелперами."""

    def __init__(self, db: Database, default_user: str = "Operator") -> None:
        self.db = db
        self.default_user = default_user

    # ---------------- запись ----------------
    def log(self, action: str, table: str = "App",
            old: Any = None, new: Any = None,
            user: str | None = None) -> int:
        return self.db.log_action(
            table_name=table,
            action=action,
            old=None if old is None else str(old),
            new=None if new is None else str(new),
            user=user or self.default_user,
        )

    def log_sale(self, batch_id: int, product_name: str, qty: int,
                 user: str = "Operator") -> None:
        self.log(
            action="SALE",
            table="SalesHistory",
            new=f"batch={batch_id} product='{product_name}' qty={qty}",
            user=user,
        )

    def log_writeoff(self, batch_id: int, product_name: str, qty: int,
                     reason: str, act_number: str | None,
                     user: str = "SeniorOperator") -> None:
        self.log(
            action="WRITE_OFF",
            table="WriteOffs",
            new=f"batch={batch_id} product='{product_name}' qty={qty} "
                f"reason='{reason}' act={act_number}",
            user=user,
        )

    def log_blocked_batch(self, batch_id: int, product_name: str,
                          days_remaining: int) -> None:
        self.log(
            action="BLOCK_EXPIRED",
            table="Batches",
            new=f"batch={batch_id} product='{product_name}' days={days_remaining}",
            user="ShelfLifeControl",
        )

    def log_critical_alert(self, batch_id: int, product_name: str,
                           days_remaining: int) -> None:
        self.log(
            action="CRITICAL_ALERT",
            table="Batches",
            new=f"batch={batch_id} product='{product_name}' days={days_remaining}",
            user="ShelfLifeControl",
        )

    def log_order_generated(self, order_id: int, items_count: int,
                            user: str = "SeniorOperator") -> None:
        self.log(
            action="ORDER_GENERATED",
            table="Orders",
            new=f"order={order_id} items={items_count}",
            user=user,
        )

    def log_search(self, query: str, results: int, user: str = "Operator") -> None:
        self.log(
            action="SEARCH",
            table="Products",
            new=f"query='{query}' results={results}",
            user=user,
        )

    # ---------------- чтение ----------------
    def get_recent(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.db.get_action_log(limit=limit)
