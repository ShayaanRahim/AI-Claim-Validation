from pydantic import BaseModel, Field
from datetime import date

class Patient(BaseModel):
    id: str
    age: int = Field(ge=0)
    state: str

class CareEvent(BaseModel):
    type: str
    date: date
    duration_minutes: int = Field(gt = 0)

class Insurance(BaseModel):
    payer: str
    policy_id: str
    plan_type: str

class Billing(BaseModel):
    procedure_code: str
    units: int = Field(ge = 1)
    amount: float = Field(ge = 0)

class Claim(BaseModel):
    claim_id: str
    patient: Patient
    care_event: CareEvent
    insurance: Insurance
    billing: Billing
