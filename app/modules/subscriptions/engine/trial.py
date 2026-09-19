"""Funções utilitárias e regras para cálculo de período de teste gratuito (Free Trial).

Configurável via variável de ambiente DEFAULT_TRIAL_DAYS (default: 30 dias).
Aplica a política canônica de normalização de âncora 1–28 para eliminar indefinições de calendário.
"""

from datetime import datetime, timezone, timedelta
import calendar
from app.config.settings import settings


def normalize_anchor_day(day: int) -> int:
    """Normaliza o dia de cobrança (anchor) no intervalo 1 a 28.
    
    Elimina o risco de meses curtos (ex: 28 de fevereiro) gerarem saltos
    ou erros de cálculo de ciclo.
    """
    return max(1, min(day, 28))


def get_default_trial_days() -> int:
    """Retorna os dias padrão de trial configurados via ENV."""
    return getattr(settings, "DEFAULT_TRIAL_DAYS", 30)


def add_months_preserving_billing_day(dt: datetime, months: int, billing_day: int | None = None) -> datetime:
    """Adiciona N meses a uma data preservando o billing_day normalizado (1–28) às 12:00 UTC."""
    if billing_day is None:
        billing_day = dt.day

    normalized_day = normalize_anchor_day(billing_day)

    year = dt.year
    month = dt.month + months
    while month > 12:
        year += 1
        month -= 12
    while month < 1:
        year -= 1
        month += 12

    max_days = calendar.monthrange(year, month)[1]
    day = min(normalized_day, max_days)
    return datetime(year, month, day, 12, 0, 0, tzinfo=timezone.utc)


def calculate_trial_end(start_dt: datetime | None = None, trial_days: int | None = None) -> tuple[datetime, int]:
    """Calcula a data final do trial e o billing_day normalizado (1–28).
    
    Args:
        start_dt: Data de início (default: agora em UTC).
        trial_days: Duração em dias (default: configurado em DEFAULT_TRIAL_DAYS).
        
    Returns:
        tuple[trial_ends_at, normalized_billing_day]
    """
    if start_dt is None:
        start_dt = datetime.now(timezone.utc)
    elif start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)

    if trial_days is None:
        trial_days = get_default_trial_days()

    if trial_days <= 0:
        return start_dt, normalize_anchor_day(start_dt.day)

    normalized_anchor = normalize_anchor_day(start_dt.day)

    if trial_days % 30 == 0:
        months_to_add = trial_days // 30
        trial_end = add_months_preserving_billing_day(start_dt, months_to_add, normalized_anchor)
        return trial_end, normalized_anchor
    else:
        raw_end = start_dt + timedelta(days=trial_days)
        final_anchor = normalize_anchor_day(raw_end.day)
        trial_end = raw_end.replace(
            day=final_anchor,
            hour=12,
            minute=0,
            second=0,
            microsecond=0,
        )
        return trial_end, final_anchor
