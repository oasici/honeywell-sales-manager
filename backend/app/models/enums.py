from enum import Enum


class QuoteStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class EmailStatus(str, Enum):
    NEW = "new"
    PARSED = "parsed"
    QUOTED = "quoted"
    SENT = "sent"
    ERROR = "error"


class ReviewStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class UserRole(str, Enum):
    SALES_REP = "sales_rep"
    SALES_MANAGER = "sales_manager"
    OPERATIONS = "operations"


class OpportunityStage(str, Enum):
    PROSPECTING = "prospecting"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"
