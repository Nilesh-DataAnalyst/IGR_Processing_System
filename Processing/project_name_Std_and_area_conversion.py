# -*- coding: utf-8 -*-
"""
Combined pipeline (compact version):

PART A - Hybrid project-name entity resolution
  1. Parse list-like project names.
  2. Normalize legal/society suffixes.
  3. Character n-gram TF-IDF vectors.
  4. Candidate pairs via cosine nearest neighbours.
  5. Reject unsafe pairs (number/phase/first-token/core-name rules).
  6. Complete-linkage style greedy clustering.
  7. Row-level confidence, reason, manual-review columns.
  8. Preserve initials (S L K / M S / K P C T).
  9. Remove phase identifiers and legal suffixes (Bldg/Coop/Co Op Hos Soc).
  10. Normalize Apartment/Apartments.

PART B - Area-unit conversion (applied to the clustered dataframe)
  1. Clean/normalize raw area text.
  2. Parse Hectare-Are-Sq.m / Hectare-Are / Are-only / Sq.m / Sq.ft formats.
  3. Convert everything to square metres.
  4. Track conversion source, status and completion flags per area column.
  5. Build a review sheet for unrecognized values.
  6. Run a quick self-test suite.
  7. Export a formatted, multi-sheet Excel workbook.

pip install pandas numpy rapidfuzz scikit-learn openpyxl xlsxwriter tqdm
"""

import ast, datetime, re, sys
from pathlib import Path
import numpy as np
import pandas as pd
from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neighbors import NearestNeighbors
from tqdm.auto import tqdm

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure local directory is on sys.path for static dictionary imports
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from static import result_dict, word_number_dict
except ImportError:
    try:
        # pyrefly: ignore [missing-import]
        from required_files.static import result_dict, word_number_dict
    except ImportError:
        result_dict, word_number_dict = {}, {}

# ============================================================
# PIPELINE CONFIG - SINGLE INPUT & OUTPUT PATH
# ============================================================
COL_PROJECT, COL_PROJECT_LIST = "final_project_name", "project_name_list"
COL_PROJECT_TEXT, COL_CLEANED_PROJECT = "project_name_text", "Modified_Project_Name_1"

MINIMUM_NAME_LENGTH = 3
CANDIDATE_COSINE_THRESHOLD = 0.68
MAX_CANDIDATES_PER_NAME = 40
TFIDF_ACCEPT_THRESHOLD = 0.82
CORE_FUZZY_THRESHOLD = FIRST_TOKEN_THRESHOLD = TOKEN_SET_THRESHOLD = 88
SHORT_CORE_LENGTH = 4
SHORT_CORE_FUZZY_THRESHOLD = 96
SHORT_TFIDF_THRESHOLD = 0.92
REVIEW_CONFIDENCE_THRESHOLD = 90.0
SEPARATE_BLANK_ROWS = True
PRESERVE_NUMERIC_IDENTIFIERS = True
PRESERVE_PHASE_IDENTIFIERS = False
PRESERVE_WING_IDENTIFIERS = True
REMOVE_PHASE_IDENTIFIERS = True

MULTI_SPACE_PATTERN = re.compile(r"\s+")
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9\s]", flags=re.IGNORECASE)
STANDALONE_SINGLE_CHARACTER_PATTERN = re.compile(r"\b[a-zA-Z]\b")
STANDALONE_NOISE_WORDS = {"a", "an", "and", "or", "of", "in", "on", "at", "to", "for", "with", "by"}
WING_PATTERN = re.compile(r"\b(?:wing|block)\s*[-:]?\s*([a-z0-9]+)\b", flags=re.IGNORECASE)
PHASE_PATTERN = re.compile(r"\b(?:phase|ph)\s*[-:]?\s*([a-z0-9]+)\b", flags=re.IGNORECASE)

GENERIC_PROJECT_NAMES = {
    "", "apartment", "apartments", "building", "buildings", "society",
    "housing society", "commercial complex", "residential project", "project",
    "projects", "premises", "chawl", "house", "houses", "bungalow", "bungalows",
    "plot", "plots", "flat", "flats", "residency", "residential", "complex",
}

GENERIC_SUFFIX_WORDS = {
    "apartment", "apartments", "apt", "apts", "enclave", "heights", "height",
    "residency", "residencies", "residence", "homes", "home", "villa", "villas",
    "complex", "commercial", "building", "buildings", "tower", "towers", "wing",
    "wings", "block", "blocks", "phase", "project", "projects", "chawl", "nivas",
    "society", "premises", "housing", "co", "op", "coop", "operative", "hsg",
    "chs", "chsl", "ltd", "limited",
}

VARIANT_NORMALIZATION_RULES = [
    (r"\bapartments\b", "apartment"), (r"\bapts\b", "apartment"), (r"\bapt\b", "apartment"),
    (r"\bbldgs\b", "building"), (r"\bbldg\b", "building"),
    (r"\bhos\s+soc\b", "housing society"), (r"\bhous\s+soc\b", "housing society"),
    (r"\bhsg\s+soc\b", "housing society"), (r"\bhsg\s+society\b", "housing society"),
    (r"\bcoop\b", "co operative"), (r"\bapartments\b", "apartment"),
    (r"\bwoods\b", "wood"), (r"\btowers\b", "tower"), (r"\bbuildings\b", "building"),
    (r"\bvillas\b", "villa"), (r"\bresidencies\b", "residency"),
    (r"\bno\s+(?=\d+\b)", ""),
]

REMOVE_TERMS = [
    "housing society limited", "co-op housing society ltd", "coop soc",
    "co op hos soc", "co op hous soc", "co op housing soc", "coophousing soc ltd",
    "coop hous so li", "cooperative housing society limited", "co-op house",
    "co hous ltd", "coop soc ltd", "coop housing soc", "house co-op housing society",
    "op house li", "chs ltd mg", "soc coop hous soc ltd", "co-operative housing society",
    "co-operative housing society ltd", "coop housing soc ltd", "coop housing soc ltd mg",
    "co op hsg soc ltd", "coop housing society", "coop hsg soc ltd", "co op hous soc ltd",
    "cooperative housing society ltd", "oop housing soc ltd", "co-operative housing society limited",
    "co op housing society", "co op housing society ltd", "cooperative housing society",
    "co op ho so sa li", "co ho so li", "co ho so ltd", "co op hsg society", "co op hsg soc",
    "co op society", "operative housing society", "hsg society", "housing society",
    "sahakari gruhrakshana sanstha maryadit", "sahakari gruhrachna sanstha",
    "sahakari gruhanirman sanstha", "gruh rachna sanstha", "sah grih rachna sanstha",
    "sah grihrachna sanstha", "condominium", "row houses condominium",
    "residential project", "premises", "chs ltd", "chs", "chsl", "ltd", "limited",
    "building", "buildings", "bldg", "bldgs", "coop", "co op", "co operative",
]

TRUNCATE_KEYWORDS = [
    "sahakari", "cooperative", "co operative", "co-operative", "co op housing",
    "co-op housing", "co-op-housing", "co op hsg", "co-op hsg", "co ho so",
    "co op ho so", "co op hsg society", "co op hsg soc", "co op society",
    "gruhrachna", "gruhrachana", "gruhnirman", "gruhrakshana", "gruh rachna",
    "gruhaprakalp", "grih prakalp", "housing society", "hsg society",
    "operative housing society", "premises", "building", "buildings", "ltd", "limited",
]

