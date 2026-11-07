"""Demo catalogue, retailers and users. Dev/demo data only; passwords are not secret."""

from __future__ import annotations

from datetime import date

from .domain.draft import Catalog, CustomerRef, ProductRef

DEMO_PASSWORD = "demo123"

TERRITORIES = [
    {"id": "ter_delhi", "name": "Delhi NCR"},
    {"id": "ter_chennai", "name": "Chennai"},
    {"id": "ter_pune", "name": "Pune"},
]

USERS = [
    {"id": "usr_asha", "username": "asha", "name": "Asha Verma", "role": "rep", "territory_id": "ter_delhi"},
    {"id": "usr_ravi", "username": "ravi", "name": "Ravi Kumar", "role": "rep", "territory_id": "ter_chennai"},
    {"id": "usr_priya", "username": "priya", "name": "Priya Kulkarni", "role": "rep", "territory_id": "ter_pune"},
    {"id": "usr_meera", "username": "meera", "name": "Meera Nair", "role": "manager", "territory_id": None},
    {"id": "usr_admin", "username": "admin", "name": "Admin", "role": "admin", "territory_id": None},
]

# id, name, aliases, base_unit, units_per_pack, price_paise
PRODUCTS = [
    ("prd_parle_g", "Parle-G Biscuit", ["parle g", "parleg", "parle ji", "पारले जी", "पारले-जी"], "packet", 48, 1000),
    ("prd_goodday", "Britannia Good Day Cookies", ["britannia good day", "good day", "good day biscuit", "गुड डे"], "packet", 36, 3000),
    ("prd_marie", "Britannia Marie Gold", ["marie gold", "marie"], "packet", 48, 1000),
    ("prd_real_mango", "Real Mango Juice 1L", ["real mango", "real aam"], "bottle", 12, 11000),
    ("prd_real_guava", "Real Guava Juice 1L", ["real guava"], "bottle", 12, 11000),
    ("prd_real_mixed", "Real Mixed Fruit Juice 1L", ["real mixed fruit"], "bottle", 12, 11000),
    ("prd_maaza", "Maaza Mango 600ml", ["maaza", "maza", "maaza mango"], "bottle", 24, 4000),
    ("prd_amul_butter", "Amul Butter 100g", ["amul butter", "butter"], "packet", 50, 6000),
    ("prd_tata_salt", "Tata Salt 1kg", ["tata salt", "salt"], "packet", 25, 2800),
    ("prd_atta", "Aashirvaad Atta 5kg", ["aashirvaad atta", "atta"], "packet", 4, 27500),
    ("prd_lays", "Lay's Classic Salted", ["lays", "lays classic", "lay s"], "packet", 40, 2000),
]

# id, name, aliases, territory
CUSTOMERS = [
    ("cus_sharma_gen", "Sharma General Store", ["sharma ji", "sharma general", "शर्मा जी"], "ter_delhi"),
    ("cus_sharma_dairy", "Sharma Dairy", ["sharma dairy"], "ter_delhi"),
    ("cus_gupta", "Gupta Provision Store", ["gupta ji", "gupta provision", "gupta"], "ter_delhi"),
    ("cus_khan", "Khan Mini Mart", ["khan sahab", "khan mini mart", "khan"], "ter_delhi"),
    ("cus_verma", "Verma Kirana", ["verma ji", "verma"], "ter_delhi"),
    ("cus_iyer", "Iyer Stores", ["iyer", "ஐயர்"], "ter_chennai"),
    ("cus_murugan", "Murugan Provision", ["murugan"], "ter_chennai"),
    ("cus_lakshmi", "Lakshmi Mart", ["lakshmi"], "ter_chennai"),
    ("cus_patil", "Patil Kirana", ["patil", "पाटील"], "ter_pune"),
    ("cus_deshmukh", "Deshmukh Stores", ["deshmukh"], "ter_pune"),
]


def demo_catalog(today: date, territory: str | None = "ter_delhi") -> Catalog:
    customers = [CustomerRef(i, n, tuple(a)) for i, n, a, t in CUSTOMERS if territory is None or t == territory]
    products = [ProductRef(i, n, tuple(a), u, pack, price) for i, n, a, u, pack, price in PRODUCTS]
    return Catalog(customers, products, today)
