import sys
import os

# Adiciona o diretório raiz ao path para permitir imports do app
sys.path.append(os.getcwd())

from sqlalchemy import text
from app.config.database import SessionLocal, Base, engine
from app.modules.models_loader import load_all_models

# Carrega todos os modelos padrão
load_all_models()

# Importa modelos que não seguem o padrão nome_modulo.models
import app.modules.products.inventory_models

def reset_database():
    print("[RESET] Iniciando limpeza do banco de dados...")
    db = SessionLocal()
    try:
        # Tabelas que não devem ser limpas (configurações do sistema)
        EXCLUDE_TABLES = {"plans", "tenant_types", "whatsapp_templates"}
        
        driver = engine.url.drivername
        
        if "postgresql" in driver:
            # No PostgreSQL, usamos TRUNCATE em lote com CASCADE e RESTART IDENTITY.
            # É instantâneo (milissegundos) e reseta os contadores de autoincremento (IDs).
            tables_to_truncate = [
                f'"{table.name}"'
                for table in Base.metadata.sorted_tables
                if table.name not in EXCLUDE_TABLES
            ]
            
            for table in Base.metadata.sorted_tables:
                if table.name in EXCLUDE_TABLES:
                    print(f"   [SKIP] Tabela protegida: {table.name}")

            if tables_to_truncate:
                print(f"   [TRUNCATE] Limpando {len(tables_to_truncate)} tabelas simultaneamente...")
                truncate_sql = f"TRUNCATE TABLE {', '.join(tables_to_truncate)} RESTART IDENTITY CASCADE;"
                db.execute(text(truncate_sql))
        elif driver == "sqlite":
            db.execute(text("PRAGMA foreign_keys = OFF;"))
            for table in reversed(Base.metadata.sorted_tables):
                if table.name in EXCLUDE_TABLES:
                    print(f"   [SKIP] Tabela protegida: {table.name}")
                    continue
                print(f"   Limpando: {table.name}")
                db.execute(table.delete())
            db.execute(text("PRAGMA foreign_keys = ON;"))
        else:
            for table in reversed(Base.metadata.sorted_tables):
                if table.name in EXCLUDE_TABLES:
                    print(f"   [SKIP] Tabela protegida: {table.name}")
                    continue
                print(f"   Limpando: {table.name}")
                db.execute(table.delete())
        
        db.commit()
        print("[OK] Banco de dados limpo com sucesso!")
    except Exception as e:
        db.rollback()
        print(f"[ERRO] Erro ao limpar banco de dados: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    confirm = input("Tem certeza que deseja APAGAR TODOS os dados? (s/N): ")
    if confirm.lower() == 's':
        reset_database()
    else:
        print("Operação cancelada.")
