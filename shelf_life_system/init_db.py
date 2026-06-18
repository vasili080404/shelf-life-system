"""
init_db.py
----------
Создание и инициализация базы данных SQLite для системы
контроля сроков годности и интеллектуального авто-заказа.

Схема соответствует логической модели (3НФ), разработанной в разделе 2.4
дипломной работы (ER-диаграмма в Crow's Foot нотации).

Таблицы:
  • Products        — справочник товаров (ProductID, Name, Barcode, Category,
                      MinStock, AvgDailySales14Days, LastUpdate)
  • Batches         — партии товара (BatchID, ProductID, ManufactureDate,
                      ExpirationDate, ReceivedQuantity, CurrentQuantity,
                      PurchasePrice, Supplier)
  • Stock           — текущие остатки по партиям (StockID, BatchID, Quantity,
                      LastMovementDate)
  • SalesHistory    — история продаж (SaleID, BatchID, Quantity, SaleDate,
                      SalePrice)
  • Orders          — авто-заказы (OrderID, CreationDate, Status, TotalItems,
                      TotalAmount)
  • OrderItems      — позиции авто-заказа (OrderItemID, OrderID, ProductID,
                      RecommendedQuantity, Reason)
  • WriteOffs       — акты списания (WriteOffID, BatchID, WriteOffDate, Quantity,
                      Reason, ActNumber)
  • ActionLog       — журнал аудита (LogID, DateTime, TableName, Action, OldValues,
                      NewValues, User)
  • DiscountRules   — правила скидок по дням до истечения срока
"""
import sqlite3
from datetime import datetime, timedelta

DB_PATH = "database.db"


