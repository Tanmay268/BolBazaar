from datetime import date


def get(api, path, user="meera"):
    r = api.client.get(path, headers=api.auth(user))
    assert r.status_code == 200, r.text
    return r.json()


def test_summary_has_a_real_30_day_visit_trend(make_api):
    api = make_api()
    s = get(api, "/v1/manager/summary")
    assert isinstance(s["visits30d"], int) and isinstance(s["visitsPrev30d"], int)
    assert s["visits30d"] >= s["visitsToday"]
    assert s["visits30d"] > 0  # the demo seed has 70 days of history


def test_overdue_rows_carry_the_next_payment_follow_up_date(make_api):
    api = make_api()
    rows = get(api, "/v1/manager/overdue-payments")["rows"]
    assert rows and all("nextDueDate" in r for r in rows)
    dated = [r for r in rows if r["nextDueDate"]]
    assert dated and all(date.fromisoformat(r["nextDueDate"]) for r in dated)
    # an overdue follow-up can never be later than the next due date
    assert all(r["nextDueDate"] <= r["oldestDueDate"] for r in rows if r["oldestDueDate"])


def test_conversion_rows_include_order_value(make_api):
    api = make_api()
    rows = get(api, "/v1/manager/conversion")["rows"]
    assert rows and all(isinstance(r["orderValuePaise"], int) and r["orderValuePaise"] >= 0 for r in rows)
    assert any(r["orderValuePaise"] > 0 for r in rows)
