"""Capture lifecycle: record -> transcribe -> extract -> clarify/correct -> confirm -> commit.

Rules enforced here:
* Provider (network) calls never run inside a database transaction.
* ``POST /captures`` and ``/confirm`` are idempotent; other edits are guarded by revision.
* AI output only proposes; business tables change solely in ``_commit`` after validation.
* TTS happens after commit and can never fail it.
"""

from __future__ import annotations

import copy
import hashlib
import logging
import re
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..audio import extension_for, prepare_wav_segments
from ..config import Settings
from ..domain.answers import interpret_answer
from ..domain.dates import today_in
from ..domain.draft import Catalog, CustomerRef, ProductRef, apply_ops, build_draft, llm_view, validate
from ..domain.i18n import render_confirmation, render_question
from ..domain.languages import LanguageProfile, get_profile
from ..domain.units import unit_price
from ..errors import ApiError, require
from ..models import (
    AuditLog, Capture, CaptureDraft, Collection, Commitment, CompetitorNote, Complaint, Customer,
    IdempotencyKey, Order, OrderItem, Organization, OutboxEvent, Product, ReplyAudio, Visit, utcnow,
)
from ..providers.base import ExtractionContext, ProviderError, Providers
from ..schemas_llm import PatchOp
from ..security import Principal
from ..storage import AudioStore

LOGGER = logging.getLogger("bolbazaar.captures")
KEY_RX = re.compile(r"[A-Za-z0-9._:-]{8,200}")
EDITABLE = {"NEEDS_CLARIFICATION", "READY_FOR_REVIEW"}


def _sha(*parts: Any) -> str:
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()


def _provider_error(stage: str, error: ProviderError, capture_id: str | None = None) -> ApiError:
    category = error.category
    if category == "empty_transcript":
        return ApiError(422, "NO_SPEECH", "No speech was detected. Please record again.", {"captureId": capture_id})
    if category == "unsupported_audio":
        return ApiError(400, "UNSUPPORTED_AUDIO", str(error), {"captureId": capture_id})
    status = 503 if error.retryable or category in {"credits", "budget", "network", "rate_limit"} else 502
    return ApiError(status, "PROVIDER_ERROR", "The voice service could not process this request",
                    {"stage": stage, "category": category, "captureId": capture_id, "retryable": True})


