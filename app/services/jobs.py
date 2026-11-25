"""Execução de tarefas em background com acompanhamento de progresso para HTMX."""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session

from app.database.session import engine

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]
JobFn = Callable[[Session, ProgressCallback], str]


@dataclass
class JobState:
    """Estado atual de uma tarefa em background."""

    name: str
    status: str = "idle"  # idle | running | done | error
    done: int = 0
    total: int = 0
    message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def pct(self) -> int:
        """Progresso percentual (0 a 100)."""
        if self.total <= 0:
            return 0
        return min(100, int(self.done / self.total * 100))


_lock = threading.Lock()
_jobs: dict[str, JobState] = {}


def get_state(name: str) -> JobState:
    """Retorna o estado atual da tarefa (ou ``idle`` se nunca executou)."""
    with _lock:
        state = _jobs.get(name)
        if state is None:
            return JobState(name=name)
        return JobState(
            name=state.name,
            status=state.status,
            done=state.done,
            total=state.total,
            message=state.message,
            started_at=state.started_at,
            finished_at=state.finished_at,
        )


def reset_all() -> None:
    """Limpa o registro de tarefas (usado em testes)."""
    with _lock:
        _jobs.clear()


def trigger(name: str, fn: JobFn, initial_message: str = "Iniciando...") -> JobState:
    """Dispara ``fn`` em thread separada se a tarefa ainda não estiver em execução.

    Args:
        name: Identificador único da tarefa (ex.: ``"quotes"``, ``"screener"``).
        fn: Função executada com ``(session, on_progress)`` que retorna mensagem final.
        initial_message: Texto exibido enquanto a tarefa inicia.

    Returns:
        Estado atual da tarefa (``running``).
    """
    with _lock:
        current = _jobs.get(name)
        if current is not None and current.status == "running":
            return get_state(name)
        state = JobState(
            name=name,
            status="running",
            done=0,
            total=0,
            message=initial_message,
            started_at=datetime.now(UTC),
        )
        _jobs[name] = state

    def _on_progress(done: int, total: int) -> None:
        with _lock:
            st = _jobs.get(name)
            if st is not None:
                st.done = done
                st.total = total

    def _runner() -> None:
        try:
            with Session(engine) as session:
                result_msg = fn(session, _on_progress)
            with _lock:
                st = _jobs[name]
                st.status = "done"
                st.message = result_msg
                st.finished_at = datetime.now(UTC)
        except Exception as exc:
            logger.exception("Falha na tarefa em background '%s'", name)
            with _lock:
                st = _jobs[name]
                st.status = "error"
                st.message = f"Erro: {exc}"
                st.finished_at = datetime.now(UTC)

    threading.Thread(target=_runner, name=f"midas-job-{name}", daemon=True).start()
    return get_state(name)
