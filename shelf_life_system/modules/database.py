"""
modules/database.py
-------------------
Слой доступа к данным (Data Access Layer) — компонент «Database Access Layer»
из архитектуры прототипа (рис. 2.15 дипломной работы).

Инкапсулирует все SQL-запросы и предоставляет высокоуровневые методы
бизнес-логике. Используется всеми функциональными модулями:
  • ShelfLifeControl
  • AutoOrder
  • WriteOff
  • Reports
  • AuditAndLog

Подключение к SQLite инкапсулировано, реализован паттерн Repository.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Iterable, Iterator


class Database:
    """Единая точка работы с SQLite."""

    def __init__(self, db_path: str = "database.db") -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # ---------------- lifecycle ----------------
    def connect(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Cursor]:
        """Безопасный контекст-менеджер: авто-commit при успехе, rollback при ошибке."""
        self.connect()
        assert self._conn is not None
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    def commit(self) -> None:
        if self._conn is not None:
            self._conn.commit()

    # ---------------- helpers ----------------
    @staticmethod
    def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(r) for r in rows]

    @staticmethod
    def to_date(value: str | date | datetime | None) -> str:
        """Нормализация дат в ISO-формат YYYY-MM-DD для SQL."""
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    # ---------------- Products ----------------
    def get_product_by_name(self, name: str) -> dict[str, Any] | None:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM Products WHERE LOWER(Name) = LOWER(?)", (name,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_product_by_barcode(self, barcode: str) -> dict[str, Any] | None:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM Products WHERE Barcode = ?", (barcode,))
            row = cur.fetchone()
            return dict(row) if row else None

    def list_products(self) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM Products ORDER BY Name")
            return self.rows_to_dicts(cur.fetchall())

    def update_avg_sales(self, product_id: int, avg_sales: float) -> None:
        with self.cursor() as cur:
            cur.execute(
                "UPDATE Products SET AvgDailySales14Days = ?, LastUpdate = CURRENT_TIMESTAMP "
                "WHERE ProductID = ?",
                (avg_sales, product_id),
            )

    # ---------------- Batches ----------------
    def get_active_batches(self, product_id: int) -> list[dict[str, Any]]:
        """Все активные партии товара, отсортированные по сроку (FEFO)."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM Batches WHERE ProductID = ? AND IsActive = 1 "
                "ORDER BY ExpirationDate ASC",
                (product_id,),
            )
            return self.rows_to_dicts(cur.fetchall())

    def get_oldest_active_batch(self, product_id: int) -> dict[str, Any] | None:
        """FEFO: самая старая (с минимальным ExpirationDate) активная партия."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM Batches WHERE ProductID = ? AND IsActive = 1 "
                "AND CurrentQuantity > 0 "
                "ORDER BY ExpirationDate ASC LIMIT 1",
                (product_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_batch(self, batch_id: int) -> dict[str, Any] | None:
        with self.cursor() as cur:
            cur.execute("SELECT * FROM Batches WHERE BatchID = ?", (batch_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_expired_batches(self) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT b.*, p.Name AS ProductName, s.Quantity AS StockQty "
                "FROM Batches b "
                "JOIN Products p ON p.ProductID = b.ProductID "
                "LEFT JOIN Stock s ON s.BatchID = b.BatchID "
                "WHERE b.ExpirationDate < date('now') AND b.IsActive = 1 "
                "AND COALESCE(s.Quantity, 0) > 0 "
                "ORDER BY b.ExpirationDate ASC",
            )
            return self.rows_to_dicts(cur.fetchall())

    def get_critical_batches(self, days_threshold: int = 14) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT b.*, p.Name AS ProductName, s.Quantity AS StockQty "
                "FROM Batches b "
                "JOIN Products p ON p.ProductID = b.ProductID "
                "LEFT JOIN Stock s ON s.BatchID = b.BatchID "
                "WHERE b.ExpirationDate BETWEEN date('now') AND date('now', '+' || ? || ' days') "
                "AND b.IsActive = 1 AND COALESCE(s.Quantity, 0) > 0 "
                "ORDER BY b.ExpirationDate ASC",
                (days_threshold,),
            )
            return self.rows_to_dicts(cur.fetchall())

    def get_all_active_batches_with_stock(self) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT b.*, p.Name AS ProductName, p.MinStock, s.Quantity AS StockQty "
                "FROM Batches b "
                "JOIN Products p ON p.ProductID = b.ProductID "
                "LEFT JOIN Stock s ON s.BatchID = b.BatchID "
                "WHERE b.IsActive = 1 AND COALESCE(s.Quantity, 0) > 0 "
                "ORDER BY b.ExpirationDate ASC",
            )
            return self.rows_to_dicts(cur.fetchall())

    def set_batch_inactive(self, batch_id: int) -> None:
        with self.cursor() as cur:
            cur.execute("UPDATE Batches SET IsActive = 0 WHERE BatchID = ?", (batch_id,))

    # ---------------- Stock ----------------
    def get_stock(self, batch_id: int) -> int:
        with self.cursor() as cur:
            cur.execute("SELECT Quantity FROM Stock WHERE BatchID = ?", (batch_id,))
            row = cur.fetchone()
            return int(row["Quantity"]) if row else 0

    def decrement_stock(self, batch_id: int, qty: int = 1) -> int:
        """Списание со склада. Возвращает новый остаток. Запрет < 0 обеспечен CHECK."""
        with self.cursor() as cur:
            cur.execute(
                "UPDATE Stock SET Quantity = Quantity - ?, LastMovementDate = CURRENT_TIMESTAMP "
                "WHERE BatchID = ?",
                (qty, batch_id),
            )
            cur.execute("SELECT Quantity FROM Stock WHERE BatchID = ?", (batch_id,))
            row = cur.fetchone()
            return int(row["Quantity"]) if row else 0

    def zero_stock(self, batch_id: int) -> None:
        with self.cursor() as cur:
            cur.execute(
                "UPDATE Stock SET Quantity = 0, LastMovementDate = CURRENT_TIMESTAMP "
                "WHERE BatchID = ?",
                (batch_id,),
            )

    # ---------------- SalesHistory ----------------
    def record_sale(self, batch_id: int, qty: int, sale_price: float | None = None) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO SalesHistory (BatchID, Quantity, SalePrice) VALUES (?, ?, ?)",
                (batch_id, qty, sale_price),
            )
            return int(cur.lastrowid or 0)

    def get_recent_sales(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT s.SaleID, s.BatchID, s.Quantity, s.SaleDate, s.SalePrice, "
                "       p.Name AS ProductName, b.ExpirationDate "
                "FROM SalesHistory s "
                "JOIN Batches b ON b.BatchID = s.BatchID "
                "JOIN Products p ON p.ProductID = b.ProductID "
                "ORDER BY s.SaleDate DESC LIMIT ?",
                (limit,),
            )
            return self.rows_to_dicts(cur.fetchall())

    def get_sales_window_days(self, days: int = 7) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(Quantity), 0) AS TotalQty "
                "FROM SalesHistory WHERE SaleDate >= date('now', ?)",
                (f"-{days} days",),
            )
            return self.rows_to_dicts(cur.fetchall())

    def get_avg_daily_sales(self, product_id: int, days: int = 14) -> float:
        with self.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(AVG(daily_sales), 0) AS Avg "
                "FROM ("
                "  SELECT DATE(s.SaleDate) AS d, SUM(s.Quantity) AS daily_sales "
                "  FROM SalesHistory s "
                "  JOIN Batches b ON b.BatchID = s.BatchID "
                "  WHERE b.ProductID = ? AND s.SaleDate >= date('now', ?)"
                "  GROUP BY DATE(s.SaleDate)"
                ")",
                (product_id, f"-{days} days"),
            )
            row = cur.fetchone()
            return float(row["Avg"] or 0.0)

    # ---------------- DiscountRules ----------------
    def get_discount_rules(self) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM DiscountRules WHERE IsActive = 1 "
                "ORDER BY DaysBeforeExpire DESC",
            )
            return self.rows_to_dicts(cur.fetchall())

    # ---------------- Planogram ----------------
    def list_planogram(self) -> list[dict[str, Any]]:
        """Все записи планограммы с данными товара. Сортировка: полка, позиция."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT pl.PlanogramID, pl.ShelfCode, pl.Position, "
                "       pl.ProductID, pl.MinStock, pl.MaxStock, "
                "       p.Name AS ProductName, p.Category, p.Barcode "
                "FROM Planogram pl "
                "JOIN Products p ON p.ProductID = pl.ProductID "
                "ORDER BY pl.ShelfCode, pl.Position",
            )
            return self.rows_to_dicts(cur.fetchall())

    def upsert_planogram(self, shelf_code: str, position: int,
                         product_id: int, min_stock: int, max_stock: int) -> int:
        """Добавить/обновить запись планограммы. Возвращает PlanogramID."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT PlanogramID FROM Planogram "
                "WHERE ShelfCode = ? AND Position = ? AND ProductID = ?",
                (shelf_code, position, product_id),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE Planogram SET MinStock = ?, MaxStock = ? "
                    "WHERE PlanogramID = ?",
                    (min_stock, max_stock, int(row["PlanogramID"])),
                )
                return int(row["PlanogramID"])
            cur.execute(
                "INSERT INTO Planogram (ShelfCode, Position, ProductID, "
                "MinStock, MaxStock) VALUES (?, ?, ?, ?, ?)",
                (shelf_code, position, product_id, min_stock, max_stock),
            )
            return int(cur.lastrowid or 0)

    def delete_planogram(self, planogram_id: int) -> None:
        with self.cursor() as cur:
            cur.execute("DELETE FROM Planogram WHERE PlanogramID = ?",
                        (planogram_id,))

    def get_planogram_min_for_product(self, product_id: int) -> int | None:
        """MinStock из планограммы (приоритет) или None, если товар не выставлен."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT MinStock FROM Planogram WHERE ProductID = ? "
                "ORDER BY PlanogramID LIMIT 1",
                (product_id,),
            )
            row = cur.fetchone()
            return int(row["MinStock"]) if row else None

    # ---------------- Returns ----------------
    def create_return(self, batch_id: int, qty: int, reason: str,
                      act_number: str, supplier: str | None = None) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO Returns (BatchID, ReturnDate, Quantity, Reason, "
                "ActNumber, Supplier) VALUES (?, date('now'), ?, ?, ?, ?)",
                (batch_id, qty, reason, act_number, supplier),
            )
            return int(cur.lastrowid or 0)

    def list_returns(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT r.*, p.Name AS ProductName, b.ExpirationDate "
                "FROM Returns r "
                "JOIN Batches b ON b.BatchID = r.BatchID "
                "JOIN Products p ON p.ProductID = b.ProductID "
                "ORDER BY r.ReturnDate DESC, r.ReturnID DESC LIMIT ?",
                (limit,),
            )
            return self.rows_to_dicts(cur.fetchall())

    # ---------------- Orders ----------------
    def create_order(self, total_items: int, total_amount: float = 0.0,
                     status: str = "Generated") -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO Orders (Status, TotalItems, TotalAmount) VALUES (?, ?, ?)",
                (status, total_items, total_amount),
            )
            return int(cur.lastrowid or 0)

    def add_order_item(self, order_id: int, product_id: int,
                       qty: int, reason: str) -> None:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO OrderItems (OrderID, ProductID, RecommendedQuantity, Reason) "
                "VALUES (?, ?, ?, ?)",
                (order_id, product_id, qty, reason),
            )

    def list_orders(self) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM Orders ORDER BY CreationDate DESC",
            )
            return self.rows_to_dicts(cur.fetchall())

    def get_order_items(self, order_id: int) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT oi.*, p.Name AS ProductName "
                "FROM OrderItems oi "
                "JOIN Products p ON p.ProductID = oi.ProductID "
                "WHERE oi.OrderID = ?",
                (order_id,),
            )
            return self.rows_to_dicts(cur.fetchall())

    # ---------------- WriteOffs ----------------
    def create_writeoff(self, batch_id: int, qty: int, reason: str,
                        act_number: str | None = None) -> int:
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO WriteOffs (BatchID, WriteOffDate, Quantity, Reason, ActNumber) "
                "VALUES (?, date('now'), ?, ?, ?)",
                (batch_id, qty, reason, act_number),
            )
            return int(cur.lastrowid or 0)

    def get_writeoffs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT w.*, p.Name AS ProductName, b.PurchasePrice "
                "FROM WriteOffs w "
                "JOIN Batches b ON b.BatchID = w.BatchID "
                "JOIN Products p ON p.ProductID = b.ProductID "
                "ORDER BY w.WriteOffDate DESC LIMIT ?",
                (limit,),
            )
            return self.rows_to_dicts(cur.fetchall())

    def get_losses_in_window(self, days: int = 7) -> list[dict[str, Any]]:
        """Партии, у которых срок истёк за последние N дней."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT b.*, p.Name AS ProductName, s.Quantity AS StockQty, "
                "       b.PurchasePrice, "
                "       (s.Quantity * b.PurchasePrice) AS Loss "
                "FROM Batches b "
                "JOIN Products p ON p.ProductID = b.ProductID "
                "LEFT JOIN Stock s ON s.BatchID = b.BatchID "
                "WHERE b.ExpirationDate BETWEEN date('now', ?) AND date('now') "
                "AND b.IsActive = 1 AND COALESCE(s.Quantity, 0) > 0 "
                "ORDER BY b.ExpirationDate DESC",
                (f"-{days} days",),
            )
            return self.rows_to_dicts(cur.fetchall())

    # ---------------- ActionLog ----------------
    def log_action(self, table_name: str, action: str,
                   old: str | None = None, new: str | None = None,
                   user: str = "system") -> int:
        with self.cursor() as cur:
            cur.execute(
                'INSERT INTO ActionLog ("TableName", Action, OldValues, NewValues, "User") '
                "VALUES (?, ?, ?, ?, ?)",
                (table_name, action, old, new, user),
            )
            return int(cur.lastrowid or 0)

    def get_action_log(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT LogID, DateTime, TableName, Action, OldValues, NewValues, \"User\" "
                "FROM ActionLog ORDER BY DateTime DESC LIMIT ?",
                (limit,),
            )
            return self.rows_to_dicts(cur.fetchall())

    # ---------------- Dashboard stats ----------------
    def count_expiring_within(self, days: int = 7) -> int:
        with self.cursor() as cur:
            cur.execute(
                "SELECT COUNT(DISTINCT p.ProductID) AS C "
                "FROM Products p "
                "JOIN Batches b ON b.ProductID = p.ProductID "
                "LEFT JOIN Stock s ON s.BatchID = b.BatchID "
                "WHERE b.ExpirationDate BETWEEN date('now') AND date('now', '+' || ? || ' days') "
                "AND b.IsActive = 1 AND COALESCE(s.Quantity, 0) > 0",
                (days,),
            )
            return int(cur.fetchone()["C"] or 0)

    def sum_sales_in_window(self, days: int = 7) -> int:
        with self.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(Quantity), 0) AS S "
                "FROM SalesHistory WHERE SaleDate >= date('now', ?)",
                (f"-{days} days",),
            )
            return int(cur.fetchone()["S"] or 0)

    def calculate_fefo_efficiency(self) -> float:
        """FEFO-эффективность = доля продаж, ушедших из самой старой активной партии.

        Чем выше процент — тем строже система соблюдает FEFO.
        """
        with self.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS Total FROM SalesHistory "
                "WHERE SaleDate >= date('now', '-7 days')",
            )
            total = int(cur.fetchone()["Total"] or 0)
            if total == 0:
                return 100.0

            cur.execute(
                "SELECT COUNT(*) AS FefoOk FROM SalesHistory s "
                "JOIN Batches b ON b.BatchID = s.BatchID "
                "WHERE s.SaleDate >= date('now', '-7 days') "
                "AND b.BatchID = ("
                "  SELECT b2.BatchID FROM Batches b2 "
                "  WHERE b2.ProductID = b.ProductID AND b2.IsActive = 1 "
                "    AND b2.CurrentQuantity > 0 "
                "  ORDER BY b2.ExpirationDate ASC LIMIT 1"
                ")",
            )
            fefo_ok = int(cur.fetchone()["FefoOk"] or 0)
            return round(100.0 * fefo_ok / total, 1)
