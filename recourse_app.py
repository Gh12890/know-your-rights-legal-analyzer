"""
recourse_app.py  --  the single-flow public app for the ILTN Vibeathon.

One input box. One answer, built for the situation the person is in.

Thin UI over the engine:
  scenario_router.route_situation      -> which situation (LLM classify only)
  scenario_answer.build_scenario_answer -> the tailored answer (pure Python)
  scenario_draft.build_document        -> the first-draft document (pure Python)
  scenario_verification                -> the four-way citation seal

The model never states the legal conclusion. It routes the message to one of a
fixed set of situations and phrases explanations in plain words; the rights,
sections, cases, document and every verdict come from curated data and
deterministic code.
"""

import html as _html
import tempfile

import streamlit as st

from scenario_answer import build_scenario_answer, _case_library
from scenario_draft import build_document, document_pdf

st.set_page_config(page_title="Recourse — know your rights when it matters most",
                   page_icon="⚖️", layout="centered")


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


# ==========================================================================
# DESIGN SYSTEM
#
# Concept: "the steady hand" — the visual language of a well-prepared legal
# document meeting the warmth of someone who has your back. Not a SaaS
# dashboard, not a government portal, not a law-firm brochure.
#
# Colour   ink #1b2b2e · paper #f7f3ea · surface #fffdf7 · rule #e4dccb
#          seal (petrol/teal = "verified, safe") #146b63 · amber (caution,
#          not alarm) #a15c1f
# Type     Fraunces (display serif, the wordmark + heads) · Newsreader
#          (reading serif, explanations) · IBM Plex Sans / Mono (interface,
#          labels, the verification seal)
# Layout   single reading column ~720px on warm ivory; a 3px seal strip at
#          the very top like the band on official stationery; editorial
#          rhythm with uppercase eyebrow labels and generous space.
# ==========================================================================
st.html("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Spectral:wght@400;500;600;700&family=Newsreader:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
@import url('https://fonts.googleapis.com/css2?family=Spectral:wght@400;500;600;700&family=Newsreader:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root{
  --ink:#1b2b2e; --ink-soft:#42565a; --muted:#6a7b7e;
  --paper:#f7f3ea; --surface:#fffdf7; --rule:#e4dccb;
  --seal:#146b63; --seal-deep:#0f544d; --seal-tint:#e2efec;
  --amber:#a15c1f; --amber-tint:#f5e9d8;
}

/* hide all Streamlit chrome */
#MainMenu, header[data-testid="stHeader"], footer,
[data-testid="stToolbar"], [data-testid="stStatusWidget"],
[data-testid="stDecoration"], .stDeployButton { display:none !important; }

html, body, [data-testid="stAppViewContainer"]{ background:var(--paper) !important; }
.stApp{ background:var(--paper); }

/* thin stationery strip at the very top */
[data-testid="stAppViewContainer"]::before{
  content:""; position:fixed; top:0; left:0; right:0; height:3px;
  background:var(--seal); z-index:999;
}

.block-container{ max-width:730px; padding-top:3.2rem; padding-bottom:4rem; }

/* base type */
.stApp, .stMarkdown, p, li, label, .stTextArea textarea{
  font-family:"Newsreader",Georgia,"Times New Roman",serif;
  color:var(--ink); font-size:1.06rem; line-height:1.6;
}
p{ color:var(--ink-soft); }

h1,h2,h3,h4{
  font-family:"Spectral","Newsreader",Georgia,serif !important;
  color:var(--ink) !important; font-weight:600; letter-spacing:-.012em;
  text-wrap:balance;
}
h2{ font-size:1.7rem !important; margin:2.2rem 0 .4rem !important; }
h3{ font-size:1.32rem !important; margin:1.9rem 0 .5rem !important; }
h4{ font-size:1.06rem !important; font-weight:600 !important;
    margin:1.5rem 0 .4rem !important; }

/* ---------- hero ---------- */
.r-eyebrow{
  font-family:"IBM Plex Sans",system-ui,sans-serif; font-size:.72rem;
  font-weight:600; letter-spacing:.16em; text-transform:uppercase;
  color:var(--seal); margin-bottom:.5rem;
}
.r-wordmark{
  font-family:"Spectral","Newsreader",Georgia,serif !important;
  font-weight:600 !important; font-size:3.5rem !important;
  line-height:1.02 !important; color:var(--ink) !important; margin:0 !important;
  font-optical-sizing:auto; letter-spacing:-.02em;
}
.r-rule{ border:0; border-top:1px solid var(--rule); margin:1.1rem 0; }
.r-rule-seal{ border:0; border-top:2px solid var(--seal); width:44px; margin:.9rem 0 1.1rem; }
.r-tag{
  font-family:"Newsreader",serif; font-style:italic; font-size:1.34rem; line-height:1.42;
  color:var(--ink-soft); margin:.2rem 0 1.1rem; text-wrap:balance;
}
.r-lead{ font-size:1.09rem; color:var(--ink-soft); margin-bottom:.4rem; }
.r-who{
  font-family:"IBM Plex Sans",system-ui,sans-serif; font-size:.86rem;
  color:var(--muted); margin:.3rem 0 1.6rem;
}

/* ---------- pillars ---------- */
.r-pillars{ display:flex; gap:0; border:1px solid var(--rule);
  border-radius:10px; overflow:hidden; margin:1.4rem 0 2rem; background:var(--surface); }
.r-pillar{ flex:1; padding:.8rem .95rem; border-right:1px solid var(--rule); }
.r-pillar:last-child{ border-right:0; }
.r-pillar b{ font-family:"IBM Plex Sans",sans-serif; font-size:.82rem; font-weight:600;
  color:var(--ink); display:block; }
.r-pillar span{ font-family:"IBM Plex Sans",sans-serif; font-size:.76rem; color:var(--muted); }

/* ---------- eyebrow label above sections ---------- */
.r-label{
  font-family:"IBM Plex Sans",sans-serif; font-size:.72rem; font-weight:600;
  letter-spacing:.14em; text-transform:uppercase; color:var(--seal);
  margin:1.8rem 0 .6rem;
}

/* ---------- starter buttons as cards ---------- */
div[data-testid="column"] div.stButton > button{
  width:100%; text-align:left; white-space:normal; height:100%;
  background:var(--surface); border:1px solid var(--rule); border-radius:10px;
  padding:.85rem .95rem; color:var(--ink);
  font-family:"IBM Plex Sans",sans-serif; font-size:.92rem; font-weight:500;
  line-height:1.35; transition:transform .12s ease, border-color .12s ease, box-shadow .12s ease;
}
div[data-testid="column"] div.stButton > button:hover{
  border-color:var(--seal); transform:translateY(-2px);
  box-shadow:0 6px 18px -10px rgba(20,107,99,.35);
}
div[data-testid="column"] div.stButton > button p{ font-size:.92rem; color:var(--ink); }

/* ---------- text area ---------- */
.stTextArea textarea{
  background:var(--surface) !important; border:1px solid var(--rule) !important;
  border-radius:10px !important; color:var(--ink) !important;
  font-family:"Newsreader",serif !important; font-size:1.04rem !important;
  padding:.9rem 1rem !important;
}
.stTextArea textarea:focus{ border-color:var(--seal) !important;
  box-shadow:0 0 0 3px var(--seal-tint) !important; }

/* ---------- primary button (the one clear action) ---------- */
button[kind="primary"], button[kind="primaryFormSubmit"]{
  background:var(--seal) !important; border:1px solid var(--seal-deep) !important;
  color:#fff !important;
  font-family:"IBM Plex Sans",sans-serif !important; font-weight:600 !important;
  font-size:1rem !important; border-radius:9px !important;
  padding:.7rem 1.6rem !important; letter-spacing:.015em;
  width:100%; margin-top:.9rem;
  box-shadow:0 8px 20px -12px rgba(15,84,77,.55);
}
button[kind="primary"]:hover, button[kind="primaryFormSubmit"]:hover{
  background:var(--seal-deep) !important; border-color:var(--seal-deep) !important;
}
button[kind="primary"] p, button[kind="primaryFormSubmit"] p{
  color:#fff !important; font-size:1rem !important; font-weight:600 !important; }
[data-testid="stForm"]{ border:0 !important; padding:0 !important; }
div.stButton > button[kind="secondary"]{
  background:transparent; border:1px solid var(--seal); color:var(--seal);
  font-family:"IBM Plex Sans",sans-serif; font-weight:500; border-radius:8px;
}

/* ---------- answer: scenario header ---------- */
.r-conf{
  font-family:"IBM Plex Sans",sans-serif; font-size:.78rem; color:var(--muted);
  letter-spacing:.02em;
}
.r-means{ font-size:1.12rem; line-height:1.62; color:var(--ink-soft); }

/* ---------- a right ---------- */
.r-card{
  background:var(--surface); border:1px solid var(--rule); border-radius:12px;
  padding:1.05rem 1.2rem; margin:.7rem 0;
}
.r-rnum{
  display:inline-flex; align-items:center; justify-content:center;
  width:1.55rem; height:1.55rem; border-radius:50%;
  background:var(--seal-tint); color:var(--seal-deep);
  font-family:"IBM Plex Sans",sans-serif; font-weight:600; font-size:.82rem;
  margin-right:.55rem; flex:none;
}
.r-rtext{ font-family:"Newsreader",serif; font-weight:500; font-size:1.08rem;
  line-height:1.5; color:var(--ink); }
.r-sectag{
  display:inline-block; font-family:"IBM Plex Mono",monospace; font-size:.76rem;
  background:var(--seal-tint); color:var(--seal-deep);
  padding:.16rem .5rem; border-radius:5px; margin:.55rem .4rem .1rem 0;
}
.r-case{ font-family:"Newsreader",serif; font-weight:600; font-size:1rem;
  color:var(--ink); margin-top:.7rem; }
.r-casehint{ font-family:"IBM Plex Sans",sans-serif; font-size:.78rem; color:var(--muted); }

/* ---------- the verification seal (signature element) ---------- */
.r-seal{
  border:1px solid var(--seal); border-radius:9px; background:var(--seal-tint);
  padding:.5rem .7rem; margin:.55rem 0 .2rem;
  font-family:"IBM Plex Mono",monospace;
}
.r-seal .r-seal-head{
  font-size:.68rem; font-weight:500; letter-spacing:.16em; text-transform:uppercase;
  color:var(--seal-deep); margin-bottom:.25rem;
}
.r-seal .r-seal-row{ display:flex; flex-wrap:wrap; gap:.35rem .9rem; }
.r-seal .r-chk{ font-size:.8rem; color:var(--seal-deep); white-space:nowrap; }
.r-seal .r-chk.bad{ color:var(--amber); }

/* ---------- insets ---------- */
.r-neg{
  background:var(--seal-tint); border-left:3px solid var(--seal);
  padding:.75rem 1rem; border-radius:0 6px 6px 0; margin:.4rem 0; color:var(--ink);
  font-family:"Newsreader",serif;
}
.r-flag{
  background:var(--amber-tint); border-left:3px solid var(--amber);
  padding:.75rem 1rem; border-radius:0 6px 6px 0; margin:.4rem 0; color:var(--ink);
  font-family:"Newsreader",serif;
}
.r-flag::before{ content:"\\26A0  "; color:var(--amber); font-weight:700; }

.r-do{ display:flex; gap:.6rem; margin:.45rem 0; align-items:flex-start; }
.r-do .r-dot{ color:var(--seal); font-weight:700; flex:none; }
.r-do.cant .r-dot{ color:var(--amber); }

/* ---------- monospace excerpts ---------- */
.r-mono{
  font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  font-size:.82rem; line-height:1.55; white-space:pre-wrap; color:var(--ink-soft);
}
.r-src{ font-family:"IBM Plex Sans",sans-serif; font-size:.8rem; color:var(--muted); }

/* ---------- expanders ---------- */
[data-testid="stExpander"]{ border:1px solid var(--rule) !important;
  border-radius:8px !important; background:var(--surface) !important; margin:.35rem 0 !important; }
[data-testid="stExpander"] summary{ font-family:"IBM Plex Sans",sans-serif !important;
  font-size:.85rem !important; color:var(--ink-soft) !important; }
[data-testid="stExpander"] summary:hover{ color:var(--seal) !important; }

/* ---------- out of scope ---------- */
.r-oos{
  border:1px solid var(--rule); border-left:3px solid var(--amber);
  background:var(--surface); border-radius:0 8px 8px 0; padding:1rem 1.2rem; margin:.6rem 0;
}

/* ---------- footer ---------- */
.r-foot{ font-family:"IBM Plex Sans",sans-serif; font-size:.83rem; color:var(--muted);
  line-height:1.55; }
a, a:visited{ color:var(--seal); }

@media (max-width:640px){
  .r-wordmark{ font-size:2.6rem; }
  .r-pillars{ flex-direction:column; }
  .r-pillar{ border-right:0; border-bottom:1px solid var(--rule); }
  .r-pillar:last-child{ border-bottom:0; }
}
@media (prefers-reduced-motion:reduce){
  div[data-testid="column"] div.stButton > button{ transition:none; }
  div[data-testid="column"] div.stButton > button:hover{ transform:none; }
}
</style>
""")


def esc(s):
    return _html.escape(str(s or ""))


# --------------------------------------------------------------------------
# hero
# --------------------------------------------------------------------------
st.html("""
<div class="r-eyebrow">Access to justice &nbsp;·&nbsp; India</div>
<div class="r-wordmark">Recourse</div>
<hr class="r-rule-seal">
<div class="r-tag">An arrest. An FIR. A night in custody. You have more rights
than you know &mdash; and the paper to use them.</div>
<div class="r-lead">Tell Recourse what is happening, in your own words. It works out
what stage you are at, what the police can and cannot do, your rights <b>right
now</b>, what to do in the next 24 hours &mdash; and drafts a document you can
hand to a lawyer or the court.</div>
<div class="r-who">For the person a case is happening to, and their family &mdash;
not for law firms. Legal information and a first draft, not legal advice.</div>

<div class="r-pillars">
  <div class="r-pillar"><b>Your rights, right now</b><span>only the ones your facts raise</span></div>
  <div class="r-pillar"><b>In your own words</b><span>no legal language needed</span></div>
  <div class="r-pillar"><b>Checked four ways</b><span>every section, every judgment</span></div>
</div>
""")


# --------------------------------------------------------------------------
# starters + input
# --------------------------------------------------------------------------
EXAMPLES = {
    "Held 70 days, still no chargesheet":
        "the police have kept my brother 70 days and still haven't filed any chargesheet",
    "My sister was arrested at night":
        "my sister was arrested last night around 9 pm, nobody told us why, and she's a nursing mother",
    "Police won't register my FIR":
        "the police won't register my complaint about the goods stolen from my shop",
}

if "text" not in st.session_state:
    st.session_state.text = ""


def _reset_answer():
    """Drop the previous answer + draft so a new question never shows a
    stale reply."""
    st.session_state.pop("answer", None)
    st.session_state.pop("answer_msg", None)
    st.session_state.pop("doc", None)


st.html('<div class="r-label">Start with a situation</div>')
cols = st.columns(len(EXAMPLES))
for c, (label, val) in zip(cols, EXAMPLES.items()):
    if c.button(label, use_container_width=True, key=f"ex_{label[:10]}"):
        st.session_state.text = val
        _reset_answer()

st.html('<div class="r-label">&hellip; or describe your own</div>')

# A form so the textarea's current value and the submit click are processed
# TOGETHER in one rerun -- without it, the first click after typing only
# commits the text and the previous answer keeps showing.
with st.form("situation_form", border=False, clear_on_submit=False):
    msg = st.text_area("Describe your situation", key="text", height=120,
                       label_visibility="collapsed",
                       placeholder="e.g. My brother was arrested four days ago and still hasn't been produced in court…")
    go = st.form_submit_button("Check my situation  →", type="primary",
                               use_container_width=True)


# --------------------------------------------------------------------------
# footer: how it works + about + disclaimer  (shown on every view)
# --------------------------------------------------------------------------
def _footer():
    st.html('<hr class="r-rule">')

    with st.expander("How Recourse works — and why it won't invent a case"):
        st.markdown(
            "- The AI model has **three jobs only**: work out which situation your message "
            "describes, and phrase explanations in plain words. It is **never allowed to "
            "state the legal conclusion**.\n"
            "- The rights, the section numbers, the cases and the document all come from a "
            "**hand-checked library and fixed rules** — not from the model.\n"
            "- Every case is checked four ways: **it exists** in the checked library, it is "
            "**still good law**, the passage is **quoted verbatim** from the judgment, and "
            "it was **mapped to your right by a person, not a similarity score**.\n"
            "- Where a check can't be satisfied, Recourse shows an amber note — it never "
            "shows a false green tick. Outside its scope, it says so plainly."
        )

    with st.expander("About Recourse"):
        st.markdown(
            "**Who it is for.** The person a criminal case is happening to, and their "
            "family — at the moment it is happening. Not law firms.\n\n"
            "**Why it exists.** More than three-quarters of India's prison population are "
            "undertrials — people not convicted of anything. When the police come, most "
            "people and their families have never heard that an arrest must come with "
            "written grounds, that a woman cannot ordinarily be arrested after sunset, or "
            "that a missed chargesheet deadline makes bail a matter of right. Rights that "
            "exist on paper are lost in the first 24 hours because nobody in the room "
            "knows them.\n\n"
            "**What it does.** Takes a plain-language description, works out the *situation* "
            "(who you are, what stage you are at, what specific things have happened) and "
            "returns only the rights those facts raise — with the section, a real "
            "judgment, and a first-draft document you can hand to a lawyer, a Legal "
            "Services Authority, or the Magistrate.\n\n"
            "**What it is not.** Not legal advice. It cannot see anything beyond what you "
            "type. It is orientation and a starting point — the next step is always a "
            "lawyer. Your nearest **District Legal Services Authority** provides that help "
            "free.\n\n"
            "**How it was built.** The verification engine — checked retrieval, the "
            "IPC-to-BNS mapping, the rule that the model never states a legal conclusion — "
            "was built over several months. The access-to-justice layer on top (the "
            "situation router, the plain-language rights, the document generator, this "
            "interface) was built for the ILTN Vibeathon."
        )

    st.markdown(
        '<p class="r-foot">Recourse gives legal information and a starting-point document, '
        'not legal advice. It cannot see anything beyond what you type. For a real case, '
        'take this to a lawyer or your nearest District Legal Services Authority, which '
        'provides that help free.</p>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# render one right
# --------------------------------------------------------------------------
def _seal_html(badge):
    checks = badge.get("checks", []) if badge else []
    if not checks:
        return ""
    rows = "".join(
        f'<span class="r-chk{"" if c["ok"] else " bad"}">'
        f'{"&#10003;" if c["ok"] else "!"} {esc(c["label"])}</span>'
        for c in checks
    )
    return (f'<div class="r-seal"><div class="r-seal-head">Checked</div>'
            f'<div class="r-seal-row">{rows}</div></div>')


def render_right(i, r):
    st.markdown(
        f'<div class="r-card">'
        f'<div><span class="r-rnum">{i}</span>'
        f'<span class="r-rtext">{esc(r["plain_text"])}</span></div>',
        unsafe_allow_html=True,
    )
    if r.get("section_label"):
        st.markdown(f'<span class="r-sectag">{esc(r["section_label"])}</span>',
                    unsafe_allow_html=True)

    if r.get("statute_text"):
        with st.expander(f"What {r['section_label']} says"):
            st.markdown(f'<div class="r-mono">{esc(r["statute_text"].strip())}</div>',
                        unsafe_allow_html=True)

    if r.get("case"):
        hint = f' <span class="r-casehint">— {esc(r["para_hint"])}</span>' if r.get("para_hint") else ""
        st.markdown(f'<div class="r-case">{esc(r["case"])}{hint}</div>', unsafe_allow_html=True)
        st.markdown(_seal_html(r.get("badge") or {}), unsafe_allow_html=True)

        with st.expander("How this citation was checked"):
            for chk in (r.get("badge") or {}).get("checks", []):
                st.markdown(f'**{"&#10003;" if chk["ok"] else "&#9888;"} {chk["label"]}** '
                            f'&mdash; {chk["note"]}', unsafe_allow_html=True)

        ex = r.get("case_excerpt") or {}
        if ex.get("text"):
            with st.expander("In the court's words"):
                st.markdown(f'<div class="r-mono">{esc(ex["text"].strip())}</div>',
                            unsafe_allow_html=True)
                src = []
                if ex.get("citation"):
                    src.append(esc(ex["citation"]))
                if ex.get("para"):
                    src.append(f'para/section: {esc(ex["para"])}')
                if ex.get("source_url"):
                    src.append(f'<a href="{esc(ex["source_url"])}" target="_blank">read the judgment</a>')
                if src:
                    st.markdown(f'<span class="r-src">{" &nbsp;·&nbsp; ".join(src)}</span>',
                                unsafe_allow_html=True)
    elif r.get("case_ref"):
        st.markdown(f'<div class="r-casehint">Same authority as above — {esc(r["case_ref"])}.</div>',
                    unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------
if go and msg.strip():
    st.session_state.pop("doc", None)          # never carry a stale draft over
    with st.spinner("Working out your situation…"):
        answer = build_scenario_answer(msg)
    st.session_state.answer = answer
    st.session_state.answer_msg = msg

answer = st.session_state.get("answer")
# only show an answer that matches what's currently in the box
if answer and st.session_state.get("answer_msg", "").strip() == (msg or "").strip():
    msg = st.session_state.get("answer_msg", msg)
    st.html('<hr class="r-rule">')

    if answer["status"] != "answered":
        st.markdown('<div class="r-label">Out of scope</div>', unsafe_allow_html=True)
        st.markdown("## Recourse can't help with this one")
        st.markdown(f'<div class="r-oos">{esc(answer["honest_note"])}</div>', unsafe_allow_html=True)
        st.markdown('<p class="r-foot">Recourse covers arrest, FIR, police procedure and '
                    'bail for the person a case is happening to. It says so plainly rather '
                    'than guessing.</p>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="r-label">Your situation</div>', unsafe_allow_html=True)
        st.markdown(f"## {esc(answer['scenario_label'])}")
        st.markdown(f'<p class="r-conf">Recognised as {esc(answer["target_id"])} '
                    f'&nbsp;·&nbsp; confidence {answer["confidence"]:.0%}</p>',
                    unsafe_allow_html=True)

        st.markdown("### What this means")
        st.markdown(f'<p class="r-means">{esc(answer["stage_explainer"])}</p>',
                    unsafe_allow_html=True)

        st.markdown('<div class="r-label">Your rights right now</div>', unsafe_allow_html=True)
        for i, r in enumerate(answer["rights"], 1):
            render_right(i, r)

        if answer["negations"]:
            st.markdown("### What your situation does *not* raise")
            for n in answer["negations"]:
                st.markdown(f'<div class="r-neg">{esc(n["line"])}</div>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### The police can")
            for x in answer["police_can"]:
                st.markdown(f'<div class="r-do"><span class="r-dot">&#10003;</span>'
                            f'<span>{esc(x)}</span></div>', unsafe_allow_html=True)
        with c2:
            st.markdown("### They cannot")
            for x in answer["police_cannot"]:
                st.markdown(f'<div class="r-do cant"><span class="r-dot">&#10007;</span>'
                            f'<span>{esc(x)}</span></div>', unsafe_allow_html=True)

        st.markdown("### Next 24 hours")
        for n, x in enumerate(answer["next_24h"], 1):
            st.markdown(f'<div class="r-do"><span class="r-dot">{n}</span>'
                        f'<span>{esc(x)}</span></div>', unsafe_allow_html=True)

        if answer["red_flags"]:
            st.markdown("### See a lawyer immediately if")
            for x in answer["red_flags"]:
                st.markdown(f'<div class="r-flag">{esc(x)}</div>', unsafe_allow_html=True)

        # ---- document ----
        st.markdown('<div class="r-label">Your document</div>', unsafe_allow_html=True)
        doc = build_document(answer, msg)
        if doc["available"]:
            st.markdown(f'Recourse can prepare a first draft: **{doc["title"].title()}**.')
            if st.button("Prepare the draft", type="secondary"):
                st.session_state.doc = doc
            d = st.session_state.get("doc")
            if d and d.get("target") == doc["target"]:
                st.markdown(f'<div class="r-mono">{esc(d["text"])}</div>', unsafe_allow_html=True)
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
            st.markdown('<p class="r-foot">No draft document for this situation yet.</p>',
                        unsafe_allow_html=True)

_footer()