# ============================================================
# PART A - NORMALIZATION HELPERS
# ============================================================
def normalize_term(term):
    term = re.sub(r"[^a-z0-9\s]", " ", str(term).lower())
    return MULTI_SPACE_PATTERN.sub(" ", term).strip()

NORMALIZED_REMOVE_TERMS = sorted(
    {normalize_term(t) for t in REMOVE_TERMS if normalize_term(t)}, key=len, reverse=True
)
REMOVE_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in NORMALIZED_REMOVE_TERMS) + r")\b",
    flags=re.IGNORECASE,
)

def is_missing(value):
    if value is None:
        return True
    if isinstance(value, (list, tuple, np.ndarray, set)):
        return len(value) == 0
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False

def safe_parse_list(value):
    if is_missing(value):
        return []
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            out.extend(safe_parse_list(item))
        return out
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple, set)):
                out = []
                for item in parsed:
                    out.extend(safe_parse_list(item))
                return out
            if parsed is not None:
                return [str(parsed).strip()]
        except (ValueError, SyntaxError, TypeError):
            pass
    text = text.strip("[]").strip()
    parts = re.split(r"\s*(?:,|;|\||\n|\r)\s*", text)
    return [MULTI_SPACE_PATTERN.sub(" ", p.strip().strip("'\"")).strip() for p in parts if p.strip().strip("'\"")]

def remove_repeated_name_sequence(name):
    words = str(name).split()
    if len(words) < 4:
        return str(name).strip()
    lower_words = [w.lower() for w in words]
    first_word = lower_words[0]
    for i in range(1, len(lower_words)):
        if lower_words[i] == first_word:
            prefix = " ".join(words[:i]).strip()
            if len(prefix) >= 4:
                return prefix
    return str(name).strip()

def truncate_at_keywords(name):
    earliest = None
    for kw in TRUNCATE_KEYWORDS:
        kw = normalize_term(kw)
        if not kw:
            continue
        m = re.search(r"\b" + re.escape(kw) + r"\b", name, flags=re.IGNORECASE)
        if not m:
            continue
        prefix = name[:m.start()].strip()
        if len(prefix) >= 3 and (earliest is None or m.start() < earliest):
            earliest = m.start()
    return name[:earliest].strip() if earliest is not None else name

def clean_name(name):
    if not isinstance(name, str):
        return ""
    name = name.strip()
    if not name:
        return ""
    name = re.sub(r"चाळी|चाळ", " Chawl ", name, flags=re.UNICODE)
    name = re.sub(r"\b(?:chali|chal)\b", "Chawl", name, flags=re.IGNORECASE)
    name = re.sub(r"[\._/\\\-]+", " ", name)
    name = name.lower()
    name = NON_ALNUM_PATTERN.sub(" ", name)
    name = MULTI_SPACE_PATTERN.sub(" ", name).strip()

    for pattern, replacement in VARIANT_NORMALIZATION_RULES:
        name = re.sub(pattern, replacement, name, flags=re.IGNORECASE)

    if REMOVE_PHASE_IDENTIFIERS:
        name = re.sub(r"\b(?:phase|ph)\s*(?:no\s*)?[a-z0-9]+\b", " ", name, flags=re.IGNORECASE)

    name = MULTI_SPACE_PATTERN.sub(" ", name).strip()
    if not name:
        return ""

    name = remove_repeated_name_sequence(name)
    name = truncate_at_keywords(name)
    name = REMOVE_PATTERN.sub(" ", name)

    residual_patterns = [
        r"\bco\s+op\s+hsg\s+society\b", r"\bco\s+op\s+hsg\s+soc\b",
        r"\bco\s+op\s+housing\s+society\b", r"\bco\s+housing\s+society\b",
        r"\bco\s+ho\s+so\s+li\b", r"\bco\s+op\s+ho\s+so\s+sa\s+li\b",
        r"\boperative\s+housing\s+society\b", r"\bsah\s+grihrachna\s+sanstha\b",
        r"\bsahakari\s+gruhrachna\s+sanstha\b", r"\bsahakari\s+gruhanirman\s+sanstha\b",
        r"\bgruh\s+rachna\s+sanstha\b", r"\bhousing\s+society\b", r"\bhsg\s+society\b",
        r"\bhsg\s+soc\b", r"\bpremises\b", r"\bbuilding(?:s)?\b", r"\bchs\b",
        r"\bchsl\b", r"\bltd\b", r"\blimited\b",
    ]
    for pattern in residual_patterns:
        name = re.sub(pattern, " ", name, flags=re.IGNORECASE)

    tokens = [t for t in name.split() if t.lower() not in STANDALONE_NOISE_WORDS]
    name = MULTI_SPACE_PATTERN.sub(" ", " ".join(tokens)).strip()
    if not name:
        return ""

    roman_numerals = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"}
    words = []
    for w in name.split():
        if w in roman_numerals:
            words.append(w.upper())
        elif w.isdigit():
            words.append(w)
        else:
            words.append(w.capitalize())
    return " ".join(words)

def extract_primary_name(name_list):
    if not isinstance(name_list, list):
        return ""
    cleaned = [clean_name(str(c)) for c in name_list]
    cleaned = [c for c in cleaned if c]
    if not cleaned:
        return ""
    for c in cleaned:
        if c.lower() not in GENERIC_PROJECT_NAMES and len(c) >= MINIMUM_NAME_LENGTH:
            return c
    return cleaned[0]

def create_comparison_key(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower()) if isinstance(name, str) else ""

def tokenize_project_name(name):
    return re.findall(r"[a-z0-9]+", str(name).lower()) if isinstance(name, str) else []

def get_core_tokens(name):
    return [t for t in tokenize_project_name(name) if t not in GENERIC_SUFFIX_WORDS]

def get_core_name(name):
    return " ".join(get_core_tokens(name))

def get_first_core_token(name):
    tokens = get_core_tokens(name)
    return tokens[0] if tokens else ""

def get_numeric_tokens(name):
    return {t for t in tokenize_project_name(name) if t.isdigit()}

def get_phase_identifier(name):
    m = PHASE_PATTERN.search(str(name))
    return m.group(1).lower() if m else ""

def get_wing_identifier(name):
    m = WING_PATTERN.search(str(name))
    return m.group(1).lower() if m else ""

def conflicting_identifiers(name_1, name_2):
    if PRESERVE_NUMERIC_IDENTIFIERS:
        n1, n2 = get_numeric_tokens(name_1), get_numeric_tokens(name_2)
        if n1 and n2 and n1 != n2:
            return "different numeric identifiers"
    if PRESERVE_PHASE_IDENTIFIERS:
        p1, p2 = get_phase_identifier(name_1), get_phase_identifier(name_2)
        if p1 and p2 and p1 != p2:
            return "different phase identifiers"
    if PRESERVE_WING_IDENTIFIERS:
        w1, w2 = get_wing_identifier(name_1), get_wing_identifier(name_2)
        if w1 and w2 and w1 != w2:
            return "different wing/block identifiers"
    return ""

