-- ====================================================================
-- CompliGuard AI -- Supabase schema + seed data
-- Paste this whole file into the Supabase SQL Editor and click "Run".
-- It creates the 3 relational tables and fills them with demo data.
-- ====================================================================

-- Clean slate (safe to re-run)
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
('CUST-10291', 'Aiman Rahman', 'Junior Clerk',  4000, 'Completed', 'Medium', 14, 'Malaysia', 1),
('CUST-20555', 'Sarah Lim',    'Business Owner', 45000,'Completed', 'Low',    60, 'Malaysia', 0);

-- --------------------------------------------------------------------
-- Transactions
-- --------------------------------------------------------------------
create table transactions (
    transaction_id   text primary key,
    customer_id      text references customers(customer_id),
    amount           integer,
    date_time        timestamp,
    recipient        text,
    country          text,
    transaction_type text,
    is_new_recipient boolean
);

insert into transactions values
-- suspicious burst for CUST-10291 (the demo alert)
('TXN-9001','CUST-10291',9800,'2026-06-22T09:15:00','Global Trade Ltd','Cambodia','transfer',true),
('TXN-9002','CUST-10291',9800,'2026-06-22T11:40:00','Global Trade Ltd','Cambodia','transfer',true),
('TXN-9003','CUST-10291',9800,'2026-06-22T14:55:00','Global Trade Ltd','Cambodia','transfer',true),
-- normal historical activity for CUST-10291
('TXN-1001','CUST-10291',120,'2026-05-03T12:00:00','Speedmart Grocery','Malaysia','payment',false),
('TXN-1002','CUST-10291',300,'2026-05-10T18:30:00','TNB Utilities','Malaysia','payment',false),
('TXN-1003','CUST-10291',250,'2026-05-20T09:00:00','Mama Rahman','Malaysia','transfer',false);

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
('Northern Star Holdings', 'sanctions',          'High');
