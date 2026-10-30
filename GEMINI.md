# Diretrizes e Padrões de Desenvolvimento - DataPet / PetShop Manager

Este documento define regras arquiteturais, de estilo e de processos que **devem ser sempre seguidas** pelo Gemini / Antigravity em todas as interações e alterações no projeto.

---

## 1. Regras de Imports (CRÍTICO)

- **Imports sempre no topo do arquivo**:
  - TODOS os imports (`import ...`, `from ... import ...`) DEVEM ficar no topo do arquivo.
  - **É terminantemente proibido** colocar imports dentro do corpo de funções, métodos, decoradores ou serializadores (ex: dentro de `@field_serializer`, `@model_validator`, métodos de service ou rotas).
  - *Exceção controlada*: apenas em casos estritos e documentados de dependência circular de módulos ORM que não possam ser resolvidos com `from __future__ import annotations` ou `from typing import TYPE_CHECKING`.
- **Organização PEP 8**:
  1. Standard library (`datetime`, `zoneinfo`, `typing`, `uuid`, etc.)
  2. Bibliotecas de terceiros (`fastapi`, `pydantic`, `sqlalchemy`, etc.)
  3. Módulos internos da aplicação (`app.config.*`, `app.utils.*`, `app.modules.*`)

```python
# ✅ CORRETO:
from datetime import datetime
from pydantic import BaseModel, field_serializer
from app.utils.timezone import to_brazil_datetime

class ClientResponse(BaseModel):
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        return to_brazil_datetime(dt)

# ❌ INCORRETO:
class ClientResponse(BaseModel):
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, dt: datetime | None, _info):
        if dt is None:
            return None
        from app.utils.timezone import to_brazil_datetime  # PROIBIDO AQUI DENTRO!
        return to_brazil_datetime(dt)
```

---

## 2. Fuso Horário e Serialização de Datetime (CRÍTICO)

O fuso horário oficial da aplicação é **Brasília (`America/Sao_Paulo`, UTC-3)**.
Todas as regras de negócio, calendários, dashboards e mensagens de WhatsApp operam nesse fuso.

1. **Serialização de Respostas (Pydantic)**:
   - Todo schema de saída que contenha campos de data/hora (ex: `scheduled_at`, `created_at`, `updated_at`, `appointment_date`, `removed_at`) deve aplicar `@field_serializer` usando `to_brazil_datetime(dt)`.
   - Isso garante que a API emita strings ISO 8601 com offset `-03:00` (ex: `"2026-10-29T21:30:00-03:00"`), impedindo que horários após as 21:00 vazem para o dia seguinte em UTC (`"2026-10-30T00:30:00Z"`).
2. **Consultas no Banco de Dados (`PostgreSQL`)**:
   - Para intervalos diários ou mensais em colunas `TIMESTAMPTZ`, usar `get_day_bounds_brazil(target_date)` ou `get_date_range_bounds_brazil(start, end)`.
   - Para agrupamento ou destaque por data em `TIMESTAMPTZ` (ex: `list_highlighted_days` do calendário), **NUNCA** fazer `cast(coluna, Date)` direto em conexões UTC. Fazer sempre:
     ```python
     date_col = cast(func.timezone('America/Sao_Paulo', Appointment.scheduled_at), Date)
     ```
3. **Módulo Centralizador**:
   - Usar sempre os métodos de `app.utils.timezone`:
     - `to_brazil_datetime(dt)`
     - `get_day_bounds_brazil(day)`
     - `get_date_range_bounds_brazil(start, end)`
     - `get_brazil_now()`
     - `get_brazil_today()`

---

## 3. Política de Testes Automatizados Obrigatórios

- **Sempre criar testes para bugs corrigidos e novas funcionalidades**:
  - Toda correção de bug ou nova funcionalidade deve vir acompanhada de testes unitários ou de integração cobrindo o caso específico.
  - Os testes devem ser adicionados na pasta `tests/` do backend e validados com `poetry run pytest`.
  - Nenhuma alteração é considerada finalizada sem a validação da suíte de testes.

---

## 4. Segurança e Proteção de Ambientes

- **Nunca rodar comandos ou scripts contra o banco de produção**:
  - Scripts de teste, inspeções pontuais e comandos manuais não devem acessar diretamente o banco de produção.
  - Para validação de dados e queries, usar mocks, schemas Pydantic ou a fixture transacional de teste `db` (que executa rollback automático).
