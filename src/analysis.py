"""
GCSE attainment in London boroughs, 2021/22 - 2023/24: boys vs girls and borough differences.

Data: Department for Education, "GCSE results (Attainment 8) by sex", local authority level
(see README for the source and licence).  Run from the repository root:

    python src/analysis.py

Every section below is a Spyder/VS Code "cell" (# %%), so it can also be run step by step.
Outputs: figures/*.png and results/*.csv
"""

# %% 0. Setup
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

try:
    ROOT = Path(__file__).resolve().parent.parent
except NameError:  # running cell by cell in an interactive console
    ROOT = Path.cwd()

DATA_FILE = ROOT / "data" / "gcse_by_sex.xlsx"
FIG_DIR = ROOT / "figures"
RES_DIR = ROOT / "results"
FIG_DIR.mkdir(exist_ok=True)
RES_DIR.mkdir(exist_ok=True)

# Colours: validated categorical slots 1 and 2 (colour-blind safe), neutral text/grid tones.
BLUE, ORANGE = "#2a78d6", "#eb6834"
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "axes.edgecolor": GRID, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 10, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "legend.frameon": False, "savefig.dpi": 200,
})

# %% 1. Load the raw sheet and map columns BY POSITION, checking each header
raw = pd.read_excel(DATA_FILE, sheet_name="Table1")
raw.columns = [str(c).strip() for c in raw.columns]

# The sheet is laid out as three blocks of six columns after Code/Area/Date:
# All pupils (cols 3-8), Boys (9-14), Girls (15-20); within a block:
# n pupils, Attainment 8, Progress 8, % entered, % grade 5+, % grade 4+ (English and Maths).
BLOCKS = {"All": 3, "Boys": 9, "Girls": 15}
METRICS = ["n", "attainment8", "progress8", "entered", "pct5plus", "pct4plus"]

# Guard against mixing up blocks: check the header text of every column we rely on.
for sex, start in BLOCKS.items():
    assert "Attainment" in raw.columns[start + 1], (sex, raw.columns[start + 1])
    assert "Progress" in raw.columns[start + 2], (sex, raw.columns[start + 2])
    assert "entered" in raw.columns[start + 3], (sex, raw.columns[start + 3])
    assert "grades 5 or above" in raw.columns[start + 4], (sex, raw.columns[start + 4])
    assert "grades 4 or above" in raw.columns[start + 5], (sex, raw.columns[start + 5])

df = pd.DataFrame({"code": raw.iloc[:, 0].astype(str).str.strip(),
                   "borough": raw.iloc[:, 1].astype(str).str.strip(),
                   "year": raw.iloc[:, 2].astype(str).str.strip()})
for sex, start in BLOCKS.items():
    for k, metric in enumerate(METRICS):
        df[f"{sex}_{metric}"] = pd.to_numeric(raw.iloc[:, start + k], errors="coerce")

print(f"Raw rows: {len(df)}")

# %% 2. Cleaning
# 2a. Keep London boroughs only (ONS codes E09...). Drop regional/national aggregates.
df = df[df["code"].str.startswith("E09")]

# 2b. Remove exact duplicate rows (Camden 2022/23 appears twice).
n_before = len(df)
df = df.drop_duplicates()
print(f"Exact duplicate rows removed: {n_before - len(df)}")

# 2c. City of London (E09000001): the rows hold ENGLAND-wide totals (e.g. 624,275 pupils),
#     not the borough's, so they are corrupt and excluded.
col = df[df["code"] == "E09000001"]
print("City of London rows excluded (they contain England-wide figures):")
print(col[["borough", "year", "All_n"]].to_string(index=False))
df = df[df["code"] != "E09000001"]

# 2d. Percentages are stored on two scales: 0-1 in some cells and 0-100 in others,
#     sometimes even mixed within one row. No real value can be below 1 per cent
#     (the lowest genuine rate is ~40 per cent), so any value > 1 is divided by 100.
pct_cols = [c for c in df.columns if c.endswith(("_entered", "_pct5plus", "_pct4plus"))]
df[pct_cols] = df[pct_cols].where(df[pct_cols] <= 1, df[pct_cols] / 100)
assert df[pct_cols].min().min() >= 0.3 and df[pct_cols].max().max() <= 1.0

# 2e. Validation of the scale fix: the 'All' rate must equal the pupil-weighted
#     average of the boys' and girls' rates (tolerance covers rounding).
implied = (df["Boys_n"] * df["Boys_pct5plus"] + df["Girls_n"] * df["Girls_pct5plus"]) / (
    df["Boys_n"] + df["Girls_n"])
check = (implied - df["All_pct5plus"]).abs().dropna()
print(f"Check All = weighted(Boys, Girls) on 5+ rate: max abs difference = {check.max():.4f} "
      f"({len(check)} rows)")
assert check.max() < 0.01

# 2f. Remaining missing values (suppressed by DfE for small groups).
missing = df.filter(regex="_pct5plus|_pct4plus|_attainment8|_progress8").isna().sum()
print("Missing values per metric:\n", missing[missing > 0].to_string())

