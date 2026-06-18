"""
ui/notify.py
------------
Звуковые уведомления для прототипа системы контроля сроков годности.

Реализует требование U3 (Usability) дипломной работы:
  «Visual and sound prompts for critical situations
   (expired goods, expiring shelf life)».

Использует системные звуки Windows (``winsound``) — без внешних аудио-файлов,
что позволяет работать в офлайн-режиме (требование U5) на любых терминалах
БМ8003 / БИС-2000 без дополнительной настройки.
"""
from __future__ import annotations

import sys
import threading

# ``winsound`` доступен только на Windows; на других ОС — graceful fallback
if sys.platform == "win32":
    try:
        import winsound
    except ImportError:  # pragma: no cover
        winsound = None  # type: ignore
else:
    winsound = None  # type: ignore


def _beep(freq: int, duration_ms: int) -> None:
    """Безопасный вызов Beep в отдельном потоке (не блокирует UI)."""
    def _do():
        if winsound is None:
            return
        try:
            winsound.Beep(freq, duration_ms)
        except Exception:
            # Beep может не работать на виртуалках без звуковой карты
            pass
    threading.Thread(target=_do, daemon=True).start()


def play_warning() -> None:
    """Короткий двойной сигнал — для КРИТИЧЕСКИХ партий (≤ 3 дней)."""
    _beep(880, 150)
    threading.Timer(0.18, lambda: _beep(880, 150)).start()


def play_alert() -> None:
    """Тройной нарастающий сигнал — для ПРОСРОЧЕННЫХ партий."""
    _beep(660, 200)
    threading.Timer(0.22, lambda: _beep(880, 200)).start()
    threading.Timer(0.44, lambda: _beep(1100, 250)).start()


def play_success() -> None:
    """Короткий мягкий сигнал — успешная операция."""
    _beep(1200, 80)
