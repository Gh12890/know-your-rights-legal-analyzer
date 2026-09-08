"""
scenario_spec.py  (Vibeathon Step 2, 2026-09-06)

The situation catalogue behind "Recourse".

WHY THIS EXISTS -- the anti-generic problem:
The engine's Lane B has ~9 *doctrine* topics, and doctrine anchors deliberately
inject the SAME canonical case (Arnesh Kumar, D.K. Basu, ...) whenever a situation
touches that doctrine. Correct for safety -- but it means every arrest question
returns the same three "rights of an arrested person 101" cases. A judge who tries
three arrest scenarios and gets Arnesh Kumar three times files the tool under
"RAG chatbot over Indian Kanoon".

The fix is to answer the SITUATION (role x stage x factors), not the words. This
file is the catalogue of situations. Each SCENARIO:
  - has its OWN, mutually-distinct case set (Arnesh Kumar lives ONLY in
    SUMMONS_PRE_ARREST -- never in DEFAULT_BAIL, never in ARREST_WOMAN),
  - carries a plain-language stage explainer,
  - lists RIGHTS, each pinned to a specific section + a specific case + a
    paragraph hint, and each gated on sub-issue TRIGGERS so that different
    inputs into the SAME scenario surface DIFFERENT rights and cases,
  - lists what the police CAN and CANNOT lawfully do at that stage,
  - lists concrete NEXT-24-HOURS actions,
  - carries NEGATION lines ("your situation does NOT raise X") -- nothing signals
    "I understood your specific case" harder than correctly ruling things out,
  - names the document Recourse can generate for it.

DISCIPLINE -- same as the rest of this project:
  - Every `case` string MUST equal a real corpus `case_name` (test checks this),
    OR carry in_corpus=False and a note (a Step-3 corpus top-up target).
  - Every `section` is looked up live from the statute chunks, never hardcoded
    here (the assembler pulls the text).
  - `review=True` marks a line the legal teammate must verify before submission.
    The plain-language wording here is a careful first draft, not vetted law.

TRIGGERS use the same "keyword group" matching proven out in
statute_doctrine_map.py: a trigger is a tuple of lowercase words; it fires when
EVERY word in the tuple appears somewhere in the matched text (the user's message
+ the router's extracted factors). A right with `triggers=[]` (or ALWAYS) always
fires.
"""

from dataclasses import dataclass, field
from typing import List

# Sentinel: a right / negation with this trigger set always fires.
ALWAYS: List[tuple] = []


@dataclass
class Right:
    """One right the person has at this stage, pinned to real authority."""
    plain_text: str                       # ONE plain sentence, no jargon
    section: str = ""                      # e.g. "187" -- number only
    act: str = ""                          # "BNSS" | "BNS" | "Constitution" | "NI Act"
    case: str = ""                         # exact corpus case_name, or ""
    para_hint: str = ""                    # e.g. "para 18" -- pointer for the reader
    triggers: List[tuple] = field(default_factory=list)   # [] = always fires
    in_corpus: bool = True                 # False -> Step 3 corpus top-up target
    review: bool = True                    # teammate must verify the wording/pin
    note: str = ""                         # anything the teammate/reader should know


@dataclass
class Negation:
    """A 'your situation does NOT raise X' line, shown when `absent_triggers`
    did NOT fire -- i.e. the factor that WOULD raise X is not present."""
    line: str
    absent_triggers: List[tuple]           # if NONE of these fire -> show the line
    review: bool = True


@dataclass
class Scenario:
    id: str
    label: str                             # human-readable name
    role: str                              # "accused" | "family" | "complainant"
    stage: str                             # short phrase
    stage_explainer: str                   # plain language: what this situation IS
    rights: List[Right]
    police_can: List[str]
    police_cannot: List[str]
    next_24h: List[str]
    negations: List[Negation]
    paper_type: str                        # key draft_layer / the doc layer uses
    red_flags: List[str]
    cases: List[str]                       # the FULL distinct case pool for this scenario
    review: bool = True


# ===========================================================================
# THE CATALOGUE
#
# 3 heroes (DEFAULT_BAIL, ARREST_WOMAN, FIR_NOT_REGISTERED) + 2 reserves
# (SUMMONS_PRE_ARREST, CHEQUE_BOUNCE_NOTICE). More scenario IDs exist in
# scenario_router.SCENARIO_IDS as routing targets; they resolve to the closest
# built scenario until their own spec is authored (post-submission).
# ===========================================================================

