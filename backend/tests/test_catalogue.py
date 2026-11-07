"""Catalogue management (manager) and adding a missing item by voice during a visit (rep)."""

from __future__ import annotations

import pytest

RICE_VISIT = "Sharma General Store gaya tha, bees kilo chawal order diya kal bhej dena"
NEW = {"name": "Basmati Rice", "baseUnit": "kg", "priceRupees": 60}


def mgr(api, method, path, body=None, user="meera"):
    return api.client.request(method, f"/v1{path}", json=body, headers=api.auth(user))


def rep_capture(api, text=RICE_VISIT, key="rice-key-0001", user="asha"):
    r = api.client.post("/v1/captures", data={"language": "hinglish", "transcript": text},
                        headers={**api.auth(user), "Idempotency-Key": key})
    assert r.status_code == 202, r.text
    return r.json()


def correct(api, cap, text, user="asha"):
    r = api.client.post(f"/v1/captures/{cap['id']}/corrections", json={"revision": cap["revision"], "text": text},
                        headers=api.auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def answer(api, cap, value, user="asha"):
    r = api.client.post(f"/v1/captures/{cap['id']}/answers", json={"revision": cap["revision"], "answer": value},
                        headers=api.auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def confirm(api, cap, user="asha"):
    r = api.client.post(f"/v1/captures/{cap['id']}/confirm", json={"revision": cap["revision"], "speakReply": False},
                        headers={**api.auth(user), "Idempotency-Key": f"confirm-{cap['id']}"})
    assert r.status_code == 200, r.text
    return r.json()


def products(api, user="asha", **params):
    return api.client.get("/v1/products", params=params, headers=api.auth(user)).json()["products"]


# --------------------------------------------------------------------------- manager manages the catalogue

def test_manager_creates_edits_and_retires_a_product(api):
    r = mgr(api, "POST", "/products", {**NEW, "baseUnit": "kilo", "aliases": ["chawal", "rice", "basmati"]})
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["baseUnit"] == "kg" and p["pricePaise"] == 6000 and p["aliases"] == ["chawal", "rice", "basmati"] and p["active"]
    assert "Basmati Rice" in {x["name"] for x in products(api)}           # visible to reps straight away

    r = mgr(api, "PATCH", f"/products/{p['id']}", {"priceRupees": 72.5})
    assert r.status_code == 200 and r.json()["pricePaise"] == 7250

    assert mgr(api, "DELETE", f"/products/{p['id']}").json()["active"] is False
    assert "Basmati Rice" not in {x["name"] for x in products(api)}       # retired: gone from reps' list
    assert "Basmati Rice" in {x["name"] for x in products(api, "meera", includeInactive="true")}
    assert "Basmati Rice" not in {x["name"] for x in products(api, includeInactive="true")}  # reps cannot see retired items
    assert mgr(api, "PATCH", f"/products/{p['id']}", {"active": True}).json()["active"] is True


def test_reps_cannot_manage_the_catalogue(api):
    assert mgr(api, "POST", "/products", NEW, user="asha").status_code == 403
    pid = products(api)[0]["id"]
    assert mgr(api, "PATCH", f"/products/{pid}", {"priceRupees": 1}, user="asha").status_code == 403
    assert mgr(api, "DELETE", f"/products/{pid}", user="asha").status_code == 403
    assert api.client.post("/v1/products", json=NEW).status_code == 401


@pytest.mark.parametrize("body,code", [
    ({"name": "Parle-G Biscuit", "baseUnit": "packet", "priceRupees": 10}, "DUPLICATE_PRODUCT"),   # same name as a seeded item
    ({"name": "Parle Ji", "baseUnit": "packet", "priceRupees": 10, "aliases": ["parle g"]}, "DUPLICATE_PRODUCT"),  # alias clash
    ({"name": "Rice", "baseUnit": "litre", "priceRupees": 10}, "INVALID_UNIT"),
    ({"name": "Rice", "baseUnit": "case", "priceRupees": 10}, "INVALID_UNIT"),                      # "case" is derived, not a base unit
    ({"name": "Rice", "baseUnit": "kg", "priceRupees": 0}, "VALIDATION_ERROR"),
    ({"name": "Rice", "baseUnit": "kg", "priceRupees": -5}, "VALIDATION_ERROR"),
    ({"name": "Rice", "baseUnit": "kg", "priceRupees": 10 ** 7}, "VALIDATION_ERROR"),
    ({"name": "R", "baseUnit": "kg", "priceRupees": 10}, "VALIDATION_ERROR"),
    ({"name": "Rice", "baseUnit": "kg", "priceRupees": 10, "aliases": ["a"] * 11}, "VALIDATION_ERROR"),
    ({"name": "Rice", "baseUnit": "kg", "priceRupees": 10, "active": False}, "VALIDATION_ERROR"),   # unknown field refused
])
def test_catalogue_input_is_validated(api, body, code):
    r = mgr(api, "POST", "/products", body)
    assert r.status_code in (409, 422) and r.json()["error"]["code"] == code, r.text


def test_price_change_applies_to_new_orders_not_old_ones(api):
    pid = mgr(api, "POST", "/products", {**NEW, "aliases": ["chawal"]}).json()["id"]
    first = confirm(api, rep_capture(api, key="rice-a-0001"))
    assert first["orderTotalPaise"] == 20 * 6000
    mgr(api, "PATCH", f"/products/{pid}", {"priceRupees": 100})
    second = confirm(api, rep_capture(api, key="rice-b-0001"))
    assert second["orderTotalPaise"] == 20 * 10000
    old = api.client.get(f"/v1/orders/{first['orderId']}", headers=api.auth("asha")).json()
    assert old["totalPaise"] == 20 * 6000                    # history is not rewritten


def test_catalogue_cap_and_daily_creation_limit(make_api):
    seeded = len(products(make_api()))
    small = make_api(max_products=seeded + 2)
    assert [mgr(small, "POST", "/products", {**NEW, "name": f"Rice {i}"}).status_code for i in range(3)] == [201, 201, 409]
    assert mgr(small, "POST", "/products", {**NEW, "name": "Rice 9"}).json()["error"]["code"] == "CATALOGUE_FULL"
    limited = make_api(user_products_per_day=2)
    assert [mgr(limited, "POST", "/products", {**NEW, "name": f"Rice {i}"}).status_code for i in range(4)] == [201, 201, 429, 429]


# --------------------------------------------------------------------------- rep adds a missing item by voice

def test_unknown_item_offers_to_add_it_and_asks_only_for_the_price(api):
    cap = rep_capture(api)
    q = cap["clarification"]
    assert q["code"] == "UNKNOWN_PRODUCT" and "add karo" in q["question"]
    assert q["options"][-1] == {"value": "__new__", "label": '+ Add "chawal" as a new item'}

    cap = answer(api, cap, "__new__")                         # tapped the "+ Add" button
    item = cap["draft"]["order"]["items"][0]
    assert item["newProduct"] == {"name": "Chawal", "baseUnit": "kg", "pricePaise": None} and item["matchStatus"] == "new"
    assert cap["clarification"]["code"] == "NEW_PRODUCT_PRICE" and "per kg" in cap["clarification"]["question"]
    assert cap["clarification"]["answerType"] == "number"

    cap = answer(api, cap, 60)
    assert cap["state"] == "READY_FOR_REVIEW" and cap["draft"]["totalPaise"] == 20 * 6000
    assert "Chawal" not in {p["name"] for p in products(api)}   # nothing is created until the rep confirms

    done = confirm(api, cap)
    assert done["orderTotalPaise"] == 20 * 6000
    created = {p["name"]: p for p in products(api)}["Chawal"]
    assert created["baseUnit"] == "kg" and created["pricePaise"] == 6000
    order = api.client.get(f"/v1/orders/{done['orderId']}", headers=api.auth("asha")).json()
    assert order["items"][0]["product"] == "Chawal" and order["items"][0]["lineTotalPaise"] == 120000

    nxt = rep_capture(api, key="rice-key-0002")                 # next visit: "chawal" now matches by itself
    assert nxt["draft"]["order"]["items"][0]["productName"] == "Chawal" and nxt["state"] == "READY_FOR_REVIEW"


def test_everything_in_one_sentence_by_voice(api):
    cap = rep_capture(api)
    cap = correct(api, cap, "add karo, 60 rupaye kilo")          # what the rep says through hold-to-talk
    assert cap["state"] == "READY_FOR_REVIEW"
    item = cap["draft"]["order"]["items"][0]
    assert item["newProduct"]["pricePaise"] == 6000 and item["unitPricePaise"] == 6000
    confirm(api, cap)
    assert {p["name"]: p["pricePaise"] for p in products(api)}["Chawal"] == 6000


def test_spoken_number_words_and_hindi_intent(api):
    cap = correct(api, rep_capture(api), "naya item jodo saath rupaye")      # "saath" is not in the number list: no price yet
    assert cap["clarification"]["code"] == "NEW_PRODUCT_PRICE"
    cap = correct(api, cap, "pachas rupaye")                                 # fifty
    assert cap["state"] == "READY_FOR_REVIEW" and cap["draft"]["order"]["items"][0]["newProduct"]["pricePaise"] == 5000


def test_unit_is_asked_when_it_was_not_said():
    from datetime import date
    from bolbazaar.domain.draft import Catalog, CustomerRef, apply_ops, finalize, validate
    from bolbazaar.schemas_llm import PatchOp
    cat = Catalog([CustomerRef("c1", "Sharma", ())], [], date(2026, 11, 8))
    draft = finalize({"customer": {"customerId": "c1", "name": "Sharma", "spokenName": "Sharma", "matchStatus": "resolved",
                                    "candidates": [], "confidence": 1},
                      "visit": {}, "order": {"items": [{"spokenName": "chawal", "quantity": 20, "unit": None, "productId": None,
                                                         "productName": None, "candidates": [], "matchStatus": "unknown",
                                                         "unitPricePaise": None}], "deliveryText": None, "deliveryDate": None},
                      "collections": [], "complaints": [], "competitorNotes": [], "commitments": []})
    assert validate(draft, cat)[0]["code"] == "UNKNOWN_PRODUCT"
    draft, _, failed = apply_ops(draft, [PatchOp(op="set", path="order.items.0.productId", value="__new__")], cat)
    assert not failed and [i["code"] for i in validate(draft, cat)] == ["NEW_PRODUCT_UNIT", "NEW_PRODUCT_PRICE"]
    draft, _, failed = apply_ops(draft, [PatchOp(op="set", path="order.items.0.unit", value="case")], cat)
    assert failed  # a case is not something an item is sold in; it needs a base unit
    draft, _, failed = apply_ops(draft, [PatchOp(op="set", path="order.items.0.unit", value="kilo"),
                                         PatchOp(op="set", path="order.items.0.newProductPrice", value=60)], cat)
    assert not failed and validate(draft, cat) == [] and draft["totalPaise"] == 20 * 6000


def test_a_discarded_draft_adds_nothing_to_the_catalogue(api):
    cap = answer(api, rep_capture(api), "__new__")
    api.client.post(f"/v1/captures/{cap['id']}/cancel", headers=api.auth("asha"))
    assert "Chawal" not in {p["name"] for p in products(api, "meera", includeInactive="true")}


def test_absurd_price_by_voice_is_refused_and_nothing_is_created(api):
    cap = correct(api, rep_capture(api), "add karo")
    r = api.client.post(f"/v1/captures/{cap['id']}/corrections", json={"revision": cap["revision"], "text": "99999999 rupaye"},
                        headers=api.auth("asha"))
    body = r.json()
    assert body["draft"]["order"]["items"][0]["newProduct"]["pricePaise"] is None and body["unsupported"]
    assert "Chawal" not in {p["name"] for p in products(api)}


def test_existing_item_is_reused_if_someone_added_it_meanwhile(api):
    cap = correct(api, rep_capture(api), "add karo, 60 rupaye kilo")
    mgr(api, "POST", "/products", {"name": "Chawal", "baseUnit": "kg", "priceRupees": 80})   # a manager adds it first
    done = confirm(api, cap)
    assert done["orderTotalPaise"] == 20 * 8000                       # the manager's price wins; no duplicate product
    assert [p["name"] for p in products(api)].count("Chawal") == 1


def test_rep_cannot_spam_new_products(make_api):
    api = make_api(user_products_per_day=1)
    first = correct(api, rep_capture(api, key="spam-a-0001"), "add karo, 60 rupaye kilo")
    assert first["state"] == "READY_FOR_REVIEW"
    second = rep_capture(api, text="Sharma General Store gaya tha, 5 kilo dal order diya kal bhej dena", key="spam-b-0001")
    r = api.client.post(f"/v1/captures/{second['id']}/answers", json={"revision": second["revision"], "answer": "__new__"},
                        headers=api.auth("asha"))
    assert r.status_code == 429 and r.json()["error"]["code"] == "CATALOGUE_LIMIT"


def test_choosing_an_existing_product_still_works(api):
    cap = rep_capture(api)
    parle = next(p["id"] for p in products(api) if p["name"] == "Parle-G Biscuit")
    cap = answer(api, cap, parle)
    assert "newProduct" not in cap["draft"]["order"]["items"][0] and cap["draft"]["order"]["items"][0]["productId"] == parle


# --------------------------------------------------------------------------- whole catalogue from one passage (voice or text)

LIST = ("chawal 60 rupaye kilo, atta 45 rupaye kilo, Parle-G Biscuit 10 rupaye packet aur Maaza 12 rupees bottle, namak")


def draft(api, text=LIST, user="meera", **kw):
    return api.client.post("/v1/products/draft", data={"text": text}, headers=api.auth(user), **kw)


def test_draft_proposes_rows_and_saves_nothing(api):
    before = {p["name"] for p in products(api, "meera", includeInactive="true")}
    r = draft(api)
    assert r.status_code == 200, r.text
    rows = {x["name"]: x for x in r.json()["items"]}
    assert rows["Chawal"]["baseUnit"] == "kg" and rows["Chawal"]["priceRupees"] == 60 and rows["Chawal"]["include"]
    assert rows["Atta"]["priceRupees"] == 45
    assert "duplicate" in rows["Parle-G Biscuit"]["issues"] and not rows["Parle-G Biscuit"]["include"]   # already in the catalogue
    assert set(rows["Namak"]["issues"]) == {"missing_unit", "missing_price"} and not rows["Namak"]["include"]
    assert {p["name"] for p in products(api, "meera", includeInactive="true")} == before                  # a draft never writes


def test_bulk_create_adds_reviewed_rows_and_reports_skips(api):
    items = [{"name": "Chawal", "baseUnit": "kilo", "priceRupees": 60, "aliases": ["rice"]},
             {"name": "Besan", "baseUnit": "kg", "priceRupees": 45},
             {"name": "Parle-G Biscuit", "baseUnit": "packet", "priceRupees": 10},       # exists
             {"name": "Besan", "baseUnit": "kg", "priceRupees": 46},                    # listed twice
             {"name": "Ghee", "baseUnit": "litre", "priceRupees": 500}]                  # bad unit
    r = api.client.post("/v1/products/bulk", json={"items": items}, headers=api.auth("meera"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert [p["name"] for p in body["created"]] == ["Chawal", "Besan"]
    assert {s["name"]: s["reason"] for s in body["skipped"]}["Parle-G Biscuit"] == "already in the catalogue"
    assert {s["name"] for s in body["skipped"]} == {"Parle-G Biscuit", "Besan", "Ghee"}
    names = {p["name"]: p for p in products(api)}
    assert names["Chawal"]["pricePaise"] == 6000 and names["Chawal"]["aliases"] == ["rice"] and names["Besan"]["pricePaise"] == 4500
    again = api.client.post("/v1/products/bulk", json={"items": items[:2]}, headers=api.auth("meera")).json()
    assert again["created"] == [] and len(again["skipped"]) == 2        # idempotent: re-sending creates nothing


def test_spoken_catalogue_end_to_end(make_api):
    from bolbazaar.providers.base import Transcript
    from conftest import offline_providers, tone_wav

    class ListSTT:
        def transcribe(self, wav, profile):
            return Transcript(text="basmati rice sau rupaye kilo, toor dal pachas rupaye kilo", language=profile.code, model="t")

    api = make_api(providers=offline_providers(stt=ListSTT()))
    r = api.client.post("/v1/products/draft", files={"audio": ("list.wav", tone_wav(2), "audio/wav")},
                        data={"language": "hinglish"}, headers=api.auth("meera"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcript"].startswith("basmati rice")
    rows = {x["name"]: x for x in body["items"]}
    assert rows["Basmati rice"]["priceRupees"] == 100 and rows["Toor dal"]["priceRupees"] == 50 and rows["Toor dal"]["baseUnit"] == "kg"
    created = api.client.post("/v1/products/bulk", headers=api.auth("meera"), json={"items": [
        {"name": x["name"], "baseUnit": x["baseUnit"], "priceRupees": x["priceRupees"]} for x in body["items"]]})
    assert created.status_code == 201 and len(created.json()["created"]) == 2


def test_draft_and_bulk_are_manager_only(api):
    for user in ("asha", None):
        headers = api.auth(user) if user else {}
        d = api.client.post("/v1/products/draft", data={"text": LIST}, headers=headers)
        b = api.client.post("/v1/products/bulk", json={"items": [NEW]}, headers=headers)
        assert (d.status_code, b.status_code) == ((403, 403) if user else (401, 401))


def test_draft_and_bulk_limits(make_api):
    api = make_api()
    assert draft(api, text="x" * 6001).status_code == 413
    assert api.client.post("/v1/products/draft", headers=api.auth("meera")).status_code == 400
    assert api.client.post("/v1/products/bulk", json={"items": []}, headers=api.auth("meera")).status_code == 422
    assert api.client.post("/v1/products/bulk", json={"items": [NEW] * 101}, headers=api.auth("meera")).status_code == 422
    small = make_api(user_bulk_products_per_day=2)
    three = [{**NEW, "name": f"Item {i}"} for i in range(3)]
    over = small.client.post("/v1/products/bulk", json={"items": three}, headers=small.auth("meera"))
    assert over.status_code == 429 and over.json()["error"]["code"] == "CATALOGUE_LIMIT"
    seeded = len(products(make_api()))
    full = make_api(max_products=seeded + 1)
    r = full.client.post("/v1/products/bulk", json={"items": three}, headers=full.auth("meera"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CATALOGUE_FULL"


def test_hostile_model_output_cannot_create_bad_products(make_api):
    """If the model returns nonsense, drafts flag it and bulk re-validates: prices/units are never trusted."""
    from bolbazaar.providers.offline import OfflineReasoner
    from bolbazaar.schemas_llm import CatalogueExtraction, CatalogueItemX
    from conftest import offline_providers

    class Evil(OfflineReasoner):
        def parse_catalogue(self, text):
            mk = lambda n, u, p: CatalogueItemX(name=n, unit=u, price_rupees=p, units_per_pack=99999, aliases=["a"] * 50, evidence="x" * 999)
            return CatalogueExtraction(items=[mk("Rice", "kg", 1e12), mk("Dal", "furlong", 5), mk("<script>alert(1)</script>", "kg", 5),
                                              mk("Neg", "kg", -3)] + [mk(f"Bulk {i}", "kg", 1) for i in range(150)])

    api = make_api(providers=offline_providers(reasoner=Evil()))
    body = draft(api).json()
    assert len(body["items"]) == 100 and body["truncated"]
    rows = {x["name"]: x for x in body["items"]}
    assert "missing_price" in rows["Rice"]["issues"] and "missing_unit" in rows["Dal"]["issues"] and "missing_price" in rows["Neg"]["issues"]
    assert rows["Rice"]["unitsPerPack"] is None and len(rows["Rice"]["aliases"]) <= 10 and len(rows["Rice"]["evidence"]) <= 200
    r = api.client.post("/v1/products/bulk", headers=api.auth("meera"), json={"items": [
        {"name": "Rice", "baseUnit": "kg", "priceRupees": 1e12}]})
    assert r.status_code == 422
