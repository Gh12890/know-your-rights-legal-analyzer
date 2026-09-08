"""
recourse_app.py  --  the single-flow public app for the ILTN Vibeathon.

One input box. One answer, grounded in the law and real judgments.

Thin UI over the free-text engine:
  chat_assistant.answer_question  -> scope check, checked retrieval (BNS/BNSS
                                     + judgments), offence-keyword anchors,
                                     plain-language grounded answer with the
                                     ungrounded-statement guards
  recourse_upload.check_arrest_document -> deterministic compliance check on an
                                     uploaded arrest memo / FIR / remand order

The model never states a verdict on the person's case. It only explains what
the retrieved sections and judgments say, working from a fixed library -- never
its own knowledge -- and its answer is screened for statements that library
does not support before anyone sees it.
"""

import html as _html

import streamlit as st

from chat_assistant import answer_question
from recourse_upload import extract_text, check_arrest_document

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

/* ---------- document compliance check ---------- */
.r-checkrow{ border:1px solid var(--rule); border-radius:10px; background:var(--surface);
  padding:.8rem 1rem; margin:.5rem 0; }
.r-checkrow .r-chead{ font-family:"Newsreader",serif; font-weight:600; font-size:1rem;
  color:var(--ink); }
.r-verdict{ display:inline-block; font-family:"IBM Plex Sans",sans-serif; font-size:.74rem;
  font-weight:600; letter-spacing:.02em; padding:.14rem .55rem; border-radius:999px;
  margin:.35rem 0; }
