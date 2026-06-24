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
    status         text,            -- awaiting_decision | closed | auto_closed
    risk_score     integer,
    rule_score     integer,
    ai_score       integer,
    risk_level     text,
    recommendation text,
    created_at     timestamptz default now(),
    updated_at     timestamptz default now()
);

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

-- Each agent's structured output + confidence + duration
create table if not exists agent_outputs (
    id          bigserial primary key,
    case_id     text references cases(case_id),
    agent_name  text,
    output      jsonb,
    confidence  numeric,
    duration_ms integer,
    created_at  timestamptz default now()
);

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

-- The human-in-the-loop decisions
create table if not exists human_decisions (
    id          bigserial primary key,
    case_id     text references cases(case_id),
    decision    text,            -- approve | reject | edit
    notes       text,
    created_at  timestamptz default now()
);
