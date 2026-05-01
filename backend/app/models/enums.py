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


class OpportunitySignalType(str, Enum):
    PRICING_CONCERN = "pricing_concern"
    COMPETITOR = "competitor"
    OBJECTION = "objection"
    NO_TOUCH = "no_touch"
    DISCOUNT_RISK = "discount_risk"
    SLA_BREACH = "sla_breach"
    POSITIVE = "positive"
    WORKFLOW_TRIGGERED = "workflow_triggered"
    COACHING_NEEDED = "coaching_needed"
    STAGE_CHANGE = "stage_change"
    EMAIL_PARSED = "email_parsed"
    EXPANSION_SIGNAL = "expansion_signal"
    PLAYBOOK_COMPLETED = "playbook_completed"


class OpportunitySignalSeverity(str, Enum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


class TaskStatus(str, Enum):
    OPEN = "open"
    DONE = "done"
    DISMISSED = "dismissed"


class TaskSource(str, Enum):
    MANUAL = "manual"
    RULE = "rule"
    AI = "ai"


class TaskPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class InvoiceStatus(str, Enum):
    """Invoice lifecycle. Mirrors the inline string set previously
    used in invoices.py (audit A-7) so transitions can be type-checked."""

    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    OVERDUE = "overdue"
    VOIDED = "voided"