.r-verdict.ok{ background:var(--seal-tint); color:var(--seal-deep); }
.r-verdict.bad{ background:#efd9c6; color:#8a4a12; }
.r-verdict.warn{ background:var(--amber-tint); color:var(--amber); }
.r-verdict.unknown{ background:#e9e4d7; color:#6a6250; }
.r-verdict.na{ background:#eceae2; color:#8a8676; }
.r-checkrow .r-cexp{ font-family:"Newsreader",serif; font-size:.92rem; color:var(--ink-soft);
  line-height:1.5; }
.r-summ{ border-left:3px solid var(--seal); background:var(--seal-tint);
  padding:.75rem 1rem; border-radius:0 6px 6px 0; margin:.6rem 0;
  font-family:"Newsreader",serif; color:var(--ink); }
.r-summ.hasdefect{ border-left-color:var(--amber); background:var(--amber-tint); }
.r-concord{ font-family:"IBM Plex Sans",sans-serif; font-size:.85rem; color:var(--ink-soft);
  border:1px solid var(--rule); border-radius:8px; padding:.7rem .9rem; margin:.5rem 0;
  background:var(--surface); }
.r-concord code{ font-family:"IBM Plex Mono",monospace; font-size:.82rem;
  background:var(--seal-tint); color:var(--seal-deep); padding:.05rem .3rem; border-radius:4px; }

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
than you know &mdash; and the law to back them.</div>
<div class="r-lead">Tell Recourse what is happening, in your own words. It works out
what you can do <b>right now</b>, the exact sections of the law that apply, and
what the real judgments say &mdash; then points you to the papers to check.</div>
<div class="r-who">For the person a case is happening to, and their family &mdash;
not for law firms. Legal information, not legal advice.</div>

<div class="r-pillars">
  <div class="r-pillar"><b>What to do right now</b><span>concrete first steps</span></div>
  <div class="r-pillar"><b>In your own words</b><span>no legal language needed</span></div>
  <div class="r-pillar"><b>Traced to the source</b><span>every section and judgment shown</span></div>
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
    """Drop the previous answer + draft + doc-check so a new question never
    shows a stale reply."""
    for k in ("answer", "answer_msg", "doc", "doc_check", "doc_check_sig"):
        st.session_state.pop(k, None)


st.html('<div class="r-label">Start with a situation</div>')
cols = st.columns(len(EXAMPLES))
for c, (label, val) in zip(cols, EXAMPLES.items()):
    if c.button(label, use_container_width=True, key=f"ex_{label[:10]}"):
        st.session_state.text = val
        _reset_answer()
        st.session_state._autorun = True

st.html('<div class="r-label">&hellip; or describe your own</div>')

# A form so the textarea's current value and the submit click are processed
# TOGETHER in one rerun -- without it, the first click after typing only
# commits the text and the previous answer keeps showing.
with st.form("situation_form", border=False, clear_on_submit=False):
    msg = st.text_area("Describe your situation", key="text", height=120,
                       label_visibility="collapsed",
                       placeholder="e.g. My brother was arrested four days ago and still hasn't been produced in court…") or ""
    go = st.form_submit_button("Check my situation  →", type="primary",
                               use_container_width=True)


# --------------------------------------------------------------------------
# footer: how it works + about + disclaimer  (shown on every view)
# --------------------------------------------------------------------------
def _footer():
    st.html('<hr class="r-rule">')

    with st.expander("How Recourse works — and why it won't invent a case"):
        st.markdown(
            "- You describe the situation in plain words. Recourse works from a **fixed "
            "library** — the Bharatiya Nyaya Sanhita, the BNSS, and real Supreme Court and "
            "High Court judgments — **never from the model's own knowledge**.\n"
            "- It retrieves the sections and judgments that match, and for a common "
            "accusation named in plain words (theft, cheating, hurt, forgery, a bounced "
            "cheque) it **anchors the exact offence** so the answer names the right "
            "section, not a guessed one.\n"
            "- The plain-language answer is then **screened for anything the library "
            "doesn't support** — a section number it never retrieved, a wrong "
            "cognisable/bailable claim, a case stretched further than it holds — and that "
            "is caught before you see it.\n"
            "- Where a section has been **renumbered** from the old codes, or a judgment's "
            "standing is **uncertain**, Recourse says so. Outside its scope — a pure civil "
            "dispute, another area of law — it says so plainly rather than guessing.\n"
            "- The model **never states a verdict on your case**. It explains what the "
            "retrieved law says; what it means for you is for a lawyer."
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
            "**What it does.** Takes a plain-language description and returns a short "
            "**what-to-do-right-now**, the **exact sections** that apply, what the **real "
            "judgments** say, and — where an arrest has happened — a check of the actual "
            "arrest papers against the safeguards.\n\n"
            "**What it is not.** Not legal advice. It cannot see anything beyond what you "
            "type. It is orientation and a starting point — the next step is always a "
            "lawyer. Your nearest **District Legal Services Authority** provides that help "
            "free.\n\n"
            "**How it was built.** The engine — checked retrieval, the IPC-to-BNS mapping, "
            "the offence anchors, the rule that the model never states a verdict — was "
            "built over several months. The access-to-justice layer on top (this "
            "interface, the plain-language framing, the paper check) was built for the "
            "ILTN Vibeathon."
        )

    st.markdown(
        '<p class="r-foot">Recourse gives legal information, not legal advice. It cannot '
        'see anything beyond what you type. For a real case, take this to a lawyer or your '
        'nearest District Legal Services Authority, which provides that help free.</p>',
        unsafe_allow_html=True)


# --------------------------------------------------------------------------
# render the grounded answer + its sources
# --------------------------------------------------------------------------
import re as _re

_PAGE_CRUFT = _re.compile(
    r"^\s*(?:\x0c\s*)?(?:page\s+\d+\s+of\s+\d+|\d{1,4}|\d+\s*\|\s*p\s*a\s*g\s*e)\s*$",
    _re.I,
)


def _clean_excerpt(text: str) -> str:
    """Strip the OCR/print cruft that rides along in the judgment chunk
    text -- form-feeds, bare page numbers, 'Page 8 of 25' footers, and
    long runs of blank lines -- so the 'Read the source' excerpt reads
    like prose, not a scanned PDF. Display-only; the stored chunk text is
    untouched."""
    if not text:
        return ""
    out = []
    for line in text.replace("\x0c", "\n").split("\n"):
        if _PAGE_CRUFT.match(line):
            continue
        out.append(line.rstrip())
    cleaned = "\n".join(out)
    cleaned = _re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


_CASE_GENERIC_PARTY = (
    "state of", "state ", "union of india", "union of", "govt", "government",
    "central bureau of investigation", "cbi", "directorate of", "intelligence officer",
    "commissioner of", "n.c.t", "nct", "u.p.", "govt. of", "republic of",
)


def _case_is_named(m, reply_lc):
    """True if the answer prose actually refers to this case by name.
    Checks the distinctive party -- usually the first ('M. Ravindran',
    'D.K. Basu'), but the SECOND when the first is a generic 'State of X'
    / 'Union of India' ('State of Haryana v Bhajan Lal' -> 'Bhajan
    Lal')."""
    cn = (m.get("case_name") or "").lower()
    if not cn:
        return False
    parts = [p.strip() for p in cn.split(" v ") if p.strip()]
    for p in parts:
        if any(p.startswith(g) for g in _CASE_GENERIC_PARTY):
            continue
        # trim a trailing "(2026)" / ", directorate of revenue intelligence"
        core = p.split("(")[0].split(",")[0].strip()
        if len(core) >= 4 and core in reply_lc:
            return True
    return False


def _sources_worth_showing(matches, reply_text, cap=16):
    """The 'Read the source' JUDGMENT list.

    If the answer NAMES any case, show ONLY those -- every case it names
    (grounding: the prompt forbids naming a case with no excerpt) and
    nothing else. The keyword doctrine anchors deliberately over-fire
    (every "arrested" pulls Prabir/Arnesh/Satender); when the model then
    builds the answer around just the 1-3 on point, "Read the source"
    must mirror that choice, not dump the five unused anchors next to it
    -- confirmed 2026-09-08 live test (a default-bail answer showed
    Prabir, Arnesh, Satender, Md. Ibrahim and Sri Manjunath, none of
    which the answer used).

    Only when the answer names NO case at all (rare) fall back to the
    curated anchors, then the rest by score.

    CALLER PASSES JUDGMENT MATCHES ONLY -- curated statute-override
    entries (case_name=None) used to eat cap slots here."""
    reply_lc = (reply_text or "").lower()

    def _label(m):
        return str(m.get("section_number") or m.get("paragraph_number") or "")

    pool = matches or []
    named = [m for m in pool if _case_is_named(m, reply_lc)]
    if named:
        pool = named
    else:
        # nothing named -> curated anchors first, then score order
        pool = sorted(
            pool,
            key=lambda m: 0 if str(m.get("source") or "").startswith("curated") else 1,
        )

    picked, seen = [], set()
    for m in pool:
        key = (m.get("case_name") or "BNS/BNSS", _label(m))
        if key in seen:
            continue
        seen.add(key)
        picked.append(m)
        if len(picked) >= cap:
            break
    return picked


def _render_currency_caveat(m):
    """If a cited judgment carries a legal-currency note (Project 2), show it."""
    if not m.get("case_name"):
        return
    try:
        from citation_currency import get_citation_currency_for_case_name
        for rec in get_citation_currency_for_case_name(m["case_name"]):
            note = rec.get("plain_note") or rec.get("note") or rec.get("summary")
            if note:
                st.markdown(f'<div class="r-concord">{esc(note)}</div>', unsafe_allow_html=True)
    except Exception:
        pass


def render_answer(result: dict):
    """Render one chat_assistant.answer_question() result in the Recourse
    style. Every branch is honest: a real grounded answer, an out-of-scope
    note, or a technical-trouble note -- never a silent guess."""
    state = result.get("state")

    if state in ("single_match", "conflicting_matches"):
        st.markdown('<div class="r-label">Your situation</div>', unsafe_allow_html=True)
        if state == "conflicting_matches":
            st.markdown('<p class="r-conf">More than one provision applies and they don\'t '
                        'all say the same thing &mdash; Recourse lays out each rather than '
                        'picking one for you.</p>', unsafe_allow_html=True)
        reply = result.get("response_text") or ""
        if reply:
            st.markdown(reply)
        else:
            m0 = (result.get("matches") or [{}])[0]
            st.markdown("Here is what the law says on this:\n\n> "
                        + esc((m0.get("text") or "").strip()[:800]))

        reply_lc = (reply or "").lower()
        all_matches = result.get("matches") or []

        def _statute_referenced(m):
            # keep a statute only if it's a hand-anchored override or the
            # answer actually cites it -- drops semantic-search noise like
            # BNS 84 turning up next to an unrelated arrest question.
            if str(m.get("source") or "").startswith("curated"):
                return True
            sn = str(m.get("section_number") or "")
            return bool(sn) and (f"section {sn}".lower() in reply_lc
                                 or f"section {sn.split('(')[0]}".lower() in reply_lc)

        # statutes: every relevant one, no fill-cap (there are rarely > 6)
        statutes, seen_s = [], set()
        for m in all_matches:
            if not m.get("section_number") or m.get("case_name"):
                continue
            if not _statute_referenced(m):
                continue
            k = (m.get("act"), m.get("section_number"))
            if k in seen_s:
                continue
            seen_s.add(k)
            statutes.append(m)

        # judgments: the anchored + answer-named ones, capped for length.
        # Pass judgment matches ONLY -- see _sources_worth_showing docstring.
        judgments = _sources_worth_showing(
            [m for m in all_matches if m.get("case_name")], reply)

        # group judgment paragraphs under ONE heading per case
        by_case, order = {}, []
        for m in judgments:
            k = (m.get("case_name"), m.get("citation"))
            if k not in by_case:
                by_case[k] = []
                order.append(k)
            by_case[k].append(m)

        if statutes or judgments:
            with st.expander("Read the source — the sections and judgments this rests on"):
                for m in statutes:
                    st.markdown(f'**{esc(m["act"])} Section {esc(m["section_number"])}**')
                    st.markdown(f'<div class="r-mono">{esc(_clean_excerpt(m.get("text") or "")[:900])}</div>',
                                unsafe_allow_html=True)
                if judgments:
                    st.markdown('<div class="r-label" style="margin-top:1rem">Judgments</div>',
                                unsafe_allow_html=True)
                for k in order:
                    name, cite = k
                    cite_html = (f' &nbsp;·&nbsp; <span class="r-src">{esc(cite)}</span>'
                                 if cite else "")
                    st.markdown(f'**{esc(name)}**{cite_html}', unsafe_allow_html=True)
                    _render_currency_caveat(by_case[k][0])
                    for m in by_case[k]:
                        para_head = str(m.get("paragraph_number") or "").split("_")[0]
                        if para_head.isdigit():
                            st.markdown(f'<span class="r-src">paragraph {esc(para_head)}</span>',
                                        unsafe_allow_html=True)
                        st.markdown(f'<div class="r-mono">{esc(_clean_excerpt(m.get("text") or "")[:1100])}</div>',
                                    unsafe_allow_html=True)
        return bool(result.get("situation_detected"))

    # ---- everything below is an honest non-answer ----
    st.markdown('<div class="r-label">Out of scope</div>', unsafe_allow_html=True)

    if state == "covered_elsewhere_in_tool":
        dom = result.get("redirect_domain")
        label = {"freeze": "a frozen bank account", "cheque_bounce": "a bounced cheque"}.get(dom, "this")
        st.markdown("## That's a different kind of matter")
        st.markdown(f'<div class="r-oos">This looks like it is about <b>{esc(label)}</b>. '
                    'Recourse focuses on arrest, FIR, police procedure and bail. For a cheque '
                    'or bank-freeze matter, take the notice or letter to a lawyer or your '
                    'nearest District Legal Services Authority.</div>', unsafe_allow_html=True)
    elif state == "adjacent_uncovered":
        st.markdown("## Recourse can't help with this one")
        reason = result.get("reasoning") or ""
        st.markdown(f'<div class="r-oos">This looks like a real legal question, but it is '
                    'outside what Recourse checks &mdash; it covers police arrests, FIRs, '
                    'criminal procedure and bail under the BNS and BNSS. '
                    + (f'<br><span class="r-src">{esc(reason)}</span>' if reason else "")
                    + '</div>', unsafe_allow_html=True)
        st.markdown('<p class="r-foot">For this kind of question, speak with a lawyer who '
                    'handles that area of law.</p>', unsafe_allow_html=True)
    elif state == "unrelated":
        st.markdown("## That doesn't look like a legal question")
        st.markdown('<div class="r-oos">Recourse is built for police arrests, FIRs and '
                    'criminal procedure under Indian law. Ask about any of those in your '
                    'own words.</div>', unsafe_allow_html=True)
    elif state == "no_match":
        st.markdown("## Not enough to go on yet")
        st.markdown('<div class="r-oos">Recourse looked but could not find anything in the '
                    'law and judgments it holds that clearly matches this. Try adding detail '
                    '&mdash; what happened, and roughly when &mdash; or name the section of '
                    'law if you know it.</div>', unsafe_allow_html=True)
    else:  # classifier_unavailable / retrieval_unavailable / anything unexpected
        st.markdown("## Something isn't working right now")
        st.markdown('<div class="r-oos">This is a technical problem on Recourse\'s side, not '
                    'your question. Try again in a moment.</div>', unsafe_allow_html=True)
    return False


# --------------------------------------------------------------------------
# the "have the papers?" compliance check
# --------------------------------------------------------------------------
def render_doc_check(result: dict):
    if not result.get("ok"):
        st.markdown(f'<p class="r-foot">{esc(result.get("error") or result.get("note") or "Could not read that file.")}</p>',
                    unsafe_allow_html=True)
        return

    if not result.get("is_arrest_document"):
        st.markdown(f'<div class="r-oos">{esc(result.get("note"))}</div>', unsafe_allow_html=True)
        _render_concord(result.get("old_code"))
        return

    cls = "r-summ hasdefect" if result.get("n_defects") else "r-summ"
    st.markdown(f'<div class="{cls}">{esc(result.get("overall"))}</div>', unsafe_allow_html=True)

    for c in result.get("checks", []):
        st.markdown(
            f'<div class="r-checkrow">'
            f'<div class="r-chead">{esc(c["plain"])}</div>'
            f'<span class="r-verdict {c["bucket"]}">{esc(c["label"])}</span>'
            f'<div class="r-cexp">{esc(c["explanation"])}</div>'
            f'</div>', unsafe_allow_html=True)

    _render_concord(result.get("old_code"))

    st.markdown(
        '<p class="r-foot">This is a check of the safeguards against what the document '
        'itself says — it cannot see anything that happened outside the document. '
        '"Possibly not followed" means the document is silent where it should have '
        'spoken. Take the document, and this, to a lawyer or the Magistrate.</p>',
        unsafe_allow_html=True)


def _render_concord(old_code):
    if not old_code:
        return
    parts = []
    for e in old_code:
        new = e.get("new") or "no re-enacted successor"
        parts.append(f'<code>{esc(e["old"])}</code> &rarr; <code>{esc(new)}</code>')
    st.markdown(
        '<div class="r-concord">This document cites the pre-2024 codes. Current '
        'equivalents: ' + " &nbsp;·&nbsp; ".join(parts)
        + ' &mdash; the case law generally carries over to the new numbering.</div>',
        unsafe_allow_html=True)


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------
if (go or st.session_state.pop("_autorun", False)) and msg.strip():
    for _k in ("doc_check", "doc_check_sig"):
        st.session_state.pop(_k, None)          # never carry stale artefacts over
    with st.spinner("Reading the law and the judgments on this…"):
        # recourse_app is chat-only: it has no document-upload handoff, so
        # cheque-bounce and bank-freeze questions are answered inline from
        # the shared corpus's own case law rather than dead-ended with a
        # "covered elsewhere" redirect that points nowhere here.
        st.session_state.answer = answer_question(
            msg, inline_domains={"cheque_bounce", "freeze"})
    st.session_state.answer_msg = msg

answer = st.session_state.get("answer")
if answer:
    _box_now = msg.strip()
    msg = st.session_state.get("answer_msg", msg)
    st.html('<hr class="r-rule">')
    # if the box has been edited since this answer was produced, say so
    if _box_now and _box_now != msg.strip():
        st.markdown('<p class="r-foot">You\'ve changed your description &mdash; press '
                    '<b>Check my situation</b> again to update the answer below.</p>',
                    unsafe_allow_html=True)

    situation = render_answer(answer)

    # ---- optional: check the actual papers (an arrest has happened) ----
    if situation:
        st.markdown('<div class="r-label">Have the papers?</div>', unsafe_allow_html=True)
        st.markdown(
            "The answer above is what the law **requires**. Upload the **arrest "
            "memo, the FIR copy, or a remand order** and Recourse checks whether "
            "each safeguard was **actually followed** — with fixed rules, not the AI.")
        up = st.file_uploader("Upload a document (PDF or text)", type=["pdf", "txt"],
                              label_visibility="collapsed", key="doc_upload")
        if up is not None:
            sig = f"{up.name}:{up.size}"
            if st.session_state.get("doc_check_sig") != sig:
                ext = extract_text(up)
                if not ext["ok"]:
                    st.session_state["doc_check"] = {"ok": False, "error": ext["error"]}
                else:
                    with st.spinner("Checking the document against the safeguards…"):
                        st.session_state["doc_check"] = check_arrest_document(ext["text"])
                st.session_state["doc_check_sig"] = sig
            if st.session_state.get("doc_check"):
                render_doc_check(st.session_state["doc_check"])

_footer()
