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
import math
import re
import threading
import time
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..audio import extension_for, looks_like_audio, prepare_wav_segments, wav_seconds
from ..config import Settings
from ..costguard import CostGuard, estimate_tokens
from .catalogue import CatalogueService
from ..domain.answers import interpret_answer
from ..domain.dates import today_in
from ..domain.draft import NEW_PRODUCT, Catalog, CustomerRef, ProductRef, apply_ops, build_draft, llm_view, validate
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
    def __init__(self, sf: sessionmaker[Session], providers: Providers, settings: Settings, store: AudioStore,
                 guard: CostGuard, catalogue: CatalogueService) -> None:
        self.sf, self.providers, self.settings, self.store, self.guard = sf, providers, settings, store, guard
        self.catalogue = catalogue
        self._locks = [threading.Lock() for _ in range(64)]  # striped: one paid call per capture/question at a time
        self._last_purge = 0.0

    def _lock_for(self, key: str) -> threading.Lock:
        return self._locks[int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % len(self._locks)]

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
        require(not transcript or len(transcript) <= self.settings.max_transcript_chars, 413, "TEXT_TOO_LONG",
                f"The text is too long (maximum {self.settings.max_transcript_chars} characters)")
        require(len(customer_hint_id or "") <= 40 and len(captured_at or "") <= 64, 422, "VALIDATION_ERROR",
                "Invalid customerId or capturedAt")
        ext = None
        if audio:
            require(len(audio) <= self.settings.max_audio_bytes, 413, "AUDIO_TOO_LARGE", "Recording is too large")
            ext = extension_for(filename, content_type)
            require(ext, 400, "UNSUPPORTED_AUDIO", "Unsupported audio type")
            require(looks_like_audio(audio), 400, "UNSUPPORTED_AUDIO", "This file is not a supported audio recording")
        self._purge_audio()
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

    def _purge_audio(self) -> None:
        """Enforce audio retention while the server runs (it used to run only at start-up)."""
        now = time.monotonic()
        if now - self._last_purge > 600:
            self._last_purge = now
            self.store.purge_older_than(self.settings.audio_retention_hours)

    def _transcribe(self, user: Principal, audio: bytes, profile: LanguageProfile) -> str:
        # Validation and duration limits run first and cost nothing; only then is quota reserved and Gnani called.
        segments = prepare_wav_segments(audio, max_segment_s=self.settings.gnani_max_segment_seconds,
                                        max_total_s=self.settings.max_audio_seconds)
        seconds = math.ceil(sum(wav_seconds(seg) for seg in segments))
        with self.guard.user_slot(user.id):
            self.guard.reserve(user.id, "stt", requests=len(segments), audio_seconds=seconds)
            texts = [self.guard.call(user.id, "gnani", lambda seg=seg: self.providers.stt.transcribe(seg, profile).text)
                     for seg in segments]
        return " ".join(texts).strip()

    def transcribe_upload(self, user: Principal, audio: bytes, content_type: str | None, filename: str | None,
                          language: str) -> str:
        """Validate and transcribe an upload for features outside the visit flow (same limits and quotas)."""
        profile = get_profile(language)
        require(audio, 400, "EMPTY_AUDIO", "The recording is empty")
        require(len(audio) <= self.settings.max_audio_bytes, 413, "AUDIO_TOO_LARGE", "Recording is too large")
        require(extension_for(filename, content_type), 400, "UNSUPPORTED_AUDIO", "Unsupported audio type")
        require(looks_like_audio(audio), 400, "UNSUPPORTED_AUDIO", "This file is not a supported audio recording")
        try:
            text = self._transcribe(user, audio, profile)
        except ProviderError as error:
            raise _provider_error("stt", error) from error
        require(text.strip(), 422, "NO_SPEECH", "No speech was detected. Please record again.")
        return text

    def _extract(self, user: Principal, transcript: str, context: ExtractionContext):
        est = estimate_tokens(transcript, str(context.customers), str(context.products))
        return self.guard.run(user.id, "llm", lambda: self.providers.reasoner.extract(transcript, context), est_tokens=est)

    def _claim(self, capture_id: str, needs_stt: bool) -> bool:
        """Atomically take ownership of processing. Of N concurrent requests exactly one wins and pays the providers."""
        with self.sf.begin() as s:
            won = s.execute(update(Capture).where(Capture.id == capture_id, Capture.state.in_(("RECORDED", "FAILED")))
                            .values(state="TRANSCRIBING" if needs_stt else "EXTRACTING", error_category=None,
                                    error_stage=None))
            return won.rowcount == 1

    def _fail(self, capture_id: str, stage: str, error: ProviderError) -> ApiError:
        self._set(capture_id, state="FAILED", error_category=error.category, error_stage=stage)
        LOGGER.warning("capture_failed capture=%s stage=%s category=%s", capture_id, stage, error.category)
        return _provider_error(stage, error, capture_id)

    def _process(self, user: Principal, capture_id: str) -> dict[str, Any]:
        with self.sf() as s:
            cap = s.get(Capture, capture_id)
            profile, transcript, audio_key, hint = get_profile(cap.language), cap.transcript, cap.audio_key, cap.customer_hint_id
        if not self._claim(capture_id, transcript is None):
            return self.get_view(user, capture_id)  # another request is already processing this capture
        stage = "stt" if transcript is None else "llm"
        try:
            self.guard.consume(f"capture:{capture_id}", "process.attempts", "life", self.settings.max_process_attempts_per_capture,
                               code="TOO_MANY_ATTEMPTS", message="This recording has been retried too many times. Record it again.")
        except ApiError:
            self._set(capture_id, state="FAILED", error_category="attempts", error_stage=stage)
            raise
        if transcript is None:
            audio = self.store.load(audio_key) if audio_key else None
            if audio is None:
                raise self._fail(capture_id, "stt", ProviderError("unsupported_audio", "The recording is no longer available"))
            try:
                transcript = self._transcribe(user, audio, profile)
            except ProviderError as error:
                raise self._fail(capture_id, "stt", error) from error
            except ApiError:
                self._set(capture_id, state="FAILED", error_category="quota", error_stage="stt")
                raise
            self._set(capture_id, transcript=transcript, state="EXTRACTING", error_category=None, error_stage=None)
        with self.sf() as s:
            cat, _org = self._catalog(s, user)
        try:
            extraction = self._extract(user, transcript, self._context(cat, profile.code))
        except ProviderError as error:
            raise self._fail(capture_id, "llm", error) from error
        except ApiError:
            self._set(capture_id, state="FAILED", error_category="quota", error_stage="llm")
            raise
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
        if any(op.op == "set" and op.value == NEW_PRODUCT for op in ops):
            self.catalogue._spend_creation(user)  # outside the transaction: it writes to the usage ledger
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
        require(len(utterance) <= self.settings.max_correction_chars, 413, "TEXT_TOO_LONG",
                f"The correction is too long (maximum {self.settings.max_correction_chars} characters)")
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
                context = self._context(cat, language)
                view = llm_view(draft)
                result = self.guard.run(
                    user.id, "llm", lambda: self.providers.reasoner.patch(view, utterance, context),
                    est_tokens=estimate_tokens(utterance, str(view), str(context.customers), str(context.products)))
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
        require(looks_like_audio(audio), 400, "UNSUPPORTED_AUDIO", "This file is not a supported audio recording")
        with self.sf() as s:
            cap = self._load(s, user, capture_id, write=True)
            self._check_revision(cap, revision)
            profile = get_profile(cap.language)
        try:
            text = self._transcribe(user, audio, profile)
        except ProviderError as error:
            raise _provider_error("stt", error, capture_id) from error
        return self.correct_text(user, capture_id, revision, text[: self.settings.max_correction_chars])

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
        reply = self._reply(user.id, capture_id, committed["confirmationText"], get_profile(committed["language"]), speak_reply)
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
                if item.get("newProduct") and not item.get("productId"):
                    item["productId"] = self.catalogue.create_from_visit(s, user, item["newProduct"]).id
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

    def _reply(self, user_id: str, capture_id: str, text: str, profile: LanguageProfile, speak: bool) -> dict[str, Any]:
        with self.sf() as s:
            row = s.scalar(select(ReplyAudio).where(ReplyAudio.capture_id == capture_id))
            if row:
                return self._reply_view(row, capture_id)
        if not speak:
            return {"status": "SKIPPED", "text": text, "url": None}
        status, key, model, category = "READY", f"replies/{capture_id}.wav", None, None
        spoken = text[: self.settings.max_tts_chars]
        with self._lock_for(f"reply:{capture_id}"):
            with self.sf() as s:  # a concurrent confirm may have finished while we waited: never pay twice
                row = s.scalar(select(ReplyAudio).where(ReplyAudio.capture_id == capture_id))
                if row:
                    return self._reply_view(row, capture_id)
            try:
                speech = self.guard.run(user_id, "tts", lambda: self.providers.tts.synthesize(spoken, profile),
                                        chars=len(spoken))
                self.store.save(key, speech.audio)
                model = speech.model
            except Exception as error:  # noqa: BLE001 - TTS must never fail an already-committed visit
                status, key = "FAILED", None
                category = (error.category if isinstance(error, ProviderError)
                            else error.code.lower() if isinstance(error, ApiError) else "unexpected")
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
        text = text[: self.settings.max_tts_chars]
        key = f"questions/{_sha(profile.code, text)}.wav"
        data = self.store.load(key)
        if data is None:
            with self._lock_for(key):
                data = self.store.load(key)  # cache hit after waiting for a concurrent identical request
                if data is None:
                    try:
                        data = self.guard.run(user.id, "tts", lambda: self.providers.tts.synthesize(text, profile),
                                              chars=len(text)).audio
                    except ProviderError as error:
                        raise _provider_error("tts", error, capture_id) from error
                    self.store.save(key, data)
        return data, "audio/wav"
