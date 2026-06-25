-- ====================================================================
-- CompliGuard AI -- case audit & persistence tables
-- Run this in the Supabase SQL Editor (in ADDITION to schema.sql).
-- These store the investigation results so case history survives restarts
-- and the full audit trail is queryable -- a compliance requirement.
-- ====================================================================

-- One row per investigated case
create table if not exists cases (
    case_id        text primary key,
    customer_id    text,
    alert_reason   text,
    recipient      text,
    alert_type     text,
    typology       text,
    priority       text,
    status         text,            -- see app/core/case_status.py (NEW .. CLOSED)
    risk_score     integer,
    rule_score     integer,
    ai_score       integer,
    risk_level     text,
    recommendation text,
    priority       text,            -- P1 | P2 | P3 | P4
    priority_reason text,           -- why this priority was assigned
    sla_due_at     timestamptz,     -- review deadline derived from priority
    assigned_to    text,            -- analyst / queue the case is assigned to
    created_at     timestamptz default now(),
    updated_at     timestamptz default now()
);

-- For existing installs (the columns above are added idempotently):
alter table cases add column if not exists priority        text;
alter table cases add column if not exists priority_reason text;
alter table cases add column if not exists sla_due_at      timestamptz;
alter table cases add column if not exists assigned_to     text;

-- The audit timeline: one row per agent action
create table if not exists case_events (
    id          bigserial primary key,
    case_id     text references cases(case_id),
    agent_name  text,
    event_type  text,
    message     text,
    confidence  numeric,
    created_at  timestamptz default now()
);

-- Each agent's structured output + confidence + duration + model governance
create table if not exists agent_outputs (
    id              bigserial primary key,
    case_id         text references cases(case_id),
    agent_name      text,
    output          jsonb,
    confidence      numeric,
    duration_ms     integer,
    -- model governance: which model / prompt / ruleset / policy produced this output
    model_name      text,
    prompt_version  text,
    policy_version  text,
    ruleset_version text,
    created_at      timestamptz default now()
);
-- For existing installs:
alter table agent_outputs add column if not exists model_name      text;
alter table agent_outputs add column if not exists prompt_version  text;
alter table agent_outputs add column if not exists policy_version  text;
alter table agent_outputs add column if not exists ruleset_version text;

-- The risk assessment (rule + AI blend)
create table if not exists risk_assessments (
    id          bigserial primary key,
    case_id     text references cases(case_id),
    rule_score  integer,
    ai_score    integer,
    final_score integer,
    risk_level  text,
    key_drivers jsonb,
    factors     jsonb,            -- explainable breakdown: factor + points + evidence
    explanation text,
    created_at  timestamptz default now()
);

-- Generated SAR drafts
create table if not exists sar_drafts (
    id               bigserial primary key,
    case_id          text references cases(case_id),
    draft_text       text,
    quality_score    integer,
    claims_supported boolean,
    created_at       timestamptz default now()
);

-- Watchlist screening matches recorded per case
create table if not exists watchlist_matches (
    id                    bigserial primary key,
    case_id               text references cases(case_id),
    searched_name         text,
    matched_entity_id     bigint,        -- watchlist_entities.id
    matched_entity        text,
    list_type             text,
    match_score           numeric,
    match_type            text,          -- exact | fuzzy | alias | no_match
    false_positive_checked boolean default false,
    analyst_confirmed     boolean,
    created_at            timestamptz default now()
);

-- The human-in-the-loop decisions (incl. analyst feedback for learning)
create table if not exists human_decisions (
    id                     bigserial primary key,
    case_id                text references cases(case_id),
    decision               text,    -- approve | reject | edit | request_more_info
    analyst_id             text,
    notes                  text,    -- reason / requested info
    final_risk_level       text,    -- analyst override of the risk level
    analyst_agrees_with_ai boolean, -- did the analyst agree with the AI's assessment?
    corrected_typology     text,    -- the typology the analyst says it really was
    corrected_reason       text,    -- the analyst's corrected rationale
    feedback_tags          jsonb,   -- e.g. ["false_positive","wrong_typology","good_sar_draft"]
    created_at             timestamptz default now()
);

