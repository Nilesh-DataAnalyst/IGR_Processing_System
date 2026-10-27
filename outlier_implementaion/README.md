# Outlier Implementation & Database Flagging

Standalone implementation of statistical outlier detection and database update algorithms for real estate transactions in PostgreSQL.

---

## 📌 Overview

This folder contains the standalone script [`outlier_update.py`](file:///e:/Nilesh/IGR_processing_System/outlier_implementaion/outlier_update.py), which implements statistical outlier classification directly on `public.transactions`.

> [!NOTE]
> An interactive and integrated version of this logic is also maintained inside `Processing/outlier_update.py`, callable as **Step 20** in `project.py` or via the Web Operations Dashboard (`server.py`).

---

## 📐 Algorithm & Classification Rules

1. **Calculated Rate Formulation**:
   $$\text{calc\_rate} = \frac{\text{agreement\_price}}{\text{net\_carpet\_area\_sq\_m} \times 10.764}$$

2. **Hierarchical Grouping**:
   Records are grouped by `(city, location, transaction_category, property_type)`.
   - International markets (`dubai`, `abu_dhabi`) have localities collapsed into `__ALL_LOCATIONS__` to ensure robust sample sizes.

3. **Percentile Trimming & Robust Median**:
   - Computes 1st (`p1`) and 99th (`p99`) percentiles of `calc_rate` per slice.
   - Trims rows where `calc_rate < p1` or `calc_rate > p99`.
   - Calculates the **median** of the remaining trimmed transactions.

4. **Dynamic Decision Boundaries**:
   $$\text{lower\_limit} = \frac{\text{median}}{4}, \quad \text{upper\_limit} = \text{median} \times 4$$

5. **Outlier Flags & Types**:
   | Outlier Type | Condition | `is_outlier` |
   | :--- | :--- | :--- |
   | **Mumbai Zero Area & Rate** | Mumbai, `calc_rate` is 0 or null, area or price is 0/null | `False` (Exception) |
   | **Mumbai Low Price Outlier**| Mumbai, `Sale`, `agreement_price < 100,000` | `True` |
   | **Lower Outlier** | Valid record, $\text{calc\_rate} < \text{lower\_limit}$ | `True` |
   | **Upper Outlier** | Valid record, $\text{calc\_rate} > \text{upper\_limit}$ | `True` |
   | **Normal** | Valid record, within $[\text{lower\_limit}, \text{upper\_limit}]$ | `False` |
   | **Invalid/Excluded** | Non-positive price or area | `True` |

6. **Database Writeback**:
   Uses `execute_values` to perform high-speed batched updates on `public.transactions` updating `rate`, `is_outlier`, and `outlier_type`.

---

## 🏃 Running Standalone

Configure `CITY_ID`, `LOCATION_NAME` (or `None`), and `DB_PARAMS` in `outlier_update.py`, then run:

```bash
python outlier_update.py
```