# ============================================================
# PART A - PAIR SCORING
# ============================================================
def pair_metrics(name_1, name_2, tfidf_similarity):
    core_1, core_2 = get_core_name(name_1), get_core_name(name_2)
    first_1, first_2 = get_first_core_token(name_1), get_first_core_token(name_2)
    compact_1, compact_2 = create_comparison_key(name_1), create_comparison_key(name_2)

    overall_fuzzy = fuzz.ratio(compact_1, compact_2)
    core_fuzzy = fuzz.ratio(core_1, core_2) if core_1 and core_2 else 0.0
    first_token_fuzzy = fuzz.ratio(first_1, first_2) if first_1 and first_2 else 0.0
    token_set_fuzzy = fuzz.token_set_ratio(
        " ".join(tokenize_project_name(name_1)), " ".join(tokenize_project_name(name_2))
    )
    weighted_confidence = (
        tfidf_similarity * 100.0 * 0.40 + core_fuzzy * 0.30
        + first_token_fuzzy * 0.20 + token_set_fuzzy * 0.10
    )
    return {
        "tfidf_similarity": float(tfidf_similarity),
        "overall_fuzzy": float(overall_fuzzy),
        "core_fuzzy": float(core_fuzzy),
        "first_token_fuzzy": float(first_token_fuzzy),
        "token_set_fuzzy": float(token_set_fuzzy),
        "confidence": float(round(weighted_confidence, 2)),
    }

def evaluate_pair(name_1, name_2, tfidf_similarity):
    if create_comparison_key(name_1) == create_comparison_key(name_2):
        return {"accepted": True, "confidence": 100.0, "reason": "exact normalized match",
                "metrics": pair_metrics(name_1, name_2, 1.0)}

    conflict = conflicting_identifiers(name_1, name_2)
    if conflict:
        return {"accepted": False, "confidence": 0.0, "reason": conflict,
                "metrics": pair_metrics(name_1, name_2, tfidf_similarity)}

    core_1, core_2 = get_core_name(name_1), get_core_name(name_2)
    if not core_1 or not core_2:
        return {"accepted": False, "confidence": 0.0, "reason": "missing meaningful core name",
                "metrics": pair_metrics(name_1, name_2, tfidf_similarity)}

    metrics = pair_metrics(name_1, name_2, tfidf_similarity)
    shortest_core_length = min(len(core_1.replace(" ", "")), len(core_2.replace(" ", "")))

    if shortest_core_length <= SHORT_CORE_LENGTH:
        accepted = (
            metrics["tfidf_similarity"] >= SHORT_TFIDF_THRESHOLD
            and metrics["core_fuzzy"] >= SHORT_CORE_FUZZY_THRESHOLD
            and metrics["first_token_fuzzy"] >= SHORT_CORE_FUZZY_THRESHOLD
        )
        reason = "strict short-core match" if accepted else "short core name did not meet strict threshold"
        return {"accepted": accepted, "confidence": metrics["confidence"] if accepted else 0.0,
                "reason": reason, "metrics": metrics}

    accepted = (
        metrics["tfidf_similarity"] >= TFIDF_ACCEPT_THRESHOLD
        and metrics["core_fuzzy"] >= CORE_FUZZY_THRESHOLD
        and metrics["first_token_fuzzy"] >= FIRST_TOKEN_THRESHOLD
        and metrics["token_set_fuzzy"] >= TOKEN_SET_THRESHOLD
    )
    reason = "TF-IDF and core-name rules passed" if accepted else "similarity rules not satisfied"
    return {"accepted": accepted, "confidence": metrics["confidence"] if accepted else 0.0,
            "reason": reason, "metrics": metrics}

# ============================================================
# PART A - TF-IDF CANDIDATE GENERATION
# ============================================================
def build_candidate_lookup(unique_names):
    if not unique_names:
        return {}, None, None

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), lowercase=True, min_df=1, norm="l2")
    matrix = vectorizer.fit_transform(unique_names)

    neighbour_count = min(MAX_CANDIDATES_PER_NAME + 1, len(unique_names))
    nn = NearestNeighbors(n_neighbors=neighbour_count, metric="cosine", algorithm="brute", n_jobs=-1)
    nn.fit(matrix)
    distances, indices = nn.kneighbors(matrix)

    candidate_lookup = {}
    for row_index, name in enumerate(unique_names):
        candidates = []
        for distance, candidate_index in zip(distances[row_index], indices[row_index]):
            if candidate_index == row_index:
                continue
            similarity = 1.0 - float(distance)
            if similarity < CANDIDATE_COSINE_THRESHOLD:
                continue
            candidates.append((unique_names[candidate_index], similarity))
        candidate_lookup[name] = candidates

    return candidate_lookup, matrix, vectorizer

def tfidf_pair_similarity(name_1, name_2, name_to_index, matrix):
    i1, i2 = name_to_index[name_1], name_to_index[name_2]
    return float(matrix[i1].multiply(matrix[i2]).sum())

# ============================================================
# PART A - COMPLETE-LINKAGE CLUSTERING
# ============================================================
def cluster_names_complete_linkage(unique_names, name_frequencies):
    if not unique_names:
        return {}, {}, [], {}

    ordered_names = sorted(
        unique_names,
        key=lambda name: (-name_frequencies.get(name, 0), -len(name), name.lower()),
    )

    candidate_lookup, matrix, _ = build_candidate_lookup(ordered_names)
    name_to_index = {name: i for i, name in enumerate(ordered_names)}
    candidate_name_sets = {name: {c for c, _ in cands} for name, cands in candidate_lookup.items()}

    clusters = []
    name_to_cluster = {}
    pair_review_rows = []

    for name in tqdm(ordered_names, desc="Hybrid project clustering"):
        best_cluster_index = None
        best_cluster_confidence = -1.0

        for cluster_index, cluster in enumerate(clusters):
            representative = cluster["representative"]

            if (
                representative not in candidate_name_sets.get(name, set())
                and name not in candidate_name_sets.get(representative, set())
                and create_comparison_key(name) != create_comparison_key(representative)
            ):
                continue

            member_confidences = []
            all_pass = True

            for member in cluster["members"]:
                similarity = tfidf_pair_similarity(name, member, name_to_index, matrix)
                result = evaluate_pair(name, member, similarity)

                pair_review_rows.append({
                    "name_1": name, "name_2": member, "accepted": result["accepted"],
                    "confidence_score": result["confidence"], "reason": result["reason"],
                    **result["metrics"],
                })

                if not result["accepted"]:
                    all_pass = False
                    break
                member_confidences.append(result["confidence"])

            if not all_pass or not member_confidences:
                continue

            cluster_confidence = min(member_confidences)
            if cluster_confidence > best_cluster_confidence:
                best_cluster_index = cluster_index
                best_cluster_confidence = cluster_confidence

        if best_cluster_index is None:
            clusters.append({"representative": name, "members": [name]})
            name_to_cluster[name] = len(clusters) - 1
        else:
            clusters[best_cluster_index]["members"].append(name)
            name_to_cluster[name] = best_cluster_index

    cluster_metadata = {}
    for cluster_index, cluster in enumerate(clusters):
        members = cluster["members"]
        canonical = sorted(
            members,
            key=lambda v: (-name_frequencies.get(v, 0), -len(get_core_name(v)), -len(v), v.lower()),
        )[0]
        cluster["canonical"] = canonical

        member_confidence, member_reason = {}, {}
        for member in members:
            if member == canonical:
                member_confidence[member] = 100.0
                member_reason[member] = "canonical / exact cluster representative"
                continue
            similarity = tfidf_pair_similarity(member, canonical, name_to_index, matrix)
            result = evaluate_pair(member, canonical, similarity)
            member_confidence[member] = result["confidence"] if result["accepted"] else 0.0
            member_reason[member] = result["reason"]

        positive_scores = [s for s in member_confidence.values() if s > 0]
        cluster_min_confidence = min(positive_scores) if positive_scores else 100.0

        cluster_metadata[cluster_index] = {
            "canonical": canonical, "members": members,
            "member_confidence": member_confidence, "member_reason": member_reason,
            "cluster_min_confidence": round(cluster_min_confidence, 2),
        }

    pair_review_df = pd.DataFrame(pair_review_rows)
    return name_to_cluster, cluster_metadata, clusters, pair_review_df

