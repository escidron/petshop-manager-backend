from enum import Enum

from pydantic import BaseModel

class OnboardingStep(str, Enum):
    SERVICES = "services"
    BUSINESS_HOURS = "business_hours"
    CLIENT = "client"
    PET = "pet"
    COMPLETED = "completed"

class UpdateOnboardingStep(BaseModel):
    step: OnboardingStep