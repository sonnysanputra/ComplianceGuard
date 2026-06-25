-- ====================================================================
-- CompliGuard AI -- Supabase schema + seed data (richer, multi-typology)
-- Paste this whole file into the Supabase SQL Editor and click "Run".
-- Safe to re-run -- it drops and recreates the tables.
-- ====================================================================

drop table if exists transactions;
drop table if exists customers;
drop table if exists watchlist;

-- --------------------------------------------------------------------
-- Customers (KYC profiles)
-- --------------------------------------------------------------------
create table customers (
    customer_id        text primary key,
    name               text,
    occupation         text,
    declared_income    integer,        -- RM per month
    kyc_status         text,
    risk_category      text,
    account_age_months integer,
    country            text,
    previous_alerts    integer
);

insert into customers values
('CUST-10291', 'Aiman Rahman', 'Junior Clerk',   4000,  'Completed', 'Medium', 14, 'Malaysia', 1),
('CUST-20555', 'Sarah Lim',    'Business Owner',  45000, 'Completed', 'Low',    60, 'Malaysia', 0),
('CUST-30877', 'Daniel Tan',   'Student',         1500,  'Completed', 'High',   4,  'Malaysia', 2),
('CUST-40233', 'Priya Nair',   'Freelancer',      6000,  'Completed', 'Medium', 22, 'Malaysia', 0),
('CUST-50001', 'Tech Solutions Sdn Bhd', 'Business Owner', 30000, 'Completed', 'Low', 36, 'Malaysia', 0);

-- --------------------------------------------------------------------
-- Transactions  (direction: 'in' = incoming, 'out' = outgoing)
-- --------------------------------------------------------------------
create table transactions (
    transaction_id   text primary key,
    customer_id      text references customers(customer_id),
    amount           integer,
    date_time        timestamp,
    recipient        text,
    country          text,
    transaction_type text,
    is_new_recipient boolean,
    direction        text
);

insert into transactions values
-- ===== CUST-10291 : STRUCTURING (3x just under RM10k threshold, overseas) =====
('TXN-9001','CUST-10291',9800,'2026-06-22T09:15:00','Global Trade Ltd','Cambodia','transfer',true,'out'),
('TXN-9002','CUST-10291',9800,'2026-06-22T11:40:00','Global Trade Ltd','Cambodia','transfer',true,'out'),
('TXN-9003','CUST-10291',9800,'2026-06-22T14:55:00','Global Trade Ltd','Cambodia','transfer',true,'out'),
('TXN-1001','CUST-10291',120,'2026-05-03T12:00:00','Speedmart Grocery','Malaysia','payment',false,'out'),
('TXN-1002','CUST-10291',300,'2026-05-10T18:30:00','TNB Utilities','Malaysia','payment',false,'out'),
('TXN-1003','CUST-10291',250,'2026-05-20T09:00:00','Mama Rahman','Malaysia','transfer',false,'out'),

-- ===== CUST-20555 : FALSE POSITIVE (large but to a known supplier, fits income) =====
('TXN-2001','CUST-20555',18000,'2026-04-15T10:00:00','Supplier ABC Sdn Bhd','Malaysia','transfer',false,'out'),
('TXN-2002','CUST-20555',22000,'2026-05-15T10:00:00','Supplier ABC Sdn Bhd','Malaysia','transfer',false,'out'),
('TXN-2003','CUST-20555',20000,'2026-06-22T10:00:00','Supplier ABC Sdn Bhd','Malaysia','transfer',false,'out'),

-- ===== CUST-30877 : MONEY MULE (large inbound, rapidly forwarded out) =====
('TXN-3000','CUST-30877',200,'2026-06-01T12:00:00','Cafe Latte','Malaysia','payment',false,'out'),
('TXN-3001','CUST-30877',48000,'2026-06-21T10:00:00','Overseas Holdings','Malaysia','transfer',true,'in'),
('TXN-3002','CUST-30877',11500,'2026-06-21T12:30:00','Recipient One','Malaysia','transfer',true,'out'),
('TXN-3003','CUST-30877',11500,'2026-06-21T13:10:00','Recipient Two','Malaysia','transfer',true,'out'),
('TXN-3004','CUST-30877',11500,'2026-06-21T15:45:00','Recipient Three','Malaysia','transfer',true,'out'),
('TXN-3005','CUST-30877',11500,'2026-06-21T17:20:00','Recipient Four','Malaysia','transfer',true,'out'),

