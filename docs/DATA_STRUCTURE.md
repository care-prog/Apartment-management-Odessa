# DATA STRUCTURE: Apartment-management-Odessa

> Database schema and entity relationships.
> The project dashboard renders the Mermaid diagram below.
> Update this file whenever the database schema changes.

---

<!-- DASHBOARD:DATA_STRUCTURE:START -->
```mermaid
erDiagram
    PROPERTY {
        int id PK
        string name
        string address
        string type
        string status
        string owner_id FK
        datetime created_at
    }
    OWNER {
        int id PK
        string name
        string contact
        string report_schedule
        string notes
    }
    APARTMENT {
        int id PK
        int property_id FK
        string number
        int floor
        int rooms
        string status
        decimal monthly_rent
        string currency
    }
    TENANT {
        int id PK
        string name
        string phone
        string email
        string passport_info
        string language
        datetime move_in_date
    }
    LEASE {
        int id PK
        int apartment_id FK
        int tenant_id FK
        date start_date
        date end_date
        decimal rent_amount
        decimal deposit
        string status
        string contract_url
    }
    PAYMENT {
        int id PK
        int lease_id FK
        string type
        decimal amount
        date payment_date
        string method
        string status
        string receipt_url
    }
    METER_READING {
        int id PK
        int apartment_id FK
        string meter_type
        decimal reading_value
        date reading_date
        string photo_url
        string submitted_to
    }
    UTILITY_BILL {
        int id PK
        int apartment_id FK
        string period
        string bill_type
        decimal amount
        string status
        date due_date
    }
    MAINTENANCE_ORDER {
        int id PK
        int apartment_id FK
        string description
        string status
        string assigned_to
        decimal cost
        int warranty_id FK
        date created_at
        date completed_at
    }
    WARRANTY {
        int id PK
        int apartment_id FK
        string appliance
        date start_date
        date end_date
        string provider
        string document_url
    }
    TASK {
        int id PK
        string title
        string description
        string assigned_to
        date due_date
        string status
        string priority
        string notes
    }
    DOCUMENT {
        int id PK
        int property_id FK
        int apartment_id FK
        string doc_type
        string file_url
        string description
        datetime uploaded_at
    }
    FINANCIAL_TRANSACTION {
        int id PK
        int owner_id FK
        string type
        decimal amount
        date transaction_date
        string description
        string category
    }

    OWNER ||--o{ PROPERTY : owns
    PROPERTY ||--o{ APARTMENT : contains
    APARTMENT ||--o{ LEASE : has
    TENANT ||--o{ LEASE : signs
    LEASE ||--o{ PAYMENT : receives
    APARTMENT ||--o{ METER_READING : tracks
    APARTMENT ||--o{ UTILITY_BILL : generates
    APARTMENT ||--o{ MAINTENANCE_ORDER : has
    APARTMENT ||--o{ WARRANTY : covers
    APARTMENT ||--o{ DOCUMENT : stores
    PROPERTY ||--o{ DOCUMENT : stores
    OWNER ||--o{ FINANCIAL_TRANSACTION : tracks
    WARRANTY ||--o{ MAINTENANCE_ORDER : references
```
<!-- DASHBOARD:DATA_STRUCTURE:END -->
