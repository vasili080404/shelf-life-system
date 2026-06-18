# Shelf Life Control System

Desktop application for automated inventory management at gas station #16 «Pokolyubichi».
Implements the FEFO (First Expired — First Out) principle, intelligent auto-ordering,
and automatic blocking of expired sales.

Diploma project · BSU, Department of Digital Systems and Technologies · 2026.

---

## Features

- **FEFO logic** — automatic First Expired — First Out batch picking; hard block of expired sales.
- **Automatic status calculation** — Normal · Critical (1–3 days) · Expired.
- **Auto discount calculation** for critical batches.
- **Intelligent auto-order** — recommendation engine based on 14-day average sales, current stock, and planogram.
- **Expired write-off** with auto-generated act and full audit log.
- **Supplier return** for batches with expiry ≤ 14 days.
- **Planogram** with Min / Max stock thresholds per slot.
- **Reports** — catalog, sales history, 7-day losses, write-off history, my orders, order details, auto-order proposal. Export to TXT and Excel.
- **Full audit trail** in the `ActionLog` table.

## Stack

- Python 3.11
- CustomTkinter (modern wrapper over Tkinter)
- SQLite (10 tables, WAL mode)
- openpyxl (Excel export)
- winsound (system notifications)

## Project structure

```
shelf_life_system/
├── app.py                 # Application entry point
├── init_db.py             # Database initialisation + seed data
├── test_dialog.py         # Manual smoke test for dialogs
├── modules/
│   ├── database.py        # Data access layer
│   ├── shelf_life_control.py
│   ├── auto_order.py
│   ├── write_off.py
│   ├── returns.py
│   ├── reports.py
│   ├── audit_log.py
│   └── planogram.py
└── ui/
    ├── operator_tab.py    # Cashier / checkout tab
    ├── senior_tab.py      # Senior operator dashboard
    ├── dialogs.py         # Modal dialogs
    └── notify.py          # System notifications
```

## How to run

```bash
# 1. Clone the repository
git clone https://github.com/vasili080404/shelf-life-system.git
cd shelf-life-system

# 2. Install dependencies
pip install -r requirements.txt

# 3. Initialize the database with seed data
python init_db.py

# 4. Launch the application
python app.py
```

### Optional CLI flags

```bash
# Open a specific tab at startup
python app.py --tab=senior

# Open a specific dialog
python app.py --open=my_orders
python app.py --open=writeoff_history
python app.py --open=action_log
python app.py --open=planogram

# Screenshot mode (for the diploma Appendix A)
python app.py --tab=senior --screenshots=D:\shots --delay=2000
```

## Live portfolio

A visual walkthrough of the application (Figures A.1–A.13 from Appendix A of the
diploma) is published at:
**https://vasili080404.github.io/shelf-life-system/**

## Database schema

10 SQLite tables: `Users`, `Products`, `Batches`, `Sales`, `WriteOffs`, `Returns`,
`Orders`, `OrderItems`, `Planogram`, `ActionLog`. The complete schema is generated
by `init_db.py` on first run.

## Methodology

Requirements captured using **FURPS+**. Process modelled in **BPMN 2.0**.
Three-tier modular architecture: Presentation (`ui/`) → Business Logic (`modules/`)
→ Data Access (`modules/database.py`).

## License

Diploma project, BSU 2026.
