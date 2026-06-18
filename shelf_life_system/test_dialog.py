"""Тест: открыть ReturnsDialog без Tk, чтобы поймать исключения."""
import sys
from pathlib import Path
sys.path.insert(0, r"D:\minimax projects\6\shelf_life_system")

from modules import Database, AuditAndLog, Returns
from modules.returns import Returns as R

db = Database(r"D:\minimax projects\6\shelf_life_system\database.db")
db.connect()
audit = AuditAndLog(db)
ret = Returns(db, audit)
candidates = ret.list_critical_batches(days=14)
print(f"Candidates: {len(candidates)}")
for c in candidates:
    print(f"  Batch #{c['BatchID']} {c['ProductName']} exp={c['ExpirationDate']} qty={c['StockQty']} sup={c.get('Supplier')}")
db.close()
