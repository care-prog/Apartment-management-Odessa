from src.models import insert_db

# === TEAM MEMBERS ===
insert_db("INSERT OR IGNORE INTO team_members (name, phone, role, language, access_level) VALUES (?, ?, ?, ?, ?)",
    ("David", "972543006771", "owner", "he", "full"))
insert_db("INSERT OR IGNORE INTO team_members (name, phone, role, language, access_level) VALUES (?, ?, ?, ?, ?)",
    ("Amalia", "", "owner", "he", "full"))
insert_db("INSERT OR IGNORE INTO team_members (name, phone, role, language, access_level) VALUES (?, ?, ?, ?, ?)",
    ("Alina", "", "manager", "ru", "full"))
insert_db("INSERT OR IGNORE INTO team_members (name, phone, role, language, access_level) VALUES (?, ?, ?, ?, ?)",
    ("Anya", "", "manager", "ru", "full"))
insert_db("INSERT OR IGNORE INTO team_members (name, phone, role, language, access_level) VALUES (?, ?, ?, ?, ?)",
    ("Katya", "", "supervisor", "ru", "full"))

# === OWNERS ===
sam = insert_db("INSERT INTO owners (name, contact, report_schedule, notes) VALUES (?, ?, ?, ?)",
    ("Sam", "", "15-22 monthly", "Parking #1, Apt 25, 179, 134, 138"))
natan = insert_db("INSERT INTO owners (name, contact, report_schedule, notes) VALUES (?, ?, ?, ?)",
    ("Natan", "", "10-17 monthly (Pushkinskaya), 10-15 monthly (Kanatna)", "Pushkinskaya + Kanatna"))
haim = insert_db("INSERT INTO owners (name, contact, report_schedule, notes) VALUES (?, ?, ?, ?)",
    ("Haim", "", "", "Ekaterininskaya - mold/basement issue"))
amalia = insert_db("INSERT INTO owners (name, contact, report_schedule, notes) VALUES (?, ?, ?, ?)",
    ("Amalia", "", "", "Vorontsovsky, co-manages operations"))
david = insert_db("INSERT INTO owners (name, contact, report_schedule, notes) VALUES (?, ?, ?, ?)",
    ("David", "", "", "Primary owner - Tower Chekalov, Sofievskaya, M. Arnautskaya"))

# === PROPERTIES ===
tower = insert_db("INSERT INTO properties (name, address, type, status, owner_id, notes) VALUES (?, ?, ?, ?, ?, ?)",
    ("Tower Chekalov", "Tower Chekalov, Odessa", "residential", "active", david, "Main building - 14 units"))
pushkin = insert_db("INSERT INTO properties (name, address, type, status, owner_id, notes) VALUES (?, ?, ?, ?, ?, ?)",
    ("Pushkinskaya 34", "Pushkinskaya 34, Odessa", "residential", "active", natan, "Apts 1, 4, 23 + Office"))
kanatna = insert_db("INSERT INTO properties (name, address, type, status, owner_id, notes) VALUES (?, ?, ?, ?, ?, ?)",
    ("Kanatna", "Kanatna, Odessa", "residential", "active", natan, "Single unit - Eliahu tenant"))
voronts = insert_db("INSERT INTO properties (name, address, type, status, owner_id, notes) VALUES (?, ?, ?, ?, ?, ?)",
    ("Vorontsovsky", "Vorontsovsky, Odessa", "residential", "active", amalia, "Single unit"))
sofiev = insert_db("INSERT INTO properties (name, address, type, status, owner_id, notes) VALUES (?, ?, ?, ?, ?, ?)",
    ("Sofievskaya", "Sofievskaya, Odessa", "residential", "inactive", david, "Vacant - cameras need maintenance"))
arnaut = insert_db("INSERT INTO properties (name, address, type, status, owner_id, notes) VALUES (?, ?, ?, ?, ?, ?)",
    ("M. Arnautskaya 29", "Malaya Arnautskaya 29, Odessa", "storage", "active", david, "Apt 17 + mini storage spaces"))
ekater = insert_db("INSERT INTO properties (name, address, type, status, owner_id, notes) VALUES (?, ?, ?, ?, ?, ?)",
    ("Ekaterininskaya", "Ekaterininskaya, Odessa", "residential", "maintenance", haim, "Mold issue - needs basement waterproofing"))

