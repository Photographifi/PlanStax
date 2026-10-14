"""Background execution for long tasks and for the live wavelet preview."""

from __future__ import annotations

import threading
import traceback

from PySide6.QtCore import QThread, Signal

from ..core import Cancelled


class Task(QThread):
    """Runs fn(progress, cancel) off the GUI thread."""

    progress = Signal(float, str)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            result = self._fn(lambda f, m: self.progress.emit(float(f), str(m)), self.cancel_event)
        except Cancelled:
            self.cancelled.emit()
        except MemoryError:
            self.failed.emit("Mémoire insuffisante pour ce traitement.\n"
                             "Essayez un agrandissement plus faible ou moins de points d'alignement.")
        except Exception as exc:  # noqa: BLE001 - reported to the user
            traceback.print_exc()
            self.failed.emit(f"{type(exc).__name__} : {exc}")
        else:
            self.succeeded.emit(result)


class PreviewWorker(QThread):
    """Computes the latest requested preview; requests arriving while busy are coalesced."""

    ready = Signal(object, int)

    def __init__(self, compute, parent=None) -> None:
        super().__init__(parent)
        self._compute = compute
        self._cond = threading.Condition()
        self._pending = None
        self._stop = False

    def submit(self, token: int, payload) -> None:
        with self._cond:
            self._pending = (token, payload)
            self._cond.notify()

    def stop(self) -> None:
        with self._cond:
            self._stop = True
            self._cond.notify()
        self.wait(2000)

    def run(self) -> None:
        while True:
            with self._cond:
                while self._pending is None and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                token, payload = self._pending
                self._pending = None
            try:
                result = self._compute(payload)
            except Exception:  # noqa: BLE001
                traceback.print_exc()
                continue
            self.ready.emit(result, token)
