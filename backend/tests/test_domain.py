from datetime import date

import pytest

from fieldforce.domain.answers import interpret_answer
from fieldforce.domain.dates import find_date_phrase, resolve_date_text
from fieldforce.domain.draft import apply_ops, build_draft, validate
from fieldforce.domain.normalize import normalize, replace_number_words
from fieldforce.domain.resolution import resolve
from fieldforce.domain.units import normalize_unit, unit_price
from fieldforce.providers.base import ExtractionContext
from fieldforce.providers.offline import DEMO_TRANSCRIPTS, OfflineReasoner
from fieldforce.schemas_llm import PatchOp
from fieldforce.seed_data import demo_catalog

TODAY = date(2026, 11, 4)  # a Wednesday


def context(cat):
    return ExtractionContext(
        today=TODAY, weekday="Wednesday", language="hinglish",
        customers=[{"name": c.name, "aliases": list(c.aliases)} for c in cat.customers.values()],
        products=[{"name": p.name, "aliases": list(p.aliases)} for p in cat.products.values()])


def test_normalize_keeps_devanagari_marks_and_drops_punctuation():
    assert normalize("Parle-G!") == "parle g"
    assert normalize("पारले-जी") == "पारले जी"


def test_number_words():
    assert replace_number_words("bees packet") == "20 packet"
    assert replace_number_words("paanch hazaar rupaye.") == "5000 rupaye."
    assert replace_number_words("Twenty bottles") == "20 bottles"


@pytest.mark.parametrize("text,expected", [
    ("tomorrow", date(2026, 11, 5)), ("kal", date(2026, 11, 5)), ("aaj", TODAY),
    ("parso", date(2026, 11, 6)), ("day after tomorrow", date(2026, 11, 6)),
    ("next Monday", date(2026, 11, 9)), ("agle somvar", date(2026, 11, 9)),
    ("Wednesday", date(2026, 11, 11)), ("in 3 days", date(2026, 11, 7)),
    ("3 din baad", date(2026, 11, 7)), ("2026-12-01", date(2026, 12, 1)),
])
def test_resolves_dates(text, expected):
    assert resolve_date_text(text, TODAY) == expected


@pytest.mark.parametrize("text", ["next week", "agle hafte", "after Diwali", "", "2020-01-01", "2030-01-01"])
def test_ambiguous_or_out_of_range_dates_are_none(text):
    assert resolve_date_text(text, TODAY) is None


def test_find_date_phrase():
    assert find_date_phrase("He will pay next Monday") == "next Monday"
    assert find_date_phrase("no date here") is None


def test_units():
    assert normalize_unit("Peti") == "case" and normalize_unit("बोतल") == "bottle"
    assert unit_price(1000, "case", "packet", 48) == 48000
    assert unit_price(1000, "kg", "packet", 48) is None


def test_exact_alias_wins_and_partial_ties_are_ambiguous():
    cat = demo_catalog(TODAY)
    assert resolve("Parle-G", cat.product_entries).status == "resolved"
    juice = resolve("Real juice", cat.product_entries)
    assert juice.status == "ambiguous" and len(juice.candidates) == 3
    assert resolve("Sharma ji", cat.customer_entries).best.id == "cus_sharma_gen"
    assert resolve("Sharma", cat.customer_entries).status == "ambiguous"
    assert resolve("xyzzy plugh", cat.product_entries).status == "unknown"


def test_offline_demo_transcript_becomes_draft_with_one_ambiguity():
    cat = demo_catalog(TODAY)
    ex = OfflineReasoner().extract(DEMO_TRANSCRIPTS["hinglish"], context(cat))
    assert ex.customer.spoken_name.casefold() == "sharma ji"
    assert [(i.spoken_name, i.quantity) for i in ex.order.items] == [("Parle-G", 20), ("Real juice", 10)]
    draft = build_draft(ex, cat)
    assert draft["customer"]["customerId"] == "cus_sharma_gen"
    assert draft["order"]["deliveryDate"] == "2026-11-05"
    assert draft["collections"][0]["amountPaise"] == 500000
    assert draft["collections"][0]["dueDate"] == "2026-11-05"
    assert draft["complaints"][0]["category"] == "product_quality"
    kinds = {c["actionType"]: c["dueDate"] for c in draft["commitments"]}
    assert kinds == {"payment_followup": "2026-11-05", "visit": "2026-11-09"}
    issues = validate(draft, cat)
    assert [i["code"] for i in issues] == ["AMBIGUOUS_PRODUCT"]
    assert issues[0]["answerPath"] == "order.items.1.productId"


