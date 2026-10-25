"""Database tables and API schemas."""
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field as PField, StringConstraints, field_validator
from sqlmodel import Field, SQLModel

from sms import normalise_phone


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------- enums ----------
class Status(str, Enum):
    received = "received"
    diagnosing = "diagnosing"
    waiting_parts = "waiting_parts"
    repairing = "repairing"
    ready = "ready"
    collected = "collected"


OPEN_STATUSES = (Status.received, Status.diagnosing, Status.waiting_parts, Status.repairing)


class PartSource(str, Enum):
    stock = "stock"  # already in the shop
    purchase = "purchase"  # has to be bought for this job


class PaymentMethod(str, Enum):
    cash = "cash"
    mpesa = "mpesa"
    card = "card"
    bank = "bank"
    other = "other"


MAX_AMOUNT = 10_000_000  # whole shillings; guards against typos like an extra zero or three


class Role(str, Enum):
    admin = "admin"
    manager = "manager"
    technician = "technician"
    front_desk = "front_desk"


# ---------- tables ----------
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    full_name: str
    password_hash: str
    role: Role = Role.technician
    is_active: bool = True
    created_at: datetime = Field(default_factory=now_utc)
    last_login_at: Optional[datetime] = None


class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    phone: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=now_utc)


class Repair(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ticket_code: str = Field(index=True, unique=True)
    customer_id: int = Field(foreign_key="customer.id")
    imei: str
    brand: str
    model: str
    service_type: str  # e.g. screen, battery, software
    service_details: str = ""  # what is required
    assigned_to: str = ""  # technician
    status: Status = Status.received
    progress: int = 0  # 0-100
    estimated_completion: Optional[datetime] = None
    service_fee: int = 0  # labour / service charge in whole KES (parts are charged separately)
    collected_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)


class Part(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    repair_id: int = Field(foreign_key="repair.id", index=True)
    name: str
    quantity: int = 1
    source: PartSource = PartSource.stock
    unit_cost: int = 0  # what the part cost the shop
    unit_price: int = 0  # what the customer is charged for it
    acquired: bool = True  # False while a "purchase" part has not been bought yet
    added_by: str = ""
    created_at: datetime = Field(default_factory=now_utc)


class Payment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    repair_id: int = Field(foreign_key="repair.id", index=True)
    amount: int
    method: PaymentMethod = PaymentMethod.cash
    reference: str = ""
    received_by: str = ""
    created_at: datetime = Field(default_factory=now_utc)


# ---------- shared field types ----------
def _normalise_username(value):
    return value.strip().lower() if isinstance(value, str) else value


# Normalise first, then validate, so " Boss " is accepted as "boss".
Username = Annotated[
    str,
    BeforeValidator(_normalise_username),
    StringConstraints(pattern=r"^[a-z0-9._-]{3,32}$"),
]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


# ---------- auth / user schemas ----------
class LoginForm(BaseModel):
    username: Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=64)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class SetupForm(BaseModel):
    username: Username
    full_name: FullName
    password: Password
    setup_key: str = ""


class UserCreate(BaseModel):
    username: Username
    full_name: FullName
    password: Password
    role: Role


class UserUpdate(BaseModel):
    full_name: Optional[FullName] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    password: Optional[Password] = None  # admin password reset


class PasswordChange(BaseModel):
    current_password: str
    new_password: Password


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


class StaffMember(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    role: Role


# ---------- repair schemas ----------
class IntakeForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = PField(min_length=1, max_length=120)
    phone: str = PField(min_length=5, max_length=20)
    imei: str = PField(min_length=1, max_length=40)
    brand: str = PField(min_length=1, max_length=60)
    model: str = PField(min_length=1, max_length=60)
    service_type: str = PField(min_length=1, max_length=60)
    service_details: str = PField("", max_length=2000)
    assigned_to: str = PField("", max_length=80)
    service_fee: int = PField(0, ge=0, le=MAX_AMOUNT)
    deposit_amount: int = PField(0, ge=0, le=MAX_AMOUNT)
    deposit_method: PaymentMethod = PaymentMethod.cash

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalise_phone(v)


class RepairUpdate(BaseModel):
    status: Optional[Status] = None
    progress: Optional[int] = PField(None, ge=0, le=100)
    estimated_completion: Optional[datetime] = None
    assigned_to: Optional[str] = PField(None, max_length=80)
    service_fee: Optional[int] = PField(None, ge=0, le=MAX_AMOUNT)
    notify: bool = True  # send SMS on status change


class MoneyOut(BaseModel):
    service_fee: int
    parts_total: int  # what the customer is charged for parts
    parts_cost: int  # what the parts cost the shop
    total: int
    paid: int
    balance: int
    profit: Optional[int] = None  # administrators only


class PartCreate(BaseModel):
    name: str = PField(min_length=1, max_length=120)
    quantity: int = PField(1, ge=1, le=1000)
    source: PartSource = PartSource.stock
    unit_cost: Optional[int] = PField(None, ge=0, le=MAX_AMOUNT)
    unit_price: Optional[int] = PField(None, ge=0, le=MAX_AMOUNT)  # defaults to unit_cost
    acquired: Optional[bool] = None  # defaults to True for stock parts, False for purchases

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Part name is required")
        return v


class PartUpdate(BaseModel):
    name: Optional[str] = PField(None, min_length=1, max_length=120)
    quantity: Optional[int] = PField(None, ge=1, le=1000)
    source: Optional[PartSource] = None
    unit_cost: Optional[int] = PField(None, ge=0, le=MAX_AMOUNT)
    unit_price: Optional[int] = PField(None, ge=0, le=MAX_AMOUNT)
    acquired: Optional[bool] = None


class PartOut(BaseModel):
    id: int
    name: str
    quantity: int
    source: PartSource
    unit_cost: Optional[int]  # hidden (null) from technicians
    unit_price: Optional[int]
    acquired: bool
    added_by: str
    created_at: datetime


class PaymentCreate(BaseModel):
    amount: int = PField(gt=0, le=MAX_AMOUNT)
    method: PaymentMethod = PaymentMethod.cash
    reference: str = PField("", max_length=60)


class PaymentOut(BaseModel):
    id: int
    amount: int
    method: PaymentMethod
    reference: str
    received_by: str
    created_at: datetime


class RepairOut(BaseModel):
    id: int
    ticket_code: str
    customer_name: str
    imei: str
    brand: str
    model: str
    service_type: str
    service_details: str
    assigned_to: str
    status: Status
    progress: int
    estimated_completion: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    collected_at: Optional[datetime] = None
    money: Optional[MoneyOut] = None  # null for technicians
    sms_sent: Optional[bool] = None  # only set when a request tried to send an SMS


class RepairDetail(RepairOut):
    parts: list[PartOut]
    payments: list[PaymentOut]


class BulkSMS(BaseModel):
    message: str = PField(min_length=1, max_length=1000)
    phones: Optional[list[str]] = None  # None = all customers