def create_database(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF")

    # Удаляем ВСЕ таблицы (включая устаревшие из предыдущей версии схемы)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    for (name,) in cursor.fetchall():
        if name.startswith("sqlite_"):
            continue
        cursor.execute(f"DROP TABLE IF EXISTS \"{name}\"")

    cursor.execute("PRAGMA foreign_keys = ON")

    # 1. Products — справочник товаров
    cursor.execute("""
        CREATE TABLE Products (
            ProductID          INTEGER PRIMARY KEY AUTOINCREMENT,
            Name               TEXT    NOT NULL,
            Barcode            TEXT,
            Category           TEXT,
            MinStock           INTEGER DEFAULT 10,
            AvgDailySales14Days REAL   DEFAULT 0,
            LastUpdate         DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Batches — партии
    cursor.execute("""
        CREATE TABLE Batches (
            BatchID          INTEGER PRIMARY KEY AUTOINCREMENT,
            ProductID        INTEGER NOT NULL,
            ManufactureDate  DATE,
            ExpirationDate   DATE    NOT NULL,
            ReceivedQuantity INTEGER NOT NULL,
            CurrentQuantity  INTEGER NOT NULL,
            PurchasePrice    REAL,
            Supplier         TEXT,
            IsActive         BOOLEAN DEFAULT 1,
            FOREIGN KEY (ProductID) REFERENCES Products(ProductID)
        )
    """)

    # 3. Stock — текущие остатки по партиям
    cursor.execute("""
        CREATE TABLE Stock (
            StockID           INTEGER PRIMARY KEY AUTOINCREMENT,
            BatchID           INTEGER NOT NULL UNIQUE,
            Quantity          INTEGER NOT NULL,
            LastMovementDate  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (BatchID) REFERENCES Batches(BatchID)
        )
    """)

    # 4. SalesHistory — продажи (с привязкой к партии — 3НФ)
    cursor.execute("""
        CREATE TABLE SalesHistory (
            SaleID     INTEGER PRIMARY KEY AUTOINCREMENT,
            BatchID    INTEGER NOT NULL,
            Quantity   INTEGER NOT NULL,
            SaleDate   DATETIME DEFAULT CURRENT_TIMESTAMP,
            SalePrice  REAL,
            FOREIGN KEY (BatchID) REFERENCES Batches(BatchID)
        )
    """)

    # 5. Orders — авто-заказы
    cursor.execute("""
        CREATE TABLE Orders (
            OrderID      INTEGER PRIMARY KEY AUTOINCREMENT,
            CreationDate DATETIME DEFAULT CURRENT_TIMESTAMP,
            Status       TEXT DEFAULT 'Generated',
            TotalItems   INTEGER,
            TotalAmount  REAL
        )
    """)

    # 6. OrderItems — позиции заказа
    cursor.execute("""
        CREATE TABLE OrderItems (
            OrderItemID           INTEGER PRIMARY KEY AUTOINCREMENT,
            OrderID               INTEGER NOT NULL,
            ProductID             INTEGER NOT NULL,
            RecommendedQuantity   INTEGER NOT NULL,
            Reason                TEXT,
            FOREIGN KEY (OrderID)   REFERENCES Orders(OrderID),
            FOREIGN KEY (ProductID) REFERENCES Products(ProductID)
        )
    """)

    # 7. WriteOffs — списания
    cursor.execute("""
        CREATE TABLE WriteOffs (
            WriteOffID    INTEGER PRIMARY KEY AUTOINCREMENT,
            BatchID       INTEGER NOT NULL,
            WriteOffDate  DATE NOT NULL,
            Quantity      INTEGER NOT NULL,
            Reason        TEXT,
            ActNumber     TEXT,
            FOREIGN KEY (BatchID) REFERENCES Batches(BatchID)
        )
    """)

    # 8. ActionLog — журнал аудита
    cursor.execute("""
        CREATE TABLE ActionLog (
            LogID      INTEGER PRIMARY KEY AUTOINCREMENT,
            DateTime   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            TableName  TEXT NOT NULL,
            Action     TEXT NOT NULL,
            OldValues  TEXT,
            NewValues  TEXT,
            "User"     TEXT
        )
    """)

    # 9. DiscountRules — правила скидок
    cursor.execute("""
        CREATE TABLE DiscountRules (
            ID                INTEGER PRIMARY KEY AUTOINCREMENT,
            DaysBeforeExpire  INTEGER NOT NULL,
            DiscountPercent   INTEGER NOT NULL,
            IsActive          BOOLEAN DEFAULT 1,
            MinQuantity       INTEGER DEFAULT 1
        )
    """)

    # 10. Planogram — планограмма торгового зала
    #     (полка → товар → минимальный/максимальный остаток, позиция)
    cursor.execute("""
        CREATE TABLE Planogram (
            PlanogramID   INTEGER PRIMARY KEY AUTOINCREMENT,
            ShelfCode     TEXT    NOT NULL,            -- напр. "A1", "B2", "Холодильник-1"
            Position      INTEGER NOT NULL DEFAULT 0, -- позиция на полке
            ProductID     INTEGER NOT NULL,
            MinStock      INTEGER NOT NULL DEFAULT 5,
            MaxStock      INTEGER NOT NULL DEFAULT 50,
            FOREIGN KEY (ProductID) REFERENCES Products(ProductID)
        )
    """)

    # 11. Returns — акты возврата товара поставщику
    cursor.execute("""
        CREATE TABLE Returns (
            ReturnID      INTEGER PRIMARY KEY AUTOINCREMENT,
            BatchID       INTEGER NOT NULL,
            ReturnDate    DATE    NOT NULL,
            Quantity      INTEGER NOT NULL,
            Reason        TEXT    NOT NULL,
            ActNumber     TEXT    NOT NULL,
            Supplier      TEXT,
            FOREIGN KEY (BatchID) REFERENCES Batches(BatchID)
        )
    """)

    # === Индексы для производительности ===
    cursor.execute("CREATE INDEX idx_batches_expiration ON Batches(ExpirationDate)")
    cursor.execute("CREATE INDEX idx_batches_product    ON Batches(ProductID)")
    cursor.execute("CREATE INDEX idx_stock_batch        ON Stock(BatchID)")
    cursor.execute("CREATE INDEX idx_sales_batch        ON SalesHistory(BatchID)")
    cursor.execute("CREATE INDEX idx_sales_date         ON SalesHistory(SaleDate)")
    cursor.execute("CREATE INDEX idx_writeoff_batch     ON WriteOffs(BatchID)")
    cursor.execute("CREATE INDEX idx_actionlog_dt       ON ActionLog(DateTime)")
    cursor.execute("CREATE INDEX idx_planogram_shelf    ON Planogram(ShelfCode, Position)")
    cursor.execute("CREATE INDEX idx_returns_batch       ON Returns(BatchID)")

    # === Правила скидок по умолчанию ===
    discount_rules = [
        (7, 15, 1, 1),   # за 7 дней до истечения — скидка 15%
        (4, 30, 1, 1),   # за 4 дня — скидка 30%
        (2, 50, 1, 1),   # за 2 дня — скидка 50%
    ]
    cursor.executemany(
        'INSERT INTO DiscountRules (DaysBeforeExpire, DiscountPercent, IsActive, MinQuantity) '
        'VALUES (?, ?, ?, ?)',
        discount_rules,
    )

    # === Тестовые данные: товары ===
    products = [
        # (Name, Barcode, Category, MinStock, AvgDailySales14Days)
        ("Шоколад Алёнка 100г",       "4810123456789", "Шоколад",  15,  4.0),
        ("Чипсы Lays Классические 150г", "4810234567890", "Снэки",   20,  6.0),
        ("Вода БонАква 1.5л",         "4810345678901", "Напитки",  30,  8.0),
        ("Кофе Якобс Монарх 200г",    "4810456789012", "Кофе",      8,  2.0),
        ("Печенье Юбилейное 112г",    "4810567890123", "Выпечка",  12,  3.0),
    ]
    cursor.executemany(
        'INSERT INTO Products (Name, Barcode, Category, MinStock, AvgDailySales14Days) '
        'VALUES (?, ?, ?, ?, ?)',
        products,
    )

    # === Тестовые данные: партии ===
    today = datetime.now().date()
    batches = [
        # (ProductID, ManufactureDate, ExpirationDate, ReceivedQty, CurrentQty, Price, Supplier, IsActive)
        # Партии с разными сроками — для демонстрации FEFO
        (1, today - timedelta(days=70),  today + timedelta(days=2),  45, 45, 2.80, "ОАО «Коммунарка»", 1),  # Critical (2 дн)
        (1, today - timedelta(days=60),  today + timedelta(days=10), 30, 30, 2.85, "ОАО «Коммунарка»", 1),  # Normal
        (2, today - timedelta(days=70),  today + timedelta(days=1),  60, 60, 3.20, "ООО «ПепсиКо»",     1),  # Critical (1 дн)
        (2, today - timedelta(days=60),  today + timedelta(days=11), 25, 25, 3.25, "ООО «ПепсиКо»",     1),  # Normal
        (3, today - timedelta(days=100), today + timedelta(days=265),120,120,1.10,"ООО «БонАква»",   1),  # Normal (вода)
        (4, today - timedelta(days=40),  today + timedelta(days=230), 18, 18, 8.50,"ООО «Якобс»",      1),  # Normal
        (5, today - timedelta(days=20),  today + timedelta(days=4),   22, 22, 2.10,"ОАО «Спартак»",    1),  # Critical (4 дн)
    ]
    cursor.executemany(
        'INSERT INTO Batches (ProductID, ManufactureDate, ExpirationDate, '
        'ReceivedQuantity, CurrentQuantity, PurchasePrice, Supplier, IsActive) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        batches,
    )

    # === Тестовые данные: остатки ===
    cursor.execute("SELECT BatchID, CurrentQuantity FROM Batches")
    for batch_id, qty in cursor.fetchall():
        cursor.execute(
            'INSERT INTO Stock (BatchID, Quantity) VALUES (?, ?)',
            (batch_id, qty),
        )

    # === Тестовые данные: история продаж (14 дней для расчёта AvgDailySales) ===
    import random
    random.seed(42)
    for product_id, avg_sales in [(1, 4.0), (2, 6.0), (3, 8.0), (4, 2.0), (5, 3.0)]:
        cursor.execute(
            "SELECT BatchID FROM Batches WHERE ProductID = ? AND IsActive = 1 "
            "ORDER BY ExpirationDate ASC LIMIT 1",
            (product_id,),
        )
        row = cursor.fetchone()
        if not row:
            continue
        batch_id = row[0]
        for d in range(14):
            day = today - timedelta(days=d)
            qty = max(1, int(random.gauss(avg_sales, 1)))
            cursor.execute(
                'INSERT INTO SalesHistory (BatchID, Quantity, SaleDate, SalePrice) '
                'VALUES (?, ?, ?, ?)',
                (batch_id, qty, day, 5.0),
            )

    # === Тестовые данные: планограмма ===
    planogram = [
        # (ShelfCode, Position, ProductID, MinStock, MaxStock)
        ("Стеллаж-А", 1, 1, 10, 50),   # Шоколад Алёнка
        ("Стеллаж-А", 2, 4,  5, 25),   # Кофе Якобс
        ("Стеллаж-Б", 1, 2, 15, 60),   # Чипсы Lays
        ("Стеллаж-Б", 2, 5,  8, 30),   # Печенье Юбилейное
        ("Холодильник-1", 1, 3, 20, 150),  # Вода БонАква
    ]
    cursor.executemany(
        "INSERT INTO Planogram (ShelfCode, Position, ProductID, MinStock, MaxStock) "
        "VALUES (?, ?, ?, ?, ?)",
        planogram,
    )

    conn.commit()
    conn.close()
    print(f"✅ База данных успешно создана: {db_path}")


if __name__ == "__main__":
    create_database()
