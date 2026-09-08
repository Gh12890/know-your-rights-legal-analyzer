"""
recourse_app.py  --  the single-flow public app for the ILTN Vibeathon.

One input box. One answer, built for the situation the person is in.

This app is a thin UI over the engine:
  scenario_router.route_situation   -> which situation (LLM classify only)
  scenario_answer.build_scenario_answer -> the tailored answer (pure Python)
  scenario_draft.build_document     -> the first-draft document (pure Python)
  scenario_verification             -> the four-way citation badge

The model never states the legal conclusion. It routes the message to one of a
fixed set of situations and (in the older chat feature) phrases explanations;
the rights, the sections, the cases, the document and every verdict come from
curated data and deterministic code.
"""

import tempfile

import streamlit as st

from scenario_answer import build_scenario_answer, _case_library
from scenario_draft import build_document, document_pdf

st.set_page_config(page_title="Recourse", page_icon="⚖️", layout="centered")


# --------------------------------------------------------------------------
# warm the corpus once, at boot, so the first real query isn't slow
# --------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _warm():
    try:
        from semantic_retrieval import _load_corpus_embeddings
        _load_corpus_embeddings()
    except Exception:
        pass
    _case_library()
    return True


_warm()


# --------------------------------------------------------------------------
# style
# --------------------------------------------------------------------------
st.markdown("""
<style>
:root{
  --ink:#17242b; --muted:#5b6b73; --line:#e0ddd4; --paper:#faf8f3;
  --accent:#1f6f78; --accent-soft:#e7f0f0; --warn:#8a5a1a; --warn-soft:#f6ecdd;
  --ok:#1f6f78; --bad:#a8632a;
}
.stApp, .stMarkdown, p, li, .stTextArea textarea {
  font-family: "Iowan Old Style","Palatino Linotype","Book Antiqua",Georgia,serif;
}
.block-container { max-width: 780px; padding-top: 2rem; }
h1,h2,h3 { color: var(--ink) !important; letter-spacing:-.01em;
  font-family:"Iowan Old Style","Palatino Linotype",Georgia,serif !important; }
h1.r-title { font-size: 2.6rem !important; font-weight:700; margin:0 0 .1rem; }
.r-tag { color: var(--muted); font-size:1.08rem; margin:.1rem 0 1.4rem;
  font-style:italic; }
div.stButton > button { border-radius:8px; }
div.stButton > button[kind="primary"] { background:var(--accent); border-color:var(--accent); }
.r-card { background:var(--paper); border:1px solid var(--line); border-radius:10px;
          padding:1rem 1.15rem; margin:.6rem 0; }
.r-right { font-size:1.06rem; font-weight:600; color:var(--ink); margin-bottom:.35rem; }
.r-pill { display:inline-block; font-family:system-ui,sans-serif; font-size:.74rem;
          padding:.12rem .5rem; border-radius:999px; margin:.1rem .25rem .1rem 0; }
.r-sec  { background:var(--accent-soft); color:var(--accent); }
.r-ok   { background:var(--accent-soft); color:var(--ok); }
.r-bad  { background:var(--warn-soft); color:var(--bad); }
.r-neg  { background:var(--accent-soft); border-left:3px solid var(--accent);
          padding:.7rem .9rem; border-radius:4px; margin:.35rem 0; color:var(--ink); }
.r-flag { background:var(--warn-soft); border-left:3px solid var(--warn);
          padding:.7rem .9rem; border-radius:4px; margin:.35rem 0; }
.r-src  { font-family:system-ui,sans-serif; font-size:.8rem; color:var(--muted); }
.r-mono { font-family:ui-monospace,Menlo,Consolas,monospace; font-size:.82rem;
          white-space:pre-wrap; color:var(--ink); }
.r-foot { color:var(--muted); font-size:.85rem; font-family:system-ui,sans-serif; }
small.r-conf { color:var(--muted); font-family:system-ui,sans-serif; }
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# header + input
# --------------------------------------------------------------------------
st.markdown('<h1 class="r-title">Recourse</h1>', unsafe_allow_html=True)
st.markdown('<p class="r-tag">When the police come, you have more rights than you think '
            '&mdash; and the paper to use them.</p>', unsafe_allow_html=True)

st.write(
    "Tell Recourse what is happening, in your own words. It will explain what stage you "
    "are at, what the police can and cannot do, your rights **right now**, what to do in "
    "the next 24 hours — and draft a document you can hand to a lawyer or the court. "
    "Every section and every judgment it shows is checked four ways."
)

EXAMPLES = {
    "Held 70 days, no chargesheet":
        "the police have kept my brother 70 days and still haven't filed any chargesheet",
    "Sister arrested at night":
        "my sister was arrested last night around 9 pm, nobody told us why, and she's a nursing mother",
    "Police won't register my FIR":
        "the police won't register my complaint about the goods stolen from my shop",
}

if "text" not in st.session_state:
    st.session_state.text = ""

cols = st.columns(len(EXAMPLES))
for c, (label, val) in zip(cols, EXAMPLES.items()):
    if c.button(label, use_container_width=True):
        st.session_state.text = val

msg = st.text_area("Describe your situation", key="text", height=120,
                   label_visibility="collapsed",
                   placeholder="e.g. My brother was arrested four days ago and still hasn't been produced in court...")

go = st.button("Check my situation", type="primary")


# --------------------------------------------------------------------------
# render one right
# --------------------------------------------------------------------------
def render_right(i, r):
    with st.container():
        st.markdown(f'<div class="r-card"><div class="r-right">{i}. {r["plain_text"]}</div>',
                    unsafe_allow_html=True)
        pills = []
        if r.get("section_label"):
            pills.append(f'<span class="r-pill r-sec">{r["section_label"]}</span>')
        st.markdown("".join(pills), unsafe_allow_html=True)

        if r.get("statute_text"):
            with st.expander(f"What {r['section_label']} says"):
                st.markdown(f'<div class="r-mono">{r["statute_text"].strip()}</div>',
                            unsafe_allow_html=True)

        if r.get("case"):
            st.markdown(f'**{r["case"]}**'
                        + (f' &nbsp;<span class="r-src">{r["para_hint"]}</span>' if r.get("para_hint") else ""),
                        unsafe_allow_html=True)
            b = r.get("badge") or {}
            bp = []
            for chk in b.get("checks", []):
                cls = "r-ok" if chk["ok"] else "r-bad"
                mark = "✓" if chk["ok"] else "!"
                bp.append(f'<span class="r-pill {cls}">{mark} {chk["label"]}</span>')
            st.markdown("".join(bp), unsafe_allow_html=True)
            with st.expander("How this citation was checked"):
                for chk in b.get("checks", []):
                    st.markdown(f'**{"✓" if chk["ok"] else "⚠"} {chk["label"]}** '
                                f'&mdash; {chk["note"]}', unsafe_allow_html=True)
            ex = r.get("case_excerpt") or {}
            if ex.get("text"):
                with st.expander("In the court's words"):
                    st.markdown(f'<div class="r-mono">{ex["text"].strip()}</div>',
                                unsafe_allow_html=True)
                    src = []
                    if ex.get("citation"):
                        src.append(ex["citation"])
                    if ex.get("para"):
                        src.append(f'para/section: {ex["para"]}')
                    if ex.get("source_url"):
                        src.append(f'[read the judgment]({ex["source_url"]})')
                    if src:
                        st.markdown(f'<span class="r-src">{" &nbsp;·&nbsp; ".join(src)}</span>',
                                    unsafe_allow_html=True)
        elif r.get("case_ref"):
            st.markdown(f'<span class="r-src">Same authority as above &mdash; {r["case_ref"]}.</span>',
                        unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------
if go and msg.strip():
    with st.spinner("Working out your situation…"):
        answer = build_scenario_answer(msg)
    st.session_state.answer = answer
    st.session_state.answer_msg = msg

answer = st.session_state.get("answer")
if answer:
    msg = st.session_state.get("answer_msg", msg)
    st.divider()

    if answer["status"] != "answered":
        st.subheader("Recourse can't help with this one")
        st.write(answer["honest_note"])
        st.caption("Recourse covers arrest, FIR, police procedure and bail for the person a "
                   "case is happening to. It says so plainly rather than guessing.")
    else:
        st.markdown(f"### {answer['scenario_label']}")
        st.markdown(f'<small class="r-conf">Recognised as: {answer["target_id"]} '
                    f'&nbsp;·&nbsp; confidence {answer["confidence"]:.0%}</small>',
                    unsafe_allow_html=True)

        st.markdown("#### What this means")
        st.write(answer["stage_explainer"])

        st.markdown("#### Your rights right now")
        for i, r in enumerate(answer["rights"], 1):
            render_right(i, r)

        if answer["negations"]:
            st.markdown("#### What your situation does *not* raise")
            for n in answer["negations"]:
                st.markdown(f'<div class="r-neg">{n["line"]}</div>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### What the police can do")
            for x in answer["police_can"]:
                st.markdown(f"- {x}")
        with c2:
            st.markdown("#### What they cannot do")
            for x in answer["police_cannot"]:
                st.markdown(f"- {x}")

        st.markdown("#### Next 24 hours")
        for x in answer["next_24h"]:
            st.markdown(f"- {x}")

        if answer["red_flags"]:
            st.markdown("#### See a lawyer immediately if")
            for x in answer["red_flags"]:
                st.markdown(f'<div class="r-flag">{x}</div>', unsafe_allow_html=True)

        # ---- document ----
        st.markdown("#### Your document")
        doc = build_document(answer, msg)
        if doc["available"]:
            st.write(f"Recourse can prepare a first draft: **{doc['title'].title()}**.")
            if st.button("Prepare the draft"):
                st.session_state.doc = doc
            d = st.session_state.get("doc")
            if d and d.get("target") == doc["target"]:
                st.markdown(f'<div class="r-mono">{d["text"]}</div>', unsafe_allow_html=True)
                try:
                    path = tempfile.mkstemp(suffix=".pdf")[1]
                    document_pdf(d, path)
                    with open(path, "rb") as fh:
                        st.download_button("Download as PDF", fh.read(),
                                           file_name="recourse-draft.pdf", mime="application/pdf")
                except Exception:
                    st.download_button("Download as text", d["text"].encode("utf-8"),
                                       file_name="recourse-draft.txt", mime="text/plain")
        else:
            st.caption("No draft document for this situation yet.")

    # ---- how it works ----
    st.divider()
    with st.expander("How Recourse works — and why it won't invent a case"):
        st.markdown(
            "- The AI model has **three jobs only**: work out which situation your message "
            "describes, and phrase explanations in plain words. It is **never allowed to "
            "state the legal conclusion**.\n"
            "- The rights, the section numbers, the cases and the document all come from a "
            "**hand-checked library and fixed rules** — not from the model.\n"
            "- Every case is checked four ways: **it exists** in our library, it is **still "
            "good law**, the passage is **quoted verbatim** from the judgment, and it was "
            "**mapped to your right by a person, not a similarity score**.\n"
            "- Where something can't be verified, Recourse says so — it never shows a "
            "false green tick."
        )
    st.markdown(
        '<p class="r-foot">Recourse gives legal information and a starting-point document, '
        'not legal advice. It cannot see anything beyond what you type. For a real case, '
        'take this to a lawyer or your nearest District Legal Services Authority, which '
        'provides help free.</p>', unsafe_allow_html=True)