def confidence_label(score, is_singleton=False):
    if is_singleton:
        return "Unique / no accepted match"
    if score >= 97:
        return "Very High"
    if score >= 93:
        return "High"
    if score >= REVIEW_CONFIDENCE_THRESHOLD:
        return "Medium"
    return "Review"

def format_excel_sheet(worksheet, freeze_panes="A2"):
    """openpyxl-style formatter, used for the Part A workbook."""
    worksheet.freeze_panes = freeze_panes
    worksheet.auto_filter.ref = worksheet.dimensions
    for column_cells in worksheet.columns:
        column_letter = column_cells[0].column_letter
        max_len = 0
        for cell in column_cells[:500]:
            max_len = max(max_len, len("" if cell.value is None else str(cell.value)))
        worksheet.column_dimensions[column_letter].width = min(max_len + 2, 45)

# ============================================================
# PART A - MAIN CLUSTERING PIPELINE
# ============================================================
def run_project_clustering(input_path_val=None, input_df=None):

    if input_df is not None:
        print("Using dataframe received from main script...")
        df = input_df.copy()

    else:
        input_path = Path(input_path_val)

        if not input_path.exists():
            raise FileNotFoundError(
                f"Input file not found:\n{input_path}"
            )

        print(f"Reading input file:\n{input_path}")

        df = pd.read_excel(
            input_path,
            dtype=object
        )

    df.columns = df.columns.astype(str).str.strip()

    if COL_PROJECT not in df.columns:
        if "project_name_en" in df.columns:
            print(f"'{COL_PROJECT}' not found in columns. Deriving from 'project_name_en' and 'building_name_en'...")
            p_missing = df["project_name_en"].replace(r"^\s*$", pd.NA, regex=True).isna()
            bldg = df["building_name_en"] if "building_name_en" in df.columns else ""
            df[COL_PROJECT] = (
                df["project_name_en"]
                .replace(r"^\s*$", pd.NA, regex=True)
                .fillna(bldg)
            )
            df["final_project_name_status"] = p_missing.map({
                True: "Building Name Considered",
                False: "Project Name Considered",
            })
        else:
            raise ValueError(f"Column '{COL_PROJECT}' was not found.\n\nAvailable columns:\n{list(df.columns)}")

    # 1. Parse and clean
    df[COL_PROJECT_LIST] = df[COL_PROJECT].apply(safe_parse_list)
    df["project_count"] = df[COL_PROJECT_LIST].apply(lambda v: len(v) if isinstance(v, list) else 0)
    df[COL_PROJECT_TEXT] = df[COL_PROJECT_LIST].apply(extract_primary_name)
    df[COL_CLEANED_PROJECT] = df[COL_PROJECT_TEXT].fillna("").astype(str).str.strip()
    df["project_comparison_key"] = df[COL_CLEANED_PROJECT].apply(create_comparison_key)
    df["is_generic_project_name"] = (
        df[COL_CLEANED_PROJECT].fillna("").astype(str).str.lower().str.strip().isin(GENERIC_PROJECT_NAMES)
    )

    # 2. Prepare valid unique names and frequencies
    valid_mask = (
        df["project_comparison_key"].fillna("").str.len().ge(MINIMUM_NAME_LENGTH)
        & ~df["is_generic_project_name"]
    )
    valid_series = df.loc[valid_mask, COL_CLEANED_PROJECT].fillna("").astype(str).str.strip()
    name_frequencies = valid_series.value_counts().to_dict()
    unique_names = valid_series.drop_duplicates().tolist()
    print(f"\nUnique valid cleaned names: {len(unique_names):,}")

    # 3. Hybrid clustering
    name_to_raw_cluster, cluster_metadata, clusters, pair_review_df = cluster_names_complete_linkage(
        unique_names, name_frequencies
    )

    # 4. Assign clusters to rows
    raw_cluster_ids = []
    next_special_cluster = max(name_to_raw_cluster.values(), default=-1) + 1
    generic_cluster_map = {}

    for _, row in df.iterrows():
        cleaned_name = "" if pd.isna(row[COL_CLEANED_PROJECT]) else str(row[COL_CLEANED_PROJECT]).strip()
        comparison_key = "" if pd.isna(row["project_comparison_key"]) else str(row["project_comparison_key"]).strip()
        is_generic = bool(row["is_generic_project_name"])

        if cleaned_name in name_to_raw_cluster and not is_generic:
            raw_cluster_ids.append(name_to_raw_cluster[cleaned_name])
        elif is_generic and comparison_key:
            if comparison_key not in generic_cluster_map:
                generic_cluster_map[comparison_key] = next_special_cluster
                next_special_cluster += 1
            raw_cluster_ids.append(generic_cluster_map[comparison_key])
        else:
            raw_cluster_ids.append(next_special_cluster)
            if SEPARATE_BLANK_ROWS:
                next_special_cluster += 1

    df["_raw_project_cluster"] = raw_cluster_ids

    first_seen = list(dict.fromkeys(df["_raw_project_cluster"].tolist()))
    stable_cluster_map = {raw_id: stable_id for stable_id, raw_id in enumerate(first_seen, start=1)}
    df["project_cluster_id"] = df["_raw_project_cluster"].map(stable_cluster_map).astype("int64")

    # 5. Canonical name, confidence and review fields
    raw_to_canonical, raw_to_cluster_size, raw_to_cluster_min_confidence = {}, {}, {}
    for raw_cluster, metadata in cluster_metadata.items():
        raw_to_canonical[raw_cluster] = metadata["canonical"]
        raw_to_cluster_size[raw_cluster] = len(metadata["members"])
        raw_to_cluster_min_confidence[raw_cluster] = metadata["cluster_min_confidence"]

    for raw_cluster, group in df.groupby("_raw_project_cluster", sort=False):
        if raw_cluster not in raw_to_canonical:
            cleaned_values = group[COL_CLEANED_PROJECT].fillna("").astype(str).str.strip()
            cleaned_values = cleaned_values[cleaned_values.ne("")]
            canonical = cleaned_values.value_counts().index[0] if not cleaned_values.empty else ""
            raw_to_canonical[raw_cluster] = canonical
            raw_to_cluster_size[raw_cluster] = 1
            raw_to_cluster_min_confidence[raw_cluster] = 100.0

    df["project_name_canonical"] = df["_raw_project_cluster"].map(raw_to_canonical).fillna("")
    df["project_name"] = df["project_name_canonical"].copy()

    row_confidences, row_reasons, row_review_flags = [], [], []
    row_confidence_labels, row_cluster_min_confidences = [], []

    for _, row in df.iterrows():
        raw_cluster = row["_raw_project_cluster"]
        cleaned_name = "" if pd.isna(row[COL_CLEANED_PROJECT]) else str(row[COL_CLEANED_PROJECT]).strip()
        canonical = raw_to_canonical.get(raw_cluster, "")
        cluster_size = raw_to_cluster_size.get(raw_cluster, 1)
        cluster_min_confidence = raw_to_cluster_min_confidence.get(raw_cluster, 100.0)

        if not cleaned_name:
            confidence, reason, needs_review, label = 0.0, "blank or invalid cleaned project name", True, "Review"
        elif bool(row["is_generic_project_name"]):
            confidence, reason, needs_review, label = 100.0, "generic project name kept in a separate cluster", False, "Generic"
        elif cleaned_name == canonical:
            confidence, reason, needs_review = 100.0, "exact canonical name", False
            label = confidence_label(confidence, is_singleton=(cluster_size == 1))
        else:
            metadata = cluster_metadata.get(raw_cluster, {})
            confidence = metadata.get("member_confidence", {}).get(cleaned_name, 0.0)
            reason = metadata.get("member_reason", {}).get(cleaned_name, "matched to canonical name")
            needs_review = confidence < REVIEW_CONFIDENCE_THRESHOLD
            label = confidence_label(confidence)

        row_confidences.append(round(float(confidence), 2))
        row_reasons.append(reason)
        row_review_flags.append(needs_review)
        row_confidence_labels.append(label)
        row_cluster_min_confidences.append(round(float(cluster_min_confidence), 2))

    df["project_match_confidence_score"] = row_confidences
    df["project_match_confidence_label"] = row_confidence_labels
    df["project_match_reason"] = row_reasons
    df["cluster_min_confidence_score"] = row_cluster_min_confidences
    df["requires_manual_review"] = row_review_flags
    df.drop(columns=["_raw_project_cluster"], inplace=True)

    # 6. Cluster summary
    summary_rows = []
    for cluster_id, group in df.groupby("project_cluster_id", sort=False):
        canonical = group["project_name_canonical"].iloc[0]
        cleaned_names = group[COL_CLEANED_PROJECT].fillna("").astype(str).str.strip()
        cleaned_names = cleaned_names[cleaned_names.ne("")]
        summary_rows.append({
            "project_cluster_id": cluster_id,
            "project_name_canonical": canonical,
            "total_records": len(group),
            "unique_cleaned_names": cleaned_names.nunique(),
            "cluster_min_confidence_score": group["cluster_min_confidence_score"].min(),
            "requires_manual_review": group["requires_manual_review"].any(),
            "project_variants": " | ".join(sorted(cleaned_names.drop_duplicates().tolist())),
        })
    cluster_summary = pd.DataFrame(summary_rows)

    # 7. Manual review sheet
    manual_review_df = df.loc[
        df["requires_manual_review"],
        [COL_PROJECT, COL_PROJECT_TEXT, COL_CLEANED_PROJECT, "project_cluster_id",
         "project_name_canonical", "project_match_confidence_score",
         "project_match_confidence_label", "project_match_reason", "cluster_min_confidence_score"],
    ].copy()
    manual_review_df.sort_values(by=["project_match_confidence_score", "project_cluster_id"], inplace=True)

    if not pair_review_df.empty:
        pair_review_df.sort_values(by=["accepted", "confidence_score"], ascending=[False, False], inplace=True)

    # 8. Reorder columns
    generated_columns = [
        COL_PROJECT_LIST, COL_PROJECT_TEXT, COL_CLEANED_PROJECT, "project_count",
        "project_comparison_key", "is_generic_project_name", "project_cluster_id",
        "project_name_canonical", "project_name","project_match_confidence_score",
        "project_match_confidence_label", "project_match_reason",
        "cluster_min_confidence_score", "requires_manual_review",
    ]
    original_columns = [c for c in df.columns if c not in generated_columns]
    final_order = []
    for column in original_columns:
        final_order.append(column)
        if column == COL_PROJECT:
            final_order.extend(generated_columns)
    for column in generated_columns:
        if column not in final_order:
            final_order.append(column)
    df = df.reindex(columns=final_order)

    # 9. Console summary
    print("\n" + "=" * 70)
    print("PART A - HYBRID PROJECT-NAME CLUSTERING COMPLETED")
    print("=" * 70)
    print(f"Total records: {len(df):,}")
    print(f"Unique cleaned project names: {df[COL_CLEANED_PROJECT].nunique(dropna=True):,}")
    print(f"Total project clusters: {df['project_cluster_id'].nunique():,}")
    print(f"Rows requiring manual review: {df['requires_manual_review'].sum():,}")

    return df, cluster_summary, manual_review_df, pair_review_df