-- For existing installs:
alter table human_decisions add column if not exists analyst_agrees_with_ai boolean;
alter table human_decisions add column if not exists corrected_typology     text;
alter table human_decisions add column if not exists corrected_reason       text;
alter table human_decisions add column if not exists feedback_tags          jsonb;

-- ====================================================================
-- Full auditability: evidence, triggered rules, policy citations, and
-- the complete status history. Together these make every decision
-- traceable to its evidence, rules, policy basis, and human approval.
-- ====================================================================

-- Every structured evidence item behind the case's claims
create table if not exists evidence_items (
    evidence_id text primary key,
    case_id     text references cases(case_id),
    source_type text not null,   -- transaction | customer_profile | watchlist | policy | memory | analyst_note | rule
    source_id   text,
    field       text,
    value       jsonb,
    description text,
    created_at  timestamptz default now()
);

-- Each AML rule that fired, with the evidence IDs it relied on
create table if not exists rule_hits (
    id           bigserial primary key,
    case_id      text references cases(case_id),
    rule_id      text,
    rule_name    text,
    typology     text,
    severity     text,
    points       integer,
    evidence_ids jsonb,           -- the EvidenceItem IDs supporting this rule
    created_at   timestamptz default now()
);

-- The policies retrieved + reranked by the RAG layer for this case
create table if not exists policy_citations (
    id              bigserial primary key,
    case_id         text references cases(case_id),
    policy_id       text,
    chunk_id        text,          -- the specific section chunk that was cited
    title           text,
    section         text,
    category        text,
    content_excerpt text,
    retrieval_score numeric,
    rerank_score    numeric,
    created_at      timestamptz default now()
);
alter table policy_citations add column if not exists chunk_id text;

-- Append-only status transitions (who changed it, why, and when)
create table if not exists case_status_history (
    id         bigserial primary key,
    case_id    text references cases(case_id),
    old_status text,
    new_status text,
    changed_by text,
    reason     text,
    created_at timestamptz default now()
);

-- ====================================================================
-- Money-flow edges for relationship-graph analysis (layering / mule
-- detection). Each row is a directed transfer between two accounts.
-- ====================================================================
create table if not exists transaction_edges (
    id               bigserial primary key,
    from_account     text,
    to_account       text,
    amount           numeric,
    transaction_time timestamptz,
    case_id          text
);

-- Demo layering/dispersion network for CUST-40233: fan-out to 8 recipients,
-- with two of them forwarding onward to a common collector (Beneficiary D).
insert into transaction_edges (from_account, to_account, amount, transaction_time)
select * from (values
    ('CUST-40233','Beneficiary A',3000,'2026-06-20T09:05:00'::timestamptz),
    ('CUST-40233','Beneficiary B',3000,'2026-06-20T10:05:00'::timestamptz),
    ('CUST-40233','Beneficiary C',3000,'2026-06-20T11:05:00'::timestamptz),
    ('CUST-40233','Beneficiary D',3000,'2026-06-20T12:05:00'::timestamptz),
    ('CUST-40233','Beneficiary E',3000,'2026-06-20T13:05:00'::timestamptz),
    ('CUST-40233','Beneficiary F',3000,'2026-06-20T14:05:00'::timestamptz),
    ('CUST-40233','Beneficiary G',3000,'2026-06-20T15:05:00'::timestamptz),
    ('CUST-40233','Beneficiary H',3000,'2026-06-20T16:05:00'::timestamptz),
    ('Beneficiary A','Beneficiary D',2900,'2026-06-20T17:30:00'::timestamptz),
    ('Beneficiary B','Beneficiary D',2900,'2026-06-20T18:00:00'::timestamptz)
) as v
where not exists (select 1 from transaction_edges);
