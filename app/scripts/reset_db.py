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
        # Para SQLite, desabilitar foreign keys temporariamente facilita
        if engine.url.drivername == "sqlite":
            db.execute(text("PRAGMA foreign_keys = OFF;"))
        
        # Tabelas que não devem ser limpas (configurações do sistema)
        EXCLUDE_TABLES = ["plans", "tenant_types"]
        
        # Deleta dados de todas as tabelas registradas no Base.metadata
        # Iteramos em ordem reversa de dependência para evitar erros de FK (mesmo com PRAGMA OFF é boa prática)
        for table in reversed(Base.metadata.sorted_tables):
            if table.name in EXCLUDE_TABLES:
                print(f"   [SKIP] Tabela protegida: {table.name}")
                continue
                
            print(f"   Limpando: {table.name}")
            db.execute(table.delete())
        
        if engine.url.drivername == "sqlite":
            db.execute(text("PRAGMA foreign_keys = ON;"))
        
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