# ============================================================
# PART B CONFIG - AREA CONVERSION
# ============================================================
SQFT_TO_SQMT = 0.09290304

AREA_COLUMNS = [
    "carpet_area", "builtup_area", "super_builtup_area", "saleable_area",
    "terrace_area", "balcony_area", "total_area", "plot_area", "parking_area",
    "covered_parking_area", "car_parking_area", "garden_area", "gallery_area",
    "loft_area", "office_area", "shop_area", "mezzanine_area", "open_area",
]

# ---------------- TEXT CLEANING ----------------
def clean_area_text(value) -> str:
    """Normalize area text before parsing."""
    text = str(value).strip()
    text = text.replace("–", "-").replace("—", "-").replace("＋", "+").replace("＝", "=")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)                 # 17,000 -> 17000
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)         # 02 . 39 -> 02.39
    text = re.sub(r"\s*\+\s*", " + ", text)
    text = re.sub(r"\s*=\s*", " = ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# ---------------- REGEX PATTERNS ----------------
SQMT_PATTERN = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:sq\.?\s*m(?:et(?:er|re))?s?|sqm|m²|m2"
    r"|square\s*met(?:er|re)s?|चौ\.?\s*मी(?:टर)?\.?|चौरस\s*मी(?:टर)?|चौरस\s*मीटर)",
    flags=re.IGNORECASE,
)

SQFT_PATTERN = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|sft|ft²|ft2|square\s*feet|square\s*foot"
    r"|चौ\.?\s*फूट|चौ\.?\s*फुट|चौरस\s*फूट|चौरस\s*फुट|फीट|फिट|फूट|फुट)",
    flags=re.IGNORECASE,
)

# Compact Hectare.Are.Sq.m format (0.02.14 R / 00.00.86 हे.आर.चौ.मी.)
COMPACT_HA_SQM_PATTERN = re.compile(
    r"(?<![\d.])(\d{1,3})\.(\d{1,2})\.(\d{1,2})\s*"
    r"(?:हे\.?\s*आर\.?\s*चौ\.?\s*मी\.?|hectare\s*are\s*(?:sq\.?\s*m)?|आर|R)?(?![\d.])",
    flags=re.IGNORECASE,
)

