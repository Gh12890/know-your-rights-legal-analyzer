# Know Your Rights — Indian Legal Notice Analyzer

**A tool that reads an Indian legal or police document and checks whether the authorities actually followed the law — not just what the document says, but what it fails to say.**

Most legal-AI tools summarize. This one adjudicates. It takes a legal notice or police document, extracts the facts, and then checks those facts against binding Supreme Court procedural requirements — flagging where a citizen's rights may have been violated. It is built for the person on the receiving end of state or institutional power, not for the lawyer or the police.

---

## The Problem

In India, procedural safeguards laid down by the Supreme Court are routinely ignored — not always maliciously, but because the people they protect don't know they exist.

A person is arrested for an offence punishable with under seven years. Under *Arnesh Kumar v. State of Bihar* (2014), the police were required to first serve a notice to appear, not arrest directly. They didn't. The family doesn't know this was mandatory. No lawyer has told them. The arrest proceeds, and a right that existed on paper is lost in practice.

The same pattern repeats across domains: a bank account frozen on a bare police letter with no legal section cited; a cheque-bounce notice issued outside the statutory window; a person held past the 60- or 90-day limit after which bail becomes a matter of right under Section 187 BNSS. In each case, the violation is knowable from the document itself — if you know what to look for.

This tool knows what to look for.

---

## What It Does

The analyzer classifies an uploaded document into one of several categories and runs domain-specific compliance checks against established case law and statute. Three domains are fully built and tested:

### 1. Banking & Cheque Bounce (Section 138, Negotiable Instruments Act)
Checks the four Supreme Court requirements for a valid Section 138 notice: the 30-day notice window from cheque return, that the demand equals the cheque's face value with interest stated separately (*Suman Sethi v. Ajay K. Churiwal*), that the cheque was issued for a legally enforceable debt (*Laxmi Dyechem*), and the 15-day payment window.

### 2. Police & Criminal Process — Arrest
Seven deterministic checks against binding precedent:
- **Pre-arrest notice** for offences up to 7 years — *Arnesh Kumar (2014)*, reaffirmed in *Satender Kumar Antil (2026)*
- **Written grounds of arrest** furnished to the arrestee — *Prabir Purkayastha (2024)*
- **Arrest memo safeguards** — witness attestation, family notification, medical examination — *D.K. Basu (1997)*
- **Night-arrest protection** for women — Section 46(4) CrPC / *Sheela Barse*
- **Female officer involvement** for a female arrestee — *Sheela Barse*
- **24-hour production** before a magistrate — Article 22(2) / Section 58 BNSS
- **Default bail** deadline calculation — Section 187 BNSS / Section 167(2) CrPC, computing the exact calendar date on which bail becomes a matter of right if no chargesheet is filed