-- ===== CUST-40233 : LAYERING / DISPERSION (split across many new recipients) =====
('TXN-4000','CUST-40233',500,'2026-06-05T09:00:00','Grab','Malaysia','payment',false,'out'),
('TXN-4001','CUST-40233',3000,'2026-06-20T09:05:00','Beneficiary A','Malaysia','transfer',true,'out'),
('TXN-4002','CUST-40233',3000,'2026-06-20T09:40:00','Beneficiary B','Malaysia','transfer',true,'out'),
('TXN-4003','CUST-40233',3000,'2026-06-20T10:15:00','Beneficiary C','Malaysia','transfer',true,'out'),
('TXN-4004','CUST-40233',3000,'2026-06-20T11:00:00','Beneficiary D','Malaysia','transfer',true,'out'),
('TXN-4005','CUST-40233',3000,'2026-06-20T12:30:00','Beneficiary E','Malaysia','transfer',true,'out'),
('TXN-4006','CUST-40233',3000,'2026-06-20T14:10:00','Beneficiary F','Malaysia','transfer',true,'out'),
('TXN-4007','CUST-40233',3000,'2026-06-20T15:50:00','Beneficiary G','Malaysia','transfer',true,'out'),
('TXN-4008','CUST-40233',3000,'2026-06-20T17:30:00','Beneficiary H','Malaysia','transfer',true,'out'),

-- ===== CUST-50001 : DOCUMENTED SUPPLIER PAYMENT (false positive -> auto-close) =====
('TXN-5000','CUST-50001',1500,'2026-05-02T10:00:00','AWS Cloud','Malaysia','payment',false,'out'),
('TXN-5001','CUST-50001',1800,'2026-05-18T10:00:00','Office Rental','Malaysia','payment',false,'out'),
('TXN-5002','CUST-50001',20000,'2026-06-22T10:00:00','CloudHost Services','Malaysia','transfer',true,'out');

-- --------------------------------------------------------------------
-- Watchlist entities (multi-list: sanctions, PEP, blacklist, adverse media,
-- scam/mule accounts, high-risk entities). Modelled on the kind of consolidated
-- screening data a reporting institution maintains (e.g. UN Security Council
-- Consolidated List for sanctions).
-- --------------------------------------------------------------------
drop table if exists watchlist_entities cascade;
create table watchlist_entities (
    id           bigserial primary key,
    entity_name  text not null,
    entity_type  text,            -- individual | company | account | wallet | country
    list_type    text,            -- UN_SANCTIONS | PEP | INTERNAL_BLACKLIST | ADVERSE_MEDIA | SCAM_ACCOUNT | HIGH_RISK_ENTITY
    reference_id text,
    country      text,
    risk_level   text,
    source       text,
    date_added   timestamptz default now(),
    is_active    boolean default true
);

insert into watchlist_entities (entity_name, entity_type, list_type, reference_id, country, risk_level, source) values
('Global Trade Limited',      'company',    'INTERNAL_BLACKLIST', 'IBL-1001',  'Cambodia',  'High',     'Internal investigations unit'),
('Overseas Holdings Inc',     'company',    'INTERNAL_BLACKLIST', 'IBL-1002',  'Malaysia',  'Medium',   'Internal investigations unit'),
('Ahmad Zulkifli',            'individual', 'PEP',                'PEP-2001',  'Malaysia',  'High',     'Domestic PEP register'),
('Northern Star Holdings',    'company',    'UN_SANCTIONS',       'UN-3001',   'North Korea','Critical', 'UN Security Council Consolidated List'),
('Reza Karimi',               'individual', 'UN_SANCTIONS',       'UN-3002',   'Iran',      'Critical', 'UN Security Council Consolidated List'),
('Sunrise Media Group',       'company',    'ADVERSE_MEDIA',      'AM-4001',   'Malaysia',  'Medium',   'Adverse media monitoring'),
('Fast Cash Mule 88',         'account',    'SCAM_ACCOUNT',       'SCAM-5001', 'Malaysia',  'High',     'Known mule account database'),
('Crypto Mixer Wallet 0x9f',  'wallet',     'HIGH_RISK_ENTITY',   'HRE-6001',  'Unknown',   'High',     'Blockchain analytics');

-- --------------------------------------------------------------------
-- Country-risk register (production-storage form of country_risk.yaml).
-- The demo runtime reads the YAML register for portability; in production this
-- table would be maintained from FATF / UN sanctions / regulator guidance.
-- --------------------------------------------------------------------
drop table if exists country_risk;
create table country_risk (
    country      text primary key,
    risk_level   text,            -- CALL_FOR_ACTION | INCREASED_MONITORING | HIGH
    source       text,
    reason       text,
    last_updated timestamptz default now()
);

insert into country_risk (country, risk_level, source, reason) values
('North Korea', 'CALL_FOR_ACTION', 'FATF', 'FATF high-risk jurisdiction subject to a call for action'),
('Iran',        'CALL_FOR_ACTION', 'FATF', 'FATF high-risk jurisdiction subject to a call for action'),
('Myanmar',     'CALL_FOR_ACTION', 'FATF', 'FATF high-risk jurisdiction subject to a call for action'),
('Cambodia',    'HIGH', 'Internal demo configuration', 'Internal demo high-risk jurisdiction (not an official FATF listing)');
