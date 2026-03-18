# Feature Analysis Log

Tracks every feature tested, its permutation importance, status, and decisions made.
Updated after each training run.

---

## Current Model: Slim 8-Feature Model
**Date**: 2026-03-18
**Training seasons**: 2019, 2021, 2022, 2023, 2025 (315 games)
**LOSO CV**: 75.2% | **Train acc**: 88.3% | **AUC-ROC**: 0.819 | **Brier**: 0.192

---

## Permutation Importance Results (30 repeats, 2026-03-18)

> Permutation importance = accuracy drop when feature is randomly shuffled.
> Positive = feature helps. Near zero or negative = noise or harmful.

| Feature | Importance | ±Std | Status | Decision |
|---------|-----------|------|--------|----------|
| `eff_margin_diff` | +0.0388 | 0.0164 | ✅ Live | **Keep — dominant predictor** |
| `team_a_adj_eff_margin` | +0.0255 | 0.0130 | ✅ Live | **Keep — non-linear scale effects** |
| `team_a_adj_off_eff` | +0.0220 | 0.0121 | ✅ Live | **Keep** |
| `team_b_tempo` | +0.0213 | 0.0102 | ✅ Live | **Keep — slow teams disrupt higher seeds** |
| `team_a_adj_def_eff` | +0.0211 | 0.0080 | ✅ Live | **Keep** |
| `team_a_seed` | +0.0203 | 0.0085 | ✅ Live | **Keep — committee encodes info stats miss** |
| `team_a_rotation_depth` | +0.0197 | 0.0086 | ✅ Live | **Keep — tournament resilience** |
| `conf_win_pct_diff` | +0.0092 | 0.0051 | ✅ Live | **Keep — quality of wins signal** |
| `off_eff_diff` | +0.0080 | 0.0071 | ⚠️ Noise | Dropped in slim model |
| `team_a_xfactor_score` | +0.0078 | 0.0067 | ⚠️ Noise | Dropped in slim model |
| `team_b_rotation_depth` | +0.0077 | 0.0059 | ⚠️ Noise | Dropped in slim model |
| `team_b_ap_final_rank` | +0.0071 | 0.0026 | ⚠️ Noise | Dropped in slim model |
| `team_a_three_pt_rate` | +0.0068 | 0.0056 | ⚠️ Noise | Dropped in slim model |
| `team_b_adj_def_eff` | +0.0061 | 0.0092 | ⚠️ Noise | Dropped in slim model |
| `star_power_diff` | +0.0056 | 0.0063 | ⚠️ Noise | Dropped in slim model |
| `def_eff_diff` | +0.0050 | 0.0103 | ⚠️ Noise | Dropped in slim model |
| `seed_diff` | +0.0033 | 0.0058 | ⚠️ Noise | Dropped — redundant with eff_margin |
| `ap_rank_diff` | -0.0104 | 0.0069 | ❌ Harmful | **Drop — redundant with seed, adds noise** |
| `momentum_diff` | std=0 | — | ❌ Dead | No game log data — feature broken |
| `experience_diff` | std=0 | — | ❌ Dead | No class-year data scraped |
| `quad1_wins_diff` | std=0 | — | ❌ Dead | Hardcoded 0.0 — SR doesn't expose this |
| `portal_stability_diff` | std=0 | — | ❌ Dead | No transfer portal data |

---

## Feature History

### 2026-03-17: SR-Only Switch
**Change**: Replaced Torvik-dependent features with SR proxies
**Reason**: Torvik has no 2026 data → train/predict distribution mismatch
**Mapping**:
- `adj_eff_margin` ← SRS (was Torvik adj_em)
- `adj_off_eff` ← off_rtg (was Torvik adj_oe)
- `adj_def_eff` ← off_rtg - SRS (derived)
- `tempo` ← pace (was Torvik tempo)
- `conf_strength` ← SOS (weak proxy — fix pending)
**Result**: Eliminated prediction failures (e.g. Furman beating UConn)

### 2026-03-17: Dead Feature Removal
**Change**: Added zero-variance filter to train_with2025.py
**Dropped**: 15 features with std=0 across all training samples
**Result**: LOSO 69.5% → 72.1%, train/CV gap 30.5 → 15.6 pts

### 2026-03-17: Tree Regularization
**Change**: max_depth 5→3, n_estimators 300→150, added colsample/min_child constraints
**Reason**: 100% train accuracy → clear overfitting
**Result**: Train acc 100% → 87.6%, LOSO improved

### 2026-03-17: LR Scaling Fix
**Change**: Wrapped LogisticRegression in Pipeline with StandardScaler (base + meta)
**Reason**: Convergence warnings — LR on raw features fails to converge
**Result**: Convergence resolved, LOSO improved

### 2026-03-18: AP Rankings Fix
**Change**: Rebuilt `ap_rankings_all_seasons.parquet` from per-season files
**Reason**: Targeted 2026 scrape overwrote combined file with only 2026 data
**Result**: AP features now live (std=16.4 vs 0.0 before), 339 rows across all seasons

### 2026-03-18: conf_win_pct Added
**Change**: Added `wins_conf / (wins_conf + losses_conf)` to team_features.py; wired into DIFF_FEATURES and RAW_FEATURE_COLS in matchup.py
**Reason**: conference regular season record is a stronger quality signal than overall W%
**Permutation importance**: +0.0092 (ranks #8 — real signal)

### 2026-03-18: Slim Model
**Change**: Replaced full 35-feature set with 8 permutation-selected features
**Reason**: 315 samples / 35 features = 9 samples/feature — too thin, model was fitting noise
**Result**: LOSO 71.1% → **75.2%** (+4.1 pts), Brier 0.201 → 0.192

---

## Planned Features — Backlog

| Feature | Hypothesis | Data Source | Effort | Blocker |
|---------|-----------|-------------|--------|---------|
| Coach tourney wins (by coach) | Experienced coaches outperform in high-pressure games | SR coaching pages | Medium | Needs scraper |
| Senior roster % | Upperclassmen more composed in tournament | SR roster pages | Medium | Needs scraper |
| Geolocation proximity | Home crowd advantage, less travel fatigue | Tournament site data + team city | Medium | Needs scraper |
| Conference strength (mean SRS) | Better proxy than SOS for conference quality | Compute from existing SR data | Low | Implement in team_features.py |
| Comeback wins / clutch | Teams that win close games | SR game logs | High | Needs game log scraper |
| Momentum (last 10 games) | Recent form entering tournament | SR game logs | High | Needs game log scraper |

---

## Notes on Feature Strategy

**Core insight**: The model is fundamentally measuring *sustainable quality advantage*:
- How much better is team A overall? (`eff_margin_diff`)
- Where does that advantage come from? (`off_eff`, `def_eff`)
- Is it real or schedule inflation? (`conf_win_pct_diff`)
- Does the opponent's style neutralize it? (`tempo`)
- Can it hold for 6 games? (`rotation_depth`)
- What does the committee think? (`seed`)

**Sample size constraint**: With 315 training samples, each new feature costs ~10 samples of model capacity. Adding features requires adding data first. Target: scrape 2010-2018 to reach ~882 games.

**Features worth re-testing with 882 samples**:
- `xfactor_diff` (showed +0.0078 — near signal territory)
- `star_power_diff` (+0.0056)
- `three_pt_rate` (+0.0068)
- Coach experience (new — untested)
- Senior roster % (new — untested)
