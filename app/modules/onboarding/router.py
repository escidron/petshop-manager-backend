from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.modules.auth.dependencies import get_current_tenant
from app.modules.onboarding.schemas import UpdateOnboardingStep

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])

@router.patch("/step")
def update_step(
    data: UpdateOnboardingStep,
    db: Session = Depends(get_db),
    current_data=Depends(get_current_tenant),
):
    tenant = current_data["tenant"]

    tenant.onboarding_step = data.step

    db.commit()
    db.refresh(tenant)

    return {"current_step": tenant.onboarding_step}