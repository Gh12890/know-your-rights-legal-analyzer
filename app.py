import streamlit as st
import os
import re
import logging

logger = logging.getLogger("app")
from main import (
    analyze_document,
    extract_text_from_pdf,
    clean_text,
    check_default_bail,
    generate_compliance_brief,
    generate_analysis_pdf,
    generate_next_steps_pdf,
    run_arrest_compliance_checks,
    run_freeze_compliance_checks,
    run_compliance_checks,
    run_fir_no_arrest_checks,
    get_document_checklist,
    BNS_SECTION_DATA,
    compute_severity,
    compute_bail_pathway_info,
    generate_quick_reference,
    datetime,
    parse_date,

)

# =============================================================
# PAGE SETUP
# =============================================================

# =============================================================
# GOOGLE ANALYTICS
# =============================================================
GA_MEASUREMENT_ID = "G-H8M4V4P2M9"

st.markdown(
    f"""
    <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
    <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){{dataLayer.push(arguments);}}
        gtag('js', new Date());
        gtag('config', '{GA_MEASUREMENT_ID}');
    </script>
    """,
    unsafe_allow_html=True,
)
# =============================================================
# PAGE SETUP
# =============================================================
st.title("Know Your Rights")
st.caption("Check whether the police, a bank, or a court followed the law — for arrests, "
           "FIRs, account freezes and cheque-bounce notices under Indian law (BNS / BNSS).")

# --- Routing -------------------------------------------------------------
# The visible menu is 4 options. Routing is on st.session_state["route"],
# NOT the radio label, so the chat's freeze/cheque/arrest handoffs can send
# the user to an assessment flow that has no menu entry of its own.
_MENU = {
    "Ask a question or describe what happened": "chat",
    "I have a document (arrest memo, freeze letter, legal notice)": "document",
    "Answer guided questions instead": "guided",
    "Triage several documents": "triage",
}
_HANDOFF_ROUTES = {"arrest_assess", "freeze_assess", "cheque_assess"}


def _sync_route_from_menu():
    st.session_state["route"] = _MENU[st.session_state["menu_choice"]]


st.session_state.setdefault("route", "chat")

menu_labels = list(_MENU)
# if we're on a handoff-only route, don't fight the radio's own state
_menu_index = 0
if st.session_state["route"] in _MENU.values():
    _menu_index = list(_MENU.values()).index(st.session_state["route"])

st.radio(
    "What would you like to do?",
    menu_labels,
    index=_menu_index,
    key="menu_choice",
    on_change=_sync_route_from_menu,
)
if st.session_state.get("route") not in _HANDOFF_ROUTES:
    st.session_state["route"] = _MENU.get(st.session_state.get("menu_choice"), "chat")

st.divider()

# =============================================================
# SHARED HELPERS
# =============================================================
ALIASES = {
    "cheque bounce": "cheque", "bounced cheque": "cheque", "stealing": "theft",
    "fraud": "cheating", "cheat": "cheating", "domestic violence": "cruelty",
    "dowry harassment": "dowry", "rob": "robbery",
}

def find_sections_by_crime_name(typed_name):
    if not typed_name or not typed_name.strip():
        return []

    query = typed_name.strip().lower()

    # First, check if this looks like a section number rather than a crime name.
    # Strip common prefixes/suffixes a user might naturally include.
    section_candidate = re.sub(
        r'^(section|sec|s\.?)\s*', '', query, flags=re.IGNORECASE
    ).strip()
    section_candidate = re.sub(
        r'\s*(bns|bnss|ipc|crpc)\s*$', '', section_candidate, flags=re.IGNORECASE
    ).strip()

    # A bare section number/sub-section looks like "302" or "318(4)" — digits,
    # optionally followed by a parenthesised sub-section.
    if re.fullmatch(r'\d+(\([a-z0-9]+\))?', section_candidate):
        if section_candidate in BNS_SECTION_DATA:
            return [section_candidate]
        return []   # looked like a section number but isn't in our verified table

    # Otherwise, fall back to the existing crime-name keyword search.
    query = ALIASES.get(query, query)
    return [sec for sec, data in BNS_SECTION_DATA.items() if query in data["offence"].lower()]



def yn(v):
    return {True: True, False: False, "unclear": "unclear"}.get(v, "unclear")


_CITATION_CURRENCY_CAVEATS = {
    "NOT_YET_VERIFIED": ("❔", "This citation's legal currency has not yet been independently verified — it has not been checked for renumbering or later overruling."),
    "SUPERSEDED_BY_STATUTE": ("⚠️", "The specific provision this case interpreted has since been renumbered under BNS/BNSS. See the successor-provision note below for whether the holding itself has been carried forward."),
    "OVERRULED": ("🚫", "A later, binding court has held this specific holding no longer applies."),
    "DISTINGUISHED": ("⚠️", "A later court has narrowed how this holding applies — it remains good law, but not without limits."),
}


def _render_citation_currency_caveat(currency):
    """Project 2 (citation_currency.py): renders a visible caveat next to
    a citation whenever its currency status is anything other than
    GOOD_LAW, including the honest NOT_YET_VERIFIED default. Lookup-only
    display -- never changes the compliance verdict shown elsewhere."""
    if not currency:
        return
    status = currency.get("status", "NOT_YET_VERIFIED")
    if status == "GOOD_LAW":
        return
    icon, message = _CITATION_CURRENCY_CAVEATS.get(status, ("❔", "Currency status unrecognised."))
    st.warning(f"{icon} {message}")
    # Plain-language only -- 'successor_treatment' is a detailed
    # verification trail (dates, IK tid numbers, source URLs) meant for
    # an auditor or for the chat LLM to paraphrase, not for direct
    # display. Confirmed a real problem via live testing 2026-09-01:
    # showing it raw here read as internal audit notes, not something a
    # layperson using this tool should see.
    user_facing_note = currency.get("user_facing_note")
    if user_facing_note:
        st.caption(user_facing_note)


def _render_chat_match_currency_caveat(m):
    """Project 2 (citation_currency.py): same caveat as
    _render_citation_currency_caveat, but for a raw semantic-search match
    dict (chat path) rather than a compliance-check result -- these carry
    a case_name, not a doctrine_key, so currency is resolved via
    citation_currency.get_citation_currency_for_case_name(). A statute
    match (no case_name) is a no-op here."""
    if not m.get("case_name"):
        return
    from citation_currency import get_citation_currency_for_case_name
    for record in get_citation_currency_for_case_name(m["case_name"]):
        _render_citation_currency_caveat(record)


def render_draft_section(full_analysis, key_prefix, *, authorities=None, matters_raised=None):
    """Project 3: turn the findings into a draft the person can act on.
    One body of content (assembled deterministically from the same
    findings shown above); the person chooses who it is addressed to.
    Covers arrest, freeze and cheque-bounce -- a no-op for any analysis
    draft_layer has no template for.

    authorities / matters_raised: optional -- verbatim judgment passages
    and the person's own unassessed grievances, folded into the draft
    (see draft_layer.assemble_for)."""
    from draft_layer import (
        detect_draft_domain, available_targets, TARGET_LABELS,
        draft_for, generate_draft_pdf,
    )
    if detect_draft_domain(full_analysis) is None:
        return

    targets = available_targets(full_analysis)
    if not targets:
        return
    st.subheader("Prepare a draft")
    st.caption(
        "This builds a draft from the findings above. It is a starting point to check and "
        "complete with a lawyer, not a filed document. Fill in anything shown as [ ___ ]. "
        "Any passage marked NOT VERIFIED is from an automatic search — read the judgment "
        "and confirm it before you keep it."
    )
    choice_label = st.radio(
        "What do you want to do with this?",
        [TARGET_LABELS[t] for t in targets],
        key=f"{key_prefix}_draft_target",
    )
    target = next(t for t in targets if TARGET_LABELS[t] == choice_label)

    # seed once per (prefix, target) so the person's edits survive reruns;
    # switching target makes a fresh key and re-seeds from the template
    text_key = f"{key_prefix}_draft_text_{target}"
    if text_key not in st.session_state:
        st.session_state[text_key] = draft_for(
            full_analysis, target, authorities=authorities, matters_raised=matters_raised
        )
    text = st.text_area("Draft (editable)", height=460, key=text_key)

    if st.button("Prepare PDF", key=f"{key_prefix}_draft_pdf_btn_{target}"):
        path = generate_draft_pdf(text, target, output_path=f"action_draft_{key_prefix}.pdf")
        with open(path, "rb") as fh:
            st.session_state[f"{key_prefix}_draft_pdf_bytes"] = fh.read()

    if f"{key_prefix}_draft_pdf_bytes" in st.session_state:
        st.download_button(
            "Download draft (PDF)",
            data=st.session_state[f"{key_prefix}_draft_pdf_bytes"],
            file_name="action_draft.pdf",
            mime="application/pdf",
            key=f"{key_prefix}_draft_dl",
        )


# =============================================================
# UNIFIED RESULTS SURFACE  --  one analysis, three audience views
# =============================================================
def _assessment_full_analysis(domain, payload):
    """Wrap a freeze / cheque free-text-interview payload
    ({compliance_result, severity, fields_known, ...}) into the same
    full_analysis shape the document and arrest flows already produce,
    so render_results() can treat every path identically."""
    labels = {
        "freeze": ("Bank / Account Freezing", "Account freeze — free-text conversation (no document)"),
        "cheque_bounce": ("Cheque Bounce", "Section 138 NI Act — free-text conversation (no document)"),
    }
    doc_type, sub_type = labels[domain]
    fa = {
        "classification": {
            "document_type": doc_type, "sub_type": sub_type,
            "reasoning": "Built from your answers in this conversation, since no document was available.",
        },
        "missing_info": {"missing_or_unclear": [],
                         "completeness_assessment": "Based on conversational answers only."},
        "compliance": payload["compliance_result"],
        "checklist": get_document_checklist(doc_type),
        "urgency": {"urgency_level": "Cannot Determine", "deadline_message": "N/A", "days_remaining": None},
        "severity": payload.get("severity", {}),
        "bail_pathway": None,
        "extracted_fields": payload.get("fields_known", {}),
    }
    for k in ("presumption_info", "settlement_info"):
        if k in payload:
            fa[k] = payload[k]
    return fa


def _plain_fallback(full_analysis):
    """Deterministic plain-language text when the API summary is
    unavailable -- render_results must never show a blank tab."""
    checks = full_analysis.get("compliance", {}).get("compliance_checks", []) or []
    bad = [c for c in checks if c.get("status") in ("Non-Compliant", "May be Non-Compliant")]
    unknown = [c for c in checks if c.get("status") == "Cannot Determine"]
    lines = ["**What was found**", ""]
    if bad:
        lines.append("Some things may not have been done as the law requires:")
        for c in bad:
            head = re.split(r"\s*\[", c.get("requirement", ""), maxsplit=1)[0].strip()
            lines.append(f"- {head} — {c.get('explanation','').strip()}")
    else:
        lines.append("Nothing in the information given shows a clear procedural problem. "
                     "That does not prove there is none.")
    if unknown:
        lines += ["", "**Still unclear**"]
        for c in unknown:
            head = re.split(r"\s*\[", c.get("requirement", ""), maxsplit=1)[0].strip()
            lines.append(f"- {head} — {c.get('explanation','').strip()}")
    lines += ["", "**What you can do now**",
              "Take this analysis, and any papers you have (arrest memo, FIR copy, the notice or "
              "letter), to a lawyer or the nearest District Legal Services Authority, which provides "
              "free help."]
    return "\n".join(lines)


def render_results(full_analysis, *, key_prefix, counsel_text=None):
    """The single results surface. Tabs: In plain words / Legal analysis /
    Documents. One compliance computation feeds all three; the two
    summary registers are cached per compliance-signature so tab
    switches and reruns don't re-hit the API."""
    import hashlib
    import json as _json
    from layman_summary import generate_layman_summary

    compliance = full_analysis.get("compliance", {}) or {}
    checks = compliance.get("compliance_checks", []) or []
    sig = hashlib.md5(
        _json.dumps(checks, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]

    severity = full_analysis.get("severity", {}) or {}
    bail_pathway = full_analysis.get("bail_pathway")
    fields = full_analysis.get("extracted_fields", {}) or {}
    secs = fields.get("sections_cited") or []
    offence_name = full_analysis.get("_offence_name")
    section_number = full_analysis.get("_section_number") or (str(secs[0]) if secs else None)
    statute_text = full_analysis.get("_statute_text")

    def _summary(audience):
        k = f"{key_prefix}_sum_{audience}_{sig}"
        if audience == "counsel" and counsel_text and k not in st.session_state:
            st.session_state[k] = counsel_text
        if k not in st.session_state:
            st.session_state[k] = generate_layman_summary(
                compliance, severity, bail_pathway,
                offence_name=offence_name, section_number=section_number,
                statute_text=statute_text if audience == "counsel" else None,
                audience=audience,
            )
        return st.session_state[k]

    tab_plain, tab_legal, tab_docs = st.tabs(["In plain words", "Legal analysis", "Documents"])

    with tab_plain:
        plain = _summary("plain")
        st.markdown(plain if plain else _plain_fallback(full_analysis))
        st.caption("A plain-language explanation of the analysis — not legal advice.")

    with tab_legal:
        counsel = _summary("counsel")
        if counsel:
            st.markdown(counsel)
            st.divider()
        render_compliance_ui_main(full_analysis)
        qr = generate_quick_reference(full_analysis)
        if qr.get("actionable_issues"):
            with st.expander("At a glance — issues, worst first"):
                for c in qr["actionable_issues"]:
                    st.markdown(f"**{c['status']}** — {c.get('requirement','')}")
                    st.caption(c.get("explanation", ""))

    with tab_docs:
        st.markdown("**Take-away documents**")
        c1, c2 = st.columns(2)
        with c1:
            _one_click_pdf(
                "Analysis (PDF)", f"{key_prefix}_analysispdf",
                lambda p: generate_analysis_pdf(full_analysis, output_path=p),
                "compliance_analysis.pdf",
                help="Legal findings + case-law references. For a lawyer or your own file.",
            )
        with c2:
            _one_click_pdf(
                "What to do next (PDF)", f"{key_prefix}_nextpdf",
                lambda p: generate_next_steps_pdf(full_analysis, plain_text=_summary("plain"), output_path=p),
                "what_to_do_next.pdf",
                help="Plain-language summary + a checklist of what to gather.",
            )
        st.divider()
        render_draft_section(full_analysis, key_prefix=key_prefix)


def _back_to_start_button(flow_prefix):
    """Shown on a handoff-only assessment flow (arrest/freeze/cheque
    reached from the chat). Returns routing to whatever the menu radio
    still shows and clears that flow's session state."""
    if st.button("← Back to start", key=f"{flow_prefix}_back_to_start"):
        st.session_state["route"] = _MENU.get(
            st.session_state.get("menu_choice"), "chat")
        for k in list(st.session_state):
            if k.startswith(flow_prefix) or k.startswith(
                {"ivchat": "interview_chat", "freezechat": "freeze_chat",
                 "chequechat": "cheque_chat"}.get(flow_prefix, flow_prefix)):
                st.session_state.pop(k, None)
        st.rerun()


def _one_click_pdf(label, key, build_fn, download_name, help=None):
    """Generate-on-click then offer the download, as one affordance
    instead of the old two-button dance. Bytes cached in session."""
    bytes_key = f"{key}_bytes"
    if bytes_key not in st.session_state:
        if st.button(f"Prepare {label}", key=f"{key}_btn", help=help, use_container_width=True):
            path = build_fn(f"scratch_{key}.pdf")
            with open(path, "rb") as fh:
                st.session_state[bytes_key] = fh.read()
            st.rerun()
    else:
        st.download_button(
            f"Download {label}", data=st.session_state[bytes_key],
            file_name=download_name, mime="application/pdf",
            key=f"{key}_dl", use_container_width=True,
        )


def _render_chat_match_old_code_note(m):
    """When a retrieved paragraph quotes an old IPC/CrPC section number,
    show the reader its modern BNS/BNSS equivalent from the checked
    concordance -- the same mapping the answer generator is given. Case
    law is indexed under the old numbers, so this is common on judgment
    matches; a no-op when the text has no old-code references."""
    from chat_assistant import _old_code_equivalents
    eqs = _old_code_equivalents(m.get("text", ""))
    if not eqs:
        return
    bits = []
    for e in eqs:
        if e["new"] is None:
            bits.append(f"{e['old']} → not re-enacted")
        else:
            bits.append(f"{e['old']} → {e['new']}"
                        + (" (changed)" if e["changed"] else ""))
    st.caption("Old→new section numbers in this extract: " + " · ".join(bits))


# Chat-to-domain-flow handoff (added 2026-09-01): when the chat feature's
# classifier recognises a freeze or cheque-bounce question, the dedicated
# free-text interview flows (freeze_interview_flow.py /
# cheque_bounce_interview_flow.py) already give a BETTER answer than the
# chat feature ever could -- they ask smart follow-ups and produce an
# actual Compliant/Non-Compliant verdict, something chat_assistant.py's
# answer_question() is explicitly barred from doing (RESPONSE_GENERATION_
# PROMPT: "Never state a compliance verdict"). Rather than building a
# second semantic-search corpus so chat could merely EXPLAIN these
# domains (strictly worse than a real verdict), this hands the person's
# already-typed question straight to the real flow, processed as its
# first real turn immediately, so they never have to repeat themselves.
_DOMAIN_FLOW_CONFIG = {
    "freeze": {
        "history_key": "freeze_chat_history",
        "state_key": "freeze_state_obj",
        "results_key": "freeze_chat_results",
        "module": "freeze_interview_flow",
        "state_class_name": "FreezeInterviewState",
        "button_label": "🏦 Continue in the bank-freeze assistant →",
    },
    "cheque_bounce": {
        "history_key": "cheque_chat_history",
        "state_key": "cheque_state_obj",
        "results_key": "cheque_chat_results",
        "module": "cheque_bounce_interview_flow",
        "state_class_name": "ChequeBounceInterviewState",
        "button_label": "🧾 Continue in the cheque-bounce assistant →",
    },
    # ADDED 2026-09-01 (chat-quality plan Phase 4). Unlike freeze/cheque,
    # the arrest handoff is offered ALONGSIDE the chat answer, not
    # instead of it -- the chat corpus DOES cover arrest/FIR/police
    # procedure well (post Phase 1/2), so the explanation stays and this
    # is just a faster route to a real Compliant/Non-Compliant verdict.
    # interview_flow.py's process_turn has a richer state machine than
    # freeze/cheque's (an offence-identification + confirmation gate) and
    # a differently-shaped results payload, so _handoff_to_domain_flow
    # special-cases this domain via _arrest_turn_reply() rather than the
    # generic module-lookup path.
    "arrest": {
        "history_key": "interview_chat_history",
        "state_key": "interview_state_obj",
        "results_key": "interview_chat_results",
        "module": "interview_flow",
        "state_class_name": "InterviewState",
        "button_label": "📝 Get a real compliance assessment of what happened →",
    },
}


def _sources_worth_showing(matches, reply_text, cap=6):
    """The 'Read the source' expander used to loop over EVERY retrieved
    match -- for a weak query that's ~17 near-noise rows (confirmed live
    2026-09-01). Show, in order: every match the ANSWER actually
    references (its section number or case name appears in reply_text),
    then fill up to `cap` from the top of the (score-ordered) list.
    Deduped by (source, label)."""
    reply_lc = (reply_text or "").lower()

    def _label(m):
        return str(m.get("section_number") or m.get("paragraph_number") or "")

    def _referenced(m):
        cn = (m.get("case_name") or "").lower()
        return (m.get("section_number") and f"section {m['section_number']}" in reply_lc) \
            or (cn and cn.split(" v ")[0].strip() in reply_lc)

    picked, seen = [], set()
    for m in sorted(matches, key=lambda m: not _referenced(m)):  # referenced first, stable within
        key = (m.get("case_name") or "BNS/BNSS", _label(m))
        if key in seen:
            continue
        seen.add(key)
        picked.append(m)
        if len(picked) >= cap:
            break
    return picked


def _arrest_turn_reply(state_obj, user_message):
    """Turn-processing for interview_flow.py's arrest free-text flow,
    factored out (2026-09-01) so run_interview_chat_flow() -- someone
    typing directly into that mode -- and _handoff_to_domain_flow() --
    someone arriving via the chat handoff button -- call the SAME code
    and can never drift apart.

    interview_flow.process_turn() returns a richer set of states than
    freeze/cheque's (awaiting_offence / offence_unclear /
    confirming_offence / asking_field / ready_for_results, vs. their
    plain asking_field / ready_for_results) and, on ready_for_results,
    a different payload (compliance_result + bail_pathway + severity +
    fields_known + layman_summary, assembled here into the
    full_analysis dict run_interview_chat_flow's renderer expects) --
    which is why the generic _handoff_to_domain_flow path can't handle
    it and this exists.

    Returns (reply, results_payload_or_None). The caller stores
    results_payload into st.session_state itself (kept out of here so
    this stays a pure function). The process_turn() call is wrapped in
    the same diagnostic try/except run_interview_chat_flow used inline
    before this was extracted."""
    from interview_flow import process_turn

    try:
        result = process_turn(state_obj, user_message)
    except Exception:
        import traceback
        print(f"=== process_turn DIAGNOSTIC, user_message={user_message!r} ===")
        traceback.print_exc()
        print("=== END DIAGNOSTIC ===")
        result = {"state": "extraction_unavailable", "field_name": None}

    turn_state = result["state"]

    if turn_state in ("awaiting_offence", "offence_unclear", "asking_field"):
        acknowledgment = result.get("acknowledgment")
        reply = f"{acknowledgment} {result['question']}" if acknowledgment else result["question"]
        return reply, None

    if turn_state == "confirming_offence":
        return result["question"], None

    if turn_state == "extraction_unavailable":
        return "Sorry, I had trouble understanding that -- could you try rephrasing your answer?", None

    if turn_state == "ready_for_results":
        full_analysis = {
            "classification": {
                "document_type": "Police & Criminal Process",
                "sub_type": "Arrest — reported via free-text conversation (no document)",
                "reasoning": "Built from your answers in this conversation, since no document was available.",
            },
            "missing_info": {
                "missing_or_unclear": [],
                "completeness_assessment": "Based on conversational answers only -- not a document review.",
            },
            "compliance": result["compliance_result"],
            "checklist": get_document_checklist("Police & Criminal Process"),
            "urgency": {"urgency_level": "Cannot Determine", "deadline_message": "N/A for this mode", "days_remaining": None},
            "severity": result["severity"],
            "bail_pathway": result["bail_pathway"],
            "extracted_fields": result["fields_known"],
            # hints for render_results' counsel summary
            "_offence_name": result.get("offence_plain_language") or getattr(state_obj, "offence_plain_language", None),
            "_section_number": result.get("section_number"),
            "_statute_text": result.get("statute_text"),
        }
        results_payload = {
            "full_analysis": full_analysis,
            "layman_summary": result.get("layman_summary"),
            "tier_shown": result.get("tier_shown"),
        }
        return "Thanks -- I have enough to give you a real assessment now. I've put it together below.", results_payload

    return "Something unexpected happened on my end -- please try rephrasing.", None


def _handoff_to_domain_flow(domain, question):
    """MUST be used as a widget's on_click callback, never called from
    the normal script body. CONFIRMED via live testing (2026-09-01):
    calling this directly from the script body raises
    StreamlitAPIException ('st.session_state.mode cannot be modified
    after the widget with key "mode" is instantiated') -- the mode
    radio (key="mode") has ALREADY rendered earlier in the same script
    pass by the time run_chat_flow() reaches this point, and Streamlit
    locks a keyed widget's session_state for the rest of that run once
    it's been instantiated. on_click callbacks run in a separate phase
    BEFORE the next script pass's widgets are instantiated, which is
    exactly why Streamlit provides them for this pattern. No st.rerun()
    call here -- one happens automatically after any on_click callback
    returns.

    Switches mode to the dedicated interview flow for `domain` and
    immediately processes `question` (the user's original, already-typed
    chat message) as that flow's first real turn -- mirrors exactly the
    turn-handling logic each flow's own run_*_chat_flow() uses (asking_
    field -> show the question; ready_for_results -> stash the verdict;
    anything else -> the same honest "couldn't understand that" fallback),
    so behavior stays identical whether a person starts in that flow
    directly or arrives here via handoff. Does NOT touch chat_history --
    CONFIRMED via live AppTest tracing (2026-09-01) that run_chat_flow()
    already appends the chat reply on the SAME script pass that renders
    the handoff button, before any click can happen. An earlier version
    of this function re-appended it here too, producing a duplicate
    identical assistant turn in chat_history every time this button was
    clicked.

    domain == "arrest" (added 2026-09-01) is special-cased: it goes
    through _arrest_turn_reply() because interview_flow.py's process_turn
    has a richer state machine and results shape than freeze/cheque's
    (see that helper's docstring). freeze/cheque keep the generic
    module-lookup path below, completely unchanged."""
    config = _DOMAIN_FLOW_CONFIG[domain]
    st.session_state[config["history_key"]] = [{"role": "user", "content": question}]

    if domain == "arrest":
        from interview_flow import InterviewState

        st.session_state[config["state_key"]] = InterviewState()
        state_obj = st.session_state[config["state_key"]]
        flow_reply, results_payload = _arrest_turn_reply(state_obj, question)
        if results_payload is not None:
            st.session_state[config["results_key"]] = results_payload
    else:
        import importlib

        module = importlib.import_module(config["module"])
        state_class = getattr(module, config["state_class_name"])
        process_turn = getattr(module, "process_turn")

        st.session_state[config["state_key"]] = state_class()
        state_obj = st.session_state[config["state_key"]]
        try:
            result = process_turn(state_obj, question)
        except Exception:
            result = {"state": "extraction_unavailable", "field_name": None}

        turn_state = result["state"]
        if turn_state == "asking_field":
            flow_reply = result["question"]
        elif turn_state == "ready_for_results":
            results_payload = {
                "compliance_result": result["compliance_result"],
                "severity": result["severity"],
                "fields_known": result["fields_known"],
            }
            for optional_key in ("presumption_info", "settlement_info"):
                if optional_key in result:
                    results_payload[optional_key] = result[optional_key]
            st.session_state[config["results_key"]] = results_payload
            flow_reply = "Thanks -- I have enough to give you a real assessment now. I've put it together below."
        else:
            flow_reply = "Sorry, I had trouble understanding that -- could you try rephrasing your answer?"

    st.session_state[config["history_key"]].append({"role": "assistant", "content": flow_reply})
    st.session_state["route"] = {
        "arrest": "arrest_assess", "freeze": "freeze_assess", "cheque_bounce": "cheque_assess",
    }[domain]


def render_compliance_ui_main(result):
    """Replaces raw st.json() calls with a readable, structured display."""

    classification = result.get("classification", {})
    compliance = result.get("compliance", {})
    missing = result.get("missing_info", {})
    checklist = result.get("checklist", [])
    urgency = result.get("urgency", {})

    # ---- BLOCK 1: What this is ----
    st.markdown("### 📄 What This Is")
    col1, col2 = st.columns(2)
    with col1:
        st.caption("Category")
        st.markdown(f"**{classification.get('document_type', 'N/A')}**")
    with col2:
        st.caption("Sub-type")
        st.markdown(f"**{classification.get('sub_type', 'N/A')}**")
    st.caption(classification.get("reasoning", ""))
    st.divider()

    # ---- BLOCK 2a: Urgency & Deadline — Section 138 ONLY ----
    document_type = classification.get("document_type", "")
    if document_type == "Banking & Cheque Bounce":
        st.markdown("### ⏱️ Urgency & Deadline")
        urgency_level = urgency.get("urgency_level", "Cannot Determine")
        urgency_colors = {
            "DEADLINE PASSED": "🔴", "CRITICAL": "🔴", "HIGH RISK": "🟠",
            "FORMAL": "🟡", "ROUTINE": "🟢", "Cannot Determine": "⚪",
        }
        icon = urgency_colors.get(urgency_level, "⚪")
        st.markdown(f"## {icon} {urgency_level}")
        if urgency.get("days_remaining") is not None:
            st.metric("Days remaining", urgency["days_remaining"])
        dm = urgency.get("deadline_message")
        if isinstance(dm, dict):
            for k, v in dm.items():
                st.write(f"**{k.replace('_', ' ').title()}:** {v}")
        elif dm:
            st.write(dm)
        st.divider()

    # ---- BLOCK 2b: Procedural Compliance Severity — ALL domains ----
    severity = result.get("severity", {})
    st.markdown("### 🛡️ Severity of Procedural Compliance Violations")
    severity_icons = {"green": "🟢", "amber": "🟡", "orange": "🟠", "red": "🔴"}
    icon = severity_icons.get(severity.get("severity_color"), "⚪")
    st.markdown(f"## {icon} {severity.get('severity_label', 'Not Available')}")
    st.markdown(f"# {severity.get('severity_meter', '')}")
    unresolved = severity.get("unresolved_checks", 0)
    if unresolved > 0:
        st.caption(f"{unresolved} check(s) could not be verified from the information given.")
    st.divider()

    # ---- BLOCK 3: Compliance findings ----
    st.markdown("### ⚖️ Was Correct Procedure Followed?")
    status_style = {
        "Compliant": ("✅", "green"),
        "Non-Compliant": ("❌", "red"),
        "May be Non-Compliant": ("⚠️", "orange"),
        "Cannot Determine": ("❔", "gray"),
        "Not Applicable": ("➖", "gray"),
    }
    for check in compliance.get("compliance_checks", []):
        emoji, color = status_style.get(check.get("status"), ("❔", "gray"))
        with st.container(border=True):
            st.markdown(f"{emoji} **{check.get('requirement', '').strip()}**")
            st.markdown(f":{color}[{check.get('status', '')}]")
            st.caption(check.get("explanation", ""))
            source_paragraphs = check.get("source_paragraphs")
            if source_paragraphs:
                case_name = source_paragraphs[0].get("case_name", "")
                citation = source_paragraphs[0].get("citation", "")
                with st.expander(f"📖 Read the source: {case_name} ({citation})"):
                    _render_citation_currency_caveat(check.get("citation_currency"))
                    for para in source_paragraphs:
                        para_label = para.get("paragraph_number", "")
                        author = para.get("opinion_author")
                        label = f"¶{para_label}" + (f" ({author}, J.)" if author else "")
                        st.markdown(f"**{label}**")
                        st.caption(para.get("text", ""))
            applying_precedent_paragraphs = check.get("applying_precedent_paragraphs")
            if applying_precedent_paragraphs:
                case_name = applying_precedent_paragraphs[0].get("case_name", "")
                citation = applying_precedent_paragraphs[0].get("citation", "")
                with st.expander(f"⚖️ How a court has applied this: {case_name} ({citation})"):
                    _render_citation_currency_caveat(check.get("applying_precedent_currency"))
                    for para in applying_precedent_paragraphs:
                        para_label = para.get("paragraph_number", "")
                        author = para.get("opinion_author")
                        label = f"¶{para_label}" + (f" ({author}, J.)" if author else "")
                        st.markdown(f"**{label}**")
                        st.caption(para.get("text", ""))
    overall = compliance.get("overall_assessment", "")
    if overall:
        st.info(overall)
    st.divider()
    
    # ---- BLOCK 3b: Bail Pathway — informational, NOT a compliance verdict ----
    bail_pathway = result.get("bail_pathway")
    if bail_pathway:
        st.markdown("### 🔑 If Bail Is Needed")
        st.info(bail_pathway.get("message", ""))
        st.divider()
        
        

    # ---- BLOCK 4: What's missing ----
    flags = missing.get("missing_or_unclear", [])
    if flags:
        st.markdown("### 🔍 What's Missing or Unclear")
        for flag in flags:
            st.markdown(f"- {flag}")
        st.divider()


def render_checklist_and_raw(result):
    """Block 5: documents to gather, plus the raw-data expander."""
    checklist = result.get("checklist", [])
    if checklist:
        st.markdown("### 📋 Documents to Gather")
        for item in checklist:
            st.checkbox(item, key=f"chk_{hash(item)}")
    #Raw data, collapsed, for de bugging only 
    with st.expander("Show raw data"):
        st.json(result)
        
def render_quick_reference(full_analysis):
    qr = generate_quick_reference(full_analysis)
    st.markdown("## ⚡ Courtroom Quick View")
    st.markdown(f"### {qr['severity_meter']} {qr['severity_label']}")

    if qr["actionable_issues"]:
        st.markdown(f"**{len(qr['actionable_issues'])} issue(s) worth raising:**")
        for issue in qr["actionable_issues"]:
            if issue["status"] == "Non-Compliant":
                st.error(f"**RAISE NOW:** {issue['requirement']}")
            else:
                st.warning(f"**MAY BE WORTH RAISING:** {issue['requirement']}")
            st.caption(issue["explanation"])
    else:
        st.success("No confirmed or suspected defects to raise.")

    if qr["default_bail"]:
        db = qr["default_bail"]
        if db["status"] == "Compliant" and "becomes available on" in db["explanation"]:
            st.info(f"**DEFAULT BAIL:** {db['explanation']}")
        elif db["status"] in ("Non-Compliant", "May be Non-Compliant"):
            st.warning(f"**DEFAULT BAIL — ACT NOW:** {db['explanation']}")
        
# =============================================================
# DOMAIN 1: ARREST-RELATED — questions (unchanged from before)
# =============================================================
ARREST_QUESTIONS = [
    {"key": "arrestee_gender", "text": "Is the person who was arrested a man, a woman, or third gender?",
     "type": "choice", "options": ["Man", "Woman", "Third gender"]},
    {"key": "arrest_datetime", "text": "When did the police take the person?",
     "type": "datetime"},
    {"key": "arrest_mode", "text": "How was the person arrested?",
     "type": "choice",
     "options": [
         "At the scene, while it was happening — police were present there",
         "Later — at home or elsewhere, after hours or days had passed",
         "Before anything happened — police said it was to prevent an offence",
         "Not sure",
     ]},
    {"key": "arrest_power_limb",
     "text": "Did any of these apply at the time of the arrest?",
     "type": "choice",
     "options": [
         "None of these",
         "Stolen goods were found on the person during the arrest",
         "A court had already declared the person an absconder",
         "Arrested for obstructing police, or after escaping from custody",
         "Police said another police station had asked for the arrest",
         "Not sure",
     ]},
    {"key": "notice_before", "text": "Before taking them, did police give any paper asking them to come to the station?",
     "type": "yesno"},
    {"key": "grounds_given", "text": "At the time of arrest, did police give a paper explaining exactly why?",
     "type": "yesno"},
    {"key": "witness_present", "text": "Was a family member or neighbour present, and did they sign any paper?",
     "type": "yesno"},
    {"key": "family_informed", "text": "Was any family member told about the arrest?",
     "type": "yesno"},
    {"key": "medical_done", "text": "Was the person checked by a doctor around the time of arrest?",
     "type": "yesno"},
    {"key": "female_officer", "text": "Was a woman police officer present?",
     "type": "yesno"},
    {"key": "production_datetime", "text": "Has the person been taken in front of a judge yet? If yes, when?",
     "type": "datetime_optional"},
    {"key": "section_known",
     "text": "Do you know the name of the crime or section of BNS that the police mentioned? (e.g. cheating/theft/dowry/section 302 BNS etc.)",
     "type": "crime_name_search"},
    {"key": "chargesheet_filed", "text": "Has a formal charge-sheet been filed? If yes, when?",
     "type": "datetime_optional"},
]


def arrest_filter(questions, answers):
    qs = questions
    if answers.get("arrestee_gender") not in ("Woman", "Third gender"):
        return [q for q in questions if q["key"] != "female_officer"]
    mode_answer = answers.get("arrest_mode", "")
    if mode_answer.startswith("At the scene") or mode_answer.startswith("Before anything"):
        qs = [q for q in qs if q["key"] not in ("notice_before", "arrest_power_limb")]
    return qs


def build_arrest_fields(answers):
    mode_map = {
        "At the scene, while it was happening — police were present there": "in_presence",
        "Later — at home or elsewhere, after hours or days had passed": "post_facto",
        "Before anything happened — police said it was to prevent an offence": "preventive",
        "Not sure": "unclear",
    }
    limb_map = {
        "Stolen goods were found on the person during the arrest": "stolen_property",
        "A court had already declared the person an absconder": "proclaimed_offender",
        "Arrested for obstructing police, or after escaping from custody": "obstruction_escape",
        "Police said another police station had asked for the arrest": "requisition",
        "None of these": None,
        "Not sure": None,
    }
    gender_map = {"Man": "male", "Woman": "female", "Third gender": "third_gender"}
    resolved_gender = gender_map.get(answers.get("arrestee_gender"), "male")
    return {
        "arrestee_gender": resolved_gender,
        "arrest_datetime_full": answers.get("arrest_datetime"),
        "production_datetime_full": answers.get("production_datetime"),
        "sections_cited": answers.get("section_known", []),
        "punishment_years_upper_bound": None,
        "arrest_mode": mode_map.get(answers.get("arrest_mode"), "unclear"),
        "arrest_power_limb": limb_map.get(answers.get("arrest_power_limb")),
        "41A_or_35_BNSS_notice_issued_before_arrest": yn(answers.get("notice_before")),
        "grounds_of_arrest_in_writing_furnished_to_arrestee": yn(answers.get("grounds_given")),
        "witness_attested_memo": yn(answers.get("witness_present")),
        "family_or_friend_informed": yn(answers.get("family_informed")),
        "medical_exam_at_arrest_recorded": yn(answers.get("medical_done")),
        "female_officer_present_for_female_arrestee": (
            yn(answers.get("female_officer")) if answers.get("arrestee_gender") == "Woman" else "not applicable"
        ),
        "chargesheet_filed_date": answers.get("chargesheet_filed"),
    }
    



# =============================================================
# DOMAIN 2: BANK ACCOUNT FREEZING — new
# =============================================================
FREEZE_QUESTIONS = [
    {"key": "freeze_date", "text": "When did you find out the account was frozen or blocked?",
     "type": "datetime_optional"},
    {"key": "section_choice", "text": "Did the freeze letter or notice mention a specific legal section?",
     "type": "choice_or_text",
     "options": ["Section 106", "Section 107", "Some other section (type it)", "No section was mentioned", "I don't know — never received any freeze letter or notice"],
     "text_trigger": "Some other section (type it)"},
    {"key": "scope", "text": "Was the entire account frozen, or only a specific amount?",
     "type": "choice",
     "options": ["Entire account was frozen", "Only a specific amount was frozen", "Not sure"]},
    {"key": "specific_amount", "text": "Do you know the amount that was allegedly involved (the disputed amount)?",
     "type": "number_optional", "input_label": "Amount (Rs.)"},
    {"key": "account_holder_intimated",
     "text": "How did you find out about the freeze?",
     "type": "choice",
     "options": ["A written intimation was received", "Card / Payment decline", "Other"]},
    {"key": "magistrate_intimation", "text": "Do you know if a magistrate or court was informed about this freeze?",
     "type": "yesno"},
    {"key": "court_order_107", "text": "Was any court order mentioned or shown to you along with the freeze?",
     "type": "yesno"},
]

def freeze_filter(questions, answers):
    if answers.get("section_choice") != "Section 107":
        return [q for q in questions if q["key"] != "court_order_107"]
    return questions

def build_freeze_fields(answers):
    section_map = {
        "Section 106": "106 BNSS",
        "Section 107": "107 BNSS",
        "No section was mentioned": "none cited",
        "I don't know — never received any freeze letter or notice": "unclear",
    }
    raw_section = answers.get("section_choice", "unclear")
    if isinstance(raw_section, str) and raw_section.startswith("typed:"):
        section_invoked = raw_section.replace("typed:", "").strip() or "other"
    else:
        section_invoked = section_map.get(raw_section, "unclear")

    scope_map = {
        "Entire account was frozen": "entire account",
        "Only a specific amount was frozen": "specific disputed amount",
        "Not sure": "unclear",
    }

    intimation_map = {
        "A written intimation was received": True,
        "Card / Payment decline": False,
        "Other": "unclear",
    }

    return {
        "freeze_date": answers.get("freeze_date"),
        "section_invoked": section_invoked,
        "scope": scope_map.get(answers.get("scope"), "unclear"),
        "specific_amount_stated": answers.get("specific_amount"),
        "account_holder_intimated": intimation_map.get(answers.get("account_holder_intimated"), "unclear"),
        "magistrate_intimation_recorded": yn(answers.get("magistrate_intimation")),
        "magistrate_intimation_date": None,
        "court_order_referenced_for_107": (
            yn(answers.get("court_order_107")) if section_invoked == "107 BNSS" else "not applicable"
        ),
    }


# =============================================================
# DOMAIN 3: CHEQUE BOUNCE (Section 138 NI Act) — new
# =============================================================
CHEQUE_QUESTIONS = [
    {"key": "return_memo_date", "text": "When did the bank return or bounce the cheque?",
     "type": "datetime_optional"},
    {"key": "notice_date", "text": "When was the legal notice sent or received?",
     "type": "datetime_optional"},
    {"key": "cheque_face_value", "text": "What amount was written on the cheque?",
     "type": "number_optional", "input_label": "Amount (Rs.)"},
    {"key": "demand_amount", "text": "What amount is the notice asking you to pay?",
     "type": "number_optional", "input_label": "Amount (Rs.)"},
    {"key": "payment_window", "text": "How many days did the notice give you to pay?",
     "type": "number_optional", "input_label": "Number of days"},
    {"key": "interest_bundled",
     "text": "Does the notice mix interest or extra costs together with the main amount in the same sentence, rather than listing them separately?",
     "type": "yesno"},
    {"key": "cheque_was_blank",
     "text": "Was the cheque signed and handed over blank (with the amount/date filled in later by someone else), or was it fully filled in when signed?",
     "type": "choice",
     "options": ["Signed blank, filled in later", "Fully filled in when signed", "Not sure"]},
    {"key": "presentation_bank_location",
     "text": "In which city/town was the cheque presented for collection (i.e. where is the bank branch that tried to process it)?",
     "type": "text_optional"},
    {"key": "complaint_filed_location",
     "text": "In which city/town has the complaint been filed (or is expected to be filed)?",
     "type": "text_optional"},
    {"key": "case_stage",
     "text": "What stage is the case at right now?",
     "type": "choice",
     "options": ["Before trial has started", "Convicted at the trial court", "On appeal at the High Court",
                 "On appeal at the Supreme Court", "Not sure"]},
]

def cheque_filter(questions, answers):
    return questions  # no conditional questions in this domain

def build_cheque_fields(answers):
    """UPDATED 2026-08-30: see module docstring above for reasoning
    behind each field change. cheque_purpose/purpose_map REMOVED
    entirely -- no longer collected or used by any check."""
    blank_map = {
        "Signed blank, filled in later": True,
        "Fully filled in when signed": False,
        "Not sure": "unclear",
    }
    stage_map = {
        "Before trial has started": "pre_trial",
        "Convicted at the trial court": "convicted_at_trial_court",
        "On appeal at the High Court": "on_appeal_hc",
        "On appeal at the Supreme Court": "on_appeal_sc",
        "Not sure": "unclear",
    }
 
    return {
        "return_memo_date": answers.get("return_memo_date"),
        "notice_date": answers.get("notice_date"),
        "cheque_face_value": answers.get("cheque_face_value"),
        "demand_principal_amount": answers.get("demand_amount"),
        "payment_window_days_granted": answers.get("payment_window"),
        "interest_bundled_in_principal_sentence": answers.get("interest_bundled") is True,
        "cheque_was_blank_when_signed": blank_map.get(answers.get("cheque_was_blank"), "unclear"),
        "cheque_presentation_bank_location": answers.get("presentation_bank_location"),
        "complaint_filed_location": answers.get("complaint_filed_location"),
        "case_stage": stage_map.get(answers.get("case_stage"), "unclear"),
    }
 
# =============================================================
# DOMAIN 4: FIR / COMPLAINT — NO ARREST YET
# =============================================================   
FIR_NO_ARREST_QUESTIONS = [
    {"key": "user_role", "text": "Are you the person who filed this complaint, or are you named as the accused/suspect in it?",
     "type": "choice", "options": ["I filed the complaint (I am the informant)", "I am named as the accused/suspect"]},
    {"key": "section_known", "text": "Do you know the name of the crime or section of BNS named in the FIR? (e.g. cheating/theft/dowry/section 302 etc.)",
     "type": "crime_name_search"},
    {"key": "reporting_date", "text": "When was the FIR registered, if you know?",
     "type": "datetime_optional"},
    {"key": "free_copy_given", "text": "Did you (as the person who filed the complaint) receive a free copy of the FIR immediately?",
     "type": "yesno"},
    {"key": "accused_applied_for_copy", "text": "Have you (or your lawyer) applied for a copy of the FIR — either to the police station or to the court?",
     "type": "yesno"},
    {"key": "accused_copy_provided", "text": "After applying, were you given a copy of the FIR?",
     "type": "yesno"},
    {"key": "checked_online", "text": "Have you actually checked whether the FIR is available on the police/State website?",
     "type": "choice",
     "options": ["Yes, I found it online", "Yes, I checked and could NOT find it", "No, I haven't checked yet"]},
]



def fir_no_arrest_filter(questions, answers):
    role = answers.get("user_role")
    if role == "I am named as the accused/suspect":
        qs = [q for q in questions if q["key"] != "free_copy_given"]
        if answers.get("accused_applied_for_copy") is not True:
            qs = [q for q in qs if q["key"] != "accused_copy_provided"]
        return qs
    elif role == "I filed the complaint (I am the informant)":
        return [q for q in questions if q["key"] not in ("accused_applied_for_copy", "accused_copy_provided")]
    return questions



def build_fir_no_arrest_fields(answers):
    reporting_dt = parse_date(answers.get("reporting_date")) if answers.get("reporting_date") else None
    days_since = (datetime.now() - reporting_dt).days if reporting_dt else None

    online_map = {
        "Yes, I found it online": True,
        "Yes, I checked and could NOT find it": False,
        "No, I haven't checked yet": None,
    }

    role = answers.get("user_role")
    perspective_map = {
        "I filed the complaint (I am the informant)": "informant",
        "I am named as the accused/suspect": "accused",
    }
    perspective = perspective_map.get(role, "unclear")

    return {
        "sections_cited": answers.get("section_known", []),
        "occurrence_date": None,
        "reporting_date": answers.get("reporting_date"),
        "arrest_mentioned": False,
        "fir_document_perspective": perspective,
        "free_copy_given_to_informant": yn(answers.get("free_copy_given")),
        "accused_applied_for_fir_copy": yn(answers.get("accused_applied_for_copy")),
        "accused_fir_copy_provided": yn(answers.get("accused_copy_provided")),
        "_user_checked_online": online_map.get(answers.get("checked_online")),
        "_days_since_registration": days_since,
    }


# =============================================================
# DOMAIN REGISTRY — one config per issue type
# =============================================================
INTERVIEW_CONFIGS = {
    "Arrest-related process": {
        "questions": ARREST_QUESTIONS,
        "filter_fn": arrest_filter,
        "build_fields": build_arrest_fields,
        "compliance_runner": run_arrest_compliance_checks,
        "checklist_category": "Police & Criminal Process",
        "sub_type_label": "Arrest — reported via guided interview (no document)",
    },
    "Bank Account Freezing": {
        "questions": FREEZE_QUESTIONS,
        "filter_fn": freeze_filter,
        "build_fields": build_freeze_fields,
        "compliance_runner": run_freeze_compliance_checks,
        "checklist_category": "Police & Criminal Process",
        "sub_type_label": "Bank/Account Freezing — reported via guided interview (no document)",
    },
    "Cheque Bounce": {
        "questions": CHEQUE_QUESTIONS,
        "filter_fn": cheque_filter,
        "build_fields": build_cheque_fields,
        "compliance_runner": run_compliance_checks,
        "checklist_category": "Banking & Cheque Bounce",
        "sub_type_label": "Section 138 NI Act — reported via guided interview (no document)",
    },
     "FIR / Complaint (No Arrest Yet)": {
        "questions": FIR_NO_ARREST_QUESTIONS,
        "filter_fn": fir_no_arrest_filter,
        "build_fields": build_fir_no_arrest_fields,
        "compliance_runner": lambda fields: run_fir_no_arrest_checks(
            fields, fields.get("_user_checked_online"), fields.get("_days_since_registration")
        ),
        "checklist_category": "Police & Criminal Process",
        "sub_type_label": "FIR/Complaint — reported via guided interview (no arrest, no document)",
    },
}
NOT_YET_AVAILABLE = ["Other"]


# =============================================================
# GENERIC INTERVIEW ENGINE — domain-agnostic
# =============================================================
def run_interview(domain_key):
    config = INTERVIEW_CONFIGS[domain_key]
    step_key = f"step__{domain_key}"
    answers_key = f"answers__{domain_key}"
    st.session_state.setdefault(step_key, 0)
    st.session_state.setdefault(answers_key, {})
    st.session_state.setdefault("crime_matches", None)

    step = st.session_state[step_key]

    if step == 0:
        st.subheader(f"Has this situation ({domain_key}) actually happened to you or someone you know?")
        col1, col2 = st.columns(2)
        if col1.button("Yes", use_container_width=True, key=f"gate_yes_{domain_key}"):
            st.session_state[step_key] = 1
            st.rerun()
        if col2.button("No, I'm just exploring", use_container_width=True, key=f"gate_no_{domain_key}"):
            st.info("No problem — feel free to explore the tool, or come back when you need it.")
        return

    questions = config["filter_fn"](config["questions"], st.session_state[answers_key])

    if step > len(questions):
        show_interview_results(domain_key, config)
        return

    q = questions[step - 1]
    st.progress(step / len(questions), text=f"Question {step} of {len(questions)}")

    if st.button("◀ Back", key=f"back_{domain_key}_{step}"):
        st.session_state[step_key] = step - 1
        st.rerun()

    st.subheader(q["text"])

    answer = None

    if q["type"] == "yesno":
        c1, c2, c3 = st.columns(3)
        if c1.button("Yes", use_container_width=True, key=f"y_{domain_key}_{q['key']}"):
            answer = True
        if c2.button("No", use_container_width=True, key=f"n_{domain_key}_{q['key']}"):
            answer = False
        if c3.button("Not sure", use_container_width=True, key=f"u_{domain_key}_{q['key']}"):
            answer = "unclear"

    elif q["type"] == "choice":
        for opt in q["options"]:
            if st.button(opt, use_container_width=True, key=f"c_{domain_key}_{q['key']}_{opt}"):
                answer = opt

    elif q["type"] == "choice_or_text":
        for opt in q["options"]:
            if st.button(opt, use_container_width=True, key=f"ct_{domain_key}_{q['key']}_{opt}"):
                if opt == q.get("text_trigger"):
                    st.session_state[f"showtext_{domain_key}_{q['key']}"] = True
                    st.rerun()
                else:
                    answer = opt
        if st.session_state.get(f"showtext_{domain_key}_{q['key']}"):
            typed = st.text_input("Type it here", key=f"typed_{domain_key}_{q['key']}")
            if st.button("Use this", use_container_width=True, key=f"usetyped_{domain_key}_{q['key']}"):
                if typed.strip():
                    answer = f"typed:{typed.strip()}"

    elif q["type"] == "datetime":
        d = st.date_input("Date", key=f"date_{domain_key}_{q['key']}")
        t = st.time_input("Approximate time", key=f"time_{domain_key}_{q['key']}")
        if st.button("Next", use_container_width=True, key=f"next_{domain_key}_{q['key']}"):
            answer = f"{d.strftime('%d-%m-%Y')} {t.strftime('%H:%M')}"

    elif q["type"] == "datetime_optional":
        known = st.radio("Do you know this?", ["Not yet / Don't know", "Yes, I know the date"],
                          key=f"radio_{domain_key}_{q['key']}")
        if known == "Yes, I know the date":
            d = st.date_input("Date", key=f"date2_{domain_key}_{q['key']}")
            if st.button("Next", use_container_width=True, key=f"next2_{domain_key}_{q['key']}"):
                answer = d.strftime("%d-%m-%Y")
        else:
            if st.button("Next", use_container_width=True, key=f"next3_{domain_key}_{q['key']}"):
                answer = "SKIPPED"

    elif q["type"] == "number_optional":
        known = st.radio("Do you know this?", ["Not sure / don't know", "Yes, I know it"],
                          key=f"radion_{domain_key}_{q['key']}")
        if known == "Yes, I know it":
            val = st.number_input(q.get("input_label", "Amount"), min_value=0, step=1,
                                   key=f"num_{domain_key}_{q['key']}")
            if st.button("Next", use_container_width=True, key=f"nextn_{domain_key}_{q['key']}"):
                answer = val
        else:
            if st.button("Next", use_container_width=True, key=f"nextn2_{domain_key}_{q['key']}"):
                answer = "SKIPPED"
    
    
    elif q["type"] == "text_optional":
        known = st.radio("Do you know this?", ["Not sure / don't know", "Yes, I know it"],
                          key=f"radiot_{domain_key}_{q['key']}")
        if known == "Yes, I know it":
            val = st.text_input(q.get("input_label", "Answer"), key=f"text_{domain_key}_{q['key']}")
            if st.button("Next", use_container_width=True, key=f"nextt_{domain_key}_{q['key']}"):
                if val.strip():
                    answer = val.strip()
                else:
                    answer = "SKIPPED"
        else:
            if st.button("Next", use_container_width=True, key=f"nextt2_{domain_key}_{q['key']}"):
                answer = "SKIPPED"

    elif q["type"] == "crime_name_search":
        accum_key = f"confirmed_sections_{domain_key}"
        st.session_state.setdefault(accum_key, [])

        if st.session_state[accum_key]:
            st.write("**Sections/crimes confirmed so far:**")
            for sec in st.session_state[accum_key]:
                if sec in BNS_SECTION_DATA:
                    st.write(f"- {BNS_SECTION_DATA[sec]['offence']} (Section {sec})")
                else:
                    st.write(f"- Section {sec} (not in our verified reference table)")

        st.write("Type the name of a crime, or a section number, in your own words:")
        typed = st.text_input("Crime name or section", key=f"crime_typed_{domain_key}",
                               placeholder="e.g. cheating, theft, dowry, section 302")

        if st.button("Search", use_container_width=True, key=f"search_{domain_key}_{q['key']}") and typed.strip():
            st.session_state["crime_matches"] = find_sections_by_crime_name(typed)

        matches = st.session_state.get("crime_matches")
        if matches is not None:
            if len(matches) == 0:
                st.info("We couldn't match that to a known offence. That's fine — we'll say so honestly rather than guess.")
            elif len(matches) == 1:
                sec = matches[0]
                st.success(f"Matched: {BNS_SECTION_DATA[sec]['offence']} (Section {sec})")
                if st.button("Add this section", use_container_width=True, key=f"conf_{domain_key}_{q['key']}"):
                    if sec not in st.session_state[accum_key]:
                        st.session_state[accum_key].append(sec)
                    st.session_state["crime_matches"] = None
                    st.rerun()
            else:
                st.write("A few offences matched — please pick the one that fits best:")
                for sec in matches:
                    label = f"{BNS_SECTION_DATA[sec]['offence']} (Section {sec})"
                    if st.button(label, use_container_width=True, key=f"match_{domain_key}_{sec}"):
                        if sec not in st.session_state[accum_key]:
                            st.session_state[accum_key].append(sec)
                        st.session_state["crime_matches"] = None
                        st.rerun()

        st.divider()
        col1, col2 = st.columns(2)
        if col1.button("Add another section/crime", use_container_width=True, key=f"addmore_{domain_key}_{q['key']}"):
            st.session_state["crime_matches"] = None
            st.rerun()
        if col2.button("Done — no more sections", use_container_width=True, key=f"done_{domain_key}_{q['key']}"):
            answer = list(st.session_state[accum_key])
            st.session_state.pop(accum_key, None)

        st.caption("If we don't recognize the exact offence, we'll say so honestly rather than guess.")

    if answer is not None:
        stored = None if answer == "SKIPPED" else answer
        st.session_state[answers_key][q["key"]] = stored
        st.session_state["crime_matches"] = None
        st.session_state[step_key] += 1
        st.rerun()

from main import compute_bail_pathway_info
def show_interview_results(domain_key, config):
    """UPDATED 2026-08-30: added presumption_info and settlement_info
    keys to full_analysis, gated to domain_key == "Cheque Bounce",
    same ternary pattern already used for bail_pathway's arrest-only
    gating. Calls explain_debt_presumption_status and
    compute_settlement_cost_incentive, both new functions sourced from
    Rangappa v Sri Mohan (2010), Bir Singh v Mukesh Kumar (2019), and
    Damodar S. Prabhu v Sayed Babalal H (2010) -- see main.py for full
    citations.

    IMPORTANT: whether these render via render_compliance_ui_main
    depends on that function already having a branch for these NEW
    keys, which was not confirmed. Rather than assume, this also adds
    a guaranteed-visible DIRECT render below the main call -- if
    render_compliance_ui_main is later confirmed to handle these keys
    itself, remove the direct block below to avoid double-rendering."""
    if st.button("◀ Back to last question", key=f"back_results_{domain_key}"):
        st.session_state[f"step__{domain_key}"] = len(config["questions"])
        st.rerun()
    answers = st.session_state[f"answers__{domain_key}"]
    fields = config["build_fields"](answers)
    compliance_result = config["compliance_runner"](fields)

    presumption_info = None
    settlement_info = None
    if domain_key == "Cheque Bounce":
        from main import explain_debt_presumption_status, compute_settlement_cost_incentive
        presumption_info = explain_debt_presumption_status(fields)
        settlement_info = compute_settlement_cost_incentive(fields)

    full_analysis = {
        "classification": {
            "document_type": config["checklist_category"],
            "sub_type": config["sub_type_label"],
            "reasoning": "Built from answers you gave, since no document was available."
        },
        "missing_info": {
            "missing_or_unclear": [],
            "completeness_assessment": "Based on interview answers only — not a document review."
        },
        "compliance": compliance_result,
        "checklist": get_document_checklist(config["checklist_category"]),
        "urgency": {"urgency_level": "Cannot Determine", "deadline_message": "N/A for interview mode", "days_remaining": None},
        "severity": compute_severity(compliance_result.get("compliance_checks", [])),
        "bail_pathway": compute_bail_pathway_info(fields.get("sections_cited", [])) if domain_key == "Arrest-related process" else None,
        "presumption_info": presumption_info,
        "settlement_info": settlement_info,
        "extracted_fields": fields
    }

    render_results(full_analysis, key_prefix=f"iv_{domain_key}")

    if presumption_info:
        st.subheader("About the debt presumption")
        st.write(presumption_info["explanation"])
        st.caption(presumption_info["note"])
    if settlement_info:
        st.subheader("If you are considering settlement")
        st.write(settlement_info["message"])

    default_bail_check = next(
        (c for c in compliance_result.get("compliance_checks", []) if "Default bail" in c["requirement"]),
        None
    )
    if default_bail_check and default_bail_check["status"] in ("Cannot Determine", "May be Non-Compliant"):
        st.subheader("One more question")
        st.write("We couldn't fully resolve the default-bail deadline from your answers.")
        chargesheet_answer = st.radio("Has a chargesheet been filed in this case?",
                                       ["Not yet / Don't know", "Yes"], key=f"cs_radio_{domain_key}")
        if chargesheet_answer == "Yes":
            user_cs_date = st.date_input("Chargesheet filing date", key=f"cs_date_{domain_key}")
            updated_check = check_default_bail(fields, user_chargesheet_date=user_cs_date.strftime("%d-%m-%Y"))
            st.write("Updated result:")
            st.json(updated_check)

    with st.expander("Raw data (advanced)"):
        render_checklist_and_raw(full_analysis)

    if st.button("Start over", key=f"restart_{domain_key}"):
        st.session_state[f"step__{domain_key}"] = 0
        st.session_state[f"answers__{domain_key}"] = {}
        for k in list(st.session_state):
            if k.startswith(f"iv_{domain_key}_"):
                st.session_state.pop(k, None)
        st.rerun()


# =============================================================
# NO-DOCUMENT FLOW: issue-type selector -> routes to the right interview
# =============================================================
def run_no_document_flow():
    issue_type = st.selectbox(
        "What kind of legal issue are you facing?",
        list(INTERVIEW_CONFIGS.keys()) + NOT_YET_AVAILABLE
    )

    if "active_domain" not in st.session_state:
        st.session_state["active_domain"] = issue_type
    elif st.session_state["active_domain"] != issue_type:
        # domain switched mid-session — reset so old answers don't leak in
        st.session_state["active_domain"] = issue_type

    if issue_type in NOT_YET_AVAILABLE:
        st.info(
            f"Guided questions for **{issue_type}** aren't available yet — this is still being built. "
            "If you have any paper related to this issue, even a partial one, please try uploading it instead."
        )
        return

    run_interview(issue_type)


# =============================================================
# DOCUMENT UPLOAD FLOW — unchanged from before
# =============================================================
def run_document_flow():
    uploaded_file = st.file_uploader("Choose a PDF", type="pdf")

    if uploaded_file is not None:
        with open("temp_uploaded.pdf", "wb") as f:
            f.write(uploaded_file.getbuffer())

        if st.button("Analyze", use_container_width=True):
            with st.spinner("Analyzing..."):
                document_text = clean_text(extract_text_from_pdf("temp_uploaded.pdf"))
                st.session_state["result"] = analyze_document(document_text)

        if "result" in st.session_state:
            result = st.session_state["result"]

            render_results(result, key_prefix="doc")

            default_bail_check = next(
                (c for c in result["compliance"].get("compliance_checks", []) if "Default bail" in c["requirement"]),
                None
            )
            if default_bail_check and default_bail_check["status"] in ("Cannot Determine", "May be Non-Compliant"):
                st.subheader("One more question")
                st.write("This document alone couldn't fully resolve the default-bail deadline.")
                chargesheet_answer = st.radio("Has a chargesheet been filed in this case?", ["Not yet / Don't know", "Yes"])
                if chargesheet_answer == "Yes":
                    user_cs_date = st.date_input("Chargesheet filing date")
                    updated_check = check_default_bail(
                        result["extracted_fields"],
                        user_chargesheet_date=user_cs_date.strftime("%d-%m-%Y")
                    )
                    st.write("Updated result:")
                    st.json(updated_check)

            with st.expander("Raw data (advanced)"):
                render_checklist_and_raw(result)

            if st.button("Start over", key="restart_document_flow"):
                for k in ("result", "brief_bytes"):
                    st.session_state.pop(k, None)
                for k in list(st.session_state):
                    if k.startswith("doc_"):
                        st.session_state.pop(k, None)
                st.rerun()


def run_batch_triage_flow():
    st.subheader("📋 Batch Triage — Cause List Mode")
    st.write("Upload several documents to see which need urgent attention first.")
    uploaded_files = st.file_uploader(
        "Choose PDFs", type="pdf", accept_multiple_files=True, key="batch_uploader"
    )

    if uploaded_files and st.button("Analyze All", key="batch_analyze_all"):
        results = []
        with st.spinner(f"Analyzing {len(uploaded_files)} document(s)..."):
            for i, uf in enumerate(uploaded_files):
                temp_path = f"temp_batch_{i}_{uf.name}"
                with open(temp_path, "wb") as f:
                    f.write(uf.getbuffer())
                document_text = clean_text(extract_text_from_pdf(temp_path))
                analysis = analyze_document(document_text)
                results.append({"filename": uf.name, "analysis": analysis})
        st.session_state["batch_results"] = results
        st.session_state.pop("batch_zip_bytes", None)  # clear stale ZIP from any prior batch

    if "batch_results" in st.session_state:
        sorted_results = sorted(
            st.session_state["batch_results"],
            key=lambda r: r["analysis"].get("severity", {}).get("severity_score", 0),
            reverse=True
        )

        # ---- Idea 1: summary counts, before anything else ----
        counts = {"red": 0, "orange": 0, "amber": 0, "green": 0}
        for r in sorted_results:
            color = r["analysis"].get("severity", {}).get("severity_color", "green")
            counts[color] = counts.get(color, 0) + 1
        st.markdown(
            f"### 🔴 {counts['red']} urgent · 🟠 {counts['orange']} concerns · "
            f"🟡 {counts['amber']} minor · 🟢 {counts['green']} clear"
        )

        # ---- Idea 3: generate every brief in one action ----
        if st.button("📑 Generate All Compliance Briefs", key="batch_gen_all"):
            import zipfile
            zip_path = "batch_briefs.zip"
            with zipfile.ZipFile(zip_path, "w") as zf:
                for r in sorted_results:
                    safe_name = re.sub(r'[^A-Za-z0-9_\-]', '_', r["filename"].replace(".pdf", ""))
                    brief_path = generate_compliance_brief(
                        r["analysis"], output_path=f"brief_{safe_name}.pdf"
                    )
                    zf.write(brief_path, arcname=f"Brief_{safe_name}.pdf")
            with open(zip_path, "rb") as f:
                st.session_state["batch_zip_bytes"] = f.read()

        if "batch_zip_bytes" in st.session_state:
            st.download_button(
                "Download all briefs (ZIP)",
                data=st.session_state["batch_zip_bytes"],
                file_name="compliance_briefs.zip",
                mime="application/zip",
                key="batch_zip_download"
            )

        st.divider()
        st.markdown("### Triage Summary — worst first")
        icon = {"red": "🔴", "orange": "🟠", "amber": "🟡", "green": "🟢"}

        for r in sorted_results:
            sev = r["analysis"].get("severity", {})
            label = sev.get("severity_label", "Not Available")
            dot = icon.get(sev.get("severity_color"), "⚪")
            is_urgent = sev.get("severity_color") == "red"

            # ---- Idea 4: case-like label instead of raw filename ----
            classification = r["analysis"].get("classification", {})
            sub_type = classification.get("sub_type") or r["filename"]

            # ---- Idea 2: auto-expand anything urgent ----
            with st.expander(f"{dot} {sub_type} — {label}", expanded=is_urgent):
                st.caption(f"Source file: {r['filename']}")
                render_quick_reference(r["analysis"])
                st.divider()
                render_compliance_ui_main(r["analysis"])

        st.divider()
        if st.button("Clear batch and start over", key="batch_clear"):
            st.session_state.pop("batch_results", None)
            st.session_state.pop("batch_zip_bytes", None)
            st.rerun()

# =============================================================
# CHAT MODE (ask in your own words)
# =============================================================

# --- Lane B: live "related judgments" panel -------------------------------
# Runs AFTER the grounded answer, entirely to the side of it (see
# related_judgments.py's module docstring). Opt-in: the user taps a button.
# Only offered on states that produced a real answer, and only rendered to
# the user when every issue is a settled doctrine (result["show_user"]).

_RELATED_STATES = ("single_match", "conflicting_matches")


def _candidate_key(c):
    """Stable identity for a ranked candidate, for session-state tracking
    of which unverified ones the user has confirmed. Same shape record_approved
    already dedupes on."""
    t = c.get("triage", {})
    return (c.get("source"), t.get("tid") or t.get("title"))


def _render_one_judgment(c, *, key_prefix=""):
    """Shared card layout for one candidate -- title/citation line, gloss,
    up to 2 pinned paragraphs, link, adverse markers. Used by both the
    fully-trusted panel and the unverified-review panel.

    procedural_disposal=True never reaches this function via the
    fully-trusted panel (related_judgments._display_worthy hard-excludes
    it there) -- it can only appear here via the unverified-review panel,
    which shows everything per that panel's own "never hide, only flag"
    design. The warning below is that flag."""
    t = c.get("triage", {})
    if c.get("procedural_disposal") is True:
        st.warning(
            "⚠ **This looks like a bail or interlocutory application, not a final judgment.** "
            "Courts don't treat these as legal precedent the way a decided case is treated"
            + (" — flagged phrase: “" + c["procedural_disposal_markers"][0] + "”"
               if c.get("procedural_disposal_markers") else "")
            + "."
        )
    title = t.get("title") or "Judgment"
    bits = [f"**{title}**"]
    if t.get("cited_in_answer"):
        bits.append("_the judgment cited in the answer above_")
    elif t.get("previously_approved"):
        bits.append("_you kept this in a draft before_")
    elif c.get("source") == "corpus":
        bits.append("in our verified library")
    elif t.get("court"):
        bits.append(t["court"])
    if (t.get("publish_date") or "")[:4]:
        bits.append((t["publish_date"])[:4])
    st.markdown(" · ".join(bits))

    if c.get("gloss"):
        st.markdown(f"*{c['gloss']}*")

    for p in (c.get("pinned") or [])[:2]:
        where = f"Para {p['para_number']}" if p.get("para_number") else "Extract"
        st.markdown(f"> **{where}.** {(p.get('text') or '').strip()[:600]}…")

    if t.get("url"):
        st.markdown(f"[Read the full judgment on Indian Kanoon ↗]({t['url']})")
    if t.get("adverse_markers"):
        st.caption("⚠ A later case may have questioned this — flagged terms: "
                   + ", ".join(t["adverse_markers"]))


def _render_related_judgments_result(result, qhash):
    """Render the outcome of a related-judgments run under the last answer.

    Two distinct panels, never blended:
      - the fully-trusted panel (result['for_display']) -- shown whenever
        show_user is True (every issue is a whitelisted settled doctrine).
      - the unverified-review panel (result['unverified_for_display']) --
        shown when show_user is False. This is the FULL ranked list,
        unfiltered by score/gloss/alignment (2026-09-04, per explicit
        user direction: this tool's own confidence judgment must never
        decide what the user is even allowed to see). Nothing here is
        ever treated as approved on its own; the user must explicitly
        confirm each one via its own button before it is recorded or
        used in a draft (see confirmed_unverified_<qhash> in session
        state)."""
    disp = result.get("for_display") or []
    unverified = result.get("unverified_for_display") or []

    if not result.get("show_user") or not disp:
        if not unverified:
            st.caption(
                "I looked for related court judgments but the search itself came back empty for "
                "this one. (This doesn't change the answer above.)"
            )
            return
        _render_unverified_judgments(unverified, result, qhash)
        return

    with st.expander(f"⚖️ {len(disp)} related court judgment(s) — read these yourself", expanded=True):
        st.warning(
            "**Unverified.** These were found automatically, not checked by a lawyer. A judgment "
            "may have been appealed or narrowed since — read the full text before relying on it. "
            "This does not change the answer above."
        )
        for c in disp:
            _render_one_judgment(c)
            st.divider()

        st.caption("This is general information, not legal advice. Please consult a qualified lawyer.")


def _render_unverified_judgments(unverified, result, qhash):
    """The stricter, not-whitelisted path: this topic (e.g. cheating,
    breach of trust -- a substantive offence, not one of the settled
    arrest-procedure doctrines) has no safety-net whitelist entry, so
    nothing here is shown as confirmed. Each candidate needs the user's
    own, per-item confirmation before it is remembered for reuse or
    folded into a draft -- confirming does NOT change the answer above,
    it only decides what this session's draft (if any) may cite."""
    confirmed_key = f"confirmed_unverified_{qhash}"
    confirmed = st.session_state.setdefault(confirmed_key, [])
    confirmed_ids = {_candidate_key(c) for c in confirmed}

    with st.expander(
        f"🔎 {len(unverified)} judgment(s) found for this situation — unfiltered, read carefully",
        expanded=True,
    ):
        st.warning(
            "**Not verified, and not pre-filtered by confidence.** This topic doesn't have the "
            "same built-in settled-doctrine safety check the arrest-procedure judgments above get, "
            "so every judgment this search found is listed here, best match first, including ones "
            "that may turn out to be a weak or wrong match. Nothing has been screened out for you -- "
            "read each one in full and decide for yourself whether it actually matches your "
            "situation before relying on it or using it in a draft. This does not change the answer "
            "above."
        )
        for c in unverified:
            _render_one_judgment(c)
            ck = _candidate_key(c)
            if ck in confirmed_ids:
                st.caption("✓ You confirmed this one — it will be offered for your draft and remembered for next time.")
            else:
                flagged = c.get("procedural_disposal") is True
                if st.button(
                    "👍 Yes, use this despite the warning above" if flagged else "👍 Yes, this matches my situation",
                    key=f"confirm_unverified_{qhash}_{ck[0]}_{ck[1]}",
                    help=("This looks like a bail/interlocutory order, not a judgment -- only confirm if "
                          "you've read it and are sure it's actually relevant precedent." if flagged else
                          "Only what you confirm here is used -- nothing on this panel is kept automatically."),
                ):
                    confirmed.append(c)
                    try:
                        from related_judgments import record_approved
                        profile = result.get("profile") or {}
                        record_approved(
                            profile.get("_question", ""), profile.get("issues", []),
                            {"for_display": [c]},
                        )
                    except Exception:
                        pass
                    st.rerun()
            st.divider()

        st.caption("This is general information, not legal advice. Please consult a qualified lawyer.")


def _render_related_judgments_section():
    """The opt-in button + (once run) the panel, for the most recent
    answered question. Rendered on every pass of run_chat_flow so it
    survives the button-click rerun."""
    import hashlib, os

    la = st.session_state.get("chat_last_answer")
    if not la or la.get("state") not in _RELATED_STATES:
        return
    if os.getenv("KYR_DISABLE_LIVE_JUDGMENTS"):
        return

    qhash = hashlib.md5(la["question"].encode()).hexdigest()[:12]
    result_key = f"related_result_{qhash}"

    if result_key in st.session_state:
        _render_related_judgments_result(st.session_state[result_key], qhash)
        if st.button("↻ Search again", key=f"related_again_{qhash}",
                     help="Run the search again from scratch."):
            st.session_state.pop(result_key, None)
            st.session_state.pop(f"related_prep_{qhash}", None)
            st.session_state.pop(f"confirmed_unverified_{qhash}", None)
            st.rerun()
        return

    if st.button("🔎 Show related court judgments", key=f"related_btn_{qhash}",
                 help="Searches Indian court judgments for a situation like the one you described."):
        prepared = None
        fut = st.session_state.get(f"related_prep_{qhash}")
        if fut is not None:
            try:
                prepared = fut.result(timeout=20)   # the free half; usually already done
            except Exception:
                prepared = None
        with st.spinner("Searching Indian court judgments for a similar situation…"):
            try:
                from related_judgments import get_related_judgments
                st.session_state[result_key] = get_related_judgments(
                    la["question"], la.get("reply"), prepared=prepared
                )
            except Exception:
                # CONFIRMED REAL GAP (2026-09-05, reported by the user: the
                # button "when clicked didn't show" on a real run): this
                # bare except previously swallowed ANY failure -- a live
                # Indian Kanoon timeout, a decompose_situation() API error,
                # anything -- into the exact same empty dict a genuinely-
                # empty search produces, with zero logging. The user (and
                # this project) had no way to tell "nothing found" apart
                # from "something broke," the same failure class already
                # found and fixed twice today for classify_scope. Logging
                # the real exception here doesn't fix whatever the
                # underlying transient failure was, but makes it
                # diagnosable the next time it happens instead of invisible.
                logger.exception(
                    "_render_related_judgments_section: get_related_judgments failed for qhash=%s",
                    qhash,
                )
                st.session_state[result_key] = {"show_user": False, "for_display": [], "unverified_for_display": []}
        st.rerun()


def _render_arrest_draft_section():
    """Under an arrest-situation chat answer: an opt-in button that runs
    the arrest compliance checklist on what the person described and
    produces an editable draft (representation to the Magistrate /
    complaint to the SP), with the retrieved judgment passages and the
    person's own grievances folded in. Rendered on every pass so it
    survives the button-click rerun, same as the related-judgments panel."""
    import hashlib

    la = st.session_state.get("chat_last_answer")
    if not la or la.get("state") not in _RELATED_STATES or not la.get("situation"):
        return

    qhash = hashlib.md5(la["question"].encode()).hexdigest()[:12]
    fa_key = f"chatdraft_{qhash}"

    if fa_key not in st.session_state:
        if not st.button("📝 Prepare a draft to send", key=f"chatdraft_btn_{qhash}",
                         help="Runs the arrest checklist on what you've described and writes a "
                              "representation you can edit and send to the Magistrate or the SP."):
            return
        with st.spinner("Preparing the draft…"):
            try:
                from chat_assistant import extract_arrest_situation
                from main import run_arrest_compliance_checks, compute_severity
                from related_judgments import authorities_from_matches, authorities_from_result
                convo = "\n".join(
                    f"{t['role']}: {t['content']}" for t in st.session_state.get("chat_history", [])
                ) or la["question"]
                fields, matters = extract_arrest_situation(convo)
                if fields is None:
                    st.session_state[fa_key] = {"error": True}
                else:
                    checks = run_arrest_compliance_checks(fields)
                    fa = {
                        "compliance": checks,
                        "extracted_fields": fields,
                        "severity": compute_severity(checks["compliance_checks"]),
                    }
                    auths = authorities_from_matches(la.get("matches"))
                    rr = st.session_state.get(f"related_result_{qhash}")
                    if rr:
                        auths = authorities_from_result(rr) + auths
                        # the user has read these live judgments and is putting
                        # them into a filing -> remember them so the same /
                        # a similar question retrieves them instantly next time
                        try:
                            from related_judgments import record_approved
                            record_approved(la["question"], (rr.get("profile") or {}).get("issues", []), rr)
                        except Exception:
                            pass
                    # not-whitelisted domain: only what the user EXPLICITLY
                    # confirmed on the unverified-review panel (never the
                    # whole unverified list) is offered to the draft --
                    # record_approved for these already ran at confirm-time
                    # (see _render_unverified_judgments), this just makes
                    # them available to THIS session's draft too.
                    confirmed = st.session_state.get(f"confirmed_unverified_{qhash}") or []
                    if confirmed:
                        auths = authorities_from_result({"for_display": confirmed}) + auths
                    st.session_state[fa_key] = {"fa": fa, "authorities": auths, "matters": matters}
            except Exception:
                st.session_state[fa_key] = {"error": True}
        st.rerun()

    stashed = st.session_state[fa_key]
    if stashed.get("error"):
        st.caption(
            "I couldn't prepare a draft for this one. You can use the \"describe my situation\" "
            "option above — it walks through the same checklist step by step."
        )
        return

    from draft_layer import detect_draft_domain
    if detect_draft_domain(stashed["fa"]) is None:
        return

    if st.session_state.get(f"related_result_{qhash}") and not stashed.get("_had_related"):
        stashed["_had_related"] = True  # note only; the draft was built with them if present
    render_draft_section(
        stashed["fa"], key_prefix=fa_key,
        authorities=stashed["authorities"], matters_raised=stashed["matters"],
    )
    if st.button("↻ Rebuild draft", key=f"chatdraft_again_{qhash}",
                 help="Rebuild from scratch (e.g. after running 'Show related judgments')."):
        for k in list(st.session_state):
            if k.startswith(fa_key):
                st.session_state.pop(k, None)
        st.rerun()


def run_chat_flow():
    st.write(
        "Ask about a police arrest, an FIR, or your rights during criminal proceedings "
        "in your own words — no need to know any legal terms or section numbers. "
        "I'll tell you honestly if something is outside what I can check."
    )

    st.session_state.setdefault("chat_history", [])

    # Replay the conversation so far, so the person can scroll back and see
    # what's already been asked/answered, same as any familiar chat app.
    for turn in st.session_state["chat_history"]:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    question = st.chat_input("Type your question here...")
    if not question:
        # No new question this pass -- still render the opt-in affordances
        # for the most recent answer (they must survive the rerun a button
        # click triggers) and the standing disclaimer.
        _render_related_judgments_section()
        _render_arrest_draft_section()
        st.caption(
            "This is general information based on Indian law and court judgments, not legal "
            "advice. For guidance on your specific situation, please consult a qualified lawyer."
        )
        return

    st.session_state["chat_history"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Looking into this..."):
            from chat_assistant import answer_question
            result = answer_question(question)

        state = result["state"]
        handoff_domain = None

        if state == "unrelated":
            reply = (
                "That doesn't look like a legal question, so I don't think I can help with it here. "
                "I'm built specifically to help with **police arrests, FIRs, and criminal procedure "
                "under Indian law (BNS/BNSS)**. If you had a question along those lines, feel free to "
                "ask — in your own words is completely fine."
            )

        elif state == "covered_elsewhere_in_tool":
            redirect_domain = result.get("redirect_domain")
            handoff_domain = redirect_domain if redirect_domain in _DOMAIN_FLOW_CONFIG else None
            if handoff_domain:
                domain_label = "bank account freeze" if redirect_domain == "freeze" else "cheque bounce"
                reply = (
                    f"This sounds like it's about a **{domain_label}** — good news, this tool has a "
                    f"dedicated assistant for exactly this, and it can give you a real assessment, not "
                    f"just an explanation. No document needed; it'll ask you a few questions directly.\n\n"
                    f"Click below and I'll carry over what you already told me, so you won't have to "
                    f"repeat yourself."
                )
            else:
                # Classifier recognised the domain but couldn't confidently
                # say WHICH one -- fall back to the older, domain-less
                # redirect rather than guessing and launching the wrong flow.
                reply = (
                    "This sounds like it's about a **bank account freeze** or a **cheque bounce case** — "
                    "and good news, this tool does handle those.\n\n"
                    "**What you can do next:** choose **\"Answer guided questions instead\"** above and "
                    "pick the matching issue (no document needed), or **\"I have a document\"** if you "
                    "have the actual notice or letter."
                )

        elif state == "adjacent_uncovered":
            reply = (
                "This sounds like a real legal question, but it's outside what I'm built to check. "
                "Right now I only cover **police arrests, FIRs, and criminal procedure** under Indian "
                "law (BNS/BNSS) — things like whether police can arrest someone, what notice must be "
                "given before an arrest, and what rights an arrested person has.\n\n"
                "**What you can do next:** for this kind of question, it's best to speak with a lawyer "
                "who handles that specific area of law."
            )

        elif state == "classifier_unavailable" or state == "retrieval_unavailable":
            reply = (
                "I'm having trouble looking into this right now — something on my end isn't working "
                "properly. This isn't about your question; it's a technical issue.\n\n"
                "**What you can do next:** try again in a moment, or use the **\"I have a document\"** "
                "or **\"Answer guided questions instead\"** options above, which don't depend on this."
            )

        elif state == "no_match":
            reply = (
                "I looked, but I couldn't find anything in what I've studied that clearly matches this. "
                "That might mean I just need more detail, or it might genuinely be outside what I "
                "currently cover.\n\n"
                "**What you can do next:** try describing the situation with a bit more detail (what "
                "happened, and roughly when), or if you know the specific section of law involved, "
                "mention it directly — I can look that up precisely."
            )

        elif state == "conflicting_matches":
            if result.get("response_text"):
                reply = result["response_text"]
                # The grounded answer already ends with its own single
                # "what you can do next" line (the prompt mandates it) --
                # appending another here produced a visible DUPLICATE
                # closer (confirmed live 2026-09-01).
            else:
                reply = (
                    "This touches on more than one part of the law, and they don't all say the same "
                    "thing — so I don't want to guess which one applies to you. Here's what I found:"
                    "\n\n**What you can do next:** if you have a document (like an FIR or arrest memo), "
                    "uploading it here would let me check exactly which provision applies to your "
                    "situation, instead of guessing between them."
                )
            # Only the handful of matches that actually drive the answer
            # -- the old loop over EVERY match dumped ~17 near-identical
            # near-noise rows (confirmed live 2026-09-01).
            with st.expander("📖 See what I found and compared"):
                for m in result["matches"][:5]:
                    label = m.get("section_number") or m.get("paragraph_number")
                    source = m.get("case_name") or "BNS/BNSS"
                    st.markdown(f"**{source}, Section/Para {label}** (relevance: {m['score']:.2f})")
                    _render_chat_match_currency_caveat(m)
                    _render_chat_match_old_code_note(m)
                    st.caption((m.get("text") or "").strip()[:500])
            if result.get("situation_detected"):
                handoff_domain = "arrest"

        elif state == "single_match":
            if result.get("response_text"):
                reply = result["response_text"]
                if result.get("situation_detected"):
                    handoff_domain = "arrest"
            else:
                # Generation failed but retrieval succeeded -- fall back
                # to showing the real retrieved text directly rather than
                # inventing a summary, consistent with this project's
                # "never guess" principle.
                m = result["matches"][0]
                reply = f"Here's what I found on this:\n\n> {m['text'][:800]}"
            with st.expander("📖 Read the source"):
                for m in _sources_worth_showing(result["matches"], reply):
                    label = m.get("section_number") or m.get("paragraph_number")
                    source = m.get("case_name") or "BNS/BNSS"
                    st.markdown(f"**{source}, Section/Para {label}**")
                    _render_chat_match_currency_caveat(m)
                    _render_chat_match_old_code_note(m)
                    st.caption((m.get("text") or "").strip()[:800])

        else:
            reply = "Something unexpected happened on my end — please try rephrasing your question."

        st.markdown(reply)
        if handoff_domain:
            # For freeze/cheque the reply IS the handoff pitch (chat has
            # no corpus for those). For arrest the reply is a full answer,
            # so the button needs its own one-line lead-in.
            if handoff_domain == "arrest":
                st.caption(
                    "Want more than an explanation? I can take what you've already told me and run a "
                    "full procedural-compliance check on it — the same one used for uploaded documents."
                )
            # MUST use on_click, not `if st.button(...):` -- see
            # _handoff_to_domain_flow's docstring for the confirmed
            # StreamlitAPIException this avoids.
            st.button(
                _DOMAIN_FLOW_CONFIG[handoff_domain]["button_label"],
                key="chat_domain_handoff",
                on_click=_handoff_to_domain_flow,
                args=(handoff_domain, question),
            )

    st.session_state["chat_history"].append({"role": "assistant", "content": reply})

    # Remember this answer so the opt-in "related judgments" affordance can
    # render under it -- both now and on the reruns a button click triggers
    # (only for states that produced a real grounded answer, never for
    # redirects / no-match / errors).
    if state in _RELATED_STATES:
        st.session_state["chat_last_answer"] = {
            "question": question, "reply": reply, "state": state,
            "situation": bool(result.get("situation_detected")),
            "matches": result.get("matches") or [],
        }
        # Kick off the FREE half of Lane B in the background now, so a
        # later "Show related judgments" click only waits on the paid
        # Indian Kanoon + gloss part. Best-effort -- if it fails, the
        # click just does the whole thing.
        if not os.getenv("KYR_DISABLE_LIVE_JUDGMENTS"):
            import hashlib as _hl
            pk = f"related_prep_{_hl.md5(question.encode()).hexdigest()[:12]}"
            if pk not in st.session_state:
                try:
                    from related_judgments import submit_prepare
                    st.session_state[pk] = submit_prepare(question, reply)
                except Exception:
                    pass
    else:
        st.session_state.pop("chat_last_answer", None)

    _render_related_judgments_section()
    _render_arrest_draft_section()

    st.caption(
        "This is general information based on Indian law and court judgments, not legal advice. "
        "For guidance on your specific situation, please consult a qualified lawyer."
    )

    

def run_freeze_interview_chat_flow():
    """Free-text conversational compliance-check flow for bank-account
    freezing. Mirrors run_interview_chat_flow()'s (arrest) structure,
    but has NO offence/section-identification step -- per explicit user
    confirmation, a person whose account is frozen typically does not
    know which BNSS section was invoked. Instead asks about observable
    facts and feeds them into check_freeze_authorization_inferred, a
    function specifically built to never silently convert an inferred
    fact into a confident section citation the person never stated.
 
    Every verdict still comes from the SAME check_freeze_section_and_scope,
    check_freeze_holder_intimation, and check_freeze_authorization_inferred
    functions main.py already has.
    """
    from freeze_interview_flow import FreezeInterviewState, process_turn
 
    st.write(
        "Describe what happened with your frozen account, in your own words -- no document needed. "
        "I'll ask a few follow-up questions, then give you a real assessment of whether proper "
        "procedure was followed."
    )
 
    st.session_state.setdefault("freeze_chat_history", [])
    st.session_state.setdefault("freeze_state_obj", FreezeInterviewState())
 
    for turn in st.session_state["freeze_chat_history"]:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
 
    if st.session_state.get("freeze_chat_results") is not None:
        results = st.session_state["freeze_chat_results"]
        st.divider()

        severity = results.get("severity", {})
        if severity.get("severity_color") in ("orange", "red"):
            st.warning(f"{severity.get('severity_label', 'Concerns found')} — see the tabs below.")

        full_analysis = _assessment_full_analysis("freeze", results)
        render_results(full_analysis, key_prefix="freezechat")

        st.divider()
        _back_to_start_button("freezechat")
        return
 
    user_message = st.chat_input("Describe what happened, or answer the question above...")
    if not user_message:
        return
 
    st.session_state["freeze_chat_history"].append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)
 
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            state = st.session_state["freeze_state_obj"]
            try:
                result = process_turn(state, user_message)
            except Exception:
                result = {"state": "extraction_unavailable", "field_name": None}
 
        turn_state = result["state"]
 
        if turn_state == "asking_field":
            reply = result["question"]
 
        elif turn_state == "extraction_unavailable":
            reply = "Sorry, I had trouble understanding that -- could you try rephrasing your answer?"
 
        elif turn_state == "ready_for_results":
            st.session_state["freeze_chat_results"] = {
                "compliance_result": result["compliance_result"],
                "severity": result["severity"],
                "fields_known": result["fields_known"],
            }
            reply = "Thanks -- I have enough to give you a real assessment now. I've put it together below."
 
        else:
            reply = "Something unexpected happened on my end -- please try rephrasing."
 
        st.markdown(reply)
 
    st.session_state["freeze_chat_history"].append({"role": "assistant", "content": reply})
 
    if st.session_state.get("freeze_chat_results") is not None:
        st.rerun()
 
    st.caption(
        "This is general information based on Indian law and court judgments, not legal advice. "
        "For guidance on your specific situation, please consult a qualified lawyer."
    )
def run_cheque_interview_chat_flow():
    """Free-text conversational compliance-check flow for cheque-bounce
    (Section 138 NI Act) cases. Same architecture as
    run_interview_chat_flow (arrest) and run_freeze_interview_chat_flow
    (bank freezing). No offence/section-identification step -- every
    conversation here is automatically a Section 138 matter.
 
    Renders BOTH informational sidebars (debt presumption explanation,
    settlement cost incentive) alongside the 4 hard compliance checks.
    """
    from cheque_bounce_interview_flow import ChequeBounceInterviewState, process_turn
 
    st.write(
        "Describe your bounced-cheque situation, in your own words -- no document needed. I'll ask "
        "a few follow-up questions, then give you a real assessment of whether proper procedure was "
        "followed."
    )
 
    st.session_state.setdefault("cheque_chat_history", [])
    st.session_state.setdefault("cheque_state_obj", ChequeBounceInterviewState())
 
    for turn in st.session_state["cheque_chat_history"]:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])
 
    if st.session_state.get("cheque_chat_results") is not None:
        results = st.session_state["cheque_chat_results"]
        st.divider()

        severity = results.get("severity", {})
        if severity.get("severity_color") in ("orange", "red"):
            st.warning(f"{severity.get('severity_label', 'Concerns found')} — see the tabs below.")

        full_analysis = _assessment_full_analysis("cheque_bounce", results)
        render_results(full_analysis, key_prefix="chequechat")

        presumption_info = results.get("presumption_info")
        if presumption_info:
            st.subheader("About the debt presumption")
            st.write(presumption_info["explanation"])
            st.caption(presumption_info["note"])

        settlement_info = results.get("settlement_info")
        if settlement_info:
            st.subheader("If you are considering settlement")
            st.write(settlement_info["message"])

        st.divider()
        _back_to_start_button("chequechat")
        return
 
    user_message = st.chat_input("Describe what happened, or answer the question above...")
    if not user_message:
        return
 
    st.session_state["cheque_chat_history"].append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)
 
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            state = st.session_state["cheque_state_obj"]
            try:
                result = process_turn(state, user_message)
            except Exception:
                result = {"state": "extraction_unavailable", "field_name": None}
 
        turn_state = result["state"]
 
        if turn_state == "asking_field":
            reply = result["question"]
 
        elif turn_state == "extraction_unavailable":
            reply = "Sorry, I had trouble understanding that -- could you try rephrasing your answer?"
 
        elif turn_state == "ready_for_results":
            st.session_state["cheque_chat_results"] = {
                "compliance_result": result["compliance_result"],
                "presumption_info": result["presumption_info"],
                "settlement_info": result["settlement_info"],
                "severity": result["severity"],
                "fields_known": result["fields_known"],
            }
            reply = "Thanks -- I have enough to give you a real assessment now. I've put it together below."
 
        else:
            reply = "Something unexpected happened on my end -- please try rephrasing."
 
        st.markdown(reply)
 
    st.session_state["cheque_chat_history"].append({"role": "assistant", "content": reply})
 
    if st.session_state.get("cheque_chat_results") is not None:
        st.rerun()
 
    st.caption(
        "This is general information based on Indian law and court judgments, not legal advice. "
        "For guidance on your specific situation, please consult a qualified lawyer."
    )
    

def run_interview_chat_flow():
    """Free-text conversational compliance-check flow, for a person with
    NO document who wants to describe their situation in their own words
    and get a REAL compliance verdict -- not just an explanation like
    run_chat_flow() gives. Every verdict still comes from
    run_arrest_compliance_checks(), the SAME function the document-upload
    and button-based interview flows already use -- this mode only
    changes HOW the fields get collected (conversation, not a form or a
    PDF), never how compliance is decided.

    UPDATED 2026-08-29: results now lead with a warm, offence-specific,
    plain-language summary (layman_summary.py) instead of the
    lawyer-style structured render as the FIRST thing shown. The
    existing structured render (render_compliance_ui_main) is still
    fully available -- just moved behind a "Show full legal breakdown"
    expander, for when the person (or their lawyer) wants the formal
    version. Nothing about the underlying verdict changed; this is
    purely a presentation reorder based on two confirmed real problems:
    the old default output was offence-generic (never named "theft"
    even when that's what the checks were about) and assumed a level
    of legal literacy a stressed layperson often doesn't have.

    Scope: arrest cases only, matching Interview_flow.py's current scope.
    """
    from interview_flow import InterviewState  # process_turn now goes via _arrest_turn_reply

    st.write(
        "Describe what happened, in your own words -- no document needed. "
        "I'll ask a few follow-up questions, then give you a real assessment "
        "of whether proper procedure was followed, the same way I would for "
        "an uploaded document."
    )

    st.session_state.setdefault("interview_chat_history", [])
    st.session_state.setdefault("interview_state_obj", InterviewState())

    for turn in st.session_state["interview_chat_history"]:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    
    if st.session_state.get("interview_chat_results") is not None:
        results = st.session_state["interview_chat_results"]
        full_analysis = results["full_analysis"]
        st.divider()

        severity = full_analysis.get("severity", {})
        if severity.get("severity_color") in ("orange", "red"):
            st.warning(f"{severity.get('severity_label', 'Concerns found')} — see the tabs below.")

        render_results(full_analysis, key_prefix="ivchat",
                       counsel_text=results.get("layman_summary"))

        st.divider()

        _back_to_start_button("ivchat")

        if results.get("tier_shown") == 1:
            st.markdown(
                "This covers the most important arrest-procedure questions. A few more "
                "questions would let me check additional safeguards too -- whether your "
                "family was told, whether a medical exam was done, when the person was "
                "produced before a court, and whether a chargesheet has been filed yet -- "
                "entirely optional."
            )
            if st.button("Answer a few more quick questions", key="advance_tier_2"):
                state = st.session_state["interview_state_obj"]
                state.advance_to_tier_2()
                next_field, next_question = state.next_question() or (None, None)
                if next_field is not None:
                    st.session_state["interview_chat_history"].append(
                        {"role": "assistant", "content": next_question}
                    )
                st.session_state.pop("interview_chat_results", None)
                st.rerun()
 
        with st.expander("Raw data (advanced)"):
            render_checklist_and_raw(full_analysis)

        if st.button("Start over", key="restart_interview_chat"):
            from interview_flow import InterviewState
            st.session_state["interview_chat_history"] = []
            st.session_state["interview_state_obj"] = InterviewState()
            st.session_state.pop("interview_chat_results", None)
            for k in list(st.session_state):
                if k.startswith("ivchat_"):
                    st.session_state.pop(k, None)
            st.rerun()
        return

    user_message = st.chat_input("Describe what happened, or answer the question above...")
    if not user_message:
        return

    st.session_state["interview_chat_history"].append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            state = st.session_state["interview_state_obj"]
            # Shared with the chat-handoff button (_handoff_to_domain_flow,
            # domain="arrest") so both entry points behave identically.
            reply, results_payload = _arrest_turn_reply(state, user_message)
            if results_payload is not None:
                st.session_state["interview_chat_results"] = results_payload

        st.markdown(reply)

    st.session_state["interview_chat_history"].append({"role": "assistant", "content": reply})

    if st.session_state.get("interview_chat_results") is not None:
        st.rerun()

    st.caption(
        "This is general information based on Indian law and court judgments, not legal advice. "
        "For guidance on your specific situation, please consult a qualified lawyer."
    )


# =============================================================
# ROUTER
# =============================================================
_ROUTER = {
    "chat": run_chat_flow,
    "document": run_document_flow,
    "guided": run_no_document_flow,
    "triage": run_batch_triage_flow,
    "arrest_assess": run_interview_chat_flow,
    "freeze_assess": run_freeze_interview_chat_flow,
    "cheque_assess": run_cheque_interview_chat_flow,
}
_ROUTER.get(st.session_state.get("route", "chat"), run_chat_flow)()