_SCENARIOS = [

    # -------------------------------------------------------------------
    Scenario(
        id="DEFAULT_BAIL",
        label="Held past the chargesheet deadline",
        role="family",
        stage="in custody, investigation ongoing, chargesheet not yet filed",
        stage_explainer=(
            "When the police arrest someone, they have a fixed window to finish the "
            "investigation and file the chargesheet (the final report) in court - "
            "60 days for most offences, or 90 days for the most serious ones "
            "(punishable with death, imprisonment for life, or 10 years or more). "
            "If that deadline passes and the chargesheet still has not been filed, "
            "the arrested person gets an automatic right to be released on bail. "
            "This is called default bail or statutory bail. The court does not "
            "re-examine how strong the case is - if the deadline was missed and the "
            "person applies and is ready to give bail, release follows."
        ),
        rights=[
            Right(
                plain_text=(
                    "Once the 60- or 90-day period is over and no chargesheet has "
                    "been filed, you have a right to be released on bail that the "
                    "court cannot refuse on the merits of the case - you only have "
                    "to apply and be ready to furnish bail."
                ),
                section="187", act="BNSS",
                case="M. Ravindran v Intelligence Officer, Directorate of Revenue Intelligence",
                para_hint="para 18",
                triggers=ALWAYS,
                note="Ravindran: cleanest modern statement of when the right is "
                     "'availed of' and what it survives.",
            ),
            Right(
                plain_text=(
                    "The application does not have to be a long formal petition - "
                    "even an oral request once the right has arisen is enough, and "
                    "this right is treated as part of the right to life and personal "
                    "liberty under Article 21."
                ),
                section="187", act="BNSS",
                case="Bikramjit Singh v State of Punjab",
                para_hint="",
                triggers=ALWAYS,
            ),
            Right(
                plain_text=(
                    "If the offence is NOT one punishable with death, life, or 10 "
                    "years or more, the deadline is 60 days, not 90 - and any real "
                    "doubt about which limit applies is resolved in the arrested "
                    "person's favour."
                ),
                section="187", act="BNSS",
                case="Rakesh Kumar Paul v State of Assam",
                para_hint="",
                triggers=[("10 year",), ("ten year",), ("life",), ("murder",),
                          ("serious",), ("90 day",), ("ninety",)],
                note="Rakesh Kumar Paul is a 2:1 split; the 60-vs-90 ratio is "
                     "narrower than the other two - kept as a triggered right, "
                     "not an always-on one.",
            ),
        ],
        police_can=[
            "Ask the court for more time only where a special law (such as UAPA or "
            "the NDPS Act) specifically allows it - not under the ordinary BNSS.",
            "Continue the investigation after default bail is granted and file the "
            "chargesheet later; default bail does not end the case.",
        ],
        police_cannot=[
            "Defeat the right by filing an incomplete 'piecemeal' chargesheet just "
            "to stop the clock.",
            "Treat a default-bail application as if it were an ordinary bail plea to "
            "be weighed on how strong the evidence is.",
        ],
        next_24h=[
            "Work out the exact date and time of arrest and count the days that "
            "have passed.",
            "Check the maximum punishment for the offence - that decides whether "
            "the limit is 60 or 90 days.",
            "The moment the period lapses, file a written default-bail application "
            "stating that the person is ready to furnish bail.",
            "If the Magistrate delays hearing it, move the Sessions Court - delay "
            "by the court does not defeat the right, but filing the chargesheet "
            "before you apply can.",
        ],
        negations=[
            Negation(
                line=(
                    "Because the offence here is not one punishable with death, "
                    "life, or 10 or more years, the deadline is 60 days, not 90."
                ),
                absent_triggers=[("10 year",), ("ten year",), ("life",),
                                 ("murder",), ("serious",), ("90 day",), ("ninety",)],
            ),
        ],
        paper_type="default_bail_application",
        red_flags=[
            "If the person is being held under UAPA, the NDPS Act, or PMLA, the "
            "timelines and the rules for extending them are different - speak to a "
            "lawyer immediately.",
        ],
        cases=[
            "M. Ravindran v Intelligence Officer, Directorate of Revenue Intelligence",
            "Bikramjit Singh v State of Punjab",
            "Rakesh Kumar Paul v State of Assam",
        ],
    ),

    # -------------------------------------------------------------------
    Scenario(
        id="ARREST_GENERAL",
        label="Someone has been arrested",
        role="family",
        stage="arrested, in custody, first 24 hours",
        stage_explainer=(
            "An arrest is only lawful if certain safeguards are followed at the "
            "moment it happens and in the hours right after. The person must be "
            "told WHY they are being arrested, in enough detail to actually "
            "respond to it. For most offences punishable with up to 7 years the "
            "police are expected to serve a written notice to appear first, not "
            "arrest straight away. A relative or friend must be told about the "
            "arrest and where the person is being held. And the person must be "
            "produced before a Magistrate within 24 hours. These are not "
            "formalities - if they are broken, the continued custody itself can "
            "be challenged as unlawful."
        ),
        rights=[
            Right(
                plain_text=(
                    "The person, and the family, have a right to be told the "
                    "grounds of the arrest - the actual reasons and the substance "
                    "of the allegation, not just a section number read out."
                ),
                section="47", act="BNSS",
                case="Prabir Purkayastha v State (NCT of Delhi)",
                triggers=ALWAYS,
            ),
            Right(
                plain_text=(
                    "For an offence punishable with up to 7 years, the police are "
                    "expected to serve a written notice to appear first; arresting "
                    "straight away is the exception and needs reasons recorded in "
                    "writing."
                ),
                section="35", act="BNSS",
                case="Arnesh Kumar v State of Bihar",
                triggers=[("directly",), ("straight away",), ("without", "notice"),
                          ("no notice",), ("never gave", "notice"), ("came to my house",),
                          ("came to our house",), ("stole",), ("theft",), ("cheat",),
                          ("goat",), ("shop",), ("minor",), ("small",)],
            ),
            Right(
                plain_text=(
                    "A relative or friend has a right to be told that the person "
                    "has been arrested and exactly where they are being held, as "
                    "soon as the arrest is made."
                ),
                section="48", act="BNSS",
                case="D.K. Basu v State of West Bengal",
                triggers=[("nobody told us",), ("didn't tell us",), ("did not tell",),
                          ("family",), ("we don't know where",), ("dont know where",),
                          ("not informed",), ("no information",), ("where he is",),
                          ("where she is",)],
            ),
            Right(
                plain_text=(
                    "The person must be examined by a doctor after arrest, the "
                    "arrest memo must be attested by a witness, and any injury or "
                    "ill-treatment in custody must be recorded."
                ),
                section="", act="",
                case="D.K. Basu v State of West Bengal",
                triggers=[("beat",), ("beaten",), ("hit",), ("slap",), ("tortur",),
                          ("thrash",), ("injur",), ("medical",), ("doctor",),
                          ("memo",), ("witness",), ("kept awake",), ("lockup",),
                          ("lock-up",), ("lock up",)],
            ),
            Right(
                plain_text=(
                    "The person has a right to meet and consult a lawyer, "
                    "including during questioning."
                ),
                section="38", act="BNSS",
                case="D.K. Basu v State of West Bengal",
                triggers=[("lawyer",), ("advocate",), ("counsel",), ("legal aid",)],
            ),
            Right(
                plain_text=(
                    "The person must be produced before a Magistrate within 24 "
                    "hours of arrest, not counting the time needed for the journey "
                    "to court."
                ),
                section="58", act="BNSS",
                case="Rakhi Mitra and Anr v State of West Bengal",
                triggers=ALWAYS,
            ),
        ],
        police_can=[
            "Arrest without a warrant for a cognizable offence, provided they give "
            "the grounds of arrest.",
            "Arrest despite the notice-first rule where they record specific "
            "reasons why arrest is necessary, or for an offence above 7 years.",
        ],
        police_cannot=[
            "Keep the grounds of arrest from the person or the family.",
            "Arrest routinely for a minor offence without recording why arrest was "
            "necessary.",
            "Refuse to let the person meet a lawyer, or refuse to tell the family "
            "where they are held.",
        ],
        next_24h=[
            "Ask, in writing, for the grounds of arrest and a copy of the arrest "
            "memo - keep a copy of your request.",
            "Write down the exact date and time of the arrest and who was present.",
            "Find out which Magistrate the person will be produced before, and when.",
            "Arrange a lawyer for that production hearing - procedural breaches are "
            "raised there, in front of the Magistrate, not saved for later.",
        ],
        negations=[
            Negation(
                line=(
                    "If the offence is one punishable with more than 7 years, the "
                    "written-notice-first rule does not apply - the focus is the "
                    "grounds of arrest and the 24-hour production."
                ),
                absent_triggers=[("stole",), ("theft",), ("cheat",), ("goat",),
                                 ("shop",), ("minor",), ("small",), ("directly",),
                                 ("no notice",), ("without", "notice")],
                review=True,
            ),
        ],
        paper_type="magistrate_representation",
        red_flags=[
            "If the person has visible injuries or says they were hit, slapped or "
            "kept awake - that is custodial violence. Raise it with the Magistrate "
            "at the production hearing and ask for a medical examination to be "
            "recorded, straight away.",
        ],
        cases=[
            "Prabir Purkayastha v State (NCT of Delhi)",
            "Arnesh Kumar v State of Bihar",
            "D.K. Basu v State of West Bengal",
            "Rakhi Mitra and Anr v State of West Bengal",
        ],
    ),

    # -------------------------------------------------------------------
    Scenario(
        id="ARREST_WOMAN",
        label="A woman has been arrested",
        role="family",
        stage="arrested, in custody, first 24 hours, reason not given",
        stage_explainer=(
            "An arrest is only lawful if certain safeguards are followed at the "
            "moment it happens and in the hours right after. The person - and, "
            "through them, their family - must be told WHY they are being arrested, "
            "in enough detail to actually respond to it. A woman ordinarily cannot "
            "be arrested between sunset and sunrise. The family must be told about "
            "the arrest and where the person is being held. And the person must be "
            "produced before a Magistrate within 24 hours. These are not "
            "formalities - if they are broken, the continued custody itself can be "
            "challenged as unlawful."
        ),
        rights=[
            Right(
                plain_text=(
                    "She and your family have a right to be told the grounds of her "
                    "arrest - the actual reasons and the substance of the "
                    "allegation, not just a section number read out."
                ),
                section="47", act="BNSS",
                case="Prabir Purkayastha v State (NCT of Delhi)",
                para_hint="",
                triggers=ALWAYS,
                note="Pankaj Bansal is the companion authority; the assembler's "
                     "suppression rule decides which name is shown where.",
            ),
            Right(
                plain_text=(
                    "A woman shall not be arrested after sunset and before sunrise "
                    "except in exceptional circumstances - and even then only by a "
                    "woman police officer who has the prior written permission of a "
                    "Judicial Magistrate of the first class."
                ),
                section="43", act="BNSS",
                case="Deepa v S. Vijayalakshmi",
                para_hint="held s.43(5) BNSS not mandatory",
                triggers=[("night",), ("sunset",), ("sunrise",), ("last night",),
                          ("evening",), ("9 pm",), ("10 pm",), ("11 pm",),
                          ("midnight",), ("late night",), ("after dark",)],
                note="Statute text verbatim-verified in statute_doctrine_map.py (bnss_43_5). "
                     "Deepa v S. Vijayalakshmi (Madras HC DB, 2025) is now in the corpus "
                     "and is squarely on Section 43(5) BNSS: it holds the provision "
                     "DIRECTORY, not mandatory - a breach does not automatically void the "
                     "arrest, but the officer must still be able to justify the deviation, "
                     "and the victim/complainant cannot be made to suffer for the officer's "
                     "neglect of the safeguard.",
            ),
            Right(
                plain_text=(
                    "A relative or friend has a right to be told that she has been "
                    "arrested and exactly where she is being held, as soon as the "
                    "arrest is made."
                ),
                section="48", act="BNSS",
                case="D.K. Basu v State of West Bengal",
                para_hint="",
                triggers=[("nobody told us",), ("didn't tell us",), ("did not tell",),
                          ("family",), ("we don't know where",), ("dont know where",),
                          ("not informed",), ("no information",)],
            ),
            Right(
                plain_text=(
                    "She must be examined by a doctor after arrest, and if she is a "
                    "nursing mother her medical needs and her infant's dependence on "
                    "her must be accommodated in custody and weighed in any bail "
                    "decision."
                ),
                section="", act="",
                case="D.K. Basu v State of West Bengal",
                para_hint="",
                triggers=[("nursing",), ("breastfeed",), ("breast feed",),
                          ("infant",), ("baby",), ("newborn",), ("child",),
                          ("months old",), ("year old",)],
                in_corpus=True,
                review=True,
                note="STEP 3 TOP-UP CANDIDATE: a nursing-mother / woman-dignity "
                     "specific authority would strengthen this. D.K. Basu covers "
                     "the medical-exam + humane-custody core only.",
            ),
            Right(
                plain_text=(
                    "She must be produced before a Magistrate within 24 hours of "
                    "arrest, not counting the time needed for the journey to court."
                ),
                section="58", act="BNSS",
                case="Prabir Purkayastha v State (NCT of Delhi)",
                para_hint="",
                triggers=ALWAYS,
            ),
        ],
        police_can=[
            "Arrest a woman during the day for a cognizable offence, provided they "
            "give her the grounds of arrest.",
            "Arrest a woman at night only in genuinely exceptional circumstances, "
            "and only with a Magistrate's prior written permission and a woman "
            "officer present.",
        ],
        police_cannot=[
            "Arrest a woman between sunset and sunrise without that written "
            "permission and a woman officer.",
            "Keep the grounds of arrest from her or from the family.",
            "Refuse to tell the family where she is being held.",
        ],
        next_24h=[
            "Ask, in writing, for the grounds of arrest and a copy of the arrest "
            "memo - and keep a copy of your request.",
            "Write down the exact time she was taken and who was present, including "
            "whether any woman police officer was there.",
            "Find out which Magistrate she will be produced before, and when.",
            "Arrange a lawyer for that production hearing - safeguard breaches are "
            "raised there, in front of the Magistrate, not saved for later.",
        ],
        negations=[
            Negation(
                line=(
                    "Since the arrest was during the day, the sunset-to-sunrise "
                    "restriction does not apply here - the key questions are the "
                    "grounds of arrest and the 24-hour production."
                ),
                absent_triggers=[("night",), ("sunset",), ("sunrise",),
                                 ("last night",), ("evening",), ("9 pm",),
                                 ("10 pm",), ("11 pm",), ("midnight",),
                                 ("late night",), ("after dark",)],
            ),
        ],
        paper_type="magistrate_representation",
        red_flags=[
            "If she has visible injuries or says she was hit, slapped, or kept "
            "awake - that is custodial violence. Raise it with the Magistrate at "
            "the production hearing and ask for a medical examination to be "
            "recorded, straight away.",
        ],
        cases=[
            "Prabir Purkayastha v State (NCT of Delhi)",
            "Pankaj Bansal v Union of India",
            "D.K. Basu v State of West Bengal",
            "Deepa v S. Vijayalakshmi",
        ],
    ),

    # -------------------------------------------------------------------
    Scenario(
        id="FIR_NOT_REGISTERED",
        label="Police refusing to register an FIR",
        role="complainant",
        stage="no FIR yet - police refusing to register a cognizable complaint",
        stage_explainer=(
            "If you report a cognizable offence - one the police can investigate "
            "without a Magistrate's order, such as theft, robbery, or hurt - the "
            "police must register an FIR. They cannot refuse because the incident "
            "happened in a different police station's area (in that case they must "
            "register a 'zero FIR' and transfer it), and they cannot insist on "
            "checking out your complaint first for a straightforward cognizable "
            "offence. If they still refuse, the law gives you a clear escalation "
            "path: a written complaint to the Superintendent of Police, and then an "
            "application to the Magistrate directing the police to register and "
            "investigate."
        ),
        rights=[
            Right(
                plain_text=(
                    "Registering an FIR is mandatory when your complaint discloses "
                    "a cognizable offence - the police have no discretion to refuse."
                ),
                section="173", act="BNSS",
                case="Lalita Kumari v Government of Uttar Pradesh",
                para_hint="para 111(i)",
                triggers=ALWAYS,
                in_corpus=True, review=True,
                note="Seeded to corpus in batch 4 (Step 3). The Constitution Bench "
                     "holding (para 111(i)): registration is mandatory where the "
                     "information discloses a cognizable offence, and no preliminary "
                     "inquiry is permissible in that situation.",
            ),
            Right(
                plain_text=(
                    "If the offence happened in another police station's "
                    "jurisdiction, the police here must still register a 'zero FIR' "
                    "and forward it to the correct station - they cannot turn you "
                    "away on jurisdiction grounds."
                ),
                section="173", act="BNSS",
                case="Lalita Kumari v Government of Uttar Pradesh",
                para_hint="para 111(iv) - police cannot avoid the duty to register",
                triggers=[("different area",), ("another area",), ("not our",),
                          ("wrong police station",), ("jurisdiction",),
                          ("other station",), ("different city",), ("outside",)],
                in_corpus=True, review=True,
                note="The 'zero FIR' term is an MHA advisory; the legal backing is "
                     "the mandatory-registration duty (Lalita Kumari para 111(i)/(iv)) "
                     "plus the settled position that territorial jurisdiction goes to "
                     "investigation and trial, not to registration. Teammate: confirm "
                     "the framing; consider adding a territorial-jurisdiction authority "
                     "(e.g. Satvinder Kaur) post-submission.",
            ),
            Right(
                plain_text=(
                    "You can send the substance of your complaint in writing to the "
                    "Superintendent of Police, who must then either investigate it "
                    "or direct a subordinate officer to register and investigate."
                ),
                section="173", act="BNSS",
                case="",
                para_hint="sub-section (4)",
                triggers=[("sp",), ("superintendent",), ("senior officer",),
                          ("higher officer",), ("already complained",),
                          ("wrote to",), ("escalat",)],
            ),
            Right(
                plain_text=(
                    "You can apply to the Magistrate for an order directing the "
                    "police to register the FIR and investigate - the Magistrate "
                    "can also hold an inquiry first."
                ),
                section="175", act="BNSS",
                case="",
                para_hint="sub-section (3)",
                triggers=ALWAYS,
            ),
        ],
        police_can=[
            "Hold a short preliminary inquiry before registering, but only for "
            "specific categories (family or matrimonial disputes, commercial "
            "offences, medical negligence, corruption, or an unexplained long "
            "delay) - and they must record why.",
        ],
        police_cannot=[
            "Refuse to register an FIR for a clear cognizable offence.",
            "Refuse on the ground that the offence happened somewhere else.",
            "Demand that you produce proof or witnesses before they will register "
            "it.",
        ],
        next_24h=[
            "Put your complaint in writing and keep a dated copy.",
            "If the station refuses it, send it to the Superintendent of Police by "
            "registered post or email and keep the receipt.",
            "If there is still no action within a reasonable time, prepare the "
            "application to the Magistrate under Section 175(3) BNSS.",
        ],
        negations=[
            Negation(
                line=(
                    "If what happened is a non-cognizable matter, the police only "
                    "record it and point you to the Magistrate - an FIR is not "
                    "automatic in that situation."
                ),
                absent_triggers=[("theft",), ("stolen",), ("robbery",), ("robbed",),
                                 ("assault",), ("beat",), ("hurt",), ("attack",),
                                 ("threat",), ("cheat",), ("fraud",), ("break in",),
                                 ("broke in",)],
            ),
        ],
        paper_type="fir_complaint_to_magistrate",
        red_flags=[
            "If you are being threatened for pursuing the complaint, or the person "
            "you are complaining against is a police officer, speak to a lawyer "
            "before you escalate.",
        ],
        cases=[
            "Lalita Kumari v Government of Uttar Pradesh",
        ],
    ),

    # -------------------------------------------------------------------
    # RESERVE 1 - the ONLY home of Arnesh Kumar.
    Scenario(
        id="SUMMONS_PRE_ARREST",
        label="A notice to appear, or a feared arrest",
        role="accused",
        stage="not arrested - served or expecting a notice to appear, or fears arrest",
        stage_explainer=(
            "For an offence punishable with up to 7 years, the police are expected "
            "to first serve a written notice asking you to appear, rather than "
            "arresting you straight away. Arrest at this stage is meant to be the "
            "exception - used only where it is genuinely necessary, with the "
            "reasons written down. If you comply with the notice, you should not be "
            "arrested for that offence unless the officer records specific reasons "
            "why arrest is still necessary."
        ),
        rights=[
            Right(
                plain_text=(
                    "For an offence punishable with up to 7 years, you have a right "
                    "to be served a written notice to appear instead of being "
                    "arrested - unless the officer records specific reasons why "
                    "arrest is necessary."
                ),
                section="35", act="BNSS",
                case="Arnesh Kumar v State of Bihar",
                para_hint="",
                triggers=ALWAYS,
            ),
            Right(
                plain_text=(
                    "Being named in the FIR is not, by itself, a reason to arrest "
                    "you - the officer must still be able to justify that arrest is "
                    "necessary."
                ),
                section="35", act="BNSS",
                case="Satender Kumar Antil v Central Bureau of Investigation (2026)",
                para_hint="",
                triggers=[("named in the fir",), ("named in fir",), ("my name",),
                          ("accused",), ("fir against me",)],
            ),
            Right(
                plain_text=(
                    "You must attend when the police require it, but if you are "
                    "cooperating, a threat to arrest you anyway - or repeated "
                    "informal calls with no written notice - goes against these "
                    "safeguards."
                ),
                section="35", act="BNSS",
                case="Arnesh Kumar v State of Bihar",
                para_hint="",
                triggers=[("keep calling",), ("calling me",), ("asking me to come",),
                          ("come to the station",), ("threaten",), ("cooperat",)],
            ),
        ],
        police_can=[
            "Require you to attend for questioning.",
            "Arrest you despite the notice if you fail to comply with it, or if "
            "arrest is genuinely necessary for reasons recorded in writing.",
        ],
        police_cannot=[
            "Arrest you routinely or automatically for an offence up to 7 years "
            "just because the offence is made out.",
            "Arrest you for having complied with the notice.",
        ],
        next_24h=[
            "Attend as required and keep proof that you did.",
            "Ask for any notice in writing and keep it.",
            "If the offence is non-bailable and arrest still looks likely, consider "
            "applying for anticipatory bail now.",
            "Take a lawyer with you to any visit to the police station.",
        ],
        negations=[],
        paper_type="anticipatory_bail_note",
        red_flags=[
            "If the offence is non-bailable and you have real reason to expect "
            "arrest, move for anticipatory bail now - do not wait for the arrest.",
        ],
        cases=[
            "Arnesh Kumar v State of Bihar",
            "Satender Kumar Antil v Central Bureau of Investigation (2026)",
        ],
    ),

    # -------------------------------------------------------------------
    # RESERVE 2 - minimal; a different domain, kept as a routing target.
    Scenario(
        id="CHEQUE_BOUNCE_NOTICE",
        label="A cheque has bounced",
        role="complainant",
        stage="cheque dishonoured, deciding whether to send the statutory notice",
        stage_explainer=(
            "When a cheque is returned unpaid, the law gives the person it was "
            "written to a strict timeline. You must send a written demand for the "
            "amount within 30 days of learning the cheque bounced; the other side "
            "then has 15 days to pay; only if they do not pay can a complaint be "
            "filed, and it must be filed within the next month. Missing any of "
            "these steps can end the case before it starts."
        ),
        rights=[
            Right(
                plain_text=(
                    "You have a right to send a written demand for the cheque "
                    "amount within 30 days of the bank's return memo, and to file a "
                    "complaint if it is not paid within 15 days of that demand."
                ),
                section="138", act="NI Act",
                case="",
                para_hint="",
                triggers=ALWAYS,
                review=True,
            ),
        ],
        police_can=[],
        police_cannot=[
            "Arrest anyone over a bounced cheque - it is a complaint case before a "
            "Magistrate, not a police matter.",
        ],
        next_24h=[
            "Get the bank's cheque-return memo and note its date.",
            "Have a lawyer send the demand notice well within 30 days.",
        ],
        negations=[],
        paper_type="cheque_demand_notice",
        red_flags=[
            "If more than 30 days have passed since the cheque was returned, speak "
            "to a lawyer immediately - the notice window may have closed and there "
            "may be a limited way to still proceed.",
        ],
        cases=[
            "Rangappa v Sri Mohan",
            "Damodar S. Prabhu v Sayed Babalal H",
        ],
    ),
]


SCENARIOS = {s.id: s for s in _SCENARIOS}


def get_scenario(scenario_id: str):
    """The Scenario for an id, or None. OUT_OF_SCOPE and un-built routing
    targets return None -- the caller renders the honest 'not covered' path."""
    return SCENARIOS.get(scenario_id)


def all_case_names():
    """Every case named anywhere in the catalogue -- for the corpus check."""
    out = set()
    for s in _SCENARIOS:
        out.update(c for c in s.cases if c)
        out.update(r.case for r in s.rights if r.case)
    return sorted(out)
