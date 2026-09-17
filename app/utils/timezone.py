from __future__ import annotations
from datetime import datetime, date, time, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Tuple

BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")


def get_brazil_now() -> datetime:
    """Retorna datetime atual com fuso de Brasília (America/Sao_Paulo)."""
    return datetime.now(BRAZIL_TZ)


def get_brazil_today() -> date:
    """Retorna a data atual no fuso de Brasília."""
    return get_brazil_now().date()


def to_brazil_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    """Converte qualquer datetime (naive em UTC ou tz-aware) para datetime no fuso de Brasília."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BRAZIL_TZ)


def get_day_bounds_brazil(target_date: date) -> Tuple[datetime, datetime]:
    """
    Retorna (start_dt, end_dt) para o dia especificado no fuso de Brasília.
    Exemplo: para 2026-09-16, retorna:
      - 2026-09-16 00:00:00-03:00 (equivalente a 03:00:00 UTC)
      - 2026-09-16 23:59:59.999999-03:00 (equivalente a 02:59:59.999999 UTC do dia seguinte)
    """
    start_dt = datetime.combine(target_date, time.min, tzinfo=BRAZIL_TZ)
    end_dt = datetime.combine(target_date, time.max, tzinfo=BRAZIL_TZ)
    return start_dt, end_dt


def get_date_range_bounds_brazil(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Retorna (start_dt, end_dt) para um intervalo de datas no fuso de Brasília.
    Se start_date for informado, o início é 00:00:00 BRT daquela data.
    Se end_date for informado, o fim é 23:59:59.999999 BRT daquela data.
    """
    start_dt = datetime.combine(start_date, time.min, tzinfo=BRAZIL_TZ) if start_date else None
    end_dt = datetime.combine(end_date, time.max, tzinfo=BRAZIL_TZ) if end_date else None
    return start_dt, end_dt
