from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_, desc, or_, text

from app.modules.financial.models import DREAccount, DREEntry, EmployeePayrollProfile, FinancialBill
from app.modules.financial.schemas import DREAccountCreate, DREAccountUpdate
from app.modules.employees.models import Employee
from app.modules.suppliers.models import Supplier
from app.modules.clients.models import Client
from app.modules.sales.models import Sale, SaleItem
from app.modules.products.models import Product
from app.modules.commissions.models import CommissionEntry


class FinancialRepository:
    def migrate_legacy_financial_accounts(self, db: Session, tenant_id: Optional[int] = None) -> None:
        """Migra contas legadas com group_type='financial_result' para financial_revenue ou financial_expense."""
        q = db.query(DREAccount).filter(DREAccount.group_type == "financial_result")
        if tenant_id:
            q = q.filter(DREAccount.tenant_id == tenant_id)
        legacy = q.all()
        if not legacy:
            return
        for acc in legacy:
            name_lower = (acc.name or "").lower()
            if "rendimento" in name_lower or "receita" in name_lower or "desconto" in name_lower:
                acc.group_type = "financial_revenue"
                if acc.code and acc.code.startswith("5."):
                    acc.code = "5.01"
            else:
                acc.group_type = "financial_expense"
                if acc.code and acc.code.startswith("5."):
                    acc.code = "6." + acc.code[2:]
        db.commit()

    def get_accounts(
        self, db: Session, tenant_id: int, active_only: bool = True
    ) -> List[DREAccount]:
        q = db.query(DREAccount).filter(DREAccount.tenant_id == tenant_id)
        if active_only:
            q = q.filter(DREAccount.is_active == True)
        accounts = q.order_by(DREAccount.order_index, DREAccount.id).all()

        # Migração pontual sob demanda apenas se houver conta antiga com group_type legada
        has_legacy = any(acc.group_type == "financial_result" for acc in accounts)
        if has_legacy:
            self.migrate_legacy_financial_accounts(db, tenant_id)
            return q.order_by(DREAccount.order_index, DREAccount.id).all()

        return accounts

    def get_account(
        self, db: Session, tenant_id: int, account_id: int
    ) -> Optional[DREAccount]:
        return (
            db.query(DREAccount)
            .filter(
                DREAccount.id == account_id,
                DREAccount.tenant_id == tenant_id,
            )
            .first()
        )

    def create_account(
        self, db: Session, tenant_id: int, data: DREAccountCreate
    ) -> DREAccount:
        # Determine highest order_index if not provided
        order_idx = data.order_index
        if order_idx == 0:
            max_order = (
                db.query(func.max(DREAccount.order_index))
                .filter(
                    DREAccount.tenant_id == tenant_id,
                    DREAccount.group_type == data.group_type,
                )
                .scalar()
            )
            order_idx = (max_order or 0) + 10

        acc = DREAccount(
            tenant_id=tenant_id,
            name=data.name.strip(),
            code=data.code.strip() if data.code else None,
            group_type=data.group_type,
            is_system=False,
            system_source=None,
            order_index=order_idx,
            is_active=data.is_active,
        )
        db.add(acc)
        db.commit()
        db.refresh(acc)
        return acc

    def update_account(
        self, db: Session, tenant_id: int, account_id: int, data: DREAccountUpdate
    ) -> Optional[DREAccount]:
        acc = self.get_account(db, tenant_id, account_id)
        if not acc:
            return None

        if data.name is not None:
            acc.name = data.name.strip()
        if data.code is not None:
            acc.code = data.code.strip() if data.code else None
        if data.group_type is not None:
            acc.group_type = data.group_type
        if data.order_index is not None:
            acc.order_index = data.order_index
        if data.is_active is not None:
            acc.is_active = data.is_active

        db.commit()
        db.refresh(acc)
        return acc

    def delete_account(
        self, db: Session, tenant_id: int, account_id: int
    ) -> bool:
        acc = self.get_account(db, tenant_id, account_id)
        if not acc or acc.is_system:
            # System accounts cannot be deleted, only deactivated if needed
            return False

        db.delete(acc)
        db.commit()
        return True

    def seed_default_accounts_if_needed(
        self, db: Session, tenant_id: int
    ) -> List[DREAccount]:
        accounts = self.get_accounts(db, tenant_id, active_only=False)
        if accounts:
            return accounts

        defaults = [
            # ── 1. RECEITA BRUTA ──────────────────────────────────────────
            {
                "name": "Vendas de Produtos",
                "code": "1.01",
                "group_type": "gross_revenue",
                "is_system": True,
                "system_source": "sales_products",
                "order_index": 10,
            },
            {
                "name": "Vendas de Serviços",
                "code": "1.02",
                "group_type": "gross_revenue",
                "is_system": True,
                "system_source": "sales_services",
                "order_index": 20,
            },
            {
                "name": "Comissões e Outras Receitas Operacionais",
                "code": "1.03",
                "group_type": "gross_revenue",
                "is_system": False,
                "system_source": None,
                "order_index": 30,
            },
            # ── 2. CUSTO DE MERCADORIA E SERVIÇO VENDIDO (CMV) ─────────────
            {
                "name": "Custo de Mercadorias Vendidas (CMV)",
                "code": "2.01",
                "group_type": "cmv",
                "is_system": True,
                "system_source": "cmv_products",
                "order_index": 10,
            },
            {
                "name": "Insumos Diretos de Serviços (Shampoos, Lâminas, etc.)",
                "code": "2.02",
                "group_type": "cmv",
                "is_system": False,
                "system_source": None,
                "order_index": 20,
            },
            # ── 3. DESPESAS FIXAS ─────────────────────────────────────────
            {
                "name": "Energia Elétrica",
                "code": "3.01",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 10,
            },
            {
                "name": "Água",
                "code": "3.02",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 20,
            },
            {
                "name": "Telefone e Internet",
                "code": "3.03",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 30,
            },
            {
                "name": "Contabilidade",
                "code": "3.04",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 40,
            },
            {
                "name": "Salários & Provisões (Salário Base + 13º + Férias)",
                "code": "3.05",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": "payroll_salaries",
                "order_index": 50,
            },
            {
                "name": "Encargos Trabalhistas (INSS + FGTS)",
                "code": "3.06",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": "payroll_charges",
                "order_index": 52,
            },
            {
                "name": "Benefícios a Funcionários (VT + VA + VR + Saúde + Outros)",
                "code": "3.07",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": "payroll_benefits",
                "order_index": 54,
            },
            {
                "name": "Aluguel e Condomínio",
                "code": "3.08",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 80,
            },
            {
                "name": "Serviço de Terceiros",
                "code": "3.09",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 90,
            },
            {
                "name": "Seguros de Veículos e Imóvel",
                "code": "3.10",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 100,
            },
            {
                "name": "Manutenção de Veículos",
                "code": "3.11",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 110,
            },
            {
                "name": "Sistemas e Softwares",
                "code": "3.12",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 120,
            },
            {
                "name": "Manutenção de Equipamentos (Sopradores/Secadores)",
                "code": "3.13",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 130,
            },
            {
                "name": "Treinamentos",
                "code": "3.14",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 140,
            },
            {
                "name": "Uniformes e EPIs",
                "code": "3.15",
                "group_type": "fixed_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 150,
            },
            # ── 4. DESPESAS VARIÁVEIS ─────────────────────────────────────
            {
                "name": "Comissões a Pagar",
                "code": "4.01",
                "group_type": "variable_expense",
                "is_system": True,
                "system_source": "commissions",
                "order_index": 10,
            },
            {
                "name": "Frete e Combustíveis (Leva e Traz)",
                "code": "4.02",
                "group_type": "variable_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 20,
            },
            {
                "name": "Publicidade, Anúncios e Site",
                "code": "4.03",
                "group_type": "variable_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 30,
            },
            {
                "name": "Documentação de Veículos e IPVA",
                "code": "4.04",
                "group_type": "variable_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 40,
            },
            {
                "name": "Alimentação e Viagens",
                "code": "4.05",
                "group_type": "variable_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 50,
            },
            {
                "name": "Pedágios",
                "code": "4.06",
                "group_type": "variable_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 60,
            },
            {
                "name": "Simples Nacional / Impostos",
                "code": "4.07",
                "group_type": "variable_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 70,
            },
            {
                "name": "Taxas de Cartão de Crédito e Débito",
                "code": "4.08",
                "group_type": "variable_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 80,
            },
            # ── 5. RECEITAS NÃO OPERACIONAIS / FINANCEIRAS ────────────────
            {
                "name": "Rendimentos de Aplicações Financeiras",
                "code": "5.01",
                "group_type": "financial_revenue",
                "is_system": False,
                "system_source": None,
                "order_index": 10,
            },
            {
                "name": "Descontos Obtidos e Outras Receitas Financeiras",
                "code": "5.02",
                "group_type": "financial_revenue",
                "is_system": False,
                "system_source": None,
                "order_index": 20,
            },
            # ── 6. DESPESAS NÃO OPERACIONAIS / FINANCEIRAS ────────────────
            {
                "name": "Despesas com Empréstimos e Financiamentos",
                "code": "6.01",
                "group_type": "financial_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 10,
            },
            {
                "name": "Tarifa de Cobrança e Bancárias",
                "code": "6.02",
                "group_type": "financial_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 20,
            },
            {
                "name": "IOF e Juros",
                "code": "6.03",
                "group_type": "financial_expense",
                "is_system": False,
                "system_source": None,
                "order_index": 30,
            },
        ]

        created_objs = []
        for d in defaults:
            obj = DREAccount(
                tenant_id=tenant_id,
                name=d["name"],
                code=d["code"],
                group_type=d["group_type"],
                is_system=d["is_system"],
                system_source=d["system_source"],
                order_index=d["order_index"],
                is_active=True,
            )
            db.add(obj)
            created_objs.append(obj)

        db.commit()
        return self.get_accounts(db, tenant_id, active_only=False)

    def get_entries_for_year(
        self, db: Session, tenant_id: int, year: int
    ) -> List[DREEntry]:
        return (
            db.query(DREEntry)
            .filter(
                DREEntry.tenant_id == tenant_id,
                DREEntry.competence_year == year,
            )
            .all()
        )

    def get_paid_bills_aggregated_by_category_and_month(
        self, db: Session, tenant_id: int, year: int
    ) -> Dict[int, Dict[int, float]]:
        """
        Agrega o valor total de contas pagas (status='paid') por category_id e mês do pagamento no ano informado.
        Regime de Caixa: data baseada no payment_date (ou due_date se payment_date for nulo).
        """
        effective_date = func.coalesce(FinancialBill.payment_date, FinancialBill.due_date)

        rows = (
            db.query(
                FinancialBill.category_id,
                extract("month", effective_date).label("month"),
                func.sum(
                    func.coalesce(
                        func.nullif(FinancialBill.paid_amount, 0),
                        FinancialBill.amount,
                    )
                ).label("total_amount"),
            )
            .filter(
                FinancialBill.tenant_id == tenant_id,
                FinancialBill.status == "paid",
                FinancialBill.category_id.isnot(None),
                extract("year", effective_date) == year,
            )
            .group_by(FinancialBill.category_id, extract("month", effective_date))
            .all()
        )

        result: Dict[int, Dict[int, float]] = {}
        for cat_id, month, total in rows:
            if cat_id not in result:
                result[cat_id] = {}
            result[cat_id][int(month)] = float(total or 0.0)
        return result

    def upsert_entry(
        self,
        db: Session,
        tenant_id: int,
        account_id: int,
        year: int,
        month: int,
        amount: float,
        notes: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> DREEntry:
        entry = (
            db.query(DREEntry)
            .filter(
                DREEntry.tenant_id == tenant_id,
                DREEntry.account_id == account_id,
                DREEntry.competence_year == year,
                DREEntry.competence_month == month,
            )
            .first()
        )

        if entry:
            entry.amount = amount
            if notes is not None:
                entry.notes = notes
            if user_id:
                entry.created_by_user_id = user_id
        else:
            entry = DREEntry(
                tenant_id=tenant_id,
                account_id=account_id,
                competence_year=year,
                competence_month=month,
                amount=amount,
                notes=notes,
                created_by_user_id=user_id,
            )
            db.add(entry)

        db.commit()
        db.refresh(entry)
        return entry

    def batch_upsert_entries(
        self,
        db: Session,
        tenant_id: int,
        entries: list,
        user_id: Optional[int] = None,
    ) -> List[DREEntry]:
        if not entries:
            return []

        years = list({e.competence_year for e in entries})
        account_ids = list({e.account_id for e in entries})

        # Carrega todos os registros existentes em UMA única query
        existing = (
            db.query(DREEntry)
            .filter(
                DREEntry.tenant_id == tenant_id,
                DREEntry.competence_year.in_(years),
                DREEntry.account_id.in_(account_ids),
            )
            .all()
        )

        existing_map = {
            (item.account_id, item.competence_year, item.competence_month): item
            for item in existing
        }

        saved_entries = []
        for e in entries:
            key = (e.account_id, e.competence_year, e.competence_month)
            if key in existing_map:
                entry = existing_map[key]
                entry.amount = e.amount
                if e.notes is not None:
                    entry.notes = e.notes
                if user_id:
                    entry.created_by_user_id = user_id
                saved_entries.append(entry)
            else:
                entry = DREEntry(
                    tenant_id=tenant_id,
                    account_id=e.account_id,
                    competence_year=e.competence_year,
                    competence_month=e.competence_month,
                    amount=e.amount,
                    notes=e.notes,
                    created_by_user_id=user_id,
                )
                db.add(entry)
                existing_map[key] = entry
                saved_entries.append(entry)

        # 1 único commit atômico para todos os registros
        db.flush()
        saved_ids = [s.id for s in saved_entries if s.id is not None]
        db.commit()

        if not saved_ids:
            return []

        return (
            db.query(DREEntry)
            .filter(DREEntry.id.in_(saved_ids))
            .all()
        )

    def replicate_entry(
        self,
        db: Session,
        tenant_id: int,
        account_id: int,
        year: int,
        start_month: int,
        end_month: int,
        amount: float,
        notes: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> List[DREEntry]:
        class _EntryItem:
            def __init__(self, acc_id, yr, mn, amt, nts):
                self.account_id = acc_id
                self.competence_year = yr
                self.competence_month = mn
                self.amount = amt
                self.notes = nts

        items = [
            _EntryItem(account_id, year, m, amount, notes)
            for m in range(start_month, end_month + 1)
        ]
        return self.batch_upsert_entries(db, tenant_id, items, user_id)

    # ── AGREGADORES AUTOMÁTICOS DO SISTEMA ─────────────────────────────────

    def get_sales_and_cmv_aggregated_by_month(
        self, db: Session, tenant_id: int, year: int
    ) -> Dict[str, Dict[int, float]]:
        """
        Retorna em uma única query otimizada:
        1. Vendas líquidas de produtos (deduzidos descontos rateados)
        2. Vendas líquidas de serviços (deduzidos descontos rateados)
        3. CMV dos produtos vendidos
        Utiliza range de datas exatas para ativar o índice ix_sales_tenant_created_at.
        """
        results = {
            "sales_products": {m: 0.0 for m in range(1, 13)},
            "sales_services": {m: 0.0 for m in range(1, 13)},
            "cmv_products": {m: 0.0 for m in range(1, 13)},
        }

        start_date = datetime(year, 1, 1, 0, 0, 0)
        end_date = datetime(year + 1, 1, 1, 0, 0, 0)

        # Query consolidada rateando o valor recebido e apurando CMV em 1 única passagem
        sql = text("""
            WITH sale_breakdown AS (
                SELECT 
                    s.id AS sale_id,
                    EXTRACT(month FROM s.created_at) AS month,
                    s.total_amount,
                    COALESCE(SUM(CASE WHEN si.item_type = 'product' THEN si.subtotal ELSE 0 END), 0) AS p_gross,
                    COALESCE(SUM(CASE WHEN si.item_type IN ('service', 'package') THEN si.subtotal ELSE 0 END), 0) AS s_gross,
                    COALESCE(SUM(CASE WHEN si.item_type = 'product' THEN si.quantity * COALESCE(p.cost, 0) ELSE 0 END), 0) AS p_cmv
                FROM sales s
                LEFT JOIN sale_items si ON si.sale_id = s.id AND COALESCE(si.status, 'active') != 'canceled'
                LEFT JOIN products p ON p.id = si.item_id AND si.item_type = 'product'
                WHERE s.tenant_id = :tenant_id
                  AND s.status = 'completed'
                  AND s.created_at >= :start_date
                  AND s.created_at < :end_date
                GROUP BY s.id, month, s.total_amount
            )
            SELECT 
                month,
                ROUND(CAST(SUM(
                    CASE 
                        WHEN (p_gross + s_gross) > 0 THEN total_amount * (p_gross / (p_gross + s_gross))
                        ELSE 0 
                    END
                ) AS numeric), 2) AS product_net,
                ROUND(CAST(SUM(
                    CASE 
                        WHEN (p_gross + s_gross) > 0 THEN total_amount * (s_gross / (p_gross + s_gross))
                        ELSE 0 
                    END
                ) AS numeric), 2) AS service_net,
                ROUND(CAST(SUM(p_cmv) AS numeric), 2) AS cmv
            FROM sale_breakdown
            GROUP BY month
            ORDER BY month;
        """)

        rows = db.execute(
            sql, {"tenant_id": tenant_id, "start_date": start_date, "end_date": end_date}
        ).fetchall()
        for r in rows:
            m = int(r.month)
            results["sales_products"][m] = float(r.product_net or 0.0)
            results["sales_services"][m] = float(r.service_net or 0.0)
            results["cmv_products"][m] = float(r.cmv or 0.0)

        return results

    def get_sales_aggregated_by_month(
        self, db: Session, tenant_id: int, year: int
    ) -> Dict[str, Dict[int, float]]:
        """Retorna vendas líquidas agregadas por mês (reaproveita a query unificada)."""
        data = self.get_sales_and_cmv_aggregated_by_month(db, tenant_id, year)
        return {
            "sales_products": data["sales_products"],
            "sales_services": data["sales_services"],
        }

    def get_cmv_aggregated_by_month(
        self, db: Session, tenant_id: int, year: int
    ) -> Dict[int, float]:
        """Calcula o CMV de produtos vendidos no ano (reaproveita a query unificada)."""
        data = self.get_sales_and_cmv_aggregated_by_month(db, tenant_id, year)
        return data["cmv_products"]

    def get_commissions_aggregated_by_month(
        self, db: Session, tenant_id: int, year: int
    ) -> Dict[int, float]:
        """
        Calcula as comissões apuradas no ano a partir do módulo de comissões,
        utilizando range de datas para index scan.
        """
        commissions_by_month = {m: 0.0 for m in range(1, 13)}
        start_date = datetime(year, 1, 1, 0, 0, 0)
        end_date = datetime(year + 1, 1, 1, 0, 0, 0)

        rows = (
            db.query(
                extract("month", CommissionEntry.created_at).label("month"),
                func.sum(CommissionEntry.commission_amount).label("total_commissions"),
            )
            .filter(
                CommissionEntry.tenant_id == tenant_id,
                CommissionEntry.status.in_(["pending", "paid"]),
                CommissionEntry.created_at >= start_date,
                CommissionEntry.created_at < end_date,
            )
            .group_by("month")
            .all()
        )

        for month_val, total in rows:
            m = int(month_val)
            commissions_by_month[m] = float(total or 0.0)

        return commissions_by_month

    def _ensure_payroll_accounts_tagged(self, db: Session, tenant_id: int):
        accounts = db.query(DREAccount).filter(DREAccount.tenant_id == tenant_id).all()

        sal_acc = None
        charges_acc = None
        fgts_acc = None
        ben_acc = None

        for acc in accounts:
            name_lower = (acc.name or "").lower()
            if acc.system_source == "payroll_salaries" or "salário" in name_lower or "folha de pagamento" in name_lower:
                if not sal_acc:
                    sal_acc = acc
            elif acc.system_source in ("payroll_charges", "payroll_inss") or "inss" in name_lower or "encargo" in name_lower:
                if not charges_acc:
                    charges_acc = acc
            elif acc.system_source == "payroll_fgts" or "fgts" in name_lower:
                fgts_acc = acc
            elif acc.system_source == "payroll_benefits" or "benefício" in name_lower:
                ben_acc = acc

        # Linha 1: Salários & Provisões (Salário Base + 13º + Férias)
        if sal_acc:
            sal_acc.name = "Salários & Provisões (Salário Base + 13º + Férias)"
            sal_acc.code = "3.05"
            sal_acc.order_index = 50
            sal_acc.system_source = "payroll_salaries"
            sal_acc.is_active = True

        # Linha 2: Encargos Trabalhistas (INSS + FGTS)
        if charges_acc:
            charges_acc.name = "Encargos Trabalhistas (INSS + FGTS)"
            charges_acc.code = "3.06"
            charges_acc.order_index = 52
            charges_acc.system_source = "payroll_charges"
            charges_acc.is_active = True
        else:
            charges_acc = DREAccount(
                tenant_id=tenant_id,
                name="Encargos Trabalhistas (INSS + FGTS)",
                code="3.06",
                group_type="fixed_expense",
                is_system=False,
                system_source="payroll_charges",
                order_index=52,
                is_active=True,
            )
            db.add(charges_acc)

        # Desativar conta isolada de FGTS para não duplicar no DRE
        if fgts_acc and fgts_acc.id != charges_acc.id:
            fgts_acc.is_active = False
            db.query(DREEntry).filter(
                DREEntry.tenant_id == tenant_id,
                DREEntry.account_id == fgts_acc.id
            ).delete()

        # Linha 3: Benefícios a Funcionários (VT + VA + VR + Saúde + Outros)
        if ben_acc:
            ben_acc.name = "Benefícios a Funcionários (VT + VA + VR + Saúde + Outros)"
            ben_acc.code = "3.07"
            ben_acc.order_index = 54
            ben_acc.system_source = "payroll_benefits"
            ben_acc.is_active = True
        else:
            ben_acc = DREAccount(
                tenant_id=tenant_id,
                name="Benefícios a Funcionários (VT + VA + VR + Saúde + Outros)",
                code="3.07",
                group_type="fixed_expense",
                is_system=False,
                system_source="payroll_benefits",
                order_index=54,
                is_active=True,
            )
            db.add(ben_acc)

        db.commit()

    def get_payroll_profiles(self, db: Session, tenant_id: int) -> List[Dict[str, Any]]:
        self._ensure_payroll_accounts_tagged(db, tenant_id)

        employees = (
            db.query(Employee)
            .filter(Employee.tenant_id == tenant_id, Employee.is_active == True)
            .order_by(Employee.name.asc())
            .all()
        )
        profiles = (
            db.query(EmployeePayrollProfile)
            .filter(EmployeePayrollProfile.tenant_id == tenant_id)
            .all()
        )
        profile_map = {p.employee_id: p for p in profiles}

        result = []
        for emp in employees:
            p = profile_map.get(emp.id)
            base_salary = float(p.base_salary) if p else 0.0
            thirteenth = float(p.thirteenth_salary) if p else 0.0
            vacation = float(p.vacation_provision) if p else 0.0
            fgts = float(p.fgts_amount) if p else 0.0
            inss = float(p.inss_amount) if p else 0.0
            vt = float(p.transport_voucher) if p else 0.0
            va = float(p.food_voucher) if p else 0.0
            vr = float(p.meal_voucher) if p else 0.0
            health = float(p.health_insurance) if p else 0.0
            other = float(p.other_benefits) if p else 0.0

            custom_sum = 0.0
            if p and p.custom_benefits and isinstance(p.custom_benefits, list):
                custom_sum = round(
                    sum(
                        float(item.get("amount", 0.0) or 0.0)
                        for item in p.custom_benefits
                        if isinstance(item, dict)
                    ),
                    2,
                )

            salaries_and_provisions = round(base_salary + thirteenth + vacation, 2)
            total_benefits = round(vt + va + vr + health + other + custom_sum, 2)
            total_monthly = round(salaries_and_provisions + fgts + inss + total_benefits, 2)
            overhead_pct = (
                round(((total_monthly - base_salary) / base_salary) * 100.0, 2)
                if base_salary > 0
                else 0.0
            )

            ROLE_TRANSLATIONS = {
                "groomer": "Tosador(a)",
                "bather": "Banhista",
                "vet": "Veterinário(a)",
                "salesperson": "Vendedor(a)",
                "receptionist": "Recepcionista",
                "driver": "Motorista / Entregador",
                "other": "Outro",
                "manager": "Gerente",
                "admin": "Administrador",
            }
            role_raw = emp.role.value if hasattr(emp.role, "value") else str(emp.role)
            role_str = ROLE_TRANSLATIONS.get(role_raw.lower(), role_raw)

            result.append({
                "id": p.id if p else None,
                "employee_id": emp.id,
                "employee_name": emp.name,
                "employee_role": role_str,
                "employee_is_active": emp.is_active,
                "base_salary": base_salary,
                "thirteenth_salary": thirteenth,
                "vacation_provision": vacation,
                "fgts_amount": fgts,
                "inss_amount": inss,
                "transport_voucher": vt,
                "food_voucher": va,
                "meal_voucher": vr,
                "health_insurance": health,
                "other_benefits": other,
                "other_benefits_description": p.other_benefits_description if p else None,
                "custom_benefits": p.custom_benefits if p else None,
                "notes": p.notes if p else None,
                "admission_date": (p.admission_date if p and p.admission_date else emp.admission_date),
                "resignation_date": (p.resignation_date if p and p.resignation_date else emp.resignation_date),
                "is_active": p.is_active if p else True,
                "total_salaries_and_provisions": salaries_and_provisions,
                "total_inss": round(inss, 2),
                "total_fgts": round(fgts, 2),
                "total_benefits": total_benefits,
                "total_monthly_cost": total_monthly,
                "overhead_percentage": overhead_pct,
            })
        return result

    def upsert_payroll_profile(
        self, db: Session, tenant_id: int, employee_id: int, data: Dict[str, Any]
    ) -> EmployeePayrollProfile:
        profile = (
            db.query(EmployeePayrollProfile)
            .filter(
                EmployeePayrollProfile.tenant_id == tenant_id,
                EmployeePayrollProfile.employee_id == employee_id,
            )
            .first()
        )
        if not profile:
            profile = EmployeePayrollProfile(
                tenant_id=tenant_id,
                employee_id=employee_id,
            )
            db.add(profile)

        for key, value in data.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        # Sync to Employee
        emp = db.query(Employee).filter(Employee.id == employee_id, Employee.tenant_id == tenant_id).first()
        if emp:
            if "admission_date" in data:
                emp.admission_date = data["admission_date"]
            if "resignation_date" in data:
                emp.resignation_date = data["resignation_date"]

        db.commit()
        db.refresh(profile)
        return profile

    def sync_payroll_to_dre(
        self,
        db: Session,
        tenant_id: int,
        year: int,
        months: List[int],
        account_mapping: Optional[Dict[str, int]] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        import calendar

        profiles_data = self.get_payroll_profiles(db, tenant_id)
        active_profiles = [p for p in profiles_data if p["is_active"] and p["employee_is_active"]]

        if not active_profiles:
            raise ValueError(
                "Nenhum colaborador ativo com salário cadastrado foi encontrado para sincronizar com o DRE."
            )

        accounts = self.get_accounts(db, tenant_id, active_only=True)
        acc_by_source = {acc.system_source: acc for acc in accounts if acc.system_source}

        def resolve_acc(key: str, default_source: str, search_name: str) -> Optional[DREAccount]:
            if account_mapping and account_mapping.get(key):
                acc = db.query(DREAccount).filter(
                    DREAccount.id == account_mapping[key],
                    DREAccount.tenant_id == tenant_id
                ).first()
                if acc:
                    return acc
            if default_source in acc_by_source:
                return acc_by_source[default_source]
            for acc in accounts:
                if search_name.lower() in (acc.name or "").lower():
                    return acc
            return None

        salaries_acc = resolve_acc("salaries", "payroll_salaries", "salário")
        charges_acc = (
            resolve_acc("charges", "payroll_charges", "encargo")
            or resolve_acc("inss", "payroll_charges", "encargo")
            or resolve_acc("charges", "payroll_inss", "inss")
        )
        benefits_acc = resolve_acc("benefits", "payroll_benefits", "benefício")

        if not salaries_acc and not charges_acc and not benefits_acc:
            raise ValueError("Nenhuma conta de folha de pagamento foi encontrada no DRE.")

        entries_count = 0
        tot_synced_salaries = 0.0
        tot_synced_charges = 0.0
        tot_synced_benefits = 0.0

        for m in months:
            _, total_days_in_month = calendar.monthrange(year, m)
            first_day_of_month = date(year, m, 1)
            last_day_of_month = date(year, m, total_days_in_month)

            month_salaries = 0.0
            month_charges = 0.0
            month_benefits = 0.0

            for p in active_profiles:
                adm: Optional[date] = p.get("admission_date")
                res: Optional[date] = p.get("resignation_date")

                # Se a data de admissão for após este mês, 0 dias trabalhados
                if adm and adm > last_day_of_month:
                    continue

                # Se a data de saída/desligamento for antes deste mês, 0 dias trabalhados
                if res and res < first_day_of_month:
                    continue

                # Determina o período efetivo trabalhado dentro deste mês
                eff_start = max(first_day_of_month, adm) if adm else first_day_of_month
                eff_end = min(last_day_of_month, res) if res else last_day_of_month

                if eff_start > eff_end:
                    continue

                worked_days = (eff_end - eff_start).days + 1
                ratio = max(0.0, min(1.0, worked_days / total_days_in_month))

                p_salaries = p.get("total_salaries_and_provisions", 0.0) or 0.0
                p_charges = (p.get("total_inss", 0.0) or 0.0) + (p.get("total_fgts", 0.0) or 0.0)
                p_benefits = p.get("total_benefits", 0.0) or 0.0

                month_salaries += round(p_salaries * ratio, 2)
                month_charges += round(p_charges * ratio, 2)
                month_benefits += round(p_benefits * ratio, 2)

            month_salaries = round(month_salaries, 2)
            month_charges = round(month_charges, 2)
            month_benefits = round(month_benefits, 2)

            tot_synced_salaries += month_salaries
            tot_synced_charges += month_charges
            tot_synced_benefits += month_benefits

            items_to_sync = []
            if salaries_acc:
                items_to_sync.append((salaries_acc.id, month_salaries, "Salários & Provisões (Salário Base + 13º + Férias)"))
            if charges_acc:
                items_to_sync.append((charges_acc.id, month_charges, "Encargos Trabalhistas (INSS + FGTS)"))
            if benefits_acc:
                items_to_sync.append((benefits_acc.id, month_benefits, "Benefícios a Funcionários (VT + VA + VR + Saúde + Outros)"))

            for acc_id, amount, note in items_to_sync:
                entry = (
                    db.query(DREEntry)
                    .filter(
                        DREEntry.tenant_id == tenant_id,
                        DREEntry.account_id == acc_id,
                        DREEntry.competence_year == year,
                        DREEntry.competence_month == m,
                    )
                    .first()
                )
                if not entry:
                    entry = DREEntry(
                        tenant_id=tenant_id,
                        account_id=acc_id,
                        competence_year=year,
                        competence_month=m,
                        amount=Decimal(str(amount)),
                        notes=note,
                        created_by_user_id=user_id,
                    )
                    db.add(entry)
                else:
                    entry.amount = Decimal(str(amount))
                    entry.notes = note
                    entry.created_by_user_id = user_id
                entries_count += 1

        db.commit()

        avg_salaries = round(tot_synced_salaries / len(months), 2) if months else 0.0
        avg_charges = round(tot_synced_charges / len(months), 2) if months else 0.0
        avg_benefits = round(tot_synced_benefits / len(months), 2) if months else 0.0

        return {
            "success": True,
            "message": f"Folha de pagamento lançada com sucesso no DRE de {year} para {len(months)} meses com cálculo proporcional de vigência.",
            "year": year,
            "months_updated": months,
            "entries_created_or_updated": entries_count,
            "accounts_used": {
                "salaries": {"account_id": salaries_acc.id, "name": salaries_acc.name, "amount": avg_salaries} if salaries_acc else None,
                "charges": {"account_id": charges_acc.id, "name": charges_acc.name, "amount": avg_charges} if charges_acc else None,
                "benefits": {"account_id": benefits_acc.id, "name": benefits_acc.name, "amount": avg_benefits} if benefits_acc else None,
            },
        }

