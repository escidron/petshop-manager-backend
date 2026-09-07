import calendar
from datetime import datetime, date
from typing import Dict, List, Tuple, Any
from sqlalchemy.orm import Session
from sqlalchemy import text, func, extract

from app.modules.appointments.models import (
    Appointment,
    AppointmentItem,
    AppointmentItemService,
    AppointmentStatus,
)
from app.modules.tenant_services.models import Service
from app.modules.sales.models import Sale, SaleItem
from app.modules.tenants.models import Tenant


PT_WEEKDAYS = {
    0: "SEG",
    1: "TER",
    2: "QUA",
    3: "QUI",
    4: "SEX",
    5: "SÁB",
    6: "DOM",
}


class OperationalResultRepository:
    """
    Repositório de dados analíticos para apuração do Resultado Operacional.
    Baseado EXCLUSIVAMENTE nos serviços cadastrados e executados pelo tenant.
    """

    def generate_service_code_and_group(
        self, name: str, size: str | None, species: str | None
    ) -> Tuple[str, str, str]:
        """
        Gera um código curto amigável e agrupa o serviço por categoria:
        Retorna (code, group_key, group_name).
        """
        name_clean = (name or "").strip()
        name_lower = name_clean.lower()
        size_str = (size or "").strip().upper() if size else ""
        species_lower = (species or "").strip().lower() if species else ""

        # 1. Gato / Felino
        if species_lower == "felino" or "gato" in name_lower:
            code = "BGA" if "banho" in name_lower else "FEL"
            return code, "cat", "Gatos"

        # 2. Tosa Tesoura
        if "tesoura" in name_lower or "tes." in name_lower:
            code = f"T{size_str}" if size_str in ["PP", "P", "M", "G", "GG"] else "TES"
            return code, "scissor", "Tosa Tesoura"

        # 3. Tosa Máquina / Geral
        if "máquina" in name_lower or "maquina" in name_lower or "máq" in name_lower:
            code = f"M{size_str}" if size_str in ["PP", "P", "M", "G", "GG"] else "MAQ"
            return code, "machine", "Tosa Máquina"

        if "tosa" in name_lower:
            code = f"TOS" if not size_str else f"T{size_str}"
            return code, "machine", "Tosas"

        # 4. Banhos
        if "banho" in name_lower:
            code = f"B{size_str}" if size_str in ["PP", "P", "M", "G", "GG"] else "BAN"
            return code, "bath", "Banhos"

        # 5. Outros Serviços (ex: Cortar Unha, Hidratação, Higiênica, etc.)
        # Abreviação com 3 letras
        words = name_clean.split()
        if len(words) >= 2:
            code = (words[0][:2] + words[1][:1]).upper()
        else:
            code = name_clean[:3].upper() if len(name_clean) >= 3 else name_clean.upper()

        return code, "other", "Outros Serviços"

    def is_tenant_closed_on_date(self, working_hours: Any, dt: date) -> bool:
        """
        Verifica se o petshop está fechado na data informada,
        consultando a configuração de working_hours da tabela de tenants.
        Convenção dayjs das chaves: '0'=Domingo ... '6'=Sábado.
        Python dt.weekday(): 0=Segunda ... 5=Sábado, 6=Domingo.
        """
        weekday_num = dt.weekday()
        day_key = str((weekday_num + 1) % 7)

        if working_hours and isinstance(working_hours, dict) and day_key in working_hours:
            day_schedule = working_hours[day_key]
            if isinstance(day_schedule, dict) and "is_open" in day_schedule:
                return not bool(day_schedule["is_open"])

        # Fallback padrão: Domingo fechado (0/Dom), Segunda a Sábado abertos
        return weekday_num == 6

    def get_monthly_operational_data(
        self, db: Session, tenant_id: int, year: int, month: int
    ) -> Dict[str, Any]:
        """
        Busca todos os serviços do tenant e os atendimentos realizados no mês.
        """
        num_days = calendar.monthrange(year, month)[1]

        # 0. Carrega configuração de funcionamento do tenant (working_hours)
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        tenant_working_hours = tenant.working_hours if tenant else None

        # 1. Metadados dos dias
        days_metadata = []
        for d in range(1, num_days + 1):
            dt = date(year, month, d)
            weekday_num = dt.weekday()
            is_closed = self.is_tenant_closed_on_date(tenant_working_hours, dt)
            days_metadata.append({
                "day": d,
                "day_of_week": PT_WEEKDAYS[weekday_num],
                "date_str": f"{d:02d}/{calendar.month_abbr[month].lower()}",
                "is_weekend": is_closed,
                "is_closed": is_closed,
            })

        # 2. Carrega os serviços cadastrados no catálogo do tenant
        tenant_services = (
            db.query(Service)
            .filter(Service.tenant_id == tenant_id)
            .order_by(Service.id)
            .all()
        )

        rows_map: Dict[str, Dict[str, Any]] = {}
        service_id_to_key: Dict[int, str] = {}

        for s in tenant_services:
            size_val = s.size.value if hasattr(s.size, "value") else (str(s.size) if s.size else None)
            species_val = s.species.value if hasattr(s.species, "value") else (str(s.species) if s.species else None)
            code, g_key, g_name = self.generate_service_code_and_group(s.name, size_val, species_val)

            # Monta nome de exibição (adiciona porte se não estiver já no nome)
            display_name = s.name.strip()
            if size_val and size_val.lower() not in display_name.lower():
                display_name = f"{display_name} ({size_val})"

            # Se já existir código duplicado, diferencia
            unique_code = code
            counter = 1
            while unique_code in rows_map:
                counter += 1
                unique_code = f"{code}{counter}"

            row_key = f"srv_{s.id}"
            service_id_to_key[s.id] = row_key

            rows_map[row_key] = {
                "id": s.id,
                "code": unique_code,
                "name": display_name,
                "group_key": g_key,
                "group_name": g_name,
                "daily_counts": {d: 0 for d in range(1, num_days + 1)},
                "total_count": 0,
                "order_index": s.id,
            }

        # 3. Buscar atendimentos de agendamento (status completed)
        sql_appointments = text("""
            SELECT 
                EXTRACT(day FROM a.scheduled_at) AS day_num,
                s.id AS service_id,
                s.name AS service_name,
                s.size AS service_size,
                s.species AS service_species,
                COALESCE(s.price_cents, 0) AS price_cents
            FROM appointments a
            JOIN appointment_items ai ON ai.appointment_id = a.id
            JOIN appointment_item_services ais ON ais.appointment_item_id = ai.id
            JOIN services s ON s.id = ais.service_id
            WHERE a.tenant_id = :tenant_id
              AND a.status = 'completed'
              AND EXTRACT(year FROM a.scheduled_at) = :year
              AND EXTRACT(month FROM a.scheduled_at) = :month
        """)

        apt_rows = db.execute(
            sql_appointments,
            {"tenant_id": tenant_id, "year": year, "month": month}
        ).fetchall()

        for r in apt_rows:
            day_num = int(r.day_num)
            srv_id = int(r.service_id)
            row_key = service_id_to_key.get(srv_id)

            if not row_key or row_key not in rows_map:
                # Caso o serviço tenha sido executado mas não esteja ativo
                code, g_key, g_name = self.generate_service_code_and_group(
                    r.service_name, str(r.service_size) if r.service_size else None, str(r.service_species) if r.service_species else None
                )
                row_key = f"srv_{srv_id}"
                service_id_to_key[srv_id] = row_key
                rows_map[row_key] = {
                    "id": srv_id,
                    "code": code,
                    "name": r.service_name,
                    "group_key": g_key,
                    "group_name": g_name,
                    "daily_counts": {d: 0 for d in range(1, num_days + 1)},
                    "total_count": 0,
                    "order_index": srv_id,
                }

            rows_map[row_key]["daily_counts"][day_num] += 1
            rows_map[row_key]["total_count"] += 1

        # 4. Buscar serviços vendidos avulsos no PDV sem agendamento vinculado
        sql_sales = text("""
            SELECT 
                EXTRACT(day FROM s.created_at) AS day_num,
                si.item_id AS service_id,
                si.name AS service_name,
                si.quantity AS quantity,
                si.subtotal AS subtotal,
                srv.size AS service_size,
                srv.species AS service_species
            FROM sales s
            JOIN sale_items si ON si.sale_id = s.id
            LEFT JOIN services srv ON srv.id = si.item_id AND si.item_type = 'service'
            WHERE s.tenant_id = :tenant_id
              AND s.status = 'completed'
              AND si.item_type = 'service'
              AND s.appointment_id IS NULL
              AND si.appointment_id IS NULL
              AND EXTRACT(year FROM s.created_at) = :year
              AND EXTRACT(month FROM s.created_at) = :month
        """)

        sale_rows = db.execute(
            sql_sales,
            {"tenant_id": tenant_id, "year": year, "month": month}
        ).fetchall()

        for r in sale_rows:
            day_num = int(r.day_num)
            qty = int(r.quantity or 1)
            srv_id = int(r.service_id or 0)
            row_key = service_id_to_key.get(srv_id)

            if not row_key or row_key not in rows_map:
                code, g_key, g_name = self.generate_service_code_and_group(
                    r.service_name, str(r.service_size) if r.service_size else None, str(r.service_species) if r.service_species else None
                )
                row_key = f"sale_srv_{srv_id or r.service_name}"
                rows_map[row_key] = {
                    "id": srv_id,
                    "code": code,
                    "name": r.service_name,
                    "group_key": g_key,
                    "group_name": g_name,
                    "daily_counts": {d: 0 for d in range(1, num_days + 1)},
                    "total_count": 0,
                    "order_index": 999,
                }

            rows_map[row_key]["daily_counts"][day_num] += qty
            rows_map[row_key]["total_count"] += qty

        # 5. Calcular totais diários (linha de rodapé)
        daily_totals = {d: 0 for d in range(1, num_days + 1)}
        for row in rows_map.values():
            for d in range(1, num_days + 1):
                daily_totals[d] += row["daily_counts"][d]

        # 6. Atualizar has_activity nos metadados de dias
        for dm in days_metadata:
            dm["has_activity"] = daily_totals[dm["day"]] > 0

        # 7. Subtotais por grupo dinâmicos
        detected_groups = {}
        for row in rows_map.values():
            g_key = row["group_key"]
            g_name = row["group_name"]
            if g_key not in detected_groups:
                detected_groups[g_key] = {
                    "group_key": g_key,
                    "group_name": g_name,
                    "daily_counts": {d: 0 for d in range(1, num_days + 1)},
                    "total_count": 0,
                }
            detected_groups[g_key]["total_count"] += row["total_count"]
            for d in range(1, num_days + 1):
                detected_groups[g_key]["daily_counts"][d] += row["daily_counts"][d]

        group_subtotals = list(detected_groups.values())

        # 8. KPIs Resumo
        total_services = sum(daily_totals.values())
        working_days = sum(1 for d in range(1, num_days + 1) if daily_totals[d] > 0)
        avg_per_day = round(total_services / working_days, 2) if working_days > 0 else 0.0

        # Apuração do Faturamento de Serviços Efetivamente Pagos (Sales finalizadas com status 'completed')
        # Considera o valor efetivamente pago na venda (total_amount) proporcional à parcela de serviços,
        # evitando dupla contagem de saldos divididos em comandas.
        sql_paid_services = text("""
            SELECT 
                COALESCE(SUM(
                    CASE 
                        WHEN totals.all_subtotal > 0 THEN s.total_amount * (totals.service_subtotal / totals.all_subtotal)
                        ELSE 0 
                    END
                ), 0) AS paid_revenue
            FROM sales s
            JOIN (
                SELECT 
                    sale_id,
                    SUM(subtotal) AS all_subtotal,
                    SUM(CASE WHEN item_type = 'service' THEN subtotal ELSE 0 END) AS service_subtotal
                FROM sale_items
                GROUP BY sale_id
            ) totals ON totals.sale_id = s.id
            WHERE s.tenant_id = :tenant_id
              AND s.status = 'completed'
              AND totals.service_subtotal > 0
              AND EXTRACT(year FROM s.created_at) = :year
              AND EXTRACT(month FROM s.created_at) = :month
        """)
        paid_res = db.execute(
            sql_paid_services,
            {"tenant_id": tenant_id, "year": year, "month": month}
        ).fetchone()
        paid_revenue = float(paid_res[0] if paid_res else 0.0)

        # Se houver vendas finalizadas de serviços no mês, utiliza a receita real de vendas pagas.
        # Caso contrário (ex: agendamentos finalizados sem checkout registrado no PDV), calcula via agendamentos concluídos.
        if paid_revenue > 0:
            total_revenue = round(paid_revenue, 2)
        else:
            sql_apt_rev = text("""
                SELECT 
                    COALESCE(SUM(s.price_cents), 0) AS apt_rev_cents
                FROM appointments a
                JOIN appointment_items ai ON ai.appointment_id = a.id
                JOIN appointment_item_services ais ON ais.appointment_item_id = ai.id
                JOIN services s ON s.id = ais.service_id
                WHERE a.tenant_id = :tenant_id
                  AND a.status = 'completed'
                  AND EXTRACT(year FROM a.scheduled_at) = :year
                  AND EXTRACT(month FROM a.scheduled_at) = :month
            """)
            apt_rev_res = db.execute(
                sql_apt_rev,
                {"tenant_id": tenant_id, "year": year, "month": month}
            ).fetchone()
            total_revenue = round(float((apt_rev_res[0] if apt_rev_res else 0) / 100.0), 2)

        avg_revenue_per_day = round((total_revenue / working_days), 2) if working_days > 0 else 0.0
        ticket_medio = round((total_revenue / total_services), 2) if total_services > 0 else 0.0

        # Apuração do Dia de Pico Operacional (Maior volume diário)
        peak_day = 0
        peak_day_count = 0
        for d in range(1, num_days + 1):
            c = daily_totals.get(d, 0)
            if c > peak_day_count:
                peak_day_count = c
                peak_day = d

        peak_day_label = f"Dia {peak_day:02d} ({peak_day_count} atend.)" if peak_day > 0 else "-"

        # Apuração do Serviço Mais Realizado (Top 1)
        top_service_name = "-"
        top_service_count = 0
        top_service_pct = 0.0
        if rows_map:
            best_srv = max(rows_map.values(), key=lambda x: x["total_count"], default=None)
            if best_srv and best_srv["total_count"] > 0:
                top_service_name = best_srv["name"]
                top_service_count = best_srv["total_count"]
                top_service_pct = round((top_service_count / total_services * 100.0), 1) if total_services > 0 else 0.0

        summary = {
            "total_services": total_services,
            "working_days": working_days,
            "avg_services_per_working_day": avg_per_day,
            "peak_day": peak_day,
            "peak_day_count": peak_day_count,
            "peak_day_label": peak_day_label,
            "top_service_name": top_service_name,
            "top_service_count": top_service_count,
            "top_service_pct": top_service_pct,
            "total_revenue": total_revenue,
            "avg_revenue_per_working_day": avg_revenue_per_day,
            "ticket_medio_operational": ticket_medio,
        }

        # 9. Serviços Estratificados (para gráficos) ordenados alfabeticamente
        sorted_rows = sorted(rows_map.values(), key=lambda x: x["name"].lower())
        stratified = []
        for r in sorted_rows:
            pct = round((r["total_count"] / total_services * 100.0), 2) if total_services > 0 else 0.0
            stratified.append({
                "code": r["code"],
                "name": r["name"],
                "group_key": r["group_key"],
                "count": r["total_count"],
                "percentage": pct,
            })

        # 10. Comparativo Anual
        annual_comparison = self.get_annual_comparison(db, tenant_id, year)

        return {
            "year": year,
            "month": month,
            "days_in_month": num_days,
            "days_metadata": days_metadata,
            "rows": sorted_rows,
            "group_subtotals": group_subtotals,
            "daily_totals": daily_totals,
            "summary": summary,
            "annual_comparison": annual_comparison,
            "stratified_services": stratified,
        }

    def get_annual_comparison(
        self, db: Session, tenant_id: int, current_year: int
    ) -> Dict[str, Any]:
        """
        Retorna os volumes de serviços mês a mês para o ano corrente e o ano anterior.
        """
        previous_year = current_year - 1
        monthly_curr = {m: 0 for m in range(1, 13)}
        monthly_prev = {m: 0 for m in range(1, 13)}

        sql_yearly = text("""
            SELECT 
                EXTRACT(year FROM a.scheduled_at) AS yr,
                EXTRACT(month FROM a.scheduled_at) AS mo,
                COUNT(ais.service_id) AS service_count
            FROM appointments a
            JOIN appointment_items ai ON ai.appointment_id = a.id
            JOIN appointment_item_services ais ON ais.appointment_item_id = ai.id
            WHERE a.tenant_id = :tenant_id
              AND a.status = 'completed'
              AND EXTRACT(year FROM a.scheduled_at) IN (:curr_year, :prev_year)
            GROUP BY yr, mo
        """)

        rows = db.execute(
            sql_yearly,
            {"tenant_id": tenant_id, "curr_year": current_year, "prev_year": previous_year}
        ).fetchall()

        for r in rows:
            yr = int(r.yr)
            mo = int(r.mo)
            cnt = int(r.service_count or 0)
            if yr == current_year:
                monthly_curr[mo] += cnt
            elif yr == previous_year:
                monthly_prev[mo] += cnt

        sql_sales_yearly = text("""
            SELECT 
                EXTRACT(year FROM s.created_at) AS yr,
                EXTRACT(month FROM s.created_at) AS mo,
                SUM(si.quantity) AS service_count
            FROM sales s
            JOIN sale_items si ON si.sale_id = s.id
            WHERE s.tenant_id = :tenant_id
              AND s.status = 'completed'
              AND si.item_type = 'service'
              AND s.appointment_id IS NULL
              AND si.appointment_id IS NULL
              AND EXTRACT(year FROM s.created_at) IN (:curr_year, :prev_year)
            GROUP BY yr, mo
        """)

        sales_rows = db.execute(
            sql_sales_yearly,
            {"tenant_id": tenant_id, "curr_year": current_year, "prev_year": previous_year}
        ).fetchall()

        for r in sales_rows:
            yr = int(r.yr)
            mo = int(r.mo)
            cnt = int(r.service_count or 0)
            if yr == current_year:
                monthly_curr[mo] += cnt
            elif yr == previous_year:
                monthly_prev[mo] += cnt

        return {
            "current_year": current_year,
            "previous_year": previous_year,
            "monthly_volume_current": monthly_curr,
            "monthly_volume_previous": monthly_prev,
        }
