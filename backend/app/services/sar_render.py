"""
SAR rendering -- turns the structured SAR package (a JSON dict) into the
regulator-style 12-section report, in Markdown / sections (for PDF + DOCX).

The SAR Drafting Agent produces the structured package; everything downstream
(display, Markdown, PDF, DOCX) renders FROM that single source of truth, so the
exports stay consistent and easy to validate.

Per SC / FIED guidance this is framed as a DRAFT investigation package for a human
analyst -- never an automatic STR submission.
"""

_DISCLAIMER = ("AI-generated DRAFT investigation package. Requires human analyst "
               "review and sign-off before any STR is lodged with FIED.")


def _kv(d: dict, *keys) -> list[str]:
    """Render selected key/values of a dict as 'Key: value' lines (skipping None)."""
    out = []
    for k in keys:
        v = d.get(k)
        if v in (None, "", [], {}):
            continue
        label = k.replace("_", " ").title()
        out.append(f"{label}: {v}")
    return out


def sar_to_sections(pkg: dict, human_review: dict | None = None) -> list[tuple[str, list[str]]]:
    """Return the 12 SAR sections as (heading, lines). `human_review`, if given,
    overrides section 11 with the live analyst decision."""
    ci = pkg.get("case_information", {})
    cust = pkg.get("customer_information", {})
    trig = pkg.get("alert_trigger", {})
    timeline = pkg.get("transaction_timeline", [])
    indicators = pkg.get("suspicious_indicators", [])
    kyc = pkg.get("kyc_review", {})
    wl = pkg.get("watchlist_screening", {})
    policies = pkg.get("policy_references", [])
    risk = pkg.get("risk_assessment", {})
    ai = pkg.get("ai_recommendation", {})
    hd = human_review or pkg.get("human_analyst_decision", {})
    attachments = pkg.get("attachments", [])
    register = pkg.get("evidence_register", [])

    def tx_line(t: dict) -> str:
        tag = " [NEW recipient]" if t.get("new_recipient") else ""
        arrow = "IN <-" if str(t.get("direction", "")).upper() == "IN" else "OUT ->"
        when = t.get("time") or t.get("date", "-")
        ttype = t.get("transaction_type") or t.get("type", "-")
        note = f"  -- {t['risk_note']}" if t.get("risk_note") else ""
        return (f"{when}  |  {arrow} RM{t.get('amount', 0):,}  "
                f"{t.get('recipient', '-')} ({t.get('country', '-')}, {ttype}){tag}{note}")

    return [
        ("1. Case Information",
         _kv(ci, "case_id", "alert_id", "alert_type", "priority", "status",
             "report_type", "generated_at")),
        ("2. Customer Information",
         _kv(cust, "customer_id", "name", "occupation", "declared_income",
             "account_age_months", "risk_category", "kyc_status", "country")),
        ("3. Alert Trigger",
         _kv(trig, "reason", "recipient", "amount", "jurisdiction",
             "num_transactions", "supporting_document")),
        ("4. Transaction Timeline",
         [tx_line(t) for t in timeline] or ["No transaction records available."]),
        ("5. Suspicious Indicators",
         list(indicators) or ["No specific indicators identified."]),
        ("6. KYC / Customer Profile Review",
         _kv(kyc, "consistency", "key_concern", "income_ratio", "checks_failed",
             "edd_required")),
        ("7. Watchlist / Sanctions Screening",
         _kv(wl, "customer_verdict", "recipient_verdict", "best_match",
             "list_type", "match_score", "required_action")),
        ("8. Policy References",
         [f"{p.get('policy_id')}: {p.get('title')} (section {p.get('section')})"
          + (f" [{p.get('source')}]" if p.get("source") else "")
          for p in policies] or ["None cited."]),
        ("9. Risk Assessment",
         _kv(risk, "final_score", "rule_score", "ai_score", "risk_level",
             "key_drivers", "explanation")),
        ("10. AI Recommendation",
         _kv(ai, "recommended_action", "narrative", "human_review_required")),
        ("11. Human Analyst Decision",
         _kv(hd, "decision", "analyst_id", "note", "final_risk_level")
         or ["Pending human analyst review."]),
        ("12. Attachments / Supporting Evidence",
         list(attachments)
         + [f"[{e['evidence_id']}] {e['source_type']}/{e['source_id']}.{e['field']} "
            f"= {e['value']} -- {e['description']}" for e in register]
         or ["None on file."]),
    ]


def sar_to_markdown(pkg: dict, human_review: dict | None = None) -> str:
    ci = pkg.get("case_information", {})
    out = [f"# Suspicious Activity Report (DRAFT) - {ci.get('case_id', '')}",
           f"_{_DISCLAIMER}_", ""]
    for title, lines in sar_to_sections(pkg, human_review):
        out.append(f"## {title}")
        out.append("")
        out += [f"- {l}" for l in lines]
        out.append("")
    return "\n".join(out)
