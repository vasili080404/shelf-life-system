"""
modules — пакет модулей бизнес-логики.

Соответствует архитектуре прототипа (рис. 2.15 дипломной работы):
  • Core Functional Modules: ShelfLifeControl, AutoOrder, WriteOff, Reports,
    AuditAndLog, Planogram, Returns
  • Data Access Layer: Database
"""
from .database import Database
from .shelf_life_control import ShelfLifeControl, BatchInfo, BatchStatus
from .auto_order import AutoOrder, OrderRecommendation
from .write_off import WriteOff, WriteOffResult
from .reports import Reports, ReportTable, save_text_report, save_excel_report
from .audit_log import AuditAndLog
from .planogram import Planogram
from .returns import Returns, ReturnResult

__all__ = [
    "Database",
    "ShelfLifeControl", "BatchInfo", "BatchStatus",
    "AutoOrder", "OrderRecommendation",
    "WriteOff", "WriteOffResult",
    "Reports", "ReportTable", "save_text_report", "save_excel_report",
    "AuditAndLog",
    "Planogram",
    "Returns", "ReturnResult",
]