# Standard Hectare + Are (00 हेक्टर 17.90 आर / 0 hectare 19 R)
HECTARE_ARE_PATTERN = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:हेक्टर|हेक्टेर|हे\.?|hectares?|ha)\s*"
    r"(\d+(?:\.\d+)?)\s*(?:आर|R|ares?)(?![\w.])",
    flags=re.IGNORECASE,
)

# Hectare + decimal Are with R/आर absent (0 हे 05.98) - decimal-only to avoid false positives
HECTARE_ARE_WITHOUT_UNIT_PATTERN = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:हेक्टर|हेक्टेर|हे\.?|hectares?|ha)\s+"
    r"(\d+\.\d+)(?!\s*(?:आर|R|ares?))",
    flags=re.IGNORECASE,
)

# Are-only (0.46 R -> 46 sq.m, 19 आर -> 1900 sq.m) - used only when no hectare format found
ARE_ONLY_PATTERN = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:आर|R|ares?)(?![\w.])",
    flags=re.IGNORECASE,
)

# ---------------- HELPERS ----------------
def remove_parenthetical_explanations(text: str) -> str:
    """Remove bracketed explanatory conversions, e.g. '(0.20 hectares)', to avoid double counting."""
    cleaned = re.sub(r"\([^)]*\)", " ", text)
    return re.sub(r"\s+", " ", cleaned).strip()

def get_final_expression(text: str) -> str:
    """For equations, use only the result after '='."""
    if "=" in text:
        final_part = text.split("=")[-1].strip()
        if final_part:
            return final_part
    return text

def convert_hectare_are_to_sqmt(hectare: float, are: float, extra_sqmt: float = 0.0) -> float:
    """Convert hectare/Are/sq.m components to sq.m."""
    return float(hectare) * 10000.0 + float(are) * 100.0 + float(extra_sqmt)

_MISSING_TEXT_VALUES = {"nan", "none", "null", "na", "n/a", "-"}

# ---------------- CONVERSION FUNCTION ----------------
def extract_sqmt(value):
    """
    Convert a mixed area value into square metres. Supports:
    1. Hectare-Are-Sq.m (0.02.14 R)          4. Are only (19 आर)
    2. Hectare + Are (00 हेक्टर 17.90 आर)     5. Sq.m (200 sq.m)
    3. Multiple hectare-Are portions (added)  6. Sq.ft (17000 sq.ft)
    Returns float square metres or np.nan.
    """
    if is_missing(value):
        return np.nan

    if isinstance(value, (list, tuple, np.ndarray, set)):
        for item in value:
            res = extract_sqmt(item)
            if not is_missing(res):
                return res
        return np.nan

    if isinstance(value, (int, float, np.integer, np.floating)):
        numeric_value = float(value)
        return np.nan if np.isnan(numeric_value) else round(numeric_value, 2)

    text = clean_area_text(value)
    if not text or text.lower() in _MISSING_TEXT_VALUES:
        return np.nan

    text = get_final_expression(text)                       # use final equation result
    parsing_text = remove_parenthetical_explanations(text)  # drop bracketed conversions

    # 1. Compact Hectare.Are.Sq.m
    compact_matches = list(COMPACT_HA_SQM_PATTERN.finditer(parsing_text))
    if compact_matches:
        total = sum(
            convert_hectare_are_to_sqmt(m.group(1), m.group(2), m.group(3))
            for m in compact_matches
        )
        return round(total, 2)

    # 2/3. Standard Hectare + Are (multiple matches summed)
    hectare_are_matches = list(HECTARE_ARE_PATTERN.finditer(parsing_text))
    if hectare_are_matches:
        total = sum(convert_hectare_are_to_sqmt(m.group(1), m.group(2)) for m in hectare_are_matches)
        return round(total, 2)

    # Hectare + decimal Are without explicit unit
    hectare_no_unit_matches = list(HECTARE_ARE_WITHOUT_UNIT_PATTERN.finditer(parsing_text))
    if hectare_no_unit_matches:
        total = sum(convert_hectare_are_to_sqmt(m.group(1), m.group(2)) for m in hectare_no_unit_matches)
        return round(total, 2)

    # 4. Are-only
    are_matches = list(ARE_ONLY_PATTERN.finditer(parsing_text))
    if are_matches:
        total_are = sum(float(m.group(1)) for m in are_matches)
        return round(total_are * 100.0, 2)

    # 5. Direct sq.m
    sqmt_match = SQMT_PATTERN.search(text)
    if sqmt_match:
        return round(float(sqmt_match.group(1)), 2)

    # 6. Direct sq.ft
    sqft_match = SQFT_PATTERN.search(text)
    if sqft_match:
        return round(float(sqft_match.group(1)) * SQFT_TO_SQMT, 2)

    return np.nan

# ---------------- CONVERSION SOURCE ----------------
def detect_area_source(value) -> str:
    """Identify which conversion method was used."""
    if is_missing(value):
        return "Missing"

    if isinstance(value, (list, tuple, np.ndarray, set)):
        for item in value:
            src = detect_area_source(item)
            if src != "Missing":
                return src
        return "Missing"

    if isinstance(value, (int, float, np.integer, np.floating)):
        return "Missing" if is_missing(value) else "Numeric value assumed as sq.m."

    text = clean_area_text(value)
    if not text or text.lower() in _MISSING_TEXT_VALUES:
        return "Missing"

    text = get_final_expression(text)
    parsing_text = remove_parenthetical_explanations(text)

    if COMPACT_HA_SQM_PATTERN.search(parsing_text):
        return "Hectare-Are-Sq.m converted"

    hectare_matches = list(HECTARE_ARE_PATTERN.finditer(parsing_text))
    if hectare_matches:
        return "Multiple Hectare-Are areas added" if len(hectare_matches) > 1 else "Hectare-Are converted"

    if HECTARE_ARE_WITHOUT_UNIT_PATTERN.search(parsing_text):
        return "Hectare-Are converted; Are unit missing"

    if ARE_ONLY_PATTERN.search(parsing_text):
        return "Are converted"

    if SQMT_PATTERN.search(text):
        return "Direct sq.m."

    if SQFT_PATTERN.search(text):
        return "Square feet converted to sq.m."

    return "Unrecognized"

# ---------------- VALIDATION STATUS ----------------
def get_conversion_status(value, converted_value) -> str:
    if is_missing(value):
        return "Missing"
    if is_missing(converted_value):
        return "Review required"
    if converted_value < 0:
        return "Review required"
    if converted_value == 0:
        return "Zero area"
    return "Converted"

def get_conversion_done_status(value, converted_value) -> str:
    if is_missing(value) or is_missing(converted_value):
        return "No"
    return "Yes"