years = sorted(df["year"].unique())
latest, earliest = years[-1], years[0]
print(f"\nBoroughs per year: {df.groupby('year')['borough'].nunique().to_dict()}")
df.to_csv(RES_DIR / "clean_borough_data.csv", index=False)

# %% 3. London rates by sex and year (pupil-weighted over boroughs)
def weighted_rate(frame, sex, metric="pct5plus"):
    sub = frame[[f"{sex}_n", f"{sex}_{metric}"]].dropna()
    return np.average(sub[f"{sex}_{metric}"], weights=sub[f"{sex}_n"])

london = pd.DataFrame({
    sex: {y: weighted_rate(g, sex) for y, g in df.groupby("year")} for sex in ["Boys", "Girls", "All"]
})
london["gap_pp"] = (london["Girls"] - london["Boys"]) * 100
print("\nLondon pupil-weighted rate of grade 5+ in English and Maths:")
print((london * [100, 100, 100, 1]).round(1).to_string())
london.to_csv(RES_DIR / "london_rates_by_year.csv")

# %% 4. Is the gender gap real? Paired comparison across boroughs
def paired_gap(frame, boys_col, girls_col, scale=1.0):
    """Girls minus boys within each borough; paired t-test, Wilcoxon, 95% CI, Cohen's dz."""
    d = ((frame[girls_col] - frame[boys_col]) * scale).dropna()
    n, mean, sd = len(d), d.mean(), d.std(ddof=1)
    lo, hi = stats.t.interval(0.95, n - 1, loc=mean, scale=sd / np.sqrt(n))
    return {"n_boroughs": n, "mean_gap": mean, "ci95_low": lo, "ci95_high": hi,
            "share_girls_ahead": (d > 0).mean(),
            "t_pvalue": stats.ttest_1samp(d, 0).pvalue, "wilcoxon_pvalue": stats.wilcoxon(d).pvalue,
            "cohens_dz": mean / sd}

MEASURES = {  # label: (metric suffix, scale -> percentage points or score points)
    "Grade 5+ English & Maths (pp)": ("pct5plus", 100),
    "Grade 4+ English & Maths (pp)": ("pct4plus", 100),
    "Attainment 8 (points)": ("attainment8", 1),
    "Progress 8 (points)": ("progress8", 1),
}
# Average each borough over the three years first so that every borough counts once.
borough_avg = df.groupby("borough")[[c for c in df.columns if c[:3] in ("Boy", "Gir")]].mean()

rows = []
for label, (suffix, scale) in MEASURES.items():
    for period, frame in [(y, df[df["year"] == y]) for y in years] + [("3-year borough average", borough_avg)]:
        rows.append({"measure": label, "period": period,
                     **paired_gap(frame, f"Boys_{suffix}", f"Girls_{suffix}", scale)})
gap_table = pd.DataFrame(rows)
gap_table.to_csv(RES_DIR / "gender_gap_tests.csv", index=False)
pd.set_option("display.width", 200)
print("\nGirls minus boys, paired across boroughs:")
print(gap_table.round(4).to_string(index=False))

# %% 5. Differences between boroughs (all pupils, grade 5+)
wide = df.pivot(index="borough", columns="year", values="All_pct5plus")
complete = wide.dropna()  # boroughs observed in all three years
rank_table = complete.copy()
rank_table["mean_3yr"] = complete.mean(axis=1)
for y in years:
    rank_table[f"rank_{y}"] = complete[y].rank(ascending=False).astype(int)
rank_table["rank_change"] = rank_table[f"rank_{earliest}"] - rank_table[f"rank_{latest}"]
rank_table = rank_table.sort_values(latest, ascending=False)
rank_table.round(4).to_csv(RES_DIR / "borough_ranking.csv")

rho, rho_p = stats.spearmanr(complete[earliest], complete[latest])
top5, bottom5 = rank_table.head(5), rank_table.tail(5)
print(f"\nTop 5 boroughs, {latest}:\n", (top5[latest] * 100).round(1).to_string())
print(f"\nBottom 5 boroughs, {latest}:\n", (bottom5[latest] * 100).round(1).to_string())
print(f"\nSpread {latest}: {(rank_table[latest].max() - rank_table[latest].min()) * 100:.1f} pp "
      f"({rank_table[latest].idxmin()} to {rank_table[latest].idxmax()})")
print(f"Rank stability {earliest} vs {latest}: Spearman rho = {rho:.2f} (p = {rho_p:.1e}, n = {len(complete)})")

# %% 6. Figures
def finish(fig, name):
    fig.savefig(FIG_DIR / name, bbox_inches="tight")
    plt.close(fig)

# 6.1 London rate by sex and year ------------------------------------------------------
fig, ax = plt.subplots(figsize=(7.5, 4.6))
x, w = np.arange(len(years)), 0.36
for offset, sex, colour in [(-w / 2 - 0.01, "Boys", BLUE), (w / 2 + 0.01, "Girls", ORANGE)]:
    bars = ax.bar(x + offset, london.loc[years, sex] * 100, w, color=colour, label=sex,
                  edgecolor=SURFACE, linewidth=1.5)
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.8, f"{b.get_height():.1f}%",
                ha="center", va="bottom", color=INK, fontsize=10)
