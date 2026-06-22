# WCWIN

WCWIN is a compact, reproducible Python model for projecting the 2026 FIFA World Cup. It generates a full 104-match tournament path, predicts exact scores, projects group tables and knockout winners, estimates title probabilities with Monte Carlo simulation, and can run a historical World Cup backtest.

The project is intentionally lightweight: it uses only the Python standard library and keeps the 2026 tournament inputs directly in `wcwin.py`.

## What it does

- Projects all 72 group-stage matches and all 32 knockout matches.
- Blends sportsbook-style odds, FIFA rankings, host advantage, confederation effects, and in-tournament form.
- Uses a Poisson score model to generate exact scorelines.
- Marks already completed matches as `observed` and future matches as `predicted`.
- Produces deterministic tournament projections plus Monte Carlo title probabilities.
- Writes results to CSV and JSON for sharing or further analysis.
- Includes a historical backtest against World Cups from 1994 through 2018.

## Repository contents

```text
WCWIN/
├── wcwin.py                  # Main predictor, CLI, model, simulation, and backtest logic
├── test_wcwin.py             # Unit tests for odds conversion, fixtures, projections, CSV output, and summaries
├── predictions.csv           # Generated 104-match projection output
├── prediction_summary.json   # Generated champion summary, title probabilities, ratings, and calibration values
└── backtest_findings.json    # Generated historical backtest metrics
```

## Requirements

- Python 3.10 or newer recommended.
- No third-party Python packages are required for normal prediction runs.
- Internet access is only required when running the historical backtest, because it downloads historical World Cup match and FIFA ranking CSV files from public GitHub-hosted datasets.

## Quick start

Clone the repository and run the predictor:

```bash
git clone <your-repo-url>
cd WCWIN
python3 wcwin.py
```

Run the test suite:

```bash
python3 -m unittest -v
```

## Usage

```bash
python3 wcwin.py [options]
```

Available options:

```text
--runs RUNS                 Number of Monte Carlo simulations for title probabilities.
                            Default: 20000

--seed SEED                 Random seed for reproducible Monte Carlo results.
                            Default: 20260618

--write-csv PATH            Write the full 104-match projected path to a CSV file.

--write-json PATH           Write champion summary, title probabilities, ratings,
                            and calibration values to a JSON file.

--backtest                  Run the 1994-2018 historical World Cup backtest.

--write-backtest PATH       Write historical backtest findings to a JSON file.
```

Example:

```bash
python3 wcwin.py \
  --runs 20000 \
  --seed 20260618 \
  --write-csv predictions.csv \
  --write-json prediction_summary.json
```

Run the historical backtest and save the findings:

```bash
python3 wcwin.py --backtest --write-backtest backtest_findings.json
```

## Example output

The bundled `prediction_summary.json` projects:

- Champion: France
- Final: Brazil 1-2 France
- Highest title probabilities:
  - France: 16.68%
  - England: 16.46%
  - Argentina: 14.11%
  - Brazil: 9.25%
  - Spain: 8.81%

The bundled `backtest_findings.json` reports the following overall historical backtest results for World Cups from 1994 through 2018:

- Matches tested: 436
- Overall accuracy: 56.19%
- Group-stage accuracy: 56.79%
- Log loss: 0.989
- Brier score: 0.586
- Final-match champion hit rate: 71.43%

These values are generated from the current checked-in model and calibration values.

## Methodology

WCWIN combines several simple, transparent signals:

1. **Market signal**: American odds are converted into implied probabilities and de-vigged for three-way match outcomes.
2. **Team strength**: Teams receive ratings based on outright odds, FIFA rankings, current tournament form, host advantage, prior World Cup signal, and confederation adjustments.
3. **Score model**: Expected goals are converted into exact score probabilities with a Poisson model.
4. **Group projection**: Group tables are calculated using observed and predicted results, then sorted by points, goal difference, goals scored, and model rating.
5. **Knockout projection**: Knockout matchups are generated from the official 48-team bracket structure and resolved with predicted scorelines.
6. **Monte Carlo simulation**: The model repeatedly simulates tournament paths to estimate title probabilities.
7. **Backtesting**: Historical World Cup results from 1994 to 2018 are used to evaluate calibration and predictive accuracy.

The model is designed to be easy to inspect and reproduce, not to guarantee betting performance.

## Data notes

The script documents its checked-in 2026 inputs in the module docstring:

- 2026 group draw and fixture odds from FIFA VOdds, read on 2026-06-18.
- Completed first-matchday scores from the 2026 FIFA World Cup Wikipedia page, read on 2026-06-18.
- The official 48-team, 12-group, Round-of-32 bracket structure.

Historical backtest data is downloaded from public CSV datasets when `--backtest` is used.

## Testing

The repository includes unit tests covering:

- Odds conversion and de-vigging.
- Fixture inventory and team counts.
- Full 104-match tournament path generation.
- CSV writing.
- Historical team-code aliases and probability calculations.
- Summary calibration output.

Run them with:

```bash
python3 -m unittest -v
```

## Output files

### `predictions.csv`

A match-by-match projection with the following columns:

```text
match_no, stage, group, team_a, team_b, score, winner, note
```

### `prediction_summary.json`

A compact JSON summary containing:

- Projected champion.
- Final matchup and score.
- Top title probabilities.
- Team ratings.
- Calibration values.

### `backtest_findings.json`

Historical validation output containing:

- Source URLs.
- Tournament list.
- Calibration values.
- Overall metrics.
- Per-tournament metrics.

## Disclaimer

WCWIN is a prediction and simulation project for analysis and entertainment. It is not financial advice, betting advice, or a guarantee of match outcomes.
