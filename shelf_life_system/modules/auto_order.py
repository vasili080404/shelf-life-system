"""
modules/auto_order.py
---------------------
Модуль AutoOrder — компонент архитектуры прототипа (рис. 2.15).

Реализует алгоритм IntelligentAutoOrderGeneration (раздел 2.5 дипломной работы):

  PROCEDURE IntelligentAutoOrderGeneration(ProductID)
      AvgSales14 = GetAverageDailySales(ProductID, 14)
      Forecast    = AvgSales14 * 7
      TargetStock = GetMinPlanogramStock(ProductID) + CalculateSafetyStock(ProductID)
      CurrentStock= GetCurrentStock(ProductID)
      Recommended = Forecast + TargetStock - CurrentStock
      IF HasCriticalBatches(ProductID) THEN
          CriticalVolume = GetCriticalBatchesVolume(ProductID)
          Recommended = Recommended - CriticalVolume
      END IF
      IF Recommended < SupplierMinBatchSize(ProductID) THEN
          Recommended = SupplierMinBatchSize(ProductID)
      END IF
      IF Recommended <= 0 THEN
          CreateAutoOrder(ProductID, 0, "Not required")
      ELSE
          CreateAutoOrder(ProductID, Recommended, "Automatically generated")
      END IF
  END PROCEDURE
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from modules.audit_log import AuditAndLog
from modules.database import Database
from modules.planogram import Planogram


@dataclass
class OrderRecommendation:
    product_id: int
    product_name: str
    current_stock: int
    avg_daily_sales: float
    forecast: int
    target_stock: int
    recommended_qty: int
    reason: str


class AutoOrder:
    """Интеллектуальное формирование авто-заказа поставщику."""

    FORECAST_DAYS = 7                # горизонт прогноза
    HISTORY_DAYS = 14               # окно истории продаж
    SAFETY_STOCK_FACTOR = 1.3        # запас безопасности (30% сверх MinStock)
    DEFAULT_SUPPLIER_MIN_BATCH = 1  # min-партия поставщика (по умолчанию)

    def __init__(self, db: Database, audit: AuditAndLog,
                 planogram: Planogram | None = None) -> None:
        self.db = db
        self.audit = audit
        self.planogram = planogram

    # ---------------- helpers ----------------
    def get_current_stock(self, product_id: int) -> int:
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(s.Quantity), 0) AS Qty "
                "FROM Stock s JOIN Batches b ON b.BatchID = s.BatchID "
                "WHERE b.ProductID = ? AND b.IsActive = 1",
                (product_id,),
            )
            return int(cur.fetchone()["Qty"] or 0)

    def get_critical_volume(self, product_id: int, days: int = 14) -> int:
        """Объём партий с критическим сроком (≤ 14 дней), которые ещё нужно продать."""
        with self.db.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(SUM(s.Quantity), 0) AS Qty "
                "FROM Stock s JOIN Batches b ON b.BatchID = s.BatchID "
                "WHERE b.ProductID = ? AND b.IsActive = 1 "
                "AND b.ExpirationDate <= date('now', '+' || ? || ' days')",
                (product_id, days),
            )
            return int(cur.fetchone()["Qty"] or 0)

    def get_target_stock(self, product: dict[str, Any]) -> int:
        # приоритет — MinStock из планограммы; fallback на Products.MinStock
        if self.planogram is not None:
            min_stock = self.planogram.get_min_stock(int(product["ProductID"]))
        else:
            min_stock = int(product.get("MinStock") or 10)
        return int(min_stock * self.SAFETY_STOCK_FACTOR)

    def build_recommendation(self, product: dict[str, Any]) -> OrderRecommendation:
        product_id = product["ProductID"]
        name = product["Name"]
        avg_sales = self.db.get_avg_daily_sales(product_id, days=self.HISTORY_DAYS)
        # fallback: используем кешированный AvgDailySales14Days, если история пуста
        if avg_sales == 0:
            avg_sales = float(product.get("AvgDailySales14Days") or 0)
        forecast = int(round(avg_sales * self.FORECAST_DAYS))
        target = self.get_target_stock(product)
        current = self.get_current_stock(product_id)
        recommended = forecast + target - current

        reason_parts: list[str] = []
        critical_vol = self.get_critical_volume(product_id, days=14)
        if critical_vol > 0:
            recommended -= critical_vol
            reason_parts.append(
                f"учтён объём критических партий ({critical_vol} шт)"
            )

        # MinStock: из планограммы или из Products
        if self.planogram is not None:
            min_stock = self.planogram.get_min_stock(product_id)
        else:
            min_stock = int(product.get("MinStock") or 10)
        if current < min_stock:
            reason_parts.append("остаток ниже MinStock")
            recommended = max(recommended, target - current)
        if recommended <= 0:
            qty = 0
            reason = "Заказ не требуется (остаток достаточен)"
        else:
            qty = max(recommended, self.DEFAULT_SUPPLIER_MIN_BATCH)
            reason = "Сформировано автоматически" + (
                f" ({'; '.join(reason_parts)})" if reason_parts else ""
            )

        return OrderRecommendation(
            product_id=product_id,
            product_name=name,
            current_stock=current,
            avg_daily_sales=round(avg_sales, 2),
            forecast=forecast,
            target_stock=target,
            recommended_qty=qty,
            reason=reason,
        )

    def generate_for_all(self) -> list[OrderRecommendation]:
        recs: list[OrderRecommendation] = []
        for product in self.db.list_products():
            recs.append(self.build_recommendation(product))
        return recs

    def save_draft(self, recs: list[OrderRecommendation]) -> int:
        """Сохранить рекомендации как черновик заказа. Возвращает order_id."""
        items = [r for r in recs if r.recommended_qty > 0]
        if not items:
            return 0
        order_id = self.db.create_order(
            total_items=len(items),
            total_amount=0.0,
            status="Generated",
        )
        for r in items:
            self.db.add_order_item(
                order_id=order_id,
                product_id=r.product_id,
                qty=r.recommended_qty,
                reason=r.reason,
            )
        self.audit.log_order_generated(order_id, len(items))
        return order_id