### 3. Bank / Account Freezing (Sections 106 & 107 BNSS)
Checks whether a freeze cites any legal authority at all (in practice, many don't), whether it was restricted to the disputed amount or improperly blanket-froze the entire account, whether the jurisdictional magistrate was intimated, and whether the account holder was informed.

The tool derives the maximum punishment for an offence directly from the BNS section cited — using a built-in reference table of 150+ sections mapped from the old IPC — so it can apply the correct legal threshold even when the police document never states the punishment (which it usually doesn't).

---

## Why This Isn't ChatGPT

The core architectural principle: **the language model extracts facts; deterministic Python code makes every legal ruling.**

A general-purpose LLM asked "is this notice compliant?" gives a different answer each time you ask, and will confidently invent case law. This tool never lets the model rule on compliance. The model's only job is to report what the document states — dates, sections cited, whether a witness signed, what time an arrest happened. Every compliance verdict is then computed by fixed Python logic against fixed legal rules. The same document produces the same verdict every time, and every verdict traces to a specific, checkable rule.

This separation is the whole point. It is what makes the output reproducible, auditable, and defensible — the things a legal tool cannot do without.

It also models honesty directly. Where a simple binary forces a compliant/non-compliant call, this tool distinguishes four states: **Compliant**, **Non-Compliant** (a confirmed defect), **May be Non-Compliant** (a defect inferred from a conspicuous silence — e.g., a memo that carefully documents every other safeguard but says nothing about the mandatory pre-arrest notice), and **Cannot Determine** (the rule applies but the document doesn't contain enough to check it). Police documents violate by omission far more than by admission, and the tool is built to catch that.

---

## Architecture

```
PDF upload
   |
   v
Text extraction  (PyMuPDF)  ->  cleaning
   |
   v
Classification   (LLM: which category?)
   |
   v
Field extraction (LLM: report the raw facts only, temperature = 0)
   |
   v
Compliance rulings (Python: deterministic checks against case law + BNS section table)
   |
   v
Structured output:
   what it is - how serious - what's claimed - what's missing - what to do - what to gather
```

Built with Python, the Anthropic API (used strictly for fact extraction, never for legal judgment), and Streamlit for the interface.

---

## Sample Output

Analysis of a sample arrest memo (offence under BNS 318(4), punishable up to 7 years):

```json
{
  "compliance_checks": [
    {
      "requirement": "41A CrPC / Section 35 BNSS notice before arrest [Arnesh Kumar (2014)]",
      "status": "May be Non-Compliant",
      "explanation": "Offence punishable up to 7 years (looked up from cited section). No mention of the mandatory 41A/35 BNSS notice in the document. The arrest may be illegal if this mandatory notice was not actually served."
    },
    {
      "requirement": "Produced before magistrate within 24 hours [Art. 22(2)/S.58 BNSS]",
      "status": "Non-Compliant",
      "explanation": "Produced 55.0 hours after arrest — exceeds constitutional 24-hour limit."
    },
    {
      "requirement": "Default bail on chargesheet delay [S.187 BNSS / S.167(2) CrPC]",
      "status": "Compliant",
      "explanation": "No chargesheet filed yet. Default bail becomes available on 05-09-2026 if not filed before then — 54 days remain."
    }
  ]
}
```

---

## Running It Locally

```bash
# Clone the repository
git clone https://github.com/Gh12890/know-your-rights-legal-analyzer.git
cd know-your-rights-legal-analyzer

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Add your Anthropic API key:
# Create a file named .env in the project root containing:
#   ANTHROPIC_API_KEY=your_key_here

# Run the app
streamlit run app.py
```

Sample documents are included in the repository (`Sample_Arrest_Memo_*.pdf`, `Sample_Bank_Freeze_Notice_NoSection.pdf`, `Sample_Legal_Notice_Section138.pdf`) so the tool can be tested immediately.

---

## Roadmap

Three domains are fully built and tested. The following are designed — with extraction schemas and case-law logic scoped — but not yet validated, and are honestly marked as work in progress rather than presented as finished:

- **Search & Seizure** — Section 50 NDPS safeguards (*Baldev Singh*), person-vs-premises scope (*Ranjan Kumar Chadha*), independent witness requirements
- **FIR Registration Dispute** — *Lalita Kumari* mandate and the CrPC/BNSS dual-regime inquiry-window logic (7 days vs 14 days, keyed on offence date)
- **Summons to Vulnerable Persons** — Section 179 BNSS residence-only rule for women and minors, *Sheela Barse* protections
- **Document-less citizens** — a guided-interview path for the many cases where police provide no paperwork at all, so the tool can construct the record the authorities failed to give

The case-law and section-mapping data is current as of mid-2026 and is not yet version-controlled against future amendments — a known limitation for any tool in this space, and a planned area of work.

---

## Disclaimer

**This tool does not provide legal advice.** It reads a document and checks it against publicly known procedural requirements for educational and informational purposes. It cannot see facts outside the document it is given, and its findings — especially those marked "May be Non-Compliant," which are inferences from what a document omits — are not legal conclusions. Anyone facing a real legal situation should consult a qualified advocate. The section mappings and case-law references reflect careful research but should be independently verified before being relied upon.

---

## About

Built by a former Sub-Divisional Magistrate transitioning into legal technology, drawing on direct administrative and criminal-procedure experience to encode the procedural safeguards that most often go unenforced in practice. The project's design principle throughout: serve the citizen against institutional power, and never claim more certainty than the evidence supports.
