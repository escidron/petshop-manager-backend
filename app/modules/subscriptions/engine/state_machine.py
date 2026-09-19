"""Decision Engine Puro da Máquina de Estados de Faturamento do Data Pet (v2.1).

Função pura (determinística, sem I/O de rede ou banco):
    decide(snapshot: BillingSnapshot, event: BillingEvent) -> BillingDecision
"""

from app.modules.subscriptions.engine.types import (
    BillingSnapshot,
    BillingEvent,
    BillingDecision,
    BillingAction,
    EventType,
    LifecycleState,
    PaymentMethodType,
    DecisionType,
)


def decide(snapshot: BillingSnapshot, event: BillingEvent) -> BillingDecision:
    """Calcula determinística e puramente a decisão baseada no Snapshot e no Evento (v2.1)."""

    # -------------------------------------------------------------
    # 1. EVENTO: CARD_ADDED
    # -------------------------------------------------------------
    if event.event_type == EventType.CARD_ADDED:
        card_id = event.payload.get("card_id", "")

        # Cenário TRIAL
        if snapshot.lifecycle == LifecycleState.TRIAL:
            # Ainda em período de teste com folga (> 60 segundos restantes)
            if snapshot.trial.is_active and snapshot.trial.seconds_remaining > 60:
                if snapshot.provider.future_subscription_id:
                    return BillingDecision(
                        decision_type=DecisionType.UPDATE_CARD_ON_FUTURE_SUBSCRIPTION,
                        reason="Cartão atualizado na assinatura futura existente no Pagar.me.",
                        actions=[
                            BillingAction("pagarme_update_future_sub_card", {"subscription_id": snapshot.provider.future_subscription_id, "card_id": card_id}),
                            BillingAction("db_set_default_card", {"card_id": card_id}),
                        ]
                    )
                elif snapshot.has_active_addon:
                    return BillingDecision(
                        decision_type=DecisionType.CREATE_FUTURE_CONSOLIDATED_SUBSCRIPTION,
                        reason="Trial ativo com pacotes contratados: criando assinatura futura consolidada (Plano + Addons).",
                        actions=[
                            BillingAction("pagarme_create_future_consolidated_sub", {"card_id": card_id, "start_at": snapshot.trial.ends_at}),
                            BillingAction("db_set_default_card", {"card_id": card_id}),
                        ]
                    )
                else:
                    return BillingDecision(
                        decision_type=DecisionType.CREATE_FUTURE_BASE_SUBSCRIPTION,
                        reason="Trial ativo sem pacotes: criando assinatura futura do Plano Base.",
                        actions=[
                            BillingAction("pagarme_create_future_base_sub", {"card_id": card_id, "start_at": snapshot.trial.ends_at}),
                            BillingAction("db_set_default_card", {"card_id": card_id}),
                        ]
                    )
            else:
                # Trial expirando agora (<= 60s ou já vencido)
                if snapshot.has_active_addon:
                    return BillingDecision(
                        decision_type=DecisionType.CHARGE_FIRST_PERIOD_NOW_CONSOLIDATED,
                        reason="Trial expirado ou no término: cobrança imediata consolidada (Plano + Addons).",
                        actions=[
                            BillingAction("pagarme_cancel_future_sub_if_exists", {"subscription_id": snapshot.provider.future_subscription_id}),
                            BillingAction("pagarme_charge_immediate_consolidated", {"card_id": card_id}),
                            BillingAction("db_set_default_card", {"card_id": card_id}),
                        ]
                    )
                else:
                    return BillingDecision(
                        decision_type=DecisionType.CHARGE_FIRST_PERIOD_NOW_BASE,
                        reason="Trial expirado ou no término: cobrança imediata do Plano Base.",
                        actions=[
                            BillingAction("pagarme_cancel_future_sub_if_exists", {"subscription_id": snapshot.provider.future_subscription_id}),
                            BillingAction("pagarme_charge_immediate_base", {"card_id": card_id}),
                            BillingAction("db_set_default_card", {"card_id": card_id}),
                        ]
                    )

        # Cenário PAST_DUE / BLOCKED / INCOMPLETE
        if snapshot.lifecycle in (LifecycleState.PAST_DUE, LifecycleState.BLOCKED, LifecycleState.INCOMPLETE):
            return BillingDecision(
                decision_type=DecisionType.CHARGE_OVERDUE_IMMEDIATELY,
                reason="Tenant em débito ou incompleto: cobrança avulsa imediata com novo cartão.",
                actions=[
                    BillingAction("pagarme_charge_overdue", {"card_id": card_id}),
                    BillingAction("db_set_default_card", {"card_id": card_id}),
                ]
            )

        # Cenário ACTIVE
        if snapshot.lifecycle == LifecycleState.ACTIVE:
            if snapshot.payment_method.type == PaymentMethodType.PIX:
                if snapshot.billing.is_current_period_paid:
                    return BillingDecision(
                        decision_type=DecisionType.SCHEDULE_CARD_CONVERSION_AT_NEXT_ANCHOR,
                        reason="Período atual já quitado via Pix. Assinatura de cartão programada para o próximo ciclo.",
                        actions=[
                            BillingAction("pagarme_create_future_sub", {"card_id": card_id, "start_at": snapshot.billing.current_period_end}),
                            BillingAction("db_set_default_card", {"card_id": card_id}),
                            BillingAction("db_set_payment_method", {"method": "card"}),
                        ]
                    )
                else:
                    return BillingDecision(
                        decision_type=DecisionType.PAY_CURRENT_PIX_WITH_CARD,
                        reason="Pix do ciclo aberto. Cobrança imediata no novo cartão e conversão para recorrência.",
                        actions=[
                            BillingAction("pagarme_cancel_pending_pix", {"charge_id": snapshot.outstanding.pending_pix_charge_id}),
                            BillingAction("pagarme_charge_current_period_now", {"card_id": card_id}),
                            BillingAction("db_set_default_card", {"card_id": card_id}),
                            BillingAction("db_set_payment_method", {"method": "card"}),
                        ]
                    )
            else:
                # Já é cartão
                return BillingDecision(
                    decision_type=DecisionType.UPDATE_DEFAULT_CARD,
                    reason="Atualização de cartão padrão da assinatura recorrente existente.",
                    actions=[
                        BillingAction("pagarme_update_subscription_card", {"subscription_id": snapshot.provider.active_subscription_id, "card_id": card_id}),
                        BillingAction("db_set_default_card", {"card_id": card_id}),
                    ]
                )

    # -------------------------------------------------------------
    # 2. EVENTO: ADDON_PURCHASED
    # -------------------------------------------------------------
    if event.event_type == EventType.ADDON_PURCHASED:
        addon_code = event.payload.get("addon_code", "")

        if snapshot.lifecycle == LifecycleState.TRIAL:
            if snapshot.payment_method.has_valid_card:
                return BillingDecision(
                    decision_type=DecisionType.CHARGE_ADDON_TRIAL_PRORATA_AND_UPDATE_FUTURE,
                    reason="Contratação de pacote no Trial com cartão salvo: cobra avulso até data do trial e inclui item na futura.",
                    actions=[
                        BillingAction("pagarme_charge_addon_one_off", {"card_id": snapshot.payment_method.default_card_id, "addon_code": addon_code}),
                        BillingAction("pagarme_add_item_to_future_sub", {"future_subscription_id": snapshot.provider.future_subscription_id, "addon_code": addon_code, "start_at": snapshot.trial.ends_at}),
                        BillingAction("db_activate_addon", {"addon_code": addon_code, "until": snapshot.trial.ends_at}),
                    ]
                )
            else:
                return BillingDecision(
                    decision_type=DecisionType.GENERATE_PIX_FOR_ADDON_IN_TRIAL,
                    reason="Contratação de pacote no Trial com Pix: gera Pix avulso até data do trial.",
                    actions=[
                        BillingAction("pagarme_create_pix_charge", {"addon_code": addon_code, "type": "addon_prorata"}),
                        BillingAction("db_set_addon_pending_payment", {"addon_code": addon_code}),
                    ]
                )

        if snapshot.lifecycle == LifecycleState.ACTIVE:
            if snapshot.payment_method.type == PaymentMethodType.CARD:
                return BillingDecision(
                    decision_type=DecisionType.CHARGE_ADDON_PRORATA_NOW_AND_UPGRADE_RECURRENCE,
                    reason="Contratação de pacote em ciclo ativo (Cartão): cobra pró-rata avulso e atualiza próxima recorrência consolidada.",
                    actions=[
                        BillingAction("pagarme_charge_prorata_card", {"card_id": snapshot.payment_method.default_card_id, "addon_code": addon_code}),
                        BillingAction("pagarme_add_item_to_recurring_sub", {"subscription_id": snapshot.provider.active_subscription_id, "addon_code": addon_code, "start_at": snapshot.billing.current_period_end}),
                        BillingAction("db_activate_addon", {"addon_code": addon_code, "until": snapshot.billing.current_period_end}),
                    ]
                )
            else:
                return BillingDecision(
                    decision_type=DecisionType.GENERATE_PIX_ADDON_PRORATA,
                    reason="Contratação de pacote em ciclo ativo (Pix): gera Pix pró-rata avulso até o próximo vencimento.",
                    actions=[
                        BillingAction("pagarme_create_pix_charge", {"addon_code": addon_code, "type": "addon_prorata"}),
                        BillingAction("db_set_addon_pending_payment", {"addon_code": addon_code}),
                    ]
                )

    # -------------------------------------------------------------
    # 3. EVENTO: ADDON_CANCEL_REQUESTED
    # -------------------------------------------------------------
    if event.event_type == EventType.ADDON_CANCEL_REQUESTED:
        addon_code = event.payload.get("addon_code", "")
        if snapshot.payment_method.type == PaymentMethodType.CARD and snapshot.provider.active_subscription_id:
            return BillingDecision(
                decision_type=DecisionType.SCHEDULE_ADDON_CANCELLATION_AT_PERIOD_END,
                reason="Cancelamento de add-on: mantém ativo até fim do ciclo e remove da próxima renovação do cartão.",
                actions=[
                    BillingAction("pagarme_remove_item_from_recurring_sub", {"subscription_id": snapshot.provider.active_subscription_id, "addon_code": addon_code}),
                    BillingAction("db_set_addon_cancel_at_period_end", {"addon_code": addon_code}),
                ]
            )
        else:
            return BillingDecision(
                decision_type=DecisionType.REMOVE_ADDON_FROM_NEXT_PIX,
                reason="Cancelamento de add-on: o próximo Pix do ciclo não incluirá o pacote.",
                actions=[
                    BillingAction("db_set_addon_cancel_at_period_end", {"addon_code": addon_code}),
                ]
            )

    # -------------------------------------------------------------
    # 4. EVENTO: PIX_SELECTED
    # -------------------------------------------------------------
    if event.event_type == EventType.PIX_SELECTED:
        if snapshot.lifecycle == LifecycleState.TRIAL:
            if snapshot.provider.future_subscription_id:
                return BillingDecision(
                    decision_type=DecisionType.CANCEL_FUTURE_CARD_SUB_AND_SWITCH_TO_PIX,
                    reason="Usuário em Trial optou por Pix: cancela assinatura futura de cartão no Pagar.me.",
                    actions=[
                        BillingAction("pagarme_cancel_future_sub", {"subscription_id": snapshot.provider.future_subscription_id}),
                        BillingAction("db_set_payment_method", {"method": "pix"}),
                    ]
                )
            else:
                return BillingDecision(
                    decision_type=DecisionType.SET_PREFERRED_METHOD_PIX,
                    reason="Método preferencial definido como Pix durante o Trial.",
                    actions=[
                        BillingAction("db_set_payment_method", {"method": "pix"}),
                    ]
                )

        if snapshot.lifecycle == LifecycleState.ACTIVE:
            if snapshot.payment_method.type == PaymentMethodType.CARD and snapshot.provider.active_subscription_id:
                return BillingDecision(
                    decision_type=DecisionType.SCHEDULE_SWITCH_TO_PIX_AT_PERIOD_END,
                    reason="Troca de Cartão para Pix: agenda cancelamento no fim do período pago e programa Pix.",
                    actions=[
                        BillingAction("pagarme_cancel_sub_at_period_end", {"subscription_id": snapshot.provider.active_subscription_id}),
                        BillingAction("db_set_payment_method", {"method": "pix"}),
                    ]
                )
            else:
                return BillingDecision(
                    decision_type=DecisionType.SET_PREFERRED_METHOD_PIX,
                    reason="Método de faturamento definido como Pix.",
                    actions=[
                        BillingAction("db_set_payment_method", {"method": "pix"}),
                    ]
                )

        if snapshot.lifecycle in (LifecycleState.PAST_DUE, LifecycleState.INCOMPLETE):
            return BillingDecision(
                decision_type=DecisionType.GENERATE_IMMEDIATE_CYCLE_PIX,
                reason="Tenant vencido: geração imediata de Pix consolidado para regularização.",
                actions=[
                    BillingAction("pagarme_create_pix_cycle_charge", {}),
                    BillingAction("db_set_payment_method", {"method": "pix"}),
                ]
            )

    # -------------------------------------------------------------
    # 5. EVENTO: CHARGE_PAID (Webhook Pagar.me)
    # -------------------------------------------------------------
    if event.event_type == EventType.CHARGE_PAID:
        pagarme_charge_id = event.payload.get("pagarme_charge_id")
        charge_type = event.payload.get("charge_type", "plan_cycle")

        # Idempotência: Se já processado como paid
        if snapshot.provider.last_charge_id == pagarme_charge_id and snapshot.provider.last_charge_status == "paid":
            return BillingDecision(
                decision_type=DecisionType.NOOP_IDEMPOTENT,
                reason=f"Cobrança {pagarme_charge_id} já processada com sucesso anteriormente (Idempotente).",
                actions=[]
            )

        if charge_type in ("addon_prorata", "whatsapp_package"):
            return BillingDecision(
                decision_type=DecisionType.ACTIVATE_ADDON_RESOURCES,
                reason="Pagamento de pacote de WhatsApp confirmado via webhook.",
                actions=[
                    BillingAction("db_mark_charge_paid", {"charge_id": pagarme_charge_id}),
                    BillingAction("db_activate_addon_messages", {}),
                ]
            )

        if snapshot.lifecycle in (LifecycleState.TRIAL, LifecycleState.PAYMENT_PROCESSING):
            return BillingDecision(
                decision_type=DecisionType.CONVERT_TRIAL_TO_ACTIVE,
                reason="Primeira mensalidade paga: transição de Trial/Processing para Active.",
                actions=[
                    BillingAction("db_mark_charge_paid", {"charge_id": pagarme_charge_id}),
                    BillingAction("db_convert_trial_to_active", {}),
                ]
            )

        return BillingDecision(
            decision_type=DecisionType.ACTIVATE_CYCLE_AND_EXTEND_ANCHOR,
            reason="Mensalidade regular paga: avanço do ciclo preservando o anchor_day (1–28).",
            actions=[
                BillingAction("db_mark_charge_paid", {"charge_id": pagarme_charge_id}),
                BillingAction("db_extend_current_period", {}),
            ]
        )

    # -------------------------------------------------------------
    # 6. EVENTO: TRIAL_EXPIRED (Scheduler / Cron)
    # -------------------------------------------------------------
    if event.event_type == EventType.TRIAL_EXPIRED:
        if snapshot.payment_method.has_valid_card:
            if snapshot.provider.future_subscription_id:
                return BillingDecision(
                    decision_type=DecisionType.AWAIT_PAGARME_FUTURE_SUB_EXECUTION,
                    reason="Trial concluído com cartão salvo e futura agendada: entra em PAYMENT_PROCESSING aguardando o webhook do gateway.",
                    actions=[
                        BillingAction("db_set_lifecycle_processing", {"grace_hours": 24}),
                    ]
                )
            else:
                return BillingDecision(
                    decision_type=DecisionType.CHARGE_CARD_IMMEDIATELY_AND_CREATE_SUB,
                    reason="Trial expirou e cliente tem cartão salvo, mas não possuía assinatura futura criada.",
                    actions=[
                        BillingAction("pagarme_charge_card_and_create_sub", {"card_id": snapshot.payment_method.default_card_id}),
                    ]
                )
        else:
            return BillingDecision(
                decision_type=DecisionType.EXPIRE_TRIAL_ENTER_PAST_DUE,
                reason="Trial expirou sem cartão cadastrado: transiciona para PAST_DUE e aguarda pagamento.",
                actions=[
                    BillingAction("db_transition_to_past_due", {}),
                ]
            )

    # -------------------------------------------------------------
    # 7. EVENTO: CHARGE_FAILED
    # -------------------------------------------------------------
    if event.event_type == EventType.CHARGE_FAILED:
        return BillingDecision(
            decision_type=DecisionType.ENTER_PAST_DUE_WITH_RETRY,
            reason="Falha de pagamento reportada pelo gateway: entra em PAST_DUE com tolerância.",
            actions=[
                BillingAction("db_set_lifecycle_past_due", {}),
                BillingAction("notify_customer_payment_failed", {}),
            ]
        )

    # -------------------------------------------------------------
    # 8. EVENTO: PIX_EXPIRED
    # -------------------------------------------------------------
    if event.event_type == EventType.PIX_EXPIRED:
        return BillingDecision(
            decision_type=DecisionType.EXPIRE_CHARGE_AND_PROMPT_NEW,
            reason="Cobrança Pix expirou sem quitação.",
            actions=[
                BillingAction("db_mark_charge_expired", {"charge_id": event.payload.get("pagarme_charge_id")}),
            ]
        )

    # Fallback Seguro
    return BillingDecision(
        decision_type=DecisionType.NOOP_IDEMPOTENT,
        reason=f"Evento {event.event_type} não gerou mutações no snapshot atual.",
        actions=[]
    )
