"""Tipos e estruturas de dados fundamentais da Máquina de Estados de Faturamento (v2.1).

Contratos tipados para Snapshot, Eventos, Ações, Decisões e Itens do Ledger.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any


class LifecycleState(str, Enum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"
    PAST_DUE = "PAST_DUE"
    BLOCKED = "BLOCKED"
    CANCELED = "CANCELED"
    INCOMPLETE = "INCOMPLETE"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"


class AddonStatus(str, Enum):
    PENDING_PAYMENT = "PENDING_PAYMENT"
    ACTIVE = "ACTIVE"
    CANCEL_AT_PERIOD_END = "CANCEL_AT_PERIOD_END"
    CANCELED = "CANCELED"


class ProviderSubscriptionState(str, Enum):
    NONE = "NONE"
    FUTURE = "FUTURE"
    ACTIVE = "ACTIVE"
    CANCEL_AT_PERIOD_END = "CANCEL_AT_PERIOD_END"
    CANCELED = "CANCELED"


class PaymentMethodType(str, Enum):
    CARD = "CARD"
    PIX = "PIX"
    NONE = "NONE"


@dataclass(frozen=True)
class BillingPeriodItem:
    """Item individual de faturamento dentro de um ciclo (Ledger)."""
    item_type: str  # "plan", "addon", "prorata"
    code: str       # "MONTHLY", "pkg_500", etc.
    description: str
    quantity: int = 1
    unit_amount_cents: int = 0
    prorated_amount_cents: int = 0
    total_amount_cents: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TrialState:
    is_active: bool
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    seconds_remaining: float = 0.0


@dataclass(frozen=True)
class BillingState:
    anchor_day: int  # Normalizado entre 1 e 28
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    is_current_period_paid: bool = False
    items: list[BillingPeriodItem] = field(default_factory=list)

    @property
    def total_amount_cents(self) -> int:
        return sum(item.total_amount_cents for item in self.items)


@dataclass(frozen=True)
class PaymentMethodState:
    type: PaymentMethodType
    default_card_id: Optional[str] = None
    has_valid_card: bool = False


@dataclass(frozen=True)
class ProviderState:
    subscription_state: ProviderSubscriptionState = ProviderSubscriptionState.NONE
    active_subscription_id: Optional[str] = None
    future_subscription_id: Optional[str] = None
    future_subscription_plan: Optional[str] = None
    future_subscription_start_at: Optional[datetime] = None
    last_charge_id: Optional[str] = None
    last_charge_status: Optional[str] = None


@dataclass(frozen=True)
class AddonState:
    code: str
    status: AddonStatus = AddonStatus.ACTIVE
    paid_until: Optional[datetime] = None
    messages_limit: int = 0
    messages_used: int = 0
    cancel_at_period_end: bool = False


@dataclass(frozen=True)
class OutstandingState:
    has_pending_pix: bool = False
    pending_pix_charge_id: Optional[str] = None
    pending_pix_amount_cents: int = 0
    has_failed_payment: bool = False


@dataclass(frozen=True)
class BillingSnapshot:
    """Fotografia imutável e consolidada do estado de faturamento do tenant."""
    tenant_id: int
    snapshot_at: datetime
    lifecycle: LifecycleState
    trial: TrialState
    billing: BillingState
    payment_method: PaymentMethodState
    provider: ProviderState
    addons: list[AddonState] = field(default_factory=list)
    outstanding: OutstandingState = field(default_factory=OutstandingState)

    def get_addon(self, code: str) -> Optional[AddonState]:
        for a in self.addons:
            if a.code == code:
                return a
        return None

    @property
    def has_active_addon(self) -> bool:
        return any(a.status == AddonStatus.ACTIVE for a in self.addons)

    @property
    def active_addons(self) -> list[AddonState]:
        return [a for a in self.addons if a.status == AddonStatus.ACTIVE]


# --- TAXONOMIA DE EVENTOS ---

class EventType(str, Enum):
    CARD_ADDED = "CARD_ADDED"
    CARD_REMOVED = "CARD_REMOVED"
    PIX_SELECTED = "PIX_SELECTED"
    ADDON_PURCHASED = "ADDON_PURCHASED"
    ADDON_CANCEL_REQUESTED = "ADDON_CANCEL_REQUESTED"
    CHARGE_PAID = "CHARGE_PAID"
    CHARGE_FAILED = "CHARGE_FAILED"
    TRIAL_EXPIRED = "TRIAL_EXPIRED"
    CYCLE_DUE = "CYCLE_DUE"
    PIX_EXPIRED = "PIX_EXPIRED"
    PAYMENT_METHOD_CHANGED = "PAYMENT_METHOD_CHANGED"
    REFUND_PROCESSED = "REFUND_PROCESSED"


@dataclass(frozen=True)
class BillingEvent:
    event_type: EventType
    tenant_id: int
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CardAddedEvent(BillingEvent):
    card_id: str = ""
    is_default: bool = True

    def __init__(self, tenant_id: int, card_id: str, is_default: bool = True, timestamp: Optional[datetime] = None):
        super().__init__(
            event_type=EventType.CARD_ADDED,
            tenant_id=tenant_id,
            timestamp=timestamp or datetime.now(),
            payload={"card_id": card_id, "is_default": is_default}
        )
        object.__setattr__(self, "card_id", card_id)
        object.__setattr__(self, "is_default", is_default)


@dataclass(frozen=True)
class AddonPurchasedEvent(BillingEvent):
    addon_code: str = ""
    payment_method: Optional[str] = None

    def __init__(self, tenant_id: int, addon_code: str, payment_method: Optional[str] = None, timestamp: Optional[datetime] = None):
        super().__init__(
            event_type=EventType.ADDON_PURCHASED,
            tenant_id=tenant_id,
            timestamp=timestamp or datetime.now(),
            payload={"addon_code": addon_code, "payment_method": payment_method}
        )
        object.__setattr__(self, "addon_code", addon_code)
        object.__setattr__(self, "payment_method", payment_method)


@dataclass(frozen=True)
class AddonCancelRequestedEvent(BillingEvent):
    addon_code: str = ""

    def __init__(self, tenant_id: int, addon_code: str, timestamp: Optional[datetime] = None):
        super().__init__(
            event_type=EventType.ADDON_CANCEL_REQUESTED,
            tenant_id=tenant_id,
            timestamp=timestamp or datetime.now(),
            payload={"addon_code": addon_code}
        )
        object.__setattr__(self, "addon_code", addon_code)


@dataclass(frozen=True)
class PixSelectedEvent(BillingEvent):
    intent: str = "cycle"  # "cycle" ou "addon"
    addon_code: Optional[str] = None

    def __init__(self, tenant_id: int, intent: str = "cycle", addon_code: Optional[str] = None, timestamp: Optional[datetime] = None):
        super().__init__(
            event_type=EventType.PIX_SELECTED,
            tenant_id=tenant_id,
            timestamp=timestamp or datetime.now(),
            payload={"intent": intent, "addon_code": addon_code}
        )
        object.__setattr__(self, "intent", intent)
        object.__setattr__(self, "addon_code", addon_code)


@dataclass(frozen=True)
class ChargePaidEvent(BillingEvent):
    pagarme_charge_id: str = ""
    amount_cents: int = 0
    payment_method: str = "pix"
    charge_type: str = "plan_cycle"

    def __init__(self, tenant_id: int, pagarme_charge_id: str, amount_cents: int, payment_method: str, charge_type: str = "plan_cycle", timestamp: Optional[datetime] = None):
        super().__init__(
            event_type=EventType.CHARGE_PAID,
            tenant_id=tenant_id,
            timestamp=timestamp or datetime.now(),
            payload={
                "pagarme_charge_id": pagarme_charge_id,
                "amount_cents": amount_cents,
                "payment_method": payment_method,
                "charge_type": charge_type,
            }
        )
        object.__setattr__(self, "pagarme_charge_id", pagarme_charge_id)
        object.__setattr__(self, "amount_cents", amount_cents)
        object.__setattr__(self, "payment_method", payment_method)
        object.__setattr__(self, "charge_type", charge_type)


@dataclass(frozen=True)
class TrialExpiredEvent(BillingEvent):
    def __init__(self, tenant_id: int, timestamp: Optional[datetime] = None):
        super().__init__(
            event_type=EventType.TRIAL_EXPIRED,
            tenant_id=tenant_id,
            timestamp=timestamp or datetime.now(),
            payload={}
        )


# --- DECISÕES DO ENGINE ---

class DecisionType(str, Enum):
    # Cartão
    CREATE_FUTURE_BASE_SUBSCRIPTION = "CREATE_FUTURE_BASE_SUBSCRIPTION"
    CREATE_FUTURE_CONSOLIDATED_SUBSCRIPTION = "CREATE_FUTURE_CONSOLIDATED_SUBSCRIPTION"
    UPDATE_CARD_ON_FUTURE_SUBSCRIPTION = "UPDATE_CARD_ON_FUTURE_SUBSCRIPTION"
    CHARGE_FIRST_PERIOD_NOW_BASE = "CHARGE_FIRST_PERIOD_NOW_BASE"
    CHARGE_FIRST_PERIOD_NOW_CONSOLIDATED = "CHARGE_FIRST_PERIOD_NOW_CONSOLIDATED"
    CHARGE_OVERDUE_IMMEDIATELY = "CHARGE_OVERDUE_IMMEDIATELY"
    SCHEDULE_CARD_CONVERSION_AT_NEXT_ANCHOR = "SCHEDULE_CARD_CONVERSION_AT_NEXT_ANCHOR"
    PAY_CURRENT_PIX_WITH_CARD = "PAY_CURRENT_PIX_WITH_CARD"
    UPDATE_DEFAULT_CARD = "UPDATE_DEFAULT_CARD"

    # Addon
    CHARGE_ADDON_TRIAL_PRORATA_AND_UPDATE_FUTURE = "CHARGE_ADDON_TRIAL_PRORATA_AND_UPDATE_FUTURE"
    GENERATE_PIX_FOR_ADDON_IN_TRIAL = "GENERATE_PIX_FOR_ADDON_IN_TRIAL"
    CHARGE_ADDON_PRORATA_NOW_AND_UPGRADE_RECURRENCE = "CHARGE_ADDON_PRORATA_NOW_AND_UPGRADE_RECURRENCE"
    GENERATE_PIX_ADDON_PRORATA = "GENERATE_PIX_ADDON_PRORATA"
    SCHEDULE_ADDON_CANCELLATION_AT_PERIOD_END = "SCHEDULE_ADDON_CANCELLATION_AT_PERIOD_END"
    REMOVE_ADDON_FROM_NEXT_PIX = "REMOVE_ADDON_FROM_NEXT_PIX"

    # Pix
    SET_PREFERRED_METHOD_PIX = "SET_PREFERRED_METHOD_PIX"
    CANCEL_FUTURE_CARD_SUB_AND_SWITCH_TO_PIX = "CANCEL_FUTURE_CARD_SUB_AND_SWITCH_TO_PIX"
    SCHEDULE_SWITCH_TO_PIX_AT_PERIOD_END = "SCHEDULE_SWITCH_TO_PIX_AT_PERIOD_END"
    GENERATE_IMMEDIATE_CYCLE_PIX = "GENERATE_IMMEDIATE_CYCLE_PIX"

    # Webhook / Quitação
    NOOP_IDEMPOTENT = "NOOP_IDEMPOTENT"
    ACTIVATE_CYCLE_AND_EXTEND_ANCHOR = "ACTIVATE_CYCLE_AND_EXTEND_ANCHOR"
    ACTIVATE_ADDON_RESOURCES = "ACTIVATE_ADDON_RESOURCES"
    CONVERT_TRIAL_TO_ACTIVE = "CONVERT_TRIAL_TO_ACTIVE"

    # Fim de Trial / Transições
    AWAIT_PAGARME_FUTURE_SUB_EXECUTION = "AWAIT_PAGARME_FUTURE_SUB_EXECUTION"
    CHARGE_CARD_IMMEDIATELY_AND_CREATE_SUB = "CHARGE_CARD_IMMEDIATELY_AND_CREATE_SUB"
    EXPIRE_TRIAL_ENTER_PAST_DUE = "EXPIRE_TRIAL_ENTER_PAST_DUE"
    ENTER_PAST_DUE_WITH_RETRY = "ENTER_PAST_DUE_WITH_RETRY"
    BLOCK_ACCESS = "BLOCK_ACCESS"
    EXPIRE_CHARGE_AND_PROMPT_NEW = "EXPIRE_CHARGE_AND_PROMPT_NEW"
    REVOKE_ACCESS_AND_CANCEL = "REVOKE_ACCESS_AND_CANCEL"
    DEACTIVATE_ADDON = "DEACTIVATE_ADDON"


@dataclass(frozen=True)
class BillingAction:
    action_name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BillingDecision:
    decision_type: DecisionType
    reason: str
    actions: list[BillingAction] = field(default_factory=list)


# --- GERADORES DE CHAVES DE IDEMPOTÊNCIA DETERMINÍSTICAS ---

def make_idempotency_key(operation: str, **kwargs) -> str:
    """Gera chaves determinísticas para blindagem de idempotência."""
    if operation == "addon_prorata":
        return f"addon_prorata:{kwargs.get('tenant_id')}:{kwargs.get('period_id')}:{kwargs.get('addon_code')}"
    elif operation == "first_payment":
        return f"first_payment:{kwargs.get('tenant_id')}:{kwargs.get('period_id')}"
    elif operation == "cycle_renewal":
        return f"cycle_renewal:{kwargs.get('tenant_id')}:{kwargs.get('period_id')}"
    elif operation == "pix_charge":
        return f"pix_charge:{kwargs.get('period_id')}:{kwargs.get('purpose', 'renewal')}"
    elif operation == "refund":
        return f"refund:{kwargs.get('charge_id')}"
    return f"billing_op:{operation}:{kwargs.get('tenant_id', 0)}:{kwargs.get('period_id', 0)}"
