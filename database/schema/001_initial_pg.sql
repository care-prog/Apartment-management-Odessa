-- Apartment Management Odessa - Initial Schema (PostgreSQL)

CREATE TABLE IF NOT EXISTS owners (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    contact TEXT,
    report_schedule TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS properties (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    address TEXT,
    type TEXT DEFAULT 'residential',
    status TEXT DEFAULT 'active',
    owner_id INTEGER REFERENCES owners(id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS apartments (
    id SERIAL PRIMARY KEY,
    property_id INTEGER NOT NULL REFERENCES properties(id),
    number TEXT NOT NULL,
    floor INTEGER,
    rooms INTEGER,
    status TEXT DEFAULT 'vacant',
    monthly_rent DOUBLE PRECISION DEFAULT 0,
    currency TEXT DEFAULT 'USD',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tenants (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    passport_info TEXT,
    language TEXT DEFAULT 'ru',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS leases (
    id SERIAL PRIMARY KEY,
    apartment_id INTEGER NOT NULL REFERENCES apartments(id),
    tenant_id INTEGER NOT NULL REFERENCES tenants(id),
    start_date DATE NOT NULL,
    end_date DATE,
    rent_amount DOUBLE PRECISION NOT NULL,
    deposit DOUBLE PRECISION DEFAULT 0,
    status TEXT DEFAULT 'active',
    contract_url TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    lease_id INTEGER NOT NULL REFERENCES leases(id),
    type TEXT NOT NULL DEFAULT 'rent',
    amount DOUBLE PRECISION NOT NULL,
    payment_date DATE,
    method TEXT DEFAULT 'cash',
    status TEXT DEFAULT 'pending',
    receipt_url TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS meter_readings (
    id SERIAL PRIMARY KEY,
    apartment_id INTEGER NOT NULL REFERENCES apartments(id),
    meter_type TEXT NOT NULL,
    reading_value DOUBLE PRECISION NOT NULL,
    reading_date DATE NOT NULL,
    photo_url TEXT,
    submitted_to TEXT,
    submitted BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS utility_bills (
    id SERIAL PRIMARY KEY,
    apartment_id INTEGER NOT NULL REFERENCES apartments(id),
    period TEXT NOT NULL,
    bill_type TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    status TEXT DEFAULT 'pending',
    due_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS warranties (
    id SERIAL PRIMARY KEY,
    apartment_id INTEGER NOT NULL REFERENCES apartments(id),
    appliance TEXT NOT NULL,
    start_date DATE,
    end_date DATE,
    provider TEXT,
    document_url TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS maintenance_orders (
    id SERIAL PRIMARY KEY,
    apartment_id INTEGER NOT NULL REFERENCES apartments(id),
    description TEXT NOT NULL,
    status TEXT DEFAULT 'reported',
    assigned_to TEXT,
    cost DOUBLE PRECISION,
    warranty_id INTEGER REFERENCES warranties(id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    assigned_to TEXT,
    due_date DATE,
    status TEXT DEFAULT 'pending',
    priority TEXT DEFAULT 'normal',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    property_id INTEGER REFERENCES properties(id),
    apartment_id INTEGER REFERENCES apartments(id),
    doc_type TEXT NOT NULL,
    file_url TEXT,
    description TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS team_members (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT UNIQUE NOT NULL,
    role TEXT DEFAULT 'manager',
    language TEXT DEFAULT 'ru',
    access_level TEXT DEFAULT 'full',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS office_expenses (
    id SERIAL PRIMARY KEY,
    description TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    category TEXT DEFAULT 'general',
    date DATE,
    receipt_url TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS owner_payments (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES owners(id),
    amount DOUBLE PRECISION NOT NULL,
    payment_date DATE NOT NULL,
    method TEXT DEFAULT 'cash',
    period TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS financial_transactions (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER REFERENCES owners(id),
    type TEXT NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    transaction_date DATE,
    description TEXT,
    category TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cash_transactions (
    id SERIAL PRIMARY KEY,
    type TEXT NOT NULL DEFAULT 'expense',
    amount DOUBLE PRECISION NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    category TEXT DEFAULT 'general',
    description TEXT,
    transaction_date DATE,
    apartment_id INTEGER REFERENCES apartments(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS commission_overrides (
    monday_id TEXT PRIMARY KEY,
    commission_type TEXT NOT NULL DEFAULT 'percent',
    commission_value DOUBLE PRECISION NOT NULL DEFAULT 10,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