# ---------------- APPLY CONVERSION TO ALL AREA COLUMNS ----------------
def apply_area_conversions(categorised_df: pd.DataFrame) -> pd.DataFrame:
    """Adds *_sqmt / *_conversion_source / *_conversion_status / *_conversion_done columns."""
    categorised_df = categorised_df.copy()
    new_columns = {}

    for column in AREA_COLUMNS:
        if column not in categorised_df.columns:
            continue

        converted_column = f"{column}_sqmt"
        source_column = f"{column}_conversion_source"
        status_column = f"{column}_conversion_status"
        done_column = f"{column}_conversion_done"

        converted_series = (
            categorised_df[column].apply(extract_sqmt).pipe(pd.to_numeric, errors="coerce").round(2)
        )
        source_series = categorised_df[column].apply(detect_area_source)
        status_series = [
            get_conversion_status(o, c) for o, c in zip(categorised_df[column], converted_series)
        ]
        done_series = [
            get_conversion_done_status(o, c) for o, c in zip(categorised_df[column], converted_series)
        ]

        new_columns[converted_column] = converted_series
        new_columns[source_column] = source_series
        new_columns[status_column] = status_series
        new_columns[done_column] = done_series

    if new_columns:
        new_cols_df = pd.DataFrame(new_columns, index=categorised_df.index)
        categorised_df = pd.concat([categorised_df, new_cols_df], axis=1)

    return categorised_df

# ---------------- REVIEW UNRECOGNIZED VALUES ----------------
def build_area_review(categorised_df: pd.DataFrame) -> pd.DataFrame:
    review_records = []
    for column in AREA_COLUMNS:
        source_column = f"{column}_conversion_source"
        converted_column = f"{column}_sqmt"
        if column not in categorised_df.columns or source_column not in categorised_df.columns:
            continue

        review_mask = categorised_df[source_column].eq("Unrecognized")
        if np.any(np.asarray(review_mask)):
            temp = categorised_df.loc[review_mask, [column, converted_column, source_column]].copy()
            temp.rename(columns={
                column: "original_value",
                converted_column: "converted_sqmt",
                source_column: "conversion_source",
            }, inplace=True)
            temp.insert(0, "source_column", column)
            review_records.append(temp)

    if review_records:
        return pd.concat(review_records, ignore_index=True)
    return pd.DataFrame(columns=["source_column", "original_value", "converted_sqmt", "conversion_source"])

# ---------------- QUICK TESTS ----------------
def run_area_conversion_tests() -> pd.DataFrame:
    test_values = [
        "00 हेक्टर 17.90 आर", "00 हे. 02.33 आर", "0.02.14 R", "0.00.46 आर",
        "3 हे 25 आर अधिक पो.ख 1 हे 59 आर", "00 हे. 22 आर + पोटखराबा 00 हे. 01 आर",
        "0 hectare 19 R + 0 hectare 01 R = 0 hectare 20 R", "17,000 sq.ft",
        "26,000.00 sq.m", "0.0046 R", "00 hectare 28.11 R",
        "00 हे 00.50 आर म्हणजेच 500 चौ. फुट", "0 sq.ft",
    ]
    test_df = pd.DataFrame({"original_value": test_values})
    test_df["converted_sqmt"] = test_df["original_value"].apply(extract_sqmt)
    test_df["conversion_source"] = test_df["original_value"].apply(detect_area_source)
    print("\nConversion test:")
    try:
        print(test_df.to_string(index=False))
    except UnicodeEncodeError:
        print(test_df.to_string(index=False).encode("ascii", errors="backslashreplace").decode("ascii"))
    return test_df