class CaptureService:
    def __init__(self, sf: sessionmaker[Session], providers: Providers, settings: Settings, store: AudioStore) -> None:
        self.sf, self.providers, self.settings, self.store = sf, providers, settings, store

    # ------------------------------------------------------------------ helpers

    def _catalog(self, s: Session, user: Principal) -> tuple[Catalog, Organization]:
        org = s.get(Organization, user.org_id)
        require(org, 404, "ORG_NOT_FOUND", "Organisation not found")
        query = select(Customer).where(Customer.org_id == user.org_id, Customer.active.is_(True))
        if user.role == "rep":
            query = query.where(Customer.territory_id == user.territory_id)
        customers = [CustomerRef(c.id, c.name, tuple(a.alias for a in c.aliases)) for c in s.scalars(query)]
        products = [ProductRef(p.id, p.name, tuple(a.alias for a in p.aliases), p.base_unit, p.units_per_pack, p.price_paise)
                    for p in s.scalars(select(Product).where(Product.org_id == user.org_id, Product.active.is_(True)))]
        return Catalog(customers, products, today_in(org.timezone)), org

    @staticmethod
    def _context(cat: Catalog, language: str) -> ExtractionContext:
        return ExtractionContext(
            today=cat.today, weekday=cat.today.strftime("%A"), language=language,
            customers=[{"name": c.name, "aliases": list(c.aliases)} for c in cat.customers.values()],
            products=[{"name": p.name, "aliases": list(p.aliases)} for p in cat.products.values()])

    @staticmethod
    def _load(s: Session, user: Principal, capture_id: str, *, write: bool) -> Capture:
        cap = s.get(Capture, capture_id)
        if cap is None or cap.org_id != user.org_id or (user.role == "rep" and cap.rep_id != user.id):
            raise ApiError(404, "CAPTURE_NOT_FOUND", "Capture was not found")
        if write and cap.rep_id != user.id:
            raise ApiError(403, "FORBIDDEN", "Only the recording rep can change this capture")
        return cap

    @staticmethod
    def _check_revision(cap: Capture, revision: int) -> None:
        require(revision == cap.revision, 409, "STALE_REVISION", "The draft changed; refresh and retry",
                {"currentRevision": cap.revision})

    @staticmethod
    def _require_key(key: str) -> None:
        require(KEY_RX.fullmatch(key or ""), 400, "IDEMPOTENCY_KEY_REQUIRED",
                "A valid Idempotency-Key header is required")

    def _audit(self, s: Session, org_id: str, actor: str | None, action: str, entity: str, entity_id: str,
               meta: dict[str, Any] | None = None) -> None:
        s.add(AuditLog(org_id=org_id, actor_id=actor, action=action, entity=entity, entity_id=entity_id, meta=meta or {}))

    def _set(self, capture_id: str, **fields: Any) -> None:
        with self.sf.begin() as s:
            cap = s.get(Capture, capture_id)
            for name, value in fields.items():
                setattr(cap, name, value)

    def _latest(self, s: Session, cap: Capture) -> CaptureDraft | None:
        return s.get(CaptureDraft, (cap.id, cap.revision)) if cap.revision else None

    def _save_revision(self, s: Session, cap: Capture, draft: dict[str, Any], issues: list[dict[str, Any]]) -> None:
        cap.revision += 1
        s.add(CaptureDraft(capture_id=cap.id, revision=cap.revision, payload=draft, issues=issues))
        cap.state = "NEEDS_CLARIFICATION" if issues else "READY_FOR_REVIEW"

    def _view(self, s: Session, cap: Capture) -> dict[str, Any]:
        row = self._latest(s, cap)
        profile = get_profile(cap.language)
        clarification = None
        if row and row.issues and cap.state == "NEEDS_CLARIFICATION":
            issue = row.issues[0]
            clarification = {
                "code": issue["code"], "fieldPath": issue["fieldPath"], "answerPath": issue["answerPath"],
                "answerType": issue["answerType"], "options": issue["options"],
                "question": render_question(profile.code, issue, row.payload),
            }
        reply = s.scalar(select(ReplyAudio).where(ReplyAudio.capture_id == cap.id))
        return {
            "id": cap.id, "state": cap.state, "revision": cap.revision, "language": cap.language,
            "source": cap.source, "transcript": cap.transcript,
            "draft": row.payload if row else None,
            "openIssues": [i["code"] for i in row.issues] if row else [],
            "clarification": clarification,
            "error": {"stage": cap.error_stage, "category": cap.error_category} if cap.error_category else None,
            "visitId": cap.committed_visit_id,
            "reply": self._reply_view(reply, cap.id),
            "createdAt": cap.created_at.isoformat(),
        }

    @staticmethod
    def _reply_view(reply: ReplyAudio | None, capture_id: str) -> dict[str, Any] | None:
        if reply is None:
            return None
        return {"status": reply.status, "text": reply.text,
                "url": f"/v1/captures/{capture_id}/reply-audio" if reply.status == "READY" else None}

    # ------------------------------------------------------------------ create / process

    def create_capture(self, user: Principal, key: str, *, audio: bytes | None, content_type: str | None,
                       filename: str | None, transcript: str | None, language: str,
                       customer_hint_id: str | None, captured_at: str | None) -> dict[str, Any]:
        self._require_key(key)
        profile = get_profile(language)
        transcript = (transcript or "").strip() or None
        require(audio or transcript, 400, "INVALID_CAPTURE", "Provide an audio recording or a transcript")
        ext = None
        if audio:
            require(len(audio) <= self.settings.max_audio_bytes, 413, "AUDIO_TOO_LARGE", "Recording is too large")
            ext = extension_for(filename, content_type)
            require(ext, 400, "UNSUPPORTED_AUDIO", "Unsupported audio type")
        fingerprint = _sha(profile.code, hashlib.sha256(audio).hexdigest() if audio else transcript, customer_hint_id or "")
        scope = f"{user.id}:capture:{key}"
        captured = None
        if captured_at:
            try:
                captured = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            except ValueError:
                captured = None

        capture_id: str | None = None
        for _ in range(2):
            try:
                with self.sf.begin() as s:
                    existing = s.get(IdempotencyKey, scope)
                    if existing:
                        require(existing.fingerprint == fingerprint, 409, "IDEMPOTENCY_CONFLICT",
                                "This Idempotency-Key was used with different content")
                        capture_id = existing.ref_id
                    else:
                        cap = Capture(org_id=user.org_id, rep_id=user.id, state="RECORDED", language=profile.code,
                                      source="audio" if audio else "text", transcript=None if audio else transcript,
                                      audio_ext=ext, customer_hint_id=customer_hint_id, client_captured_at=captured)
                        s.add(cap)
                        s.flush()
                        if audio:
                            cap.audio_key = f"captures/{cap.id}.{ext}"
                            self.store.save(cap.audio_key, audio)
                        s.add(IdempotencyKey(scope=scope, fingerprint=fingerprint, ref_id=cap.id))
                        self._audit(s, user.org_id, user.id, "CAPTURE_CREATED", "capture", cap.id, {"source": cap.source})
                        capture_id = cap.id
                break
            except IntegrityError:
                continue
        require(capture_id, 409, "CONFLICT", "Please retry")

        with self.sf() as s:
            state = s.get(Capture, capture_id).state
        if state in {"RECORDED", "FAILED"}:
            return self._process(user, capture_id)
        return self.get_view(user, capture_id)

    def retry(self, user: Principal, capture_id: str) -> dict[str, Any]:
        with self.sf() as s:
            cap = self._load(s, user, capture_id, write=True)
            require(cap.state in {"FAILED", "RECORDED"}, 409, "INVALID_STATE", "Only a failed capture can be retried")
        return self._process(user, capture_id)

    def _transcribe(self, audio: bytes, profile: LanguageProfile) -> str:
        segments = prepare_wav_segments(audio, max_segment_s=self.settings.gnani_max_segment_seconds,
                                        max_total_s=self.settings.max_audio_seconds)
        return " ".join(self.providers.stt.transcribe(seg, profile).text for seg in segments).strip()

    def _fail(self, capture_id: str, stage: str, error: ProviderError) -> ApiError:
        self._set(capture_id, state="FAILED", error_category=error.category, error_stage=stage)
        LOGGER.warning("capture_failed capture=%s stage=%s category=%s", capture_id, stage, error.category)
        return _provider_error(stage, error, capture_id)

    def _process(self, user: Principal, capture_id: str) -> dict[str, Any]:
        with self.sf() as s:
            cap = s.get(Capture, capture_id)
            profile, transcript, audio_key, hint = get_profile(cap.language), cap.transcript, cap.audio_key, cap.customer_hint_id
        if transcript is None:
            self._set(capture_id, state="TRANSCRIBING", error_category=None, error_stage=None)
            audio = self.store.load(audio_key) if audio_key else None
            if audio is None:
                raise self._fail(capture_id, "stt", ProviderError("unsupported_audio", "The recording is no longer available"))
            try:
                transcript = self._transcribe(audio, profile)
            except ProviderError as error:
                raise self._fail(capture_id, "stt", error) from error
            self._set(capture_id, transcript=transcript)
        self._set(capture_id, state="EXTRACTING", error_category=None, error_stage=None)
        with self.sf() as s:
            cat, _org = self._catalog(s, user)
        try:
            extraction = self.providers.reasoner.extract(transcript, self._context(cat, profile.code))
        except ProviderError as error:
            raise self._fail(capture_id, "llm", error) from error
        draft = build_draft(extraction, cat, hint)
        issues = validate(draft, cat)
        with self.sf.begin() as s:
            cap = s.get(Capture, capture_id)
            self._save_revision(s, cap, draft, issues)
            self._audit(s, user.org_id, user.id, "DRAFT_CREATED", "capture", capture_id, {"issues": len(issues)})
            return self._view(s, cap)

    # ------------------------------------------------------------------ reads

    def get_view(self, user: Principal, capture_id: str) -> dict[str, Any]:
        with self.sf() as s:
            return self._view(s, self._load(s, user, capture_id, write=False))

    def list_captures(self, user: Principal, limit: int = 20) -> list[dict[str, Any]]:
        with self.sf() as s:
            query = select(Capture).where(Capture.org_id == user.org_id).order_by(Capture.created_at.desc()).limit(limit)
            if user.role == "rep":
                query = query.where(Capture.rep_id == user.id)
            return [{"id": c.id, "state": c.state, "language": c.language, "revision": c.revision,
                     "createdAt": c.created_at.isoformat(), "visitId": c.committed_visit_id} for c in s.scalars(query)]

    # ------------------------------------------------------------------ edit: answers and corrections

    def _apply(self, user: Principal, capture_id: str, revision: int, ops: list[PatchOp]) -> dict[str, Any]:
        try:
            with self.sf.begin() as s:
                cap = self._load(s, user, capture_id, write=True)
                require(cap.state in EDITABLE, 409, "INVALID_STATE", f"Capture is {cap.state} and cannot be edited")
                self._check_revision(cap, revision)
                row = self._latest(s, cap)
                cat, _org = self._catalog(s, user)
                new_draft, changes, failures = apply_ops(copy.deepcopy(row.payload), ops, cat)
                if not changes:
                    return {**self._view(s, cap), "patch": [], "unsupported": failures}
                self._save_revision(s, cap, new_draft, validate(new_draft, cat))
                self._audit(s, user.org_id, user.id, "DRAFT_EDITED", "capture", capture_id,
                            {"paths": [c["path"] for c in changes], "revision": cap.revision})
                return {**self._view(s, cap), "patch": changes, "unsupported": failures}
        except IntegrityError as error:
            raise ApiError(409, "STALE_REVISION", "The draft changed; refresh and retry") from error

    def answer(self, user: Principal, capture_id: str, revision: int, value: Any) -> dict[str, Any]:
        with self.sf() as s:
            cap = self._load(s, user, capture_id, write=True)
            require(cap.state == "NEEDS_CLARIFICATION", 409, "NO_OPEN_QUESTION", "There is no open question")
            self._check_revision(cap, revision)
            issue = self._latest(s, cap).issues[0]
        if issue["answerType"] == "number":
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ApiError(400, "INVALID_ANSWER", "Please answer with a number") from None
        require(value not in (None, ""), 400, "INVALID_ANSWER", "An answer is required")
        return self._apply(user, capture_id, revision, [PatchOp(op="set", path=issue["answerPath"], value=value)])

    def correct_text(self, user: Principal, capture_id: str, revision: int, utterance: str) -> dict[str, Any]:
        utterance = (utterance or "").strip()
        require(utterance, 400, "INVALID_CORRECTION", "Nothing to apply")
        with self.sf() as s:
            cap = self._load(s, user, capture_id, write=True)
            require(cap.state in EDITABLE, 409, "INVALID_STATE", f"Capture is {cap.state} and cannot be edited")
            self._check_revision(cap, revision)
            row = self._latest(s, cap)
            cat, _org = self._catalog(s, user)
            draft, issues, language = copy.deepcopy(row.payload), list(row.issues), cap.language
        ops = interpret_answer(utterance, issues[0], cat) if issues else None
        unsupported: list[str] = []
        if ops is None:
            try:
                result = self.providers.reasoner.patch(llm_view(draft), utterance, self._context(cat, language))
            except ProviderError as error:
                raise _provider_error("llm", error, capture_id) from error
            ops, unsupported = result.ops, list(result.unsupported)
        outcome = self._apply(user, capture_id, revision, ops)
        outcome["unsupported"] = unsupported + outcome["unsupported"]
        outcome["utterance"] = utterance
        return outcome

    def correct_audio(self, user: Principal, capture_id: str, revision: int, audio: bytes,
                      content_type: str | None, filename: str | None) -> dict[str, Any]:
        require(len(audio) <= self.settings.max_audio_bytes, 413, "AUDIO_TOO_LARGE", "Recording is too large")
        require(extension_for(filename, content_type), 400, "UNSUPPORTED_AUDIO", "Unsupported audio type")
        with self.sf() as s:
            cap = self._load(s, user, capture_id, write=True)
            self._check_revision(cap, revision)
            profile = get_profile(cap.language)
        try:
            text = self._transcribe(audio, profile)
        except ProviderError as error:
            raise _provider_error("stt", error, capture_id) from error
        return self.correct_text(user, capture_id, revision, text)

    def cancel(self, user: Principal, capture_id: str) -> dict[str, Any]:
        with self.sf.begin() as s:
            cap = self._load(s, user, capture_id, write=True)
            require(cap.state not in {"COMMITTED", "CANCELLED"}, 409, "INVALID_STATE", "Capture cannot be cancelled")
            cap.state = "CANCELLED"
            self._audit(s, user.org_id, user.id, "CAPTURE_CANCELLED", "capture", capture_id)
            return self._view(s, cap)

    # ------------------------------------------------------------------ confirm / commit

    def confirm(self, user: Principal, capture_id: str, key: str, revision: int, speak_reply: bool = True) -> dict[str, Any]:
        self._require_key(key)
        scope = f"{user.id}:confirm:{capture_id}:{key}"
        fingerprint = _sha(capture_id, revision, speak_reply)
        committed: dict[str, Any] | None = None
        for _ in range(2):
            try:
                with self.sf.begin() as s:
                    existing = s.get(IdempotencyKey, scope)
                    if existing:
                        require(existing.fingerprint == fingerprint, 409, "IDEMPOTENCY_CONFLICT",
                                "This Idempotency-Key was used with different content")
                        committed = existing.response
                    else:
                        cap = self._load(s, user, capture_id, write=True)
                        require(cap.state != "COMMITTED", 409, "ALREADY_COMMITTED", "This visit was already saved")
                        require(cap.state == "READY_FOR_REVIEW", 409, "INVALID_STATE",
                                f"Capture is {cap.state}; resolve open questions first")
                        self._check_revision(cap, revision)
                        row = self._latest(s, cap)
                        cat, _org = self._catalog(s, user)
                        issues = validate(row.payload, cat)
                        require(not issues, 422, "DRAFT_INVALID", "The draft no longer passes validation",
                                [i["code"] for i in issues])
                        committed = self._commit(s, user, cap, row.payload)
                        s.add(IdempotencyKey(scope=scope, fingerprint=fingerprint, ref_id=cap.id, response=committed))
                break
            except IntegrityError:
                committed = None
                continue
        require(committed, 409, "CONFLICT", "Please retry")
        reply = self._reply(capture_id, committed["confirmationText"], get_profile(committed["language"]), speak_reply)
        return {**committed, "reply": reply}

    def _commit(self, s: Session, user: Principal, cap: Capture, draft: dict[str, Any]) -> dict[str, Any]:
        customer = s.get(Customer, draft["customer"]["customerId"])
        require(customer and customer.org_id == user.org_id, 422, "CUSTOMER_INVALID", "Customer is not available")
        visit = Visit(org_id=user.org_id, capture_id=cap.id, rep_id=cap.rep_id, customer_id=customer.id,
                      visited_at=cap.client_captured_at or utcnow(), purpose=draft["visit"].get("purpose"),
                      summary=draft["visit"].get("summary"))
        s.add(visit)
        s.flush()

        order_id, order_total, items = None, 0, draft["order"]["items"]
        if items:
            order = Order(org_id=user.org_id, visit_id=visit.id, rep_id=cap.rep_id, customer_id=customer.id,
                          status="CONFIRMED", total_paise=0,
                          delivery_date=date.fromisoformat(draft["order"]["deliveryDate"]) if draft["order"].get("deliveryDate") else None)
            for item in items:
                product = s.get(Product, item["productId"])
                require(product and product.org_id == user.org_id and product.active, 422, "PRODUCT_INVALID",
                        "A product is no longer available")
                price = unit_price(product.price_paise, item["unit"], product.base_unit, product.units_per_pack)
                require(price is not None and item["quantity"] > 0, 422, "ITEM_INVALID", "An order line is invalid")
                line = item["quantity"] * price  # server-side truth, never the client's number
                order_total += line
                order.items.append(OrderItem(product_id=product.id, spoken_name=item["spokenName"], quantity=item["quantity"],
                                             unit=item["unit"], unit_price_paise=price, line_total_paise=line))
            order.total_paise = order_total
            s.add(order)
            s.flush()
            order_id = order.id
            customer.outstanding_paise += order_total

        collection_ids = []
        for col in draft["collections"]:
            row = Collection(visit_id=visit.id, customer_id=customer.id, amount_paise=col["amountPaise"], kind=col["kind"],
                             due_date=date.fromisoformat(col["dueDate"]) if col.get("dueDate") else None)
            s.add(row)
            s.flush()
            collection_ids.append(row.id)
            if col["kind"] == "received":
                customer.outstanding_paise = max(0, customer.outstanding_paise - col["amountPaise"])
        for c in draft["complaints"]:
            s.add(Complaint(visit_id=visit.id, customer_id=customer.id, product_id=c.get("productId"),
                            category=c["category"], description=c["description"]))
        for n in draft["competitorNotes"]:
            s.add(CompetitorNote(visit_id=visit.id, competitor=n["competitor"], note=n["note"]))
        commitment_ids = []
        for c in draft["commitments"]:
            row = Commitment(org_id=user.org_id, visit_id=visit.id, customer_id=customer.id, owner_rep_id=cap.rep_id,
                             action_type=c["actionType"], description=c["description"],
                             due_date=date.fromisoformat(c["dueDate"]), priority=c["priority"], source_phrase=c.get("evidence"))
            s.add(row)
            s.flush()
            commitment_ids.append(row.id)

        cap.state, cap.committed_visit_id = "COMMITTED", visit.id
        s.add(OutboxEvent(org_id=user.org_id, type="VISIT_COMMITTED", aggregate_id=visit.id,
                          payload={"captureId": cap.id, "orderId": order_id}))
        self._audit(s, user.org_id, user.id, "VISIT_COMMITTED", "visit", visit.id,
                    {"orderId": order_id, "commitments": len(commitment_ids)})
        text = render_confirmation(cap.language, customer=customer.name, items=len(items),
                                   total_paise=order_total, follow_ups=len(commitment_ids))
        return {"captureId": cap.id, "visitId": visit.id, "orderId": order_id, "orderTotalPaise": order_total,
                "collectionIds": collection_ids, "commitmentIds": commitment_ids,
                "customer": {"id": customer.id, "name": customer.name},
                "confirmationText": text, "language": cap.language}

    # ------------------------------------------------------------------ speech output (never inside a transaction)

    def _reply(self, capture_id: str, text: str, profile: LanguageProfile, speak: bool) -> dict[str, Any]:
        with self.sf() as s:
            row = s.scalar(select(ReplyAudio).where(ReplyAudio.capture_id == capture_id))
            if row:
                return self._reply_view(row, capture_id)
        if not speak:
            return {"status": "SKIPPED", "text": text, "url": None}
        status, key, model, category = "READY", f"replies/{capture_id}.wav", None, None
        try:
            speech = self.providers.tts.synthesize(text, profile)
            self.store.save(key, speech.audio)
            model = speech.model
        except Exception as error:  # noqa: BLE001 - TTS must never fail an already-committed visit
            status, key = "FAILED", None
            category = error.category if isinstance(error, ProviderError) else "unexpected"
            LOGGER.warning("reply_tts_failed capture=%s category=%s", capture_id, category)
        row = ReplyAudio(capture_id=capture_id, audio_key=key, text=text, language=profile.code, model=model,
                         status=status, error_category=category)
        try:
            with self.sf.begin() as s:
                s.add(row)
        except IntegrityError:
            pass
        return self._reply_view(row, capture_id)

    def reply_audio(self, user: Principal, capture_id: str) -> tuple[bytes, str]:
        with self.sf() as s:
            self._load(s, user, capture_id, write=False)
            row = s.scalar(select(ReplyAudio).where(ReplyAudio.capture_id == capture_id))
        data = self.store.load(row.audio_key) if row and row.status == "READY" and row.audio_key else None
        require(data, 404, "AUDIO_NOT_FOUND", "Spoken confirmation is not available")
        return data, "audio/wav"

    def question_audio(self, user: Principal, capture_id: str) -> tuple[bytes, str]:
        with self.sf() as s:
            cap = self._load(s, user, capture_id, write=False)
            view = self._view(s, cap)
            profile = get_profile(cap.language)
        require(view["clarification"], 404, "NO_OPEN_QUESTION", "There is no open question")
        text = view["clarification"]["question"]
        key = f"questions/{_sha(profile.code, text)}.wav"
        data = self.store.load(key)
        if data is None:
            try:
                data = self.providers.tts.synthesize(text, profile).audio
            except ProviderError as error:
                raise _provider_error("tts", error, capture_id) from error
            self.store.save(key, data)
        return data, "audio/wav"
