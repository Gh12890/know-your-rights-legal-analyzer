# =============================================================
# BNS_SECTION_DATA — flattened lookup table
# Source: BNS Offence Reference Table (full punishment range, BNS-only)
# Keyed by exact BNS section/sub-section string as it would appear
# in sections_cited extracted from a document.
#
# life_or_death=True means the offence carries Life imprisonment or
# Death as its ceiling — Arnesh Kumar's 7-year test does not apply,
# and max_years is set to None since "Life"/"Death" is not a number.
#
# IMPORTANT: sub-section precision matters. 117(2) and 117(3) are
# different offences with very different consequences — do not
# collapse sub-sections into their parent section number.
# Verified against India Code and BPRD sources as of July 2026. Requires manual review if BNS/BNSS amendments occur.
# =============================================================

BNS_SECTION_DATA = {

    # ---------- Table 1: Homicide & Related ----------
    "103(1)":  {"offence": "Murder",                                             "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "103":     {"offence": "Murder",                                             "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "103(2)":  {"offence": "Mob lynching (murder by 5+ on discriminatory grounds)","max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "104":     {"offence": "Murder by life-convict",                             "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "105":     {"offence": "Culpable homicide not amounting to murder",          "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "106(1)":  {"offence": "Causing death by negligence",                       "max_years": 5,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "106(2)":  {"offence": "Hit-and-run (rash driving, escaping, not reporting)","max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "107":     {"offence": "Abetment of suicide of child/insane person",        "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "108":     {"offence": "Abetment of suicide",                               "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "109(1)":  {"offence": "Attempt to murder",                                 "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "109":     {"offence": "Attempt to murder",                                 "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "109(2)":  {"offence": "Attempt to murder by life-convict (if hurt)",       "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "110":     {"offence": "Attempt to commit culpable homicide",               "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},

    # ---------- Table 2: Organised Crime & Terrorism ----------
    "111(2)(a)": {"offence": "Organised crime resulting in death",              "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "111(2)(b)": {"offence": "Organised crime (other cases)",                   "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "111(3)":    {"offence": "Abetting/conspiring/facilitating organised crime","max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "111(4)":    {"offence": "Member of organised crime syndicate",            "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "112":       {"offence": "Petty organised crime",                         "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "113(2)(a)": {"offence": "Terrorist act resulting in death",              "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "113(2)(b)": {"offence": "Terrorist act (other cases)",                    "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},

    # ---------- Table 3: Hurt & Grievous Hurt ----------
    "115(2)":  {"offence": "Voluntarily causing hurt",                          "max_years": 1,    "life_or_death": False, "cognizable": False, "bailable": True},
    "117(2)":  {"offence": "Voluntarily causing grievous hurt",                 "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "117(3)":  {"offence": "Grievous hurt causing permanent disability/vegetative state", "max_years": None, "life_or_death": True, "cognizable": True, "bailable": False},
    "117(4)":  {"offence": "Grievous hurt by group of 5+ on discriminatory grounds", "max_years": 7, "life_or_death": False, "cognizable": True, "bailable": False},
    "118(1)":  {"offence": "Voluntarily causing hurt by dangerous weapons",     "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "118(2)":  {"offence": "Grievous hurt by dangerous weapons",                "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "119(1)":  {"offence": "Voluntarily causing hurt to extort property/constrain illegal act", "max_years": 10, "life_or_death": False, "cognizable": True, "bailable": False},
    "120(1)":  {"offence": "Voluntarily causing hurt to extort confession/information", "max_years": 7, "life_or_death": False, "cognizable": True, "bailable": True},
    "123":     {"offence": "Causing hurt by poison with intent to commit offence", "max_years": 10, "life_or_death": False, "cognizable": True, "bailable": False},
    "124(1)":  {"offence": "Grievous hurt by acid",                             "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "124(2)":  {"offence": "Throwing or attempting to throw acid",              "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "125":     {"offence": "Act endangering life or personal safety",           "max_years": None, "life_or_death": False, "cognizable": True,  "bailable": True},  # 3 months
    "125(b)":  {"offence": "Causing grievous hurt by such act",                 "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": True},

    # ---------- Table 4: Wrongful Restraint, Confinement, Assault, Kidnapping, Trafficking ----------
    "126(2)":  {"offence": "Wrongful restraint",                               "max_years": None, "life_or_death": False, "cognizable": True,  "bailable": True},  # 1 month
    "127(2)":  {"offence": "Wrongful confinement",                             "max_years": 1,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "127(3)":  {"offence": "Wrongful confinement for 3+ days",                 "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "127(4)":  {"offence": "Wrongful confinement for 10+ days",                "max_years": 5,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "131":     {"offence": "Assault/criminal force otherwise than on grave provocation", "max_years": None, "life_or_death": False, "cognizable": False, "bailable": True},  # 3 months
    "132":     {"offence": "Assault to deter public servant",                  "max_years": 2,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "137(2)":  {"offence": "Kidnapping",                                       "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "139(1)":  {"offence": "Kidnapping a child for begging",                   "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "140(1)":  {"offence": "Kidnapping/abducting to murder",                   "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "140(2)":  {"offence": "Kidnapping for ransom",                            "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "143(2)":  {"offence": "Trafficking of person",                            "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "143(4)":  {"offence": "Trafficking of a child",                           "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "145":     {"offence": "Habitual dealing in slaves",                       "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "146":     {"offence": "Unlawful compulsory labour",                       "max_years": 1,    "life_or_death": False, "cognizable": True,  "bailable": True},

    # ---------- Table 5: Sexual Offences ----------
    "64(1)":   {"offence": "Punishment for rape",                              "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "64(2)":   {"offence": "Rape by police/public servant/authority/near relative", "max_years": None, "life_or_death": True, "cognizable": True, "bailable": False},
    "65(1)":   {"offence": "Rape of woman under 16",                          "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "65(2)":   {"offence": "Rape of woman under 12",                          "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "66":      {"offence": "Rape causing death / vegetative state",           "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "67":      {"offence": "Intercourse by husband during separation",        "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "68":      {"offence": "Intercourse by person in authority",              "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "69":      {"offence": "Sexual intercourse by deceitful means/false promise to marry", "max_years": 10, "life_or_death": False, "cognizable": True, "bailable": False},
    "70(1)":   {"offence": "Gang rape",                                       "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "70(2)":   {"offence": "Gang rape of woman under 18",                     "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "71":      {"offence": "Repeat offenders (sexual offences)",              "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "72(1)":   {"offence": "Disclosure of victim's identity",                 "max_years": 2,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "74":      {"offence": "Assault on woman with intent to outrage modesty", "max_years": 5,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "75(2)":   {"offence": "Sexual harassment (physical/demand/pornography)","max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "75(3)":   {"offence": "Sexual harassment (sexually coloured remark)",    "max_years": 1,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "76":      {"offence": "Assault with intent to disrobe",                  "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "77":      {"offence": "Voyeurism",                                       "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},  # covers both first (1-3yr, bailable) and repeat (3-7yr, non-bailable); flagged in notes
    "78(2)":   {"offence": "Stalking",                                        "max_years": 5,    "life_or_death": False, "cognizable": True,  "bailable": False},  # covers both first (3yr, bailable) and repeat (5yr, non-bailable); flagged in notes
    "79":      {"offence": "Insulting modesty of a woman (word/gesture)",     "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": True},

    # ---------- Table 6: Offences Against Women & Children ----------
    "80(2)":   {"offence": "Dowry death",                                     "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "81":      {"offence": "Cohabitation by deceitfully inducing belief of marriage", "max_years": 10, "life_or_death": False, "cognizable": False, "bailable": False},
    "82(1)":   {"offence": "Bigamy",                                          "max_years": 7,    "life_or_death": False, "cognizable": False, "bailable": True},
    "82(2)":   {"offence": "Bigamy with concealment",                        "max_years": 10,   "life_or_death": False, "cognizable": False, "bailable": True},
    "83":      {"offence": "Marriage ceremony fraudulently gone through",     "max_years": 7,    "life_or_death": False, "cognizable": False, "bailable": False},
    "84":      {"offence": "Enticing/detaining a married woman",              "max_years": 2,    "life_or_death": False, "cognizable": False, "bailable": True},
    "85":      {"offence": "Cruelty by husband or relative",                  "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "87":      {"offence": "Kidnap/abduct woman to compel marriage",          "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "88":      {"offence": "Causing miscarriage",                            "max_years": 7,    "life_or_death": False, "cognizable": False, "bailable": True},  # up to 3yr normally, 7yr if quick with child
    "89":      {"offence": "Miscarriage without woman's consent",             "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "90(1)":   {"offence": "Death caused by act to cause miscarriage",        "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "93":      {"offence": "Exposure/abandonment of child under 12",          "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "94":      {"offence": "Concealment of birth by secret disposal",         "max_years": 2,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "95":      {"offence": "Hiring/engaging a child to commit an offence",    "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "96":      {"offence": "Procuration of child",                           "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "98":      {"offence": "Selling child for prostitution",                 "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},
    "99":      {"offence": "Buying child for prostitution",                  "max_years": 14,   "life_or_death": False, "cognizable": True,  "bailable": False},

    # ---------- Table 7: Property Offences ----------
    "303(2)":  {"offence": "Theft",                                          "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "304(2)":  {"offence": "Snatching",                                      "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "305":     {"offence": "Theft in dwelling house/transport/place of worship", "max_years": 7, "life_or_death": False, "cognizable": True, "bailable": False},
    "306":     {"offence": "Theft by clerk or servant",                      "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "308(2)":  {"offence": "Extortion",                                      "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "308(5)":  {"offence": "Extortion by putting in fear of death/grievous hurt", "max_years": 10, "life_or_death": False, "cognizable": True, "bailable": False},
    "309(4)":  {"offence": "Robbery",                                        "max_years": 10,   "life_or_death": False, "cognizable": True,  "bailable": False},  # 14 if on highway at night
    "309(5)":  {"offence": "Attempt to commit robbery",                      "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "310(2)":  {"offence": "Dacoity",                                        "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "310(3)":  {"offence": "Dacoity with murder",                            "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "314":     {"offence": "Dishonest misappropriation of property",         "max_years": 2,    "life_or_death": False, "cognizable": False, "bailable": True},
    "316(2)":  {"offence": "Criminal breach of trust",                       "max_years": 5,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "316(3)":  {"offence": "CBT by carrier",                                 "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "316(4)":  {"offence": "CBT by clerk or servant",                        "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "316(5)":  {"offence": "CBT by public servant/banker/agent",             "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "317(2)":  {"offence": "Dishonestly receiving stolen property",          "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "317(4)":  {"offence": "Habitually dealing in stolen property",          "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "318(2)":  {"offence": "Cheating",                                      "max_years": 3,    "life_or_death": False, "cognizable": False, "bailable": True},
    "318(3)":  {"offence": "Cheating a person whose interest offender bound to protect", "max_years": 5, "life_or_death": False, "cognizable": False, "bailable": True},
    "318(4)":  {"offence": "Cheating and dishonestly inducing delivery of property (old 420)", "max_years": 7, "life_or_death": False, "cognizable": True, "bailable": False},
    "319(2)":  {"offence": "Cheating by personation",                       "max_years": 5,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "324(2)":  {"offence": "Mischief",                                       "max_years": None, "life_or_death": False, "cognizable": False, "bailable": True},  # 6 months
    "324(4)":  {"offence": "Mischief causing damage 20,000-1 lakh",          "max_years": 2,    "life_or_death": False, "cognizable": False, "bailable": True},
    "326(g)":  {"offence": "Mischief by fire/explosive to destroy house",    "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "329(3)":  {"offence": "Criminal trespass",                             "max_years": None, "life_or_death": False, "cognizable": True,  "bailable": True},  # 3 months
    "329(4)":  {"offence": "House-trespass",                                "max_years": 1,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "331(2)":  {"offence": "Lurking house-trespass/house-breaking by night", "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "332(a)":  {"offence": "House-trespass to commit offence punishable with death", "max_years": None, "life_or_death": True, "cognizable": True, "bailable": False},

    # ---------- Table 8: Document, Forgery & Property Mark Offences ----------
    "336(2)":  {"offence": "Forgery",                                       "max_years": 2,    "life_or_death": False, "cognizable": False, "bailable": True},
    "336(3)":  {"offence": "Forgery for purpose of cheating",               "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "336(4)":  {"offence": "Forgery for harming reputation",                "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "337":     {"offence": "Forgery of court record/public register",       "max_years": 7,    "life_or_death": False, "cognizable": False, "bailable": False},
    "338":     {"offence": "Forgery of valuable security/will",             "max_years": None, "life_or_death": True,  "cognizable": False, "bailable": False},
    "339":     {"offence": "Possessing forged document intending to use as genuine (valuable security type)", "max_years": None, "life_or_death": True, "cognizable": False, "bailable": True},
    "340(2)":  {"offence": "Using as genuine a forged document",            "max_years": None, "life_or_death": False, "cognizable": True,  "bailable": True},  # same as forgery of that document — varies
    "344":     {"offence": "Falsification of accounts",                    "max_years": 7,    "life_or_death": False, "cognizable": False, "bailable": True},
    "178":     {"offence": "Counterfeiting currency/bank notes",           "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "347(1)":  {"offence": "Counterfeiting a property mark used by another","max_years": 2,    "life_or_death": False, "cognizable": False, "bailable": True},

    # ---------- Table 9: Public Tranquillity ----------
    "189(2)":  {"offence": "Being member of unlawful assembly",             "max_years": None, "life_or_death": False, "cognizable": True,  "bailable": True},  # 6 months
    "189(4)":  {"offence": "Joining unlawful assembly with deadly weapon",  "max_years": 2,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "191(2)":  {"offence": "Rioting",                                      "max_years": 2,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "191(3)":  {"offence": "Rioting armed with deadly weapon",              "max_years": 5,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "194(2)":  {"offence": "Affray",                                       "max_years": None, "life_or_death": False, "cognizable": True,  "bailable": True},  # 1 month
    "195(1)":  {"offence": "Assaulting/obstructing public servant suppressing riot", "max_years": 3, "life_or_death": False, "cognizable": True, "bailable": True},
    "196(1)":  {"offence": "Promoting enmity between groups",              "max_years": 5,    "life_or_death": False, "cognizable": True,  "bailable": False},  # 3yr normally, 5 if in place of worship
    "197(1)":  {"offence": "Imputations prejudicial to national integration","max_years": 5,   "life_or_death": False, "cognizable": True,  "bailable": False},

    # ---------- Table 10: Offences Against the State ----------
    "147":     {"offence": "Waging war against Government of India",       "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "148":     {"offence": "Conspiracy to commit offences against State",   "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "149":     {"offence": "Collecting arms to wage war",                  "max_years": None, "life_or_death": True,  "cognizable": True,  "bailable": False},
    "152":     {"offence": "Act endangering sovereignty, unity, integrity (former sedition)", "max_years": None, "life_or_death": True, "cognizable": True, "bailable": False},
    "151":     {"offence": "Assaulting President/Governor to compel/restrain power", "max_years": 7, "life_or_death": False, "cognizable": True, "bailable": False},
    "223":     {"offence": "Disobedience to order duly promulgated by public servant (violation of S.163 BNSS order)", "max_years": 1, "life_or_death": False, "cognizable": True, "bailable": True},

    # ---------- Table 11: Public Health, Safety, Decency, Religion ----------
    "271":     {"offence": "Negligent act likely to spread infection dangerous to life", "max_years": None, "life_or_death": False, "cognizable": True, "bailable": True},  # 6 months
    "272":     {"offence": "Malignant act likely to spread infection",     "max_years": 2,    "life_or_death": False, "cognizable": True,  "bailable": True},
    "274":     {"offence": "Adulteration of food/drink",                  "max_years": None, "life_or_death": False, "cognizable": False, "bailable": True},  # 6 months
    "276":     {"offence": "Adulteration of drugs",                       "max_years": 1,    "life_or_death": False, "cognizable": False, "bailable": False},
    "281":     {"offence": "Rash driving on public way",                  "max_years": None, "life_or_death": False, "cognizable": True,  "bailable": True},  # 6 months
    "283":     {"offence": "Exhibition of false light/mark/buoy endangering navigation", "max_years": 7, "life_or_death": False, "cognizable": True, "bailable": True},
    "292":     {"offence": "Public nuisance (not otherwise provided)",     "max_years": None, "life_or_death": False, "cognizable": False, "bailable": True},  # fine only
    "294(2)":  {"offence": "Sale of obscene books/objects",                "max_years": 5,    "life_or_death": False, "cognizable": True,  "bailable": True},  # 2yr first, 5yr subsequent
    "295":     {"offence": "Sale of obscene objects to a child",           "max_years": 7,    "life_or_death": False, "cognizable": True,  "bailable": True},  # 3yr first, 7yr subsequent
    "296":     {"offence": "Obscene acts and songs",                       "max_years": None, "life_or_death": False, "cognizable": True,  "bailable": True},  # 3 months
    "298":     {"offence": "Defiling place of worship",                    "max_years": 2,    "life_or_death": False, "cognizable": True,  "bailable": False},
    "299":     {"offence": "Deliberate acts to outrage religious feelings", "max_years": 3,    "life_or_death": False, "cognizable": True,  "bailable": False},

    # ---------- Table 12: Criminal Intimidation, Insult, Defamation; Conspiracy & Abetment ----------
    "351(2)":  {"offence": "Criminal intimidation",                        "max_years": 2,    "life_or_death": False, "cognizable": False, "bailable": True},
    "351(3)":  {"offence": "Criminal intimidation by threat of death/grievous hurt", "max_years": 7, "life_or_death": False, "cognizable": False, "bailable": True},  # NOTE: some states make this cognizable/non-bailable by amendment — check state notification
    "351(4)":  {"offence": "Criminal intimidation by anonymous communication", "max_years": 2, "life_or_death": False, "cognizable": False, "bailable": True},
    "352":     {"offence": "Intentional insult to provoke breach of peace", "max_years": 2,    "life_or_death": False, "cognizable": False, "bailable": True},
    "353(1)":  {"offence": "Statements conducing to public mischief",      "max_years": 3,    "life_or_death": False, "cognizable": False, "bailable": False},
    "353(3)":  {"offence": "False statement in place of worship to create enmity", "max_years": 5, "life_or_death": False, "cognizable": True, "bailable": False},
    "356(2)":  {"offence": "Defamation",                                   "max_years": 2,    "life_or_death": False, "cognizable": False, "bailable": True},
    "49":      {"offence": "Abetment of any offence (act abetted committed)", "max_years": None, "life_or_death": False, "cognizable": False, "bailable": True},  # same as offence abetted — varies
    "55":      {"offence": "Abetment of offence punishable with death/life (if not committed)", "max_years": 7, "life_or_death": False, "cognizable": False, "bailable": False},  # 14yr if harm caused
    "61(2)(a)":{"offence": "Criminal conspiracy (serious offence)",        "max_years": None, "life_or_death": False, "cognizable": False, "bailable": False},  # same as abetment of object offence — varies
    "62":      {"offence": "Attempt to commit offence punishable with life/imprisonment", "max_years": None, "life_or_death": False, "cognizable": False, "bailable": False},  # up to half the longest term — varies
}


def get_max_years_from_sections(sections_cited):
    """Given a list of section strings extracted from a document,
    return the highest max_years found among recognized sections,
    or 'LIFE_OR_DEATH' if any cited section carries life/death,
    or None if no cited section is recognized."""
    if not sections_cited:
        return None
    candidates = []
    for sec in sections_cited:
        clean = str(sec).strip()
        data = BNS_SECTION_DATA.get(clean)
        if data is None:
            continue
        if data["life_or_death"]:
            return "LIFE_OR_DEATH"
        if data["max_years"] is not None:
            candidates.append(data["max_years"])
    return max(candidates) if candidates else None