# ============================================================
# PART C - UNIT AND FLOOR PROCESSING
# ============================================================
def process_unit_and_floor(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Transaction type mapping if docname is available
    if "docname" in df.columns:
        mapped_tx = df["docname"].map(result_dict.get)
        if "transaction_type" not in df.columns:
            df["transaction_type"] = mapped_tx
        else:
            df["transaction_type"] = df["transaction_type"].fillna(mapped_tx)

    # 1. Flat number
    if "flat_no" in df.columns:
        df["flat_number"] = df["flat_no"]
    else:
        df["flat_number"] = pd.NA

    # 2. Floor number mapping using word_number_dict
    floor_dict = {str(k).strip().lower(): str(v) for k, v in word_number_dict.items()}

    def map_floor(value):
        if is_missing(value):
            return pd.NA

        if isinstance(value, (list, tuple, np.ndarray, set)):
            result = []
            for item in value:
                mf = map_floor(item)
                if pd.notna(mf) and str(mf) not in result:
                    result.append(str(mf))
            return ", ".join(result) if result else pd.NA

        text = str(value).strip().lower()
        parts = re.split(r",|/|\+|\band\b| आणि | व ", text)
        result = []

        for part in parts:
            part = re.sub(r"\([^)]*\)", "", part).strip()
            part = re.sub(r"\s*(मजल्यावरील|मजल्यावर|मजला|floor)$", "", part).strip()

            mapped = floor_dict.get(part) or floor_dict.get(part + " मजला")
            if mapped and mapped not in result:
                result.append(mapped)

        return ", ".join(result) if result else value

    if "floor_no" in df.columns:
        df["floor_number"] = df["floor_no"].apply(map_floor)
    else:
        df["floor_number"] = pd.NA

    print("Unit and floor processing completed.")
    valid_flats = df["flat_number"].dropna().ne("").sum() if "flat_number" in df.columns else 0
    valid_floors = df["floor_number"].dropna().ne("").sum() if "floor_number" in df.columns else 0
    print(f"Total flat numbers populated: {valid_flats:,}")
    print(f"Total floor numbers mapped: {valid_floors:,}")

    return df

# ---------------- EXPORT (xlsxwriter, formatted) ----------------
# ---------------- EXPORT COMBINED WORKBOOK (xlsxwriter, formatted) ----------------
def export_combined_workbook(
    categorised_df: pd.DataFrame,
    cluster_summary: pd.DataFrame,
    manual_review_df: pd.DataFrame,
    pair_review_df: pd.DataFrame,
    review_df: pd.DataFrame,
    test_df: pd.DataFrame,
    path: str | Path,
):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _write(save_path):
        with pd.ExcelWriter(save_path, engine="xlsxwriter") as writer:
            sheets_data = {
                "Processed_Data": categorised_df,
                "cluster_summary": cluster_summary,
                "manual_review": manual_review_df,
                "pair_review": pair_review_df,
                "Area_Review": review_df,
                "Conversion_Test": test_df,
            }

            workbook = writer.book
            number_format = workbook.add_format({"num_format": "0.00"})
            header_format = workbook.add_format({"bold": True, "border": 1, "text_wrap": True, "valign": "top"})

            for sheet_name, dataframe in sheets_data.items():
                dataframe.to_excel(writer, index=False, sheet_name=sheet_name)
                worksheet = writer.sheets[sheet_name]

                for column_index, column_name in enumerate(dataframe.columns):
                    worksheet.write(0, column_index, str(column_name), header_format)

                    col_str = str(column_name)
                    if col_str.endswith("_sqmt") or col_str == "converted_sqmt":
                        worksheet.set_column(column_index, column_index, 16, number_format)
                    elif (
                        col_str.endswith("_conversion_source")
                        or col_str.endswith("_conversion_status")
                        or col_str.endswith("_conversion_done")
                        or col_str == "conversion_source"
                    ):
                        worksheet.set_column(column_index, column_index, 35)
                    else:
                        max_len = len(col_str)
                        if len(dataframe) > 0:
                            sample = dataframe[column_name].dropna().astype(str)
                            if not sample.empty:
                                max_len = max(max_len, int(sample.str.len().quantile(0.95)))
                        worksheet.set_column(column_index, column_index, min(max(max_len + 3, 12), 45))

                worksheet.freeze_panes(1, 0)
                if len(dataframe.columns) > 0 and len(dataframe) > 0:
                    worksheet.autofilter(0, 0, len(dataframe), len(dataframe.columns) - 1)

    try:
        final_path = output_path
        _write(final_path)
    except PermissionError:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = output_path.with_name(f"{output_path.stem}_{timestamp}{output_path.suffix}")
        print(f"\n⚠️ Warning: '{output_path.name}' is currently locked/open. Saving to:\n{final_path}")
        _write(final_path)

    print("\n" + "=" * 70)
    print("PIPELINE COMPLETED - SINGLE COMBINED OUTPUT SAVED")
    print("=" * 70)
    print(f"Output saved to:\n{final_path}")
    print(f"\nTotal records processed: {len(categorised_df):,}")
    print("Sheets included in output workbook:")
    print("  1. Processed_Data    (Full dataset: project clusters + converted area sqmt + flat & floor numbers)")
    print("  2. cluster_summary   (Project clusters summary & variants)")
    print("  3. manual_review     (Project names requiring manual review)")
    print("  4. pair_review       (Project pair candidate matches)")
    print("  5. Area_Review       (Unrecognized area values requiring review)")
    print("  6. Conversion_Test   (Area conversion self-test suite)")  
    
# ---------------- NET CARPET AREA DERIVATION ----------------
from divisor import SALEABLE_TO_CARPET_DIVISOR_BY_CITY

BUILDUP_TO_CARPET_DIVISOR = 1.2


def resolve_city_and_divisor(city: str | int = None) -> tuple:
    """
    Resolves city key and its saleable-to-carpet divisor dynamically as per the selected city:
    - Mumbai -> 1.45
    - Thane  -> 1.40
    - Pune   -> 1.35
    """
    if not city or str(city).strip().lower() in ["none", "", "null", "nan"]:
        try:
            from city_config import CURRENT_CITY_KEY
            city = CURRENT_CITY_KEY
        except Exception:
            city = None

    if not city:
        available_cities = ", ".join(SALEABLE_TO_CARPET_DIVISOR_BY_CITY.keys())
        raise ValueError(
            f"City must be selected for area conversion. Available cities: {available_cities}."
        )

    raw = str(city).strip().lower()
    id_map = {
        "8": "mumbai",
        "12": "thane",
        "9": "pune",
        "2": "ahmedabad",
        "3": "bangalore",
        "6": "hyderabad",
        "5": "ghaziabad",
    }
    city_str = id_map.get(raw, raw)

    if city_str not in SALEABLE_TO_CARPET_DIVISOR_BY_CITY:
        if any(k in city_str for k in ["mumbai", "bandra", "borivali", "andheri", "kurla"]):
            city_str = "mumbai"
        elif any(k in city_str for k in ["thane", "kalyan", "dombivli"]):
            city_str = "thane"
        elif any(k in city_str for k in ["pune", "pcmc", "haveli"]):
            city_str = "pune"

    saleable_divisor = SALEABLE_TO_CARPET_DIVISOR_BY_CITY.get(city_str)
    if saleable_divisor is None:
        available_cities = ", ".join(SALEABLE_TO_CARPET_DIVISOR_BY_CITY.keys())
        raise ValueError(
            f"No Saleable->Carpet divisor configured for selected city '{city}'. "
            f"Configured cities in divisor.py: {available_cities}."
        )

    return city_str, saleable_divisor


def derive_net_carpet_area(df: pd.DataFrame, city: str | int = None) -> pd.DataFrame:
    """Fill net_carpet_area_sq_m from whichever area column is available using city-specific divisor."""
    city_key, saleable_divisor = resolve_city_and_divisor(city=city)
    print(f"[Area Conversion] Selected City: '{city_key}' | Saleable->Carpet Divisor: {saleable_divisor} | Buildup Divisor: {BUILDUP_TO_CARPET_DIVISOR}")

    df["net_carpet_area_sq_m"] = np.nan

    mask = df["carpet_area_sqmt"].notna()
    df.loc[mask, "net_carpet_area_sq_m"] = df.loc[mask, "carpet_area_sqmt"].values

    mask = df["net_carpet_area_sq_m"].isna() & df["builtup_area_sqmt"].notna()
    df.loc[mask, "net_carpet_area_sq_m"] = (
        df.loc[mask, "builtup_area_sqmt"].values / BUILDUP_TO_CARPET_DIVISOR
    )

    mask = df["net_carpet_area_sq_m"].isna() & df["saleable_area_sqmt"].notna()
    df.loc[mask, "net_carpet_area_sq_m"] = (
        df.loc[mask, "saleable_area_sqmt"].values / saleable_divisor
    )

    mask = (
        df["net_carpet_area_sq_m"].isna() & df["super_builtup_area_sqmt"].notna()
    )
    df.loc[mask, "net_carpet_area_sq_m"] = (
        df.loc[mask, "super_builtup_area_sqmt"].values / saleable_divisor
    )

    mask = df["net_carpet_area_sq_m"].isna() & df["plot_area_sqmt"].notna()
    df.loc[mask, "net_carpet_area_sq_m"] = df.loc[mask, "plot_area_sqmt"].values

    mask = df["net_carpet_area_sq_m"].isna() & df["total_area_sqmt"].notna()
    df.loc[mask, "net_carpet_area_sq_m"] = df.loc[mask, "total_area_sqmt"].values

    df["net_carpet_area_sq_m"] = df["net_carpet_area_sq_m"].round(2)

    # Also create net_carpet_area_sqft
    df["net_carpet_area_sqft"] = (df["net_carpet_area_sq_m"] * 10.7639).round(2)

    # Calculate rate_in_sqft directly
    df["rate_in_sqft"] = (df["consideration_amt"] / df["net_carpet_area_sqft"]).round(2)

    return df



def process_dataframe(df, output_path=None, city=None):

    # Remove any duplicate column names if already present
    df = df.loc[:, ~df.columns.duplicated()].copy()

    print("=" * 70)
    print("RUNNING PIPELINE USING EXISTING DATAFRAME")
    print("=" * 70)

    # Part A - Project clustering
    categorised_df, cluster_summary, manual_review_df, pair_review_df = (
        run_project_clustering(input_df=df)
    )

    # Part B - Area conversion
    print("\n" + "=" * 70)
    print("PART B - AREA CONVERSION")
    print("=" * 70)

    categorised_df = apply_area_conversions(categorised_df)

    review_df = build_area_review(categorised_df)

    test_df = run_area_conversion_tests()


    # Part C - Unit and Floor processing
    print("\n" + "=" * 70)
    print("PART C - UNIT AND FLOOR PROCESSING")
    print("=" * 70)

    categorised_df = process_unit_and_floor(
        categorised_df
    )

    # Part D - Calculate Net_carpet_area
    categorised_df = derive_net_carpet_area(categorised_df, city=city)

    # Part E - calculuate rate
    

    # Optional final export
    if output_path is not None:

        export_combined_workbook(
            categorised_df,
            cluster_summary,
            manual_review_df,
            pair_review_df,
            review_df,
            test_df,
            output_path
        )


    return categorised_df