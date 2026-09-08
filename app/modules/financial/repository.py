from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, extract, and_, desc, or_, text

from app.modules.financial.models import DREAccount, DREEntry, EmployeePayrollProfile
from app.modules.financial.schemas import DREAccountCreate, DREAccountUpdate
from app.modules.employees.models import Employee
from app.modules.sales.models import Sale, SaleItem
from app.modules.products.models import Product
from app.modules.commissions.models import CommissionEntry


class FinancialRepository:
    def get_accounts(
        self, db: Session, tenant_id: int, active_only: bool = True
    ) -> List[DREAccount]:
        q = db.query(DREAccount).filter(DREAccount.tenant_id == tenant_id)
        if active_only:
            q = q.filter(DREAccount.is_active == True)
        return q.order_by(DREAccount.order_index, DREAccount.id).all()

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
        count = (
            db.query(func.count(DREAccount.id))
            .filter(DREAccount.tenant_id == tenant_id)
            .scalar()
        )
        if count and count > 0:
            self._ensure_payroll_accounts_tagged(db, tenant_id)
            return self.get_accounts(db, tenant_id, active_only=False)

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
            # ── 5. RESULTADOS NÃO OPERACIONAIS / FINANCEIROS ───────────────
            {
                "name": "Despesas com Empréstimos e Financiamentos",
                "code": "5.01",
                "group_type": "financial_result",
                "is_system": False,
                "system_source": None,
                "order_index": 10,
            },
            {
                "name": "Tarifa de Cobrança e Bancárias",
                "code": "5.02",
                "group_type": "financial_result",
                "is_system": False,
                "system_source": None,
                "order_index": 20,
            },
            {
                "name": "IOF e Juros",
                "code": "5.03",
                "group_type": "financial_result",
                "is_system": False,
                "system_source": None,
                "order_index": 30,
            },
            {
                "name": "Rendimentos de Aplicações Financeiras",
                "code": "5.04",
                "group_type": "financial_result",
                "is_system": False,
                "system_source": None,
                "order_index": 40,
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

    def get_sales_aggregated_by_month(
        self, db: Session, tenant_id: int, year: int
    ) -> Dict[str, Dict[int, float]]:
        """
        Retorna as vendas líquidas reais de produtos e serviços agrupadas por mês (1-12),
        já deduzidos proporcionalmente os descontos concedidos em cada venda.
        """
        results = {
            "sales_products": {m: 0.0 for m in range(1, 13)},
            "sales_services": {m: 0.0 for m in range(1, 13)},
        }

        # Query consolidada rateando o valor efetivamente recebido (total_amount) entre produtos e serviços
        sql = text("""
            WITH sale_breakdown AS (
                SELECT 
                    s.id AS sale_id,
                    EXTRACT(month FROM s.created_at) AS month,
                    s.total_amount,
                    COALESCE(SUM(CASE WHEN si.item_type = 'product' THEN si.subtotal ELSE 0 END), 0) AS p_gross,
                    COALESCE(SUM(CASE WHEN si.item_type IN ('service', 'package') THEN si.subtotal ELSE 0 END), 0) AS s_gross
                FROM sales s
                LEFT JOIN sale_items si ON si.sale_id = s.id
                WHERE s.tenant_id = :tenant_id
                  AND s.status = 'completed'
                  AND EXTRACT(year FROM s.created_at) = :year
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
                ) AS numeric), 2) AS service_net
            FROM sale_breakdown
            GROUP BY month
            ORDER BY month;
        """)

        rows = db.execute(sql, {"tenant_id": tenant_id, "year": year}).fetchall()
        for r in rows:
            m = int(r.month)
            results["sales_products"][m] = float(r.product_net or 0.0)
            results["sales_services"][m] = float(r.service_net or 0.0)

        return results

    def get_cmv_aggregated_by_month(
        self, db: Session, tenant_id: int, year: int
    ) -> Dict[int, float]:
        """
        Calcula o CMV de produtos vendidos no ano:
        Soma(sale_items.quantity * coalesce(products.cost, 0)) agrupado por mês.
        """
        cmv_by_month = {m: 0.0 for m in range(1, 13)}

        rows = (
            db.query(
                extract("month", Sale.created_at).label("month"),
                func.sum(SaleItem.quantity * func.coalesce(Product.cost, 0)).label("total_cost"),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(Product, Product.id == SaleItem.item_id)
            .filter(
                Sale.tenant_id == tenant_id,
                Sale.status == "completed",
                SaleItem.item_type == "product",
                extract("year", Sale.created_at) == year,
            )
            .group_by("month")
            .all()
        )

        for month_val, total in rows:
            m = int(month_val)
            cmv_by_month[m] = float(total or 0.0)

        return cmv_by_month

    def get_commissions_aggregated_by_month(
        self, db: Session, tenant_id: int, year: int
    ) -> Dict[int, float]:
        """
        Calcula as comissões apuradas no ano a partir do módulo de comissões.
        """
        commissions_by_month = {m: 0.0 for m in range(1, 13)}

        rows = (
            db.query(
                extract("month", CommissionEntry.created_at).label("month"),
                func.sum(CommissionEntry.commission_amount).label("total_commissions"),
            )
            .filter(
                CommissionEntry.tenant_id == tenant_id,
                CommissionEntry.status.in_(["pending", "paid"]),
                extract("year", CommissionEntry.created_at) == year,
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
            if hasattr(profile, key) and value is not None:
                setattr(profile, key, value)

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
        profiles_data = self.get_payroll_profiles(db, tenant_id)
        active_profiles = [p for p in profiles_data if p["is_active"] and p["employee_is_active"]]

        tot_salaries = round(sum(p["total_salaries_and_provisions"] for p in active_profiles), 2)
        tot_charges = round(sum(p["total_inss"] + p["total_fgts"] for p in active_profiles), 2)
        tot_benefits = round(sum(p["total_benefits"] for p in active_profiles), 2)

        if tot_salaries <= 0 and tot_charges <= 0 and tot_benefits <= 0:
            raise ValueError(
                "Nenhum valor de salário ou benefício foi encontrado para lançar no DRE. "
                "Informe e salve o salário de pelo menos um colaborador antes de sincronizar."
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

        items_to_sync = []
        if salaries_acc:
            items_to_sync.append((salaries_acc.id, tot_salaries, "Salários & Provisões (Salário Base + 13º + Férias)"))
        if charges_acc:
            items_to_sync.append((charges_acc.id, tot_charges, "Encargos Trabalhistas (INSS + FGTS)"))
        if benefits_acc:
            items_to_sync.append((benefits_acc.id, tot_benefits, "Benefícios a Funcionários (VT + VA + VR + Saúde + Outros)"))

        entries_count = 0
        for acc_id, amount, note in items_to_sync:
            for m in months:
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

        return {
            "success": True,
            "message": f"Folha de pagamento lançada com sucesso no DRE de {year} para {len(months)} meses.",
            "year": year,
            "months_updated": months,
            "entries_created_or_updated": entries_count,
            "accounts_used": {
                "salaries": {"account_id": salaries_acc.id, "name": salaries_acc.name, "amount": tot_salaries} if salaries_acc else None,
                "charges": {"account_id": charges_acc.id, "name": charges_acc.name, "amount": tot_charges} if charges_acc else None,
                "benefits": {"account_id": benefits_acc.id, "name": benefits_acc.name, "amount": tot_benefits} if benefits_acc else None,
            },
        }