ax.set_xticks(x, years)
ax.set_ylim(0, 75)
ax.set_ylabel("Pupils achieving grade 5+ in English & Maths (%)")
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.legend(loc="upper left", ncol=2, bbox_to_anchor=(0, 1.0))
ax.set_title("Girls outperform boys in London every year", pad=14)
ax.text(0, -0.13, "32 London boroughs, pupil-weighted. Source: Department for Education.",
        transform=ax.transAxes, fontsize=8.5, color=INK2)
finish(fig, "01_gender_by_year.png")

# 6.2 Gender gap by borough, latest year (dumbbell) -----------------------------------
g = df[df["year"] == latest].dropna(subset=["Boys_pct5plus", "Girls_pct5plus"]).copy()
g["gap"] = g["Girls_pct5plus"] - g["Boys_pct5plus"]
g = g.sort_values("gap")
fig, ax = plt.subplots(figsize=(7.5, 9))
y = np.arange(len(g))
ax.hlines(y, g["Boys_pct5plus"] * 100, g["Girls_pct5plus"] * 100, color="#b9b8b2", linewidth=2, zorder=1)
ax.scatter(g["Boys_pct5plus"] * 100, y, s=55, color=BLUE, label="Boys", zorder=3, edgecolor=SURFACE, linewidth=1.2)
ax.scatter(g["Girls_pct5plus"] * 100, y, s=55, color=ORANGE, label="Girls", zorder=3, edgecolor=SURFACE, linewidth=1.2)
ax.set_yticks(y, g["borough"])
ax.set_xlabel("Pupils achieving grade 5+ in English & Maths (%)")
ax.xaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
n_ahead = int((g["gap"] > 0).sum())
ax.set_title(f"Girls lead in {n_ahead} of {len(g)} boroughs ({latest})", pad=28)
ax.legend(loc="lower right")
ax.text(0, 1.015, "Boroughs sorted by the size of the gap (smallest at the bottom).",
        transform=ax.transAxes, fontsize=9, color=INK2)
finish(fig, "02_gender_gap_by_borough.png")

# 6.3 Borough ranking, latest year -----------------------------------------------------
r = rank_table[latest].sort_values()
fig, ax = plt.subplots(figsize=(7.5, 9))
emphasis = set(r.index[-5:]) | set(r.index[:5])
colours = [BLUE if b in emphasis else "#a9c3e6" for b in r.index]
ax.barh(r.index, r.values * 100, color=colours, edgecolor=SURFACE, linewidth=1, height=0.8)
for b, v in r.items():
    if b in emphasis:
        ax.text(v * 100 + 0.6, b, f"{v * 100:.1f}%", va="center", fontsize=9, color=INK)
ref = london.loc[latest, "All"] * 100
ax.axvline(ref, color=INK2, linewidth=1.2, linestyle=(0, (4, 3)))
ax.text(ref + 0.6, -1.4, f"London average {ref:.1f}%", fontsize=9, color=INK2, va="center")
ax.set_xlim(0, r.max() * 100 + 8)
ax.set_xlabel("Pupils achieving grade 5+ in English & Maths (%)")
ax.xaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
spread = (r.max() - r.min()) * 100
ax.set_title(f"A {spread:.1f}-point spread between boroughs ({latest})", pad=14)
finish(fig, "03_borough_ranking.png")

# 6.4 Are the same boroughs ahead each year? ---------------------------------------------
fig, ax = plt.subplots(figsize=(6.4, 6.0))
ax.scatter(complete[earliest] * 100, complete[latest] * 100, s=50, color=BLUE, edgecolor=SURFACE, linewidth=1.2)
lims = [complete.min().min() * 100 - 3, complete.max().max() * 100 + 3]
ax.plot(lims, lims, color="#b9b8b2", linewidth=1.2, linestyle=(0, (4, 3)))
ax.set_xlim(lims); ax.set_ylim(lims)
for b, offset in [("Kingston upon Thames", (-8, 8)), ("Sutton", (6, -3)), ("Lambeth", (6, -12))]:
    ax.annotate(b, (complete.loc[b, earliest] * 100, complete.loc[b, latest] * 100),
                xytext=offset, textcoords="offset points", fontsize=8.5, color=INK2,
                ha="right" if offset[0] < 0 else "left")
ax.set_xlabel(f"Grade 5+ rate, {earliest} (%)")
ax.set_ylabel(f"Grade 5+ rate, {latest} (%)")
ax.xaxis.grid(True, color=GRID, linewidth=0.8); ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
ax.set_title(f"Borough rankings are stable (Spearman ρ = {rho:.2f})", pad=14)
ax.text(0.98, 0.04, "Below the dashed line = lower than in 2021/22", transform=ax.transAxes, ha="right", fontsize=8.5, color=INK2)
finish(fig, "04_borough_stability.png")

print(f"\nSaved {len(list(FIG_DIR.glob('*.png')))} figures to {FIG_DIR} and tables to {RES_DIR}")
