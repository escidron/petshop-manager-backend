import io
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.modules.financial.models import DREAccount, DREEntry
from app.modules.financial.schemas import (
    DREAccountCreate,
    DREAccountUpdate,
    DREAccountResponse,
    DREEntryUpsert,
    DREEntryReplicate,
    DRERowData,
    DREGroupData,
    DRESummary,
    DREReportResponse,
)
from app.modules.financial.repository import FinancialRepository
from app.modules.financial.operational_result_repository import OperationalResultRepository
from app.modules.financial.operational_result_schemas import OperationalResultResponse
from app.modules.financial.payroll_schemas import (
    PayrollProfileResponse,
    PayrollProfileUpdate,
    PayrollSummaryResponse,
    PayrollSyncToDRERequest,
    PayrollSyncResponse,
)


class FinancialService:
    def __init__(self):
        self.repo = FinancialRepository()
        self.operational_repo = OperationalResultRepository()

    def get_dre_report(self, db: Session, tenant_id: int, year: int) -> DREReportResponse:
        # 1. Garante que as contas padrão existam
        accounts = self.repo.seed_default_accounts_if_needed(db, tenant_id)

        # 2. Busca dados automáticos do sistema
        sales_data = self.repo.get_sales_aggregated_by_month(db, tenant_id, year)
        cmv_data = self.repo.get_cmv_aggregated_by_month(db, tenant_id, year)
        commissions_data = self.repo.get_commissions_aggregated_by_month(db, tenant_id, year)

        # 3. Busca lançamentos manuais
        manual_entries = self.repo.get_entries_for_year(db, tenant_id, year)
        entries_map: Dict[int, Dict[int, float]] = {}
        for e in manual_entries:
            if e.account_id not in entries_map:
                entries_map[e.account_id] = {}
            entries_map[e.account_id][e.competence_month] = float(e.amount or 0.0)

        # 4. Agrupa contas por grupo
        groups_config = [
            ("gross_revenue", "(+) RECEITA BRUTA DE VENDAS", "TOTAL RECEITA BRUTA"),
            ("cmv", "(-) CUSTO MERCADORIA E SERVIÇO VENDIDO (CMV / CSP)", "TOTAL CMV / CSP"),
            ("fixed_expense", "(-) DESPESAS OPERACIONAIS FIXAS", "TOTAL DESPESAS FIXAS"),
            ("variable_expense", "(-) DESPESAS OPERACIONAIS VARIÁVEIS", "TOTAL DESPESAS VARIÁVEIS"),
            ("financial_result", "(+/-) RESULTADOS NÃO OPERACIONAIS / FINANCEIROS", "TOTAL RESULTADO FINANCEIRO"),
        ]

        accounts_by_group: Dict[str, List[DREAccount]] = {g[0]: [] for g in groups_config}
        for acc in accounts:
            if acc.is_active and acc.group_type in accounts_by_group:
                accounts_by_group[acc.group_type].append(acc)

        # 5. Constrói linhas de cada conta
        group_rows_map: Dict[str, List[DRERowData]] = {g[0]: [] for g in groups_config}
        group_monthly_totals: Dict[str, Dict[int, float]] = {
            g[0]: {m: 0.0 for m in range(1, 13)} for g in groups_config
        }

        for group_type, title, subtotal_name in groups_config:
            for acc in accounts_by_group[group_type]:
                monthly_amounts: Dict[int, float] = {}

                for m in range(1, 13):
                    # Se tiver lançamento manual explícito, tem prioridade
                    if acc.id in entries_map and m in entries_map[acc.id]:
                        val = entries_map[acc.id][m]
                    elif acc.is_system and acc.system_source:
                        if acc.system_source == "sales_products":
                            val = sales_data["sales_products"].get(m, 0.0)
                        elif acc.system_source == "sales_services":
                            val = sales_data["sales_services"].get(m, 0.0)
                        elif acc.system_source == "cmv_products":
                            val = cmv_data.get(m, 0.0)
                        elif acc.system_source == "commissions":
                            val = commissions_data.get(m, 0.0)
                        else:
                            val = 0.0
                    else:
                        val = 0.0

                    monthly_amounts[m] = round(val, 2)
                    group_monthly_totals[group_type][m] += val

                total_amount = round(sum(monthly_amounts.values()), 2)
                monthly_avg = round(total_amount / 12.0, 2)

                is_payroll = bool(acc.system_source and acc.system_source.startswith("payroll_"))
                is_editable = not acc.is_system and not is_payroll

                row = DRERowData(
                    id=f"acc-{acc.id}",
                    account_id=acc.id,
                    name=acc.name,
                    code=acc.code,
                    group_type=group_type,
                    is_system=acc.is_system,
                    system_source=acc.system_source,
                    is_header=False,
                    is_subtotal=False,
                    is_result=False,
                    is_percentage_row=False,
                    is_editable=is_editable,
                    display_order=acc.order_index,
                    monthly_amounts=monthly_amounts,
                    monthly_percentages={},  # preenchido no passo da análise vertical
                    total_amount=total_amount,
                    total_percentage=0.0,
                    monthly_average=monthly_avg,
                )
                group_rows_map[group_type].append(row)

        # 6. Totais e Cálculos Gerenciais
        gross_rev_m = group_monthly_totals["gross_revenue"]
        cmv_m = group_monthly_totals["cmv"]
        fixed_exp_m = group_monthly_totals["fixed_expense"]
        var_exp_m = group_monthly_totals["variable_expense"]
        fin_res_m = group_monthly_totals["financial_result"]

        gross_margin_m = {m: round(gross_rev_m[m] - cmv_m[m], 2) for m in range(1, 13)}
        ebitda_m = {
            m: round(gross_margin_m[m] - fixed_exp_m[m] - var_exp_m[m], 2)
            for m in range(1, 13)
        }
        net_profit_m = {
            m: round(ebitda_m[m] + fin_res_m[m], 2) for m in range(1, 13)
        }

        gross_rev_tot = round(sum(gross_rev_m.values()), 2)
        cmv_tot = round(sum(cmv_m.values()), 2)
        gross_margin_tot = round(gross_rev_tot - cmv_tot, 2)
        fixed_exp_tot = round(sum(fixed_exp_m.values()), 2)
        var_exp_tot = round(sum(var_exp_m.values()), 2)
        ebitda_tot = round(gross_margin_tot - fixed_exp_tot - var_exp_tot, 2)
        fin_res_tot = round(sum(fin_res_m.values()), 2)
        net_profit_tot = round(ebitda_tot + fin_res_tot, 2)

        # 7. Preenche a Análise Vertical (% da receita bruta do mês e do ano)
        def calc_pct(val: float, base: float) -> float:
            if base and abs(base) > 0.001:
                return round((val / base) * 100.0, 2)
            return 0.0

        for group_type in group_rows_map:
            for row in group_rows_map[group_type]:
                row.monthly_percentages = {
                    m: calc_pct(row.monthly_amounts[m], gross_rev_m[m]) for m in range(1, 13)
                }
                row.total_percentage = calc_pct(row.total_amount, gross_rev_tot)

        # 8. Monta as linhas de subtotais e blocos
        all_rows: List[DRERowData] = []
        groups_list: List[DREGroupData] = []

        for group_type, title, subtotal_name in groups_config:
            subtotal_monthly = {
                m: round(group_monthly_totals[group_type][m], 2) for m in range(1, 13)
            }
            subtotal_tot = round(sum(subtotal_monthly.values()), 2)
            subtotal_avg = round(subtotal_tot / 12.0, 2)
            subtotal_pcts = {
                m: calc_pct(subtotal_monthly[m], gross_rev_m[m]) for m in range(1, 13)
            }
            subtotal_tot_pct = calc_pct(subtotal_tot, gross_rev_tot)

            sub_row = DRERowData(
                id=f"subtotal-{group_type}",
                account_id=None,
                name=title,
                code=None,
                group_type=group_type,
                is_system=True,
                is_header=False,
                is_subtotal=True,
                is_result=False,
                is_percentage_row=False,
                is_editable=False,
                display_order=0,
                monthly_amounts=subtotal_monthly,
                monthly_percentages=subtotal_pcts,
                total_amount=subtotal_tot,
                total_percentage=subtotal_tot_pct,
                monthly_average=subtotal_avg,
            )

            group_obj = DREGroupData(
                group_type=group_type,
                title=title,
                subtotal_name=subtotal_name,
                rows=group_rows_map[group_type],
                subtotal_row=sub_row,
            )
            groups_list.append(group_obj)

            # Insere no all_rows ordenado
            all_rows.append(sub_row)
            all_rows.extend(group_rows_map[group_type])

            # Linhas intermediárias calculadas:
            if group_type == "cmv":
                # (=) RECEITA LÍQUIDA / MARGEM BRUTA
                margin_sub_row = DRERowData(
                    id="result-gross-margin",
                    account_id=None,
                    name="(=) RECEITA LÍQUIDA / MARGEM BRUTA",
                    code=None,
                    group_type="cmv",
                    is_system=True,
                    is_header=False,
                    is_subtotal=True,
                    is_result=True,
                    is_percentage_row=False,
                    is_editable=False,
                    display_order=999,
                    monthly_amounts=gross_margin_m,
                    monthly_percentages={
                        m: calc_pct(gross_margin_m[m], gross_rev_m[m]) for m in range(1, 13)
                    },
                    total_amount=gross_margin_tot,
                    total_percentage=calc_pct(gross_margin_tot, gross_rev_tot),
                    monthly_average=round(gross_margin_tot / 12.0, 2),
                )
                all_rows.append(margin_sub_row)

            elif group_type == "variable_expense":
                # (=) RESULTADO OPERACIONAL (EBITDA / LAJIDA)
                ebitda_sub_row = DRERowData(
                    id="result-ebitda",
                    account_id=None,
                    name="(=) RESULTADO OPERACIONAL (EBITDA)",
                    code=None,
                    group_type="variable_expense",
                    is_system=True,
                    is_header=False,
                    is_subtotal=True,
                    is_result=True,
                    is_percentage_row=False,
                    is_editable=False,
                    display_order=999,
                    monthly_amounts=ebitda_m,
                    monthly_percentages={
                        m: calc_pct(ebitda_m[m], gross_rev_m[m]) for m in range(1, 13)
                    },
                    total_amount=ebitda_tot,
                    total_percentage=calc_pct(ebitda_tot, gross_rev_tot),
                    monthly_average=round(ebitda_tot / 12.0, 2),
                )
                all_rows.append(ebitda_sub_row)

        # 9. Linha Final de Resultado e Percentual
        net_profit_row = DRERowData(
            id="result-net-profit",
            account_id=None,
            name="(=) RESULTADO LÍQUIDO DO EXERCÍCIO (LUCRO/PREJUÍZO)",
            code=None,
            group_type="result",
            is_system=True,
            is_header=False,
            is_subtotal=True,
            is_result=True,
            is_percentage_row=False,
            is_editable=False,
            display_order=9999,
            monthly_amounts=net_profit_m,
            monthly_percentages={
                m: calc_pct(net_profit_m[m], gross_rev_m[m]) for m in range(1, 13)
            },
            total_amount=net_profit_tot,
            total_percentage=calc_pct(net_profit_tot, gross_rev_tot),
            monthly_average=round(net_profit_tot / 12.0, 2),
        )
        all_rows.append(net_profit_row)

        # Linha Percentual do Resultado
        pct_monthly = {
            m: calc_pct(net_profit_m[m], gross_rev_m[m]) for m in range(1, 13)
        }
        net_profit_pct_row = DRERowData(
            id="result-net-profit-pct",
            account_id=None,
            name="RESULTADO EM % (MARGEM LÍQUIDA)",
            code=None,
            group_type="result",
            is_system=True,
            is_header=False,
            is_subtotal=True,
            is_result=True,
            is_percentage_row=True,
            is_editable=False,
            display_order=10000,
            monthly_amounts=pct_monthly,
            monthly_percentages=pct_monthly,
            total_amount=calc_pct(net_profit_tot, gross_rev_tot),
            total_percentage=calc_pct(net_profit_tot, gross_rev_tot),
            monthly_average=calc_pct(net_profit_tot, gross_rev_tot),
        )
        all_rows.append(net_profit_pct_row)

        summary = DRESummary(
            gross_revenue_total=gross_rev_tot,
            cmv_total=cmv_tot,
            gross_margin_total=gross_margin_tot,
            gross_margin_pct=calc_pct(gross_margin_tot, gross_rev_tot),
            fixed_expenses_total=fixed_exp_tot,
            variable_expenses_total=var_exp_tot,
            ebitda_total=ebitda_tot,
            ebitda_pct=calc_pct(ebitda_tot, gross_rev_tot),
            financial_result_total=fin_res_tot,
            net_profit_total=net_profit_tot,
            net_margin_pct=calc_pct(net_profit_tot, gross_rev_tot),
        )

        return DREReportResponse(
            year=year,
            months=list(range(1, 13)),
            groups=groups_list,
            all_rows=all_rows,
            summary=summary,
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
        acc = db.query(DREAccount).filter(DREAccount.id == account_id, DREAccount.tenant_id == tenant_id).first()
        if acc and acc.system_source and acc.system_source.startswith("payroll_"):
            raise ValueError(
                "Esta conta é calculada automaticamente pela Folha de Pagamento. "
                "Para alterar os valores, utilize o módulo de Gestão da Folha."
            )
        return self.repo.upsert_entry(
            db, tenant_id, account_id, year, month, amount, notes, user_id
        )

    def batch_upsert_entries(
        self,
        db: Session,
        tenant_id: int,
        entries: List[DREEntryUpsert],
        user_id: Optional[int] = None,
    ) -> List[DREEntry]:
        payroll_acc_ids = {
            a.id for a in db.query(DREAccount.id).filter(
                DREAccount.tenant_id == tenant_id,
                DREAccount.system_source.like("payroll_%")
            ).all()
        }
        safe_entries = [e for e in entries if e.account_id not in payroll_acc_ids]
        if not safe_entries and entries:
            raise ValueError(
                "As contas de Folha de Pagamento são gerenciadas automaticamente. "
                "Utilize a Gestão da Folha para atualizá-las."
            )
        return self.repo.batch_upsert_entries(
            db=db,
            tenant_id=tenant_id,
            entries=safe_entries,
            user_id=user_id,
        )

    def replicate_entry(
        self,
        db: Session,
        tenant_id: int,
        data: DREEntryReplicate,
        user_id: Optional[int] = None,
    ) -> List[DREEntry]:
        acc = db.query(DREAccount).filter(DREAccount.id == data.account_id, DREAccount.tenant_id == tenant_id).first()
        if acc and acc.system_source and acc.system_source.startswith("payroll_"):
            raise ValueError(
                "Esta conta é calculada automaticamente pela Folha de Pagamento. "
                "Para alterar os valores, utilize o módulo de Gestão da Folha."
            )
        return self.repo.replicate_entry(
            db,
            tenant_id=tenant_id,
            account_id=data.account_id,
            year=data.competence_year,
            start_month=data.start_month,
            end_month=data.end_month,
            amount=data.amount,
            notes=data.notes,
            user_id=user_id,
        )

    def list_accounts(self, db: Session, tenant_id: int) -> List[DREAccount]:
        return self.repo.get_accounts(db, tenant_id, active_only=False)

    def create_account(
        self, db: Session, tenant_id: int, data: DREAccountCreate
    ) -> DREAccount:
        return self.repo.create_account(db, tenant_id, data)

    def update_account(
        self, db: Session, tenant_id: int, account_id: int, data: DREAccountUpdate
    ) -> Optional[DREAccount]:
        return self.repo.update_account(db, tenant_id, account_id, data)

    def delete_account(self, db: Session, tenant_id: int, account_id: int) -> bool:
        acc = db.query(DREAccount).filter(DREAccount.id == account_id, DREAccount.tenant_id == tenant_id).first()
        if acc and (acc.is_system or (acc.system_source and acc.system_source.startswith("payroll_"))):
            raise ValueError("Contas do sistema e vinculadas à Folha de Pagamento não podem ser excluídas.")
        return self.repo.delete_account(db, tenant_id, account_id)

    # ── EXPORTAÇÃO EXCEL (.XLSX) PROFISSIONAL ──────────────────────────────

    def export_dre_excel(self, db: Session, tenant_id: int, year: int) -> io.BytesIO:
        report = self.get_dre_report(db, tenant_id, year)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"DRE {year}"

        # Paleta de estilos inspirada na planilha do cliente
        header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

        subtotal_fill = PatternFill(start_color="F59E0B", end_color="F59E0B", fill_type="solid")  # Dourado âmbar
        subtotal_font = Font(name="Calibri", size=11, bold=True, color="000000")

        result_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")  # Âmbar suave
        result_font = Font(name="Calibri", size=11, bold=True, color="92400E")

        thin_border = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )

        month_names = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

        # Cabeçalho do Relatório
        ws.merge_cells("A1:P1")
        title_cell = ws["A1"]
        title_cell.value = f"RELATÓRIO DRE - DEMONSTRATIVO DE RESULTADO DO EXERCÍCIO ({year})"
        title_cell.font = Font(name="Calibri", size=14, bold=True, color="0F172A")
        title_cell.alignment = Alignment(horizontal="left", vertical="center")

        ws.row_dimensions[1].height = 28
        ws.row_dimensions[3].height = 24

        # Linha de Colunas
        headers = ["MÊS / ANO", f"TOTAL {year}", "MÉDIA MENSAL"] + [f"{m}/{str(year)[2:]}" for m in month_names]
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=3, column=col_idx, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center" if col_idx > 1 else "left", vertical="center")
            cell.border = thin_border

        current_row = 4
        currency_format = 'R$ #,##0.00;[Red](R$ #,##0.00);"-"'
        pct_format = '0.00%'

        for row_data in report.all_rows:
            ws.row_dimensions[current_row].height = 20
            is_sub = row_data.is_subtotal or row_data.is_result
            is_pct = row_data.is_percentage_row

            # Coluna Nome
            name_cell = ws.cell(row=current_row, column=1, value=("   " if not is_sub else "") + row_data.name)
            name_cell.border = thin_border

            # Formatação visual de linha
            if is_sub:
                if row_data.id.startswith("subtotal-"):
                    row_fill = subtotal_fill
                    row_font = subtotal_font
                else:
                    row_fill = result_fill
                    row_font = result_font
            else:
                row_fill = PatternFill(fill_type=None)
                row_font = Font(name="Calibri", size=10)

            name_cell.fill = row_fill
            name_cell.font = row_font

            # Coluna Total
            tot_val = row_data.total_amount if not is_pct else (row_data.total_amount / 100.0)
            tot_cell = ws.cell(row=current_row, column=2, value=tot_val)
            tot_cell.number_format = pct_format if is_pct else currency_format
            tot_cell.fill = row_fill
            tot_cell.font = row_font
            tot_cell.alignment = Alignment(horizontal="right", vertical="center")
            tot_cell.border = thin_border

            # Coluna Média
            avg_val = row_data.monthly_average if not is_pct else (row_data.monthly_average / 100.0)
            avg_cell = ws.cell(row=current_row, column=3, value=avg_val)
            avg_cell.number_format = pct_format if is_pct else currency_format
            avg_cell.fill = row_fill
            avg_cell.font = row_font
            avg_cell.alignment = Alignment(horizontal="right", vertical="center")
            avg_cell.border = thin_border

            # Colunas Meses (1-12)
            for m in range(1, 13):
                col_i = 3 + m
                m_val = row_data.monthly_amounts.get(m, 0.0)
                if is_pct:
                    m_val = m_val / 100.0

                m_cell = ws.cell(row=current_row, column=col_i, value=m_val)
                m_cell.number_format = pct_format if is_pct else currency_format
                m_cell.fill = row_fill
                m_cell.font = row_font
                m_cell.alignment = Alignment(horizontal="right", vertical="center")
                m_cell.border = thin_border

            current_row += 1

        # Ajuste de largura das colunas
        ws.column_dimensions["A"].width = 44
        ws.column_dimensions["B"].width = 16
        ws.column_dimensions["C"].width = 15
        for m in range(1, 13):
            col_letter = get_column_letter(3 + m)
            ws.column_dimensions[col_letter].width = 14

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    def get_operational_result(
        self, db: Session, tenant_id: int, year: int, month: int
    ) -> OperationalResultResponse:
        data = self.operational_repo.get_monthly_operational_data(db, tenant_id, year, month)
        return OperationalResultResponse(**data)

    def export_operational_result_excel(
        self, db: Session, tenant_id: int, year: int, month: int
    ) -> io.BytesIO:
        data = self.operational_repo.get_monthly_operational_data(db, tenant_id, year, month)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Resultado Op {month:02d}-{year}"

        # Estilos
        title_font = Font(name="Calibri", size=13, bold=True, color="1E293B")
        kpi_font = Font(name="Calibri", size=10, bold=True, color="334155")
        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        weekend_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
        footer_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        soft_green_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
        bold_font = Font(name="Calibri", size=10, bold=True)
        regular_font = Font(name="Calibri", size=10)
        thin_side = Side(border_style="thin", color="CBD5E1")
        thin_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        num_days = data["days_in_month"]
        days_meta = data["days_metadata"]
        summary = data["summary"]

        # Linha 1: Título
        ws.cell(row=1, column=1, value=f"RESULTADO OPERACIONAL - {month:02d}/{year}").font = title_font

        # Linha 2: Resumo Executivo Operacional (KPIs)
        kpi_text = (
            f"Total de Serviços: {summary['total_services']} | "
            f"Média / Dia Útil: {summary['avg_services_per_working_day']:.1f} atendimentos/dia | "
            f"Dias Úteis: {summary['working_days']} dias | "
            f"Dia de Pico: {summary.get('peak_day_label', '-')} | "
            f"Top Serviço: {summary.get('top_service_name', '-')} ({summary.get('top_service_count', 0)} atend. - {summary.get('top_service_pct', 0.0)}%)"
        )
        ws.cell(row=2, column=1, value=kpi_text).font = kpi_font

        # Linha 4: Cabeçalho da Tabela
        header_row = 4
        ws.cell(row=header_row, column=1, value="Serviço").fill = header_fill
        ws.cell(row=header_row, column=1).font = header_font
        ws.cell(row=header_row, column=1).alignment = Alignment(horizontal="left", vertical="center")

        for idx, dm in enumerate(days_meta):
            col = 2 + idx
            is_closed = dm.get("is_closed", dm.get("is_weekend", False))
            c = ws.cell(row=header_row, column=col, value=f"{dm['day_of_week']}\n{dm['date_str']}")
            c.fill = weekend_fill if is_closed else header_fill
            c.font = Font(name="Calibri", size=9, bold=True, color="1E293B" if is_closed else "FFFFFF")
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        tot_col = 2 + num_days
        ws.cell(row=header_row, column=tot_col, value="Total").fill = header_fill
        ws.cell(row=header_row, column=tot_col).font = header_font
        ws.cell(row=header_row, column=tot_col).alignment = Alignment(horizontal="center", vertical="center")

        # Linhas de Dados
        current_row = header_row + 1
        for r in data["rows"]:
            ws.cell(row=current_row, column=1, value=r["name"]).font = regular_font
            ws.cell(row=current_row, column=1).alignment = Alignment(horizontal="left", vertical="center")
            ws.cell(row=current_row, column=1).border = thin_border

            for idx, dm in enumerate(days_meta):
                col = 2 + idx
                is_closed = dm.get("is_closed", dm.get("is_weekend", False))
                val = r["daily_counts"].get(dm["day"], 0)
                c = ws.cell(row=current_row, column=col, value=val if val > 0 else "")
                c.alignment = Alignment(horizontal="center", vertical="center")
                c.font = regular_font
                c.border = thin_border
                if is_closed:
                    c.fill = weekend_fill

            # Total da Linha
            c_tot = ws.cell(row=current_row, column=tot_col, value=r["total_count"])
            c_tot.font = bold_font
            c_tot.alignment = Alignment(horizontal="center", vertical="center")
            c_tot.border = thin_border

            current_row += 1

        # Linha Rodapé - Volume Serviços / Dia (Estilo limpo e claro)
        ws.cell(row=current_row, column=1, value="VOLUME SERVIÇOS/DIA").font = bold_font
        ws.cell(row=current_row, column=1).alignment = Alignment(horizontal="left", vertical="center")
        ws.cell(row=current_row, column=1).fill = footer_fill
        ws.cell(row=current_row, column=1).border = thin_border

        for idx, dm in enumerate(days_meta):
            col = 2 + idx
            d_tot = data["daily_totals"].get(dm["day"], 0)
            c = ws.cell(row=current_row, column=col, value=d_tot)
            c.font = bold_font
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.fill = footer_fill
            c.border = thin_border

        c_grand = ws.cell(row=current_row, column=tot_col, value=summary["total_services"])
        c_grand.font = bold_font
        c_grand.alignment = Alignment(horizontal="center", vertical="center")
        c_grand.fill = soft_green_fill
        c_grand.border = thin_border

        # Ajuste de largura das colunas
        ws.column_dimensions["A"].width = 28
        for d in range(1, num_days + 1):
            ws.column_dimensions[get_column_letter(1 + d)].width = 7
        ws.column_dimensions[get_column_letter(tot_col)].width = 12

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output

    # ── GESTÃO DE FOLHA DE PAGAMENTO, SALÁRIOS & BENEFÍCIOS ─────────────────
    def get_payroll_profiles(self, db: Session, tenant_id: int) -> List[PayrollProfileResponse]:
        raw_list = self.repo.get_payroll_profiles(db, tenant_id)
        return [PayrollProfileResponse(**item) for item in raw_list]

    def upsert_payroll_profile(
        self, db: Session, tenant_id: int, employee_id: int, data: PayrollProfileUpdate
    ) -> PayrollProfileResponse:
        update_dict = data.model_dump(exclude_unset=True)
        if "custom_benefits" in update_dict and update_dict["custom_benefits"] is not None:
            update_dict["custom_benefits"] = [
                b.model_dump() if hasattr(b, "model_dump") else b for b in update_dict["custom_benefits"]
            ]
        self.repo.upsert_payroll_profile(db, tenant_id, employee_id, update_dict)
        all_profiles = self.get_payroll_profiles(db, tenant_id)
        target = next((p for p in all_profiles if p.employee_id == employee_id), None)
        if not target:
            raise ValueError("Funcionário não encontrado")
        return target

    def get_payroll_summary(self, db: Session, tenant_id: int) -> PayrollSummaryResponse:
        profiles = self.get_payroll_profiles(db, tenant_id)
        active = [p for p in profiles if p.is_active and p.employee_is_active]

        tot_base = round(sum(p.base_salary for p in active), 2)
        tot_13 = round(sum(p.thirteenth_salary for p in active), 2)
        tot_vac = round(sum(p.vacation_provision for p in active), 2)
        tot_salaries = round(sum(p.total_salaries_and_provisions for p in active), 2)
        tot_inss = round(sum(p.total_inss for p in active), 2)
        tot_fgts = round(sum(p.total_fgts for p in active), 2)
        tot_charges = round(tot_inss + tot_fgts, 2)
        tot_vt = round(sum(p.transport_voucher for p in active), 2)
        tot_va = round(sum(p.food_voucher for p in active), 2)
        tot_vr = round(sum(p.meal_voucher for p in active), 2)
        tot_health = round(sum(p.health_insurance for p in active), 2)
        tot_other = round(sum(p.other_benefits for p in active), 2)
        tot_benefits = round(sum(p.total_benefits for p in active), 2)
        tot_monthly = round(sum(p.total_monthly_cost for p in active), 2)

        return PayrollSummaryResponse(
            total_base_salary=tot_base,
            total_thirteenth=tot_13,
            total_vacation=tot_vac,
            total_salaries_and_provisions=tot_salaries,
            total_inss=tot_inss,
            total_fgts=tot_fgts,
            total_charges=tot_charges,
            total_transport_voucher=tot_vt,
            total_food_voucher=tot_va,
            total_meal_voucher=tot_vr,
            total_health_insurance=tot_health,
            total_other_benefits=tot_other,
            total_benefits=tot_benefits,
            total_monthly_cost=tot_monthly,
            total_annual_cost=round(tot_monthly * 12.0, 2),
            active_employees_count=len(active),
        )

    def sync_payroll_to_dre(
        self, db: Session, tenant_id: int, request: PayrollSyncToDRERequest, user_id: Optional[int] = None
    ) -> PayrollSyncResponse:
        res = self.repo.sync_payroll_to_dre(
            db=db,
            tenant_id=tenant_id,
            year=request.year,
            months=request.months,
            account_mapping=request.account_mapping,
            user_id=user_id,
        )
        return PayrollSyncResponse(**res)

