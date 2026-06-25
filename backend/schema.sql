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
('CUST-40233', 'Priya Nair',   'Freelancer',      6000,  'Completed', 'Medium', 22, 'Malaysia', 0);

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
('TXN-4008','CUST-40233',3000,'2026-06-20T17:30:00','Beneficiary H','Malaysia','transfer',true,'out');

-- --------------------------------------------------------------------
-- Watchlist
-- --------------------------------------------------------------------
create table watchlist (
    id          serial primary key,
    entity_name text,
    list_type   text,
    risk_level  text
);

insert into watchlist (entity_name, list_type, risk_level) values
('Global Trading Limited', 'internal_blacklist', 'High'),
('Ahmad Zulkifli',         'PEP',                'High'),
('Northern Star Holdings', 'sanctions',          'High'),
('Overseas Holdings Inc',  'internal_blacklist', 'Medium');

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
