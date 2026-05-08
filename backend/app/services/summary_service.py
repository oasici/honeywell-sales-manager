"""Summary service (Sprint 6).

Provides grounded summaries for opportunities, quotes, and customers with:
- PII redaction guard
- max token / max context policy (char-based enforcement)
- optional Redis-backed rate limit + cache friendliness (cache is handled by API layer today)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.email_request import EmailRequest
from app.models.opportunity import Opportunity, OpportunityEvent
from app.models.quote import Quote


# Round-8 R8-SEC-1 — patterns moved to ``app.services.pii_utils``.
# Re-exported here so existing import sites keep working.
from app.services.pii_utils import redact_pii  # noqa: F401


@dataclass(frozen=True)
class SummaryResult:
    summary: str
    sources: list[dict]
    generated_at: str


class SummaryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def summarize(self, entity_type: str, entity_id: int, focus: str | None = None) -> SummaryResult:
        sources: list[dict] = []
        context_text = await self._build_context(entity_type, entity_id, sources)
        context_text = redact_pii(context_text)

        focus_instruction = f"\nOdak noktasi: {focus}" if focus else ""
        prompt = (
            "Asagidaki satis verisini 3-5 cumleyle ozetle. "
            "Turkce yaz. Asla email/telefon gibi PII tekrar etme. "
            "Aksiyon odakli ol.\n"
            f"{focus_instruction}\n\n{context_text}"
        )

        # Call Claude via the existing helper (keeps retries/model settings centralized).
        from app.api.v1.ai import _call_claude, _generate_fallback_summary, CONTEXT_MAX_CHARS

        summary = await _call_claude(
            system_prompt=(
                "Sen bir satis asistanisin. Turkce, kisa ve aksiyona yonelik ozetler uretirsin. "
                "PII (email/telefon) ciktiya dahil ETME."
            ),
            user_prompt=prompt[: (CONTEXT_MAX_CHARS + 500)],
        )
        if not summary:
            summary = _generate_fallback_summary(entity_type, entity_id, context_text)

        summary = redact_pii(summary)[:2000]

        return SummaryResult(
            summary=summary,
            sources=sources,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _build_context(self, entity_type: str, entity_id: int, sources: list[dict]) -> str:
        if entity_type == "opportunity":
            opp = (
                await self.db.execute(select(Opportunity).where(Opportunity.id == entity_id))
            ).scalar_one_or_none()
            if not opp:
                raise NotFoundException("Firsat bulunamadi")

            events = (
                await self.db.execute(
                    select(OpportunityEvent)
                    .where(OpportunityEvent.opportunity_id == opp.id)
                    .order_by(OpportunityEvent.occurred_at.desc())
                    .limit(20)
                )
            ).scalars().all()

            quotes = (
                await self.db.execute(select(Quote).where(Quote.opportunity_id == opp.id))
            ).scalars().all()

            context = (
                f"Firsat: {opp.title}\n"
                f"Asama: {opp.stage}\n"
                f"Tutar: {opp.amount} {opp.currency}\n"
                f"Musteri: {opp.customer.name if opp.customer else 'Bilinmiyor'}\n"
                f"Son guncelleme: {opp.updated_at}\n\n"
            )
            context += "Olaylar:\n" + "\n".join(
                f"- {e.event_type}: {e.description}" for e in events
            )
            context += "\n\n"
            context += f"Teklifler: {len(quotes)} adet\n"
            for q in quotes:
                context += f"- {q.quote_number} ({q.status}) {q.grand_total} {q.currency}\n"
                sources.append({"type": "quote", "id": q.id, "label": q.quote_number})

            # Inbound mail: direct opportunity_id + quote.email_request_id (S2 chain)
            direct_ids = (
                await self.db.execute(
                    select(EmailRequest.id)
                    .where(EmailRequest.opportunity_id == opp.id)
                    .order_by(EmailRequest.created_at.desc())
                    .limit(15)
                )
            ).scalars().all()
            quote_er_ids = (
                await self.db.execute(
                    select(Quote.email_request_id).where(
                        Quote.opportunity_id == opp.id,
                        Quote.email_request_id.isnot(None),
                    )
                )
            ).scalars().all()
            ordered_ids: list[int] = []
            seen_mail: set[int] = set()
            for raw in direct_ids:
                if raw is None:
                    continue
                i = int(raw)
                if i in seen_mail:
                    continue
                seen_mail.add(i)
                ordered_ids.append(i)
            for raw in quote_er_ids:
                if raw is None:
                    continue
                i = int(raw)
                if i in seen_mail:
                    continue
                seen_mail.add(i)
                ordered_ids.append(i)
                if len(ordered_ids) >= 15:
                    break
            ordered_ids = ordered_ids[:15]

            mail_rows: list[EmailRequest] = []
            if ordered_ids:
                mail_rows = list(
                    (
                        await self.db.execute(select(EmailRequest).where(EmailRequest.id.in_(ordered_ids)))
                    ).scalars().all()
                )
                rank = {mid: idx for idx, mid in enumerate(ordered_ids)}
                mail_rows.sort(key=lambda em: rank.get(em.id, 999))

            context += "\nBagli e-postalar (talep kayitlari):\n"
            if not mail_rows:
                context += "- (yok)\n"
            else:
                for em in mail_rows:
                    snippet = (em.body_text or "").strip().replace("\n", " ")[:320]
                    context += (
                        f"- id={em.id} | konu={em.subject or '(yok)'} | durum={em.status} | "
                        f"gonderen={em.from_address}\n  metin: {snippet}\n"
                    )
                    sources.append(
                        {"type": "email", "id": em.id, "label": em.subject or f"email#{em.id}"}
                    )

            return context

        if entity_type == "email":
            email = (
                await self.db.execute(select(EmailRequest).where(EmailRequest.id == entity_id))
            ).scalar_one_or_none()
            if not email:
                raise NotFoundException("Email bulunamadi")
            sources.append({"type": "email", "id": email.id, "label": email.subject})
            return f"Gonderen: {email.from_address}\nKonu: {email.subject}\n\n{email.body_text or ''}"

        if entity_type == "quote":
            quote = (
                await self.db.execute(select(Quote).where(Quote.id == entity_id))
            ).scalar_one_or_none()
            if not quote:
                raise NotFoundException("Teklif bulunamadi")
            sources.append({"type": "quote", "id": quote.id, "label": quote.quote_number})
            return (
                f"Teklif: {quote.quote_number}\n"
                f"Durum: {quote.status}\n"
                f"Toplam: {quote.grand_total} {quote.currency}\n"
                f"Kalem sayisi: {len(quote.items or [])}"
            )

        if entity_type == "customer":
            from app.models.customer import Customer

            customer = (
                await self.db.execute(select(Customer).where(Customer.id == entity_id))
            ).scalar_one_or_none()
            if not customer:
                raise NotFoundException("Musteri bulunamadi")

            cust_quotes = (
                await self.db.execute(
                    select(Quote)
                    .where(Quote.customer_id == customer.id)
                    .order_by(Quote.created_at.desc())
                    .limit(10)
                )
            ).scalars().all()
            cust_opps = (
                await self.db.execute(
                    select(Opportunity)
                    .where(Opportunity.customer_id == customer.id)
                    .order_by(Opportunity.created_at.desc())
                    .limit(10)
                )
            ).scalars().all()
            cust_emails = (
                await self.db.execute(
                    select(EmailRequest)
                    .where(EmailRequest.customer_id == customer.id)
                    .order_by(EmailRequest.created_at.desc())
                    .limit(5)
                )
            ).scalars().all()

            sources.append({"type": "customer", "id": customer.id, "label": customer.name})
            context = (
                f"Musteri: {customer.name}\n"
                f"Sirket: {customer.company or '-'}\n"
                f"Email: {customer.email or '-'}\n"
                f"Telefon: {customer.phone or '-'}\n\n"
            )
            context += f"Teklifler: {len(cust_quotes)} adet\n"
            for q in cust_quotes[:5]:
                context += f"  - {q.quote_number} ({q.status}) {q.grand_total} {q.currency}\n"
            context += f"\nFirsatlar: {len(cust_opps)} adet\n"
            for o in cust_opps[:5]:
                context += f"  - {o.title} ({o.stage}) {o.amount} {o.currency}\n"
            context += f"\nSon Emailler: {len(cust_emails)} adet\n"
            for e in cust_emails[:3]:
                context += f"  - {e.subject} ({e.status})\n"
            return context

        raise BadRequestException(
            "Gecersiz entity_type. Desteklenen: opportunity, email, quote, customer"
        )

    @staticmethod
    def _touch_source(sources: list[dict], seen: set[tuple[str, int]], item: dict) -> None:
        key = (str(item["type"]), int(item["id"]))
        if key in seen:
            return
        seen.add(key)
        sources.append(item)

    async def summarize_changes(self, entity_type: str, entity_id: int, days: int = 7) -> SummaryResult:
        """Grounded 'what changed in the last N days' summary (Sprint 6)."""
        if days < 1 or days > 90:
            raise BadRequestException("Gun araligi 1-90 arasinda olmalidir")
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        sources: list[dict] = []
        context_text = await self._build_changes_context(entity_type, entity_id, days, cutoff, sources)
        context_text = redact_pii(context_text)

        focus_instruction = f"\nZaman penceresi: son {days} gun."
        prompt = (
            "Asagidaki veri SADECE son gunlerde degisen kayitlari iceriyor. "
            "Degisiklikleri 3-6 cumleyle ozetle: ne oldu, risk/firsat, onerilen sonraki adim. "
            "Turkce yaz. PII (email/telefon) tekrar etme.\n"
            f"{focus_instruction}\n\n{context_text}"
        )

        from app.api.v1.ai import CONTEXT_MAX_CHARS, _call_claude, _generate_fallback_summary

        summary = await _call_claude(
            system_prompt=(
                "Sen satis asistanisin. Kisa Turkce degisim ozeti uretirsin; PII yazma."
            ),
            user_prompt=prompt[: (CONTEXT_MAX_CHARS + 500)],
        )
        if not summary:
            summary = _generate_fallback_summary(entity_type, entity_id, context_text)

        summary = redact_pii(summary)[:2000]

        return SummaryResult(
            summary=summary,
            sources=sources,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    async def _build_changes_context(
        self,
        entity_type: str,
        entity_id: int,
        days: int,
        cutoff: datetime,
        sources: list[dict],
    ) -> str:
        seen: set[tuple[str, int]] = set()

        if entity_type == "opportunity":
            opp = (
                await self.db.execute(select(Opportunity).where(Opportunity.id == entity_id))
            ).scalar_one_or_none()
            if not opp:
                raise NotFoundException("Firsat bulunamadi")

            self._touch_source(
                sources, seen, {"type": "opportunity", "id": opp.id, "label": opp.title or f"#{opp.id}"}
            )

            events = (
                await self.db.execute(
                    select(OpportunityEvent)
                    .where(
                        OpportunityEvent.opportunity_id == opp.id,
                        OpportunityEvent.occurred_at >= cutoff,
                    )
                    .order_by(OpportunityEvent.occurred_at.desc())
                    .limit(50)
                )
            ).scalars().all()

            quotes_changed = (
                await self.db.execute(
                    select(Quote).where(
                        Quote.opportunity_id == opp.id,
                        Quote.updated_at >= cutoff,
                    )
                )
            ).scalars().all()

            direct_mail = (
                await self.db.execute(
                    select(EmailRequest)
                    .where(
                        EmailRequest.opportunity_id == opp.id,
                        EmailRequest.created_at >= cutoff,
                    )
                    .order_by(EmailRequest.created_at.desc())
                    .limit(20)
                )
            ).scalars().all()

            quote_er_ids = (
                await self.db.execute(
                    select(Quote.email_request_id).where(
                        Quote.opportunity_id == opp.id,
                        Quote.email_request_id.isnot(None),
                        Quote.updated_at >= cutoff,
                    )
                )
            ).scalars().all()
            mail_via_quote: list[EmailRequest] = []
            er_ids = [int(x) for x in quote_er_ids if x is not None]
            if er_ids:
                mail_via_quote = list(
                    (await self.db.execute(select(EmailRequest).where(EmailRequest.id.in_(er_ids))))
                    .scalars()
                    .all()
                )

            ctx = (
                f"Firsat: {opp.title}\n"
                f"Asama: {opp.stage}\n"
                f"Tutar: {opp.amount} {opp.currency}\n"
                f"Son {days} gunde guncellenen kayitlar:\n\n"
            )
            ctx += f"Olaylar ({len(events)}):\n"
            if not events:
                ctx += "- (yok)\n"
            else:
                for e in events:
                    ctx += (
                        f"- {e.occurred_at.isoformat() if e.occurred_at else ''} | "
                        f"{e.event_type}: {e.description or ''}\n"
                    )

            ctx += f"\nTeklif guncellemeleri ({len(quotes_changed)}):\n"
            if not quotes_changed:
                ctx += "- (yok)\n"
            else:
                for q in quotes_changed:
                    ctx += f"- {q.quote_number} ({q.status}) guncelleme: {q.updated_at}\n"
                    self._touch_source(
                        sources, seen, {"type": "quote", "id": q.id, "label": q.quote_number}
                    )

            ctx += f"\nYeni / guncel bagli e-postalar ({len(direct_mail) + len(mail_via_quote)}):\n"
            merged_mail = {em.id: em for em in direct_mail}
            for em in mail_via_quote:
                merged_mail.setdefault(em.id, em)
            mail_list = sorted(merged_mail.values(), key=lambda m: m.created_at or cutoff, reverse=True)
            if not mail_list:
                ctx += "- (yok)\n"
            else:
                for em in mail_list[:20]:
                    snippet = (em.body_text or "").strip().replace("\n", " ")[:280]
                    ctx += (
                        f"- id={em.id} | konu={em.subject or '(yok)'} | durum={em.status} | "
                        f"olusturma={em.created_at}\n  metin: {snippet}\n"
                    )
                    self._touch_source(
                        sources,
                        seen,
                        {"type": "email", "id": em.id, "label": em.subject or f"email#{em.id}"},
                    )

            return ctx

        if entity_type == "customer":
            from app.models.customer import Customer

            customer = (
                await self.db.execute(select(Customer).where(Customer.id == entity_id))
            ).scalar_one_or_none()
            if not customer:
                raise NotFoundException("Musteri bulunamadi")

            self._touch_source(
                sources,
                seen,
                {"type": "customer", "id": customer.id, "label": customer.name or f"#{customer.id}"},
            )

            cust_quotes = (
                await self.db.execute(
                    select(Quote)
                    .where(Quote.customer_id == customer.id, Quote.updated_at >= cutoff)
                    .order_by(Quote.updated_at.desc())
                    .limit(15)
                )
            ).scalars().all()

            cust_emails = (
                await self.db.execute(
                    select(EmailRequest)
                    .where(EmailRequest.customer_id == customer.id, EmailRequest.created_at >= cutoff)
                    .order_by(EmailRequest.created_at.desc())
                    .limit(15)
                )
            ).scalars().all()

            rows = (
                await self.db.execute(
                    select(OpportunityEvent, Opportunity.title, Opportunity.id)
                    .join(Opportunity, Opportunity.id == OpportunityEvent.opportunity_id)
                    .where(
                        Opportunity.customer_id == customer.id,
                        OpportunityEvent.occurred_at >= cutoff,
                    )
                    .order_by(OpportunityEvent.occurred_at.desc())
                    .limit(40)
                )
            ).all()

            ctx = (
                f"Musteri: {customer.name}\n"
                f"Sirket: {customer.company or '-'}\n"
                f"Son {days} gunde hesap bazli degisiklikler:\n\n"
            )
            ctx += f"Firsat olaylari ({len(rows)}):\n"
            if not rows:
                ctx += "- (yok)\n"
            else:
                for row in rows:
                    ev = row[0]
                    title = row[1]
                    oid = row[2]
                    ctx += (
                        f"- firsat={title} (#{oid}) | {ev.occurred_at} | "
                        f"{ev.event_type}: {ev.description or ''}\n"
                    )
                    self._touch_source(
                        sources,
                        seen,
                        {"type": "opportunity", "id": int(oid), "label": title or f"#{oid}"},
                    )

            ctx += f"\nTeklif guncellemeleri ({len(cust_quotes)}):\n"
            if not cust_quotes:
                ctx += "- (yok)\n"
            else:
                for q in cust_quotes:
                    ctx += f"- {q.quote_number} ({q.status}) {q.updated_at}\n"
                    self._touch_source(
                        sources, seen, {"type": "quote", "id": q.id, "label": q.quote_number}
                    )

            ctx += f"\nE-posta kayitlari ({len(cust_emails)}):\n"
            if not cust_emails:
                ctx += "- (yok)\n"
            else:
                for em in cust_emails:
                    snippet = (em.body_text or "").strip().replace("\n", " ")[:240]
                    ctx += f"- id={em.id} | {em.subject or '(yok)'} | {em.created_at}\n  {snippet}\n"
                    self._touch_source(
                        sources,
                        seen,
                        {"type": "email", "id": em.id, "label": em.subject or f"email#{em.id}"},
                    )

            return ctx

        raise BadRequestException("Degisim ozeti yalnizca opportunity ve customer icin desteklenir")