def test_answering_the_ambiguity_clears_it_and_prices_the_order():
    cat = demo_catalog(TODAY)
    ex = OfflineReasoner().extract(DEMO_TRANSCRIPTS["hinglish"], context(cat))
    draft = build_draft(ex, cat)
    issue = validate(draft, cat)[0]
    ops = interpret_answer("the mango one", issue, cat)
    assert ops and ops[0].value == "prd_real_mango"
    new, changes, failures = apply_ops(draft, ops, cat)
    assert not failures and validate(new, cat) == []
    assert new["totalPaise"] == 20 * 1000 + 10 * 11000
    assert changes[0]["new"] == "Real Mango Juice 1L"


def test_unrecognised_answer_returns_none():
    cat = demo_catalog(TODAY)
    ex = OfflineReasoner().extract(DEMO_TRANSCRIPTS["hinglish"], context(cat))
    issue = validate(build_draft(ex, cat), cat)[0]
    assert interpret_answer("banana", issue, cat) is None


def test_corrections_are_whitelisted_and_failures_reported():
    cat = demo_catalog(TODAY)
    ex = OfflineReasoner().extract(DEMO_TRANSCRIPTS["en-IN"], context(demo_catalog(TODAY)))
    draft = build_draft(ex, cat)
    _, changes, failures = apply_ops(draft, [PatchOp(op="set", path="order.items.0.quantity", value=15.0)], cat)
    assert changes[0]["old"] == 12 and changes[0]["new"] == 15
    _, changes, failures = apply_ops(draft, [PatchOp(op="set", path="customer.phone", value="1")], cat)
    assert not changes and failures
    _, changes, failures = apply_ops(draft, [PatchOp(op="set", path="order.items.9.quantity", value=1.0)], cat)
    assert not changes and failures
    _, changes, failures = apply_ops(draft, [PatchOp(op="set", path="order.items.0.quantity", value=2.5)], cat)
    assert not changes and failures


@pytest.mark.parametrize("spelling", ["/order/items/0/quantity", "order.items[0].quantity", " .order.items.0.quantity "])
def test_model_path_spellings_are_normalised_but_still_whitelisted(spelling):
    cat = demo_catalog(TODAY)
    ex = OfflineReasoner().extract(DEMO_TRANSCRIPTS["en-IN"], context(demo_catalog(TODAY)))
    draft = build_draft(ex, cat)
    new, changes, failures = apply_ops(draft, [PatchOp(op="set", path=spelling, value=15.0)], cat)
    assert not failures and changes[0]["path"] == "order.items.0.quantity"
    assert new["order"]["items"][0]["quantity"] == 15
    _, changes, failures = apply_ops(draft, [PatchOp(op="set", path="/customer/phone", value="1")], cat)
    assert not changes and failures


def test_offline_patch_changes_quantity_and_removes_items():
    cat = demo_catalog(TODAY)
    ex = OfflineReasoner().extract(DEMO_TRANSCRIPTS["en-IN"], context(cat))
    draft = build_draft(ex, cat)
    from fieldforce.domain.draft import llm_view
    result = OfflineReasoner().patch(llm_view(draft), "make Maaza 10", context(cat))
    assert result.ops[0].path == "order.items.1.quantity" and result.ops[0].value == 10
    result = OfflineReasoner().patch(llm_view(draft), "remove Good Day", context(cat))
    assert result.ops[0].op == "remove" and result.ops[0].path == "order.items.0"
    assert OfflineReasoner().patch(llm_view(draft), "sing a song", context(cat)).unsupported


def test_unit_mismatch_is_asked_not_guessed():
    cat = demo_catalog(TODAY)
    ex = OfflineReasoner().extract("Gupta Provision Store ko 5 kg Parle-G chahiye", context(cat))
    draft = build_draft(ex, cat)
    issues = validate(draft, cat)
    assert issues and issues[0]["code"] == "UNIT_MISMATCH"
    assert [o["value"] for o in issues[0]["options"]] == ["packet", "case"]


def test_manager_query_parsing():
    r = OfflineReasoner()
    assert r.parse_manager_query("which retailers haven't ordered in 45 days").days == 45
    assert r.parse_manager_query("show overdue payments").intent == "overdue_payments"
    assert r.parse_manager_query("tell me a joke").intent == "unsupported"
