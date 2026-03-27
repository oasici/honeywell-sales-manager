from app.schemas.common import ErrorResponse, PaginatedResponse, SuccessResponse
from app.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserResponse
from app.schemas.customer import CustomerCreate, CustomerResponse, CustomerUpdate
from app.schemas.email_request import (
    EmailMatchResult,
    EmailParsedData,
    EmailResponse,
    ManualEmailCreate,
    ParsedPart,
)
from app.schemas.spare_part import SparePartCreate, SparePartResponse, SparePartUpdate
from app.schemas.price_entry import PriceEntryCreate, PriceEntryResponse
from app.schemas.quote import (
    QuoteCreate,
    QuoteItemCreate,
    QuoteItemResponse,
    QuoteResponse,
    QuoteUpdate,
)
from app.schemas.dashboard import DashboardStats, TopPart, TrendData

__all__ = [
    "ErrorResponse",
    "PaginatedResponse",
    "SuccessResponse",
    "LoginRequest",
    "TokenResponse",
    "UserCreate",
    "UserResponse",
    "CustomerCreate",
    "CustomerResponse",
    "CustomerUpdate",
    "EmailMatchResult",
    "EmailParsedData",
    "EmailResponse",
    "ManualEmailCreate",
    "ParsedPart",
    "SparePartCreate",
    "SparePartResponse",
    "SparePartUpdate",
    "PriceEntryCreate",
    "PriceEntryResponse",
    "QuoteCreate",
    "QuoteItemCreate",
    "QuoteItemResponse",
    "QuoteResponse",
    "QuoteUpdate",
    "DashboardStats",
    "TopPart",
    "TrendData",
]