# === APARTMENTS - Tower Chekalov ===
tc_apts = {}
tower_units = [
    ("21", 2, 1, "occupied", 380), ("25", 2, 1, "occupied", 400),
    ("105", 10, 2, "occupied", 400), ("134", 13, 2, "occupied", 450),
    ("138", 13, 2, "occupied", 500), ("149", 14, 2, "occupied", 420),
    ("155", 15, 2, "occupied", 430), ("168", 16, 2, "occupied", 300),
    ("169", 16, 2, "occupied", 300), ("170", 17, 2, "occupied", 400),
    ("179", 17, 2, "vacant", 450), ("182", 18, 2, "occupied", 450),
    ("202", 20, 2, "occupied", 480), ("216", 21, 2, "occupied", 550),
]
for num, floor, rooms, status, rent in tower_units:
    tc_apts[num] = insert_db(
        "INSERT INTO apartments (property_id, number, floor, rooms, status, monthly_rent, currency) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (tower, num, floor, rooms, status, rent, "USD"))

# === APARTMENTS - Pushkinskaya ===
push_apts = {}
for num, floor, rooms, status, rent in [("1", 1, 2, "occupied", 350), ("4", 1, 2, "occupied", 350), ("23", 2, 2, "occupied", 400)]:
    push_apts[num] = insert_db(
        "INSERT INTO apartments (property_id, number, floor, rooms, status, monthly_rent, currency) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (pushkin, num, floor, rooms, status, rent, "USD"))
# Office
insert_db("INSERT INTO apartments (property_id, number, floor, rooms, status, monthly_rent, currency, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    (pushkin, "Office", 1, 1, "occupied", 0, "USD", "Management office"))

# === APARTMENTS - Kanatna ===
kan_apt = insert_db("INSERT INTO apartments (property_id, number, floor, rooms, status, monthly_rent, currency) VALUES (?, ?, ?, ?, ?, ?, ?)",
    (kanatna, "1", 1, 2, "occupied", 500, "USD"))

# === APARTMENTS - Vorontsovsky ===
vor_apt = insert_db("INSERT INTO apartments (property_id, number, floor, rooms, status, monthly_rent, currency) VALUES (?, ?, ?, ?, ?, ?, ?)",
    (voronts, "1", 1, 2, "occupied", 450, "USD"))

# === APARTMENTS - M. Arnautskaya ===
arn_apt = insert_db("INSERT INTO apartments (property_id, number, floor, rooms, status, monthly_rent, currency, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    (arnaut, "17", 1, 1, "vacant", 0, "USD", "Storage space - periodic checks"))

# === TENANTS + LEASES (placeholder names for occupied units) ===
tenant_data = [
    ("Tenant Apt 21", tc_apts["21"], 380), ("Tenant Apt 25", tc_apts["25"], 400),
    ("Tenant Apt 105", tc_apts["105"], 400), ("Tenant Apt 134", tc_apts["134"], 450),
    ("Tenant Apt 138", tc_apts["138"], 500), ("Tenant Apt 149", tc_apts["149"], 420),
    ("Tenant Apt 155", tc_apts["155"], 430), ("Tenant Apt 168", tc_apts["168"], 300),
    ("Tenant Apt 169", tc_apts["169"], 300), ("Tenant Apt 170", tc_apts["170"], 400),
    ("Tenant Apt 182", tc_apts["182"], 450), ("Tenant Apt 202", tc_apts["202"], 480),
    ("Tenant Apt 216", tc_apts["216"], 550),
    ("Tenant Push 1", push_apts["1"], 350), ("Tenant Push 4", push_apts["4"], 350),
    ("Tenant Push 23", push_apts["23"], 400),
    ("Eliahu", kan_apt, 500), ("Tenant Voronts", vor_apt, 450),
]

for name, apt_id, rent in tenant_data:
    tid = insert_db("INSERT INTO tenants (name, phone, language) VALUES (?, ?, ?)",
        (name, "", "ru"))
    insert_db("INSERT INTO leases (apartment_id, tenant_id, start_date, end_date, rent_amount, deposit, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (apt_id, tid, "2025-01-01", "2026-06-30", rent, rent, "active"))

# === MAINTENANCE ORDERS ===
insert_db("INSERT INTO maintenance_orders (apartment_id, description, status, assigned_to) VALUES (?, ?, ?, ?)",
    (tc_apts["138"], "Boiler not heating - under warranty", "in_progress", "Service Center"))
insert_db("INSERT INTO maintenance_orders (apartment_id, description, status, assigned_to) VALUES (?, ?, ?, ?)",
    (tc_apts["168"], "Fridge malfunction - sent to service", "in_progress", "Service Center"))
insert_db("INSERT INTO maintenance_orders (apartment_id, description, status, assigned_to) VALUES (?, ?, ?, ?)",
    (tc_apts["216"], "Fridge issue - needs service center visit", "reported", ""))
insert_db("INSERT INTO maintenance_orders (apartment_id, description, status, assigned_to) VALUES (?, ?, ?, ?)",
    (tc_apts["179"], "Door closer needs replacement - ordered 2 months ago", "in_progress", "Yura"))
insert_db("INSERT INTO maintenance_orders (apartment_id, description, status, assigned_to, notes) VALUES (?, ?, ?, ?, ?)",
    (push_apts["1"], "Controller repair", "in_progress", "Yura", "Took 2 weeks to pick up, now in service"))
# Ekaterininskaya mold - use apt 17 from arnaut as placeholder
insert_db("INSERT INTO maintenance_orders (apartment_id, description, status, assigned_to, notes) VALUES (?, ?, ?, ?, ?)",
    (arn_apt, "Mold / basement waterproofing needed - Ekaterininskaya", "reported", "", "Critical - must fix basement before any renovation"))

# === TASKS ===
insert_db("INSERT INTO tasks (title, assigned_to, due_date, status, priority) VALUES (?, ?, ?, ?, ?)",
    ("Submit meter readings to gas/electricity bots", "Alina", "2026-04-03", "pending", "high"))
insert_db("INSERT INTO tasks (title, assigned_to, due_date, status, priority) VALUES (?, ?, ?, ?, ?)",
    ("Collect rent from Apt 216", "Alina", "2026-04-01", "pending", "urgent"))
insert_db("INSERT INTO tasks (title, assigned_to, due_date, status, priority) VALUES (?, ?, ?, ?, ?)",
    ("Check Pushkinskaya roof after rain", "Anya", "2026-04-05", "pending", "normal"))
insert_db("INSERT INTO tasks (title, assigned_to, due_date, status, priority, notes) VALUES (?, ?, ?, ?, ?, ?)",
    ("Kanatna roof painting", "Kirill", "2026-04-15", "in_progress", "normal", "Waiting for dry weather"))
insert_db("INSERT INTO tasks (title, assigned_to, due_date, status, priority) VALUES (?, ?, ?, ?, ?)",
    ("Follow up on Apt 179 door closer with Yura", "Alina", "2026-04-07", "pending", "normal"))
insert_db("INSERT INTO tasks (title, assigned_to, status, priority) VALUES (?, ?, ?, ?)",
    ("Remind Eliahu about utility payment (5 months overdue)", "Alina", "pending", "high"))
insert_db("INSERT INTO tasks (title, assigned_to, status, priority, notes) VALUES (?, ?, ?, ?, ?)",
    ("Prepare owner report for Sam", "Katya", "in_progress", "normal", "Due Apr 15-22"))
insert_db("INSERT INTO tasks (title, assigned_to, status, priority, notes) VALUES (?, ?, ?, ?, ?)",
    ("Check M. Arnautskaya property", "Anya", "pending", "low", "Monthly security check"))

# === WARRANTIES ===
insert_db("INSERT INTO warranties (apartment_id, appliance, start_date, end_date, provider, notes) VALUES (?, ?, ?, ?, ?, ?)",
    (tc_apts["138"], "Boiler", "2025-06-01", "2027-06-01", "Manufacturer", "Warranty claim submitted"))
insert_db("INSERT INTO warranties (apartment_id, appliance, start_date, end_date, provider, notes) VALUES (?, ?, ?, ?, ?, ?)",
    (tc_apts["168"], "Refrigerator", "2024-01-01", "2026-12-31", "Manufacturer", "In service center"))
insert_db("INSERT INTO warranties (apartment_id, appliance, start_date, end_date, provider) VALUES (?, ?, ?, ?, ?)",
    (tc_apts["216"], "Refrigerator", "2024-06-01", "2026-06-01", "Manufacturer"))

print(f"Seeded: 5 owners, 7 properties, {len(tower_units)+4+1+1+1} apartments, {len(tenant_data)} tenants/leases, 6 maintenance orders, 8 tasks, 3 warranties")
