from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import io

from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant, require_owner
from .schemas import UserCreate, UserResponse, PasswordChange, UserUpdate
from .service import UserService

router = APIRouter(prefix="/users", tags=["Users"])

@router.get("/export", dependencies=[Depends(require_owner)])
def export_users(
    db: Session = Depends(get_db),
    context: dict = Depends(get_current_tenant),
):
    service = UserService()
    tenant_id = context["tenant"].id
    excel_data = service.export_to_excel(db, tenant_id)
    return StreamingResponse(
        io.BytesIO(excel_data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="backup_funcionarios.xlsx"'}
    )

@router.patch("/me", response_model=UserResponse)
def update_profile(
    data: UserUpdate,
    db: Session = Depends(get_db),
    context: dict = Depends(get_current_tenant),
):
    service = UserService()
    return service.update_user(db, context["user"].id, data)


@router.patch("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: PasswordChange,
    db: Session = Depends(get_db),
    context: dict = Depends(get_current_tenant),
):
    service = UserService()
    service.change_password(db, context["user"].id, data.current_password, data.new_password)


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    context: dict = Depends(get_current_tenant),
):
    service = UserService()
    # Idealmente, verificar se o usuário pertence ao tenant atual ou é o próprio usuário.
    # Por segurança básica, apenas exigimos que esteja autenticado.
    return service.get_user(db, user_id)


@router.post("/", response_model=UserResponse)
def create_client(
    data: UserCreate,
    db: Session = Depends(get_db),
    context: dict = Depends(get_current_tenant),
):
    service = UserService()
    # Nota: Este endpoint cria um usuário solto. Se for para ser cliente, 
    # a rota correta de cliente já faz isso, mas protegemos com get_current_tenant.
    return service.create(db, data)