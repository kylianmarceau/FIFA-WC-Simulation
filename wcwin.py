#!/usr/bin/env python3
"""2026 FIFA World Cup predictor.

A compact, reproducible tournament model built only on public information already
checked into this script:

* 2026 group draw and fixture odds from FIFA VOdds, read 2026-06-18.
* Completed first-matchday scores from the 2026 FIFA World Cup Wikipedia page,
  read 2026-06-18.
* The official 48-team / 12-group / Round-of-32 bracket shape.

The model is deliberately boring: sportsbook odds are treated as the strongest
signal for future games, completed results update current team strength, and a
Poisson score model turns those strengths into exact scores. It produces a full
104-match path, the projected champion, and Monte Carlo title probabilities.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

HOSTS = {"Mexico", "Canada", "USA"}
GROUP_ORDER = tuple("ABCDEFGHIJKL")
GROUPS: dict[str, tuple[str, str, str, str]] = {
    "A": ("Mexico", "South Africa", "South Korea", "Czechia"),
    "B": ("Canada", "Bosnia & Herzegovina", "Switzerland", "Qatar"),
    "C": ("Brazil", "Morocco", "Scotland", "Haiti"),
    "D": ("USA", "Paraguay", "Türkiye", "Australia"),
    "E": ("Germany", "Curaçao", "Ivory Coast", "Ecuador"),
    "F": ("Netherlands", "Japan", "Sweden", "Tunisia"),
    "G": ("Belgium", "Egypt", "Iran", "New Zealand"),
    "H": ("Spain", "Uruguay", "Saudi Arabia", "Cape Verde"),
    "I": ("France", "Norway", "Senegal", "Iraq"),
    "J": ("Argentina", "Austria", "Algeria", "Jordan"),
    "K": ("Portugal", "Colombia", "DR Congo", "Uzbekistan"),
    "L": ("England", "Croatia", "Ghana", "Panama"),
}

# Outright odds and FIFA ranks from FIFA VOdds all-teams page, read 2026-06-18.
OUTRIGHT_ODDS: dict[str, int] = {
    "France": 390,
    "Spain": 550,
    "England": 600,
    "Portugal": 900,
    "Argentina": 900,
    "Brazil": 1100,
    "Germany": 1200,
    "Netherlands": 1700,
    "Norway": 3000,
    "Belgium": 4000,
    "Morocco": 4000,
    "USA": 4000,
    "Japan": 4500,
    "Colombia": 5000,
    "Mexico": 5500,
    "Switzerland": 6000,
    "Uruguay": 7500,
    "Croatia": 8000,
    "Austria": 10000,
    "Ecuador": 11000,
    "Türkiye": 14000,
    "Canada": 15000,
    "Senegal": 15000,
    "Sweden": 16000,
    "Australia": 17000,
    "Ivory Coast": 20000,
    "Egypt": 30000,
    "Algeria": 35000,
    "Scotland": 40000,
    "Paraguay": 40000,
    "South Korea": 50000,
    "Panama": 50000,
    "Ghana": 60000,
    "Czechia": 90000,
    "Bosnia & Herzegovina": 100000,
    "DR Congo": 100000,
    "South Africa": 250000,
    "Qatar": 250000,
    "Haiti": 250000,
    "Curaçao": 250000,
    "Tunisia": 250000,
    "Iran": 250000,
    "New Zealand": 250000,
    "Saudi Arabia": 250000,
    "Cape Verde": 250000,
    "Iraq": 250000,
    "Jordan": 250000,
    "Uzbekistan": 250000,
}

FIFA_RANK: dict[str, int] = {
    "Argentina": 1,
    "Spain": 2,
    "France": 2,
    "Belgium": 3,
    "England": 4,
    "Brazil": 5,
    "Portugal": 6,
    "Netherlands": 7,
    "Croatia": 10,
    "Colombia": 11,
    "Germany": 12,
    "Norway": 13,
    "Morocco": 14,
    "Mexico": 15,
    "USA": 16,
    "Japan": 18,
    "Switzerland": 19,
    "Uruguay": 20,
    "Senegal": 21,
    "South Korea": 22,
    "Australia": 23,
    "Iran": 25,
    "Türkiye": 26,
    "Austria": 27,
    "Sweden": 29,
    "Tunisia": 35,
    "Egypt": 36,
    "Czechia": 38,
    "Scotland": 39,
    "Panama": 41,
    "Ecuador": 44,
    "Canada": 48,
    "Algeria": 52,
    "Bosnia & Herzegovina": 55,
    "Saudi Arabia": 56,
    "Ivory Coast": 58,
    "DR Congo": 59,
    "Ghana": 60,
    "Paraguay": 61,
    "South Africa": 63,
    "Uzbekistan": 66,
    "Iraq": 68,
    "Cape Verde": 71,
    "Qatar": 72,
    "Jordan": 74,
    "Curaçao": 77,
    "Haiti": 83,
    "New Zealand": 95,
}

CALIBRATED_RANK_LOG_SCALE = 0.55
CALIBRATED_HOST_ADVANTAGE = 0.42
CALIBRATED_BASE_GOALS = 2.80
CALIBRATED_TOTAL_GOALS_SLOPE = 0.22
CALIBRATED_MARKET_WEIGHT = 0.65

HISTORICAL_MATCHES_URL = "https://raw.githubusercontent.com/jfjelstul/worldcup/master/data-csv/matches.csv"
HISTORICAL_RANKINGS_URL = "https://raw.githubusercontent.com/tadhgfitzgerald/fifa_ranking/master/fifa_ranking.csv"
BACKTEST_TOURNAMENTS = ("WC-1994", "WC-1998", "WC-2002", "WC-2006", "WC-2010", "WC-2014", "WC-2018")
BACKTEST_HOSTS = {
    "WC-1994": {"USA"},
    "WC-1998": {"FRA"},
    "WC-2002": {"JPN", "KOR"},
    "WC-2006": {"GER"},
    "WC-2010": {"RSA"},
    "WC-2014": {"BRA"},
    "WC-2018": {"RUS"},
}
HISTORICAL_CODE_ALIASES = {
    "AGO": "ANG",
    "BGR": "BUL",
    "CHE": "SUI",
    "CHL": "CHI",
    "CRI": "CRC",
    "DEU": "GER",
    "DNK": "DEN",
    "DZA": "ALG",
    "GRC": "GRE",
    "HND": "HON",
    "HRV": "CRO",
    "NLD": "NED",
    "PRT": "POR",
    "PRY": "PAR",
    "SAU": "KSA",
    "TGO": "TOG",
    "TTO": "TRI",
    "URY": "URU",
    "ZAF": "RSA",
}


@dataclass(frozen=True)
class Fixture:
    group: str
    date: str
    team_a: str
    draw_odds: int
    team_b: str
    odds_a: int
    odds_b: int


@dataclass(frozen=True)
class Result:
    goals_a: int
    goals_b: int


@dataclass(frozen=True)
class Projection:
    match_no: int
    stage: str
    group: str
    team_a: str
    team_b: str
    goals_a: int
    goals_b: int
    winner: str
    note: str = "predicted"

    @property
    def score(self) -> str:
        return f"{self.goals_a}-{self.goals_b}"


FIXTURES: tuple[Fixture, ...] = (
    Fixture("A", "2026-06-11", "Mexico", 350, "South Africa", -233, 800),
    Fixture("A", "2026-06-11", "South Korea", 205, "Czechia", 160, 205),
    Fixture("A", "2026-06-15", "Mexico", 265, "Czechia", -120, 370),
    Fixture("A", "2026-06-15", "South Africa", 320, "South Korea", 475, -164),
    Fixture("A", "2026-06-19", "South Korea", 230, "Mexico", 300, 105),
    Fixture("A", "2026-06-19", "Czechia", 270, "South Africa", -125, 380),
    Fixture("B", "2026-06-12", "Canada", 255, "Bosnia & Herzegovina", -115, 360),
    Fixture("B", "2026-06-12", "Switzerland", 550, "Qatar", -417, 1400),
    Fixture("B", "2026-06-16", "Switzerland", 245, "Canada", 115, 260),
    Fixture("B", "2026-06-16", "Bosnia & Herzegovina", 310, "Qatar", -175, 500),
    Fixture("B", "2026-06-20", "Canada", 490, "Qatar", -345, 1000),
    Fixture("B", "2026-06-20", "Switzerland", 310, "Bosnia & Herzegovina", -179, 500),
    Fixture("C", "2026-06-13", "Brazil", 290, "Morocco", -149, 450),
    Fixture("C", "2026-06-13", "Scotland", 420, "Haiti", -303, 1300),
    Fixture("C", "2026-06-17", "Brazil", 410, "Scotland", -227, 600),
    Fixture("C", "2026-06-17", "Morocco", 475, "Haiti", -345, 1000),
    Fixture("C", "2026-06-21", "Brazil", 1000, "Haiti", -833, 2200),
    Fixture("C", "2026-06-21", "Morocco", 265, "Scotland", -135, 450),
    Fixture("D", "2026-06-12", "USA", 8000, "Paraguay", -5000, 35000),
    Fixture("D", "2026-06-14", "Türkiye", 285, "Australia", -145, 425),
    Fixture("D", "2026-06-18", "USA", 270, "Türkiye", 145, 180),
    Fixture("D", "2026-06-18", "Paraguay", 235, "Australia", 115, 255),
    Fixture("D", "2026-06-22", "USA", 340, "Australia", -164, 425),
    Fixture("D", "2026-06-22", "Türkiye", 240, "Paraguay", 105, 320),
    Fixture("E", "2026-06-14", "Germany", 1900, "Curaçao", -1667, 3500),
    Fixture("E", "2026-06-14", "Ivory Coast", 190, "Ecuador", 250, 145),
    Fixture("E", "2026-06-18", "Germany", 360, "Ivory Coast", -175, 490),
    Fixture("E", "2026-06-18", "Ecuador", 1000, "Curaçao", -1000, 2500),
    Fixture("E", "2026-06-22", "Germany", 300, "Ecuador", -145, 410),
    Fixture("E", "2026-06-22", "Curaçao", 800, "Ivory Coast", 1800, -714),
    Fixture("F", "2026-06-14", "Netherlands", 260, "Japan", 100, 270),
    Fixture("F", "2026-06-14", "Sweden", 410, "Tunisia", -303, 950),
    Fixture("F", "2026-06-18", "Netherlands", 295, "Sweden", -141, 380),
    Fixture("F", "2026-06-18", "Japan", 310, "Tunisia", -189, 600),
    Fixture("F", "2026-06-22", "Netherlands", 450, "Tunisia", -303, 850),
    Fixture("F", "2026-06-22", "Japan", 250, "Sweden", 115, 260),
    Fixture("G", "2026-06-13", "Belgium", 295, "Egypt", -164, 490),
    Fixture("G", "2026-06-13", "Iran", 235, "New Zealand", 250, 140),
    Fixture("G", "2026-06-17", "Belgium", 370, "Iran", -233, 700),
    Fixture("G", "2026-06-17", "Egypt", 310, "New Zealand", -164, 470),
    Fixture("G", "2026-06-21", "Belgium", 550, "New Zealand", -455, 1200),
    Fixture("G", "2026-06-21", "Egypt", 220, "Iran", 110, 300),
    Fixture("H", "2026-06-15", "Spain", 330, "Uruguay", -164, 500),
    Fixture("H", "2026-06-15", "Saudi Arabia", 275, "Cape Verde", 140, 180),
    Fixture("H", "2026-06-19", "Spain", 950, "Saudi Arabia", -909, 2500),
    Fixture("H", "2026-06-19", "Uruguay", 320, "Cape Verde", -208, 700),
    Fixture("H", "2026-06-23", "Spain", 1300, "Cape Verde", -1111, 2700),
    Fixture("H", "2026-06-23", "Uruguay", 340, "Saudi Arabia", -208, 650),
    Fixture("I", "2026-06-16", "France", 280, "Norway", -120, 350),
    Fixture("I", "2026-06-16", "Senegal", 425, "Iraq", -294, 900),
    Fixture("I", "2026-06-20", "France", 340, "Senegal", -200, 600),
    Fixture("I", "2026-06-20", "Norway", 600, "Iraq", -500, 1400),
    Fixture("I", "2026-06-24", "France", 1100, "Iraq", -1000, 2800),
    Fixture("I", "2026-06-24", "Norway", 250, "Senegal", 135, 195),
    Fixture("J", "2026-06-15", "Argentina", 300, "Austria", -164, 500),
    Fixture("J", "2026-06-15", "Algeria", 320, "Jordan", -169, 500),
    Fixture("J", "2026-06-19", "Argentina", 310, "Algeria", -185, 600),
    Fixture("J", "2026-06-19", "Austria", 400, "Jordan", -278, 800),
    Fixture("J", "2026-06-23", "Argentina", 650, "Jordan", -500, 1400),
    Fixture("J", "2026-06-23", "Algeria", 210, "Austria", 205, 155),
    Fixture("K", "2026-06-16", "Portugal", 245, "Colombia", 110, 255),
    Fixture("K", "2026-06-16", "DR Congo", 260, "Uzbekistan", 115, 250),
    Fixture("K", "2026-06-20", "Portugal", 460, "DR Congo", -323, 1000),
    Fixture("K", "2026-06-20", "Colombia", 380, "Uzbekistan", -263, 900),
    Fixture("K", "2026-06-24", "Portugal", 600, "Uzbekistan", -500, 1400),
    Fixture("K", "2026-06-24", "DR Congo", 350, "Colombia", 650, -200),
    Fixture("L", "2026-06-17", "England", 270, "Croatia", -135, 420),
    Fixture("L", "2026-06-17", "Ghana", 2200, "Panama", -5000, 35000),
    Fixture("L", "2026-06-21", "England", 500, "Ghana", -400, 1100),
    Fixture("L", "2026-06-21", "Croatia", 310, "Panama", -189, 600),
    Fixture("L", "2026-06-25", "England", 550, "Panama", -345, 1000),
    Fixture("L", "2026-06-25", "Croatia", 295, "Ghana", -161, 480),
)

# Completed scores observed in the 2026 FIFA World Cup Wikipedia article on 2026-06-18.
OBSERVED_RESULTS: dict[tuple[str, str], Result] = {
    ("Mexico", "South Africa"): Result(2, 0),
    ("South Korea", "Czechia"): Result(2, 1),
    ("Canada", "Bosnia & Herzegovina"): Result(1, 1),
    ("Switzerland", "Qatar"): Result(1, 1),
    ("Brazil", "Morocco"): Result(1, 1),
    ("Scotland", "Haiti"): Result(1, 0),
    ("USA", "Paraguay"): Result(4, 1),
    ("Türkiye", "Australia"): Result(0, 2),
    ("Germany", "Curaçao"): Result(7, 1),
    ("Ivory Coast", "Ecuador"): Result(1, 0),
    ("Netherlands", "Japan"): Result(2, 2),
    ("Sweden", "Tunisia"): Result(5, 1),
    ("Belgium", "Egypt"): Result(1, 1),
    ("Iran", "New Zealand"): Result(2, 2),
    ("Spain", "Uruguay"): Result(0, 0),
    ("Saudi Arabia", "Cape Verde"): Result(1, 1),
    ("France", "Norway"): Result(3, 1),
    ("Senegal", "Iraq"): Result(3, 1),
    ("Argentina", "Austria"): Result(3, 0),
    ("Algeria", "Jordan"): Result(1, 3),
    ("Portugal", "Colombia"): Result(1, 1),
    ("DR Congo", "Uzbekistan"): Result(1, 3),
    ("England", "Croatia"): Result(4, 2),
    ("Ghana", "Panama"): Result(1, 0),
}

R32_SLOTS = (
    (73, "2A", "2B"),
    (74, "1C", "2F"),
    (75, "1E", "3ABCDF"),
    (76, "1F", "2C"),
    (77, "2E", "2I"),
    (78, "1I", "3CDFGH"),
    (79, "1A", "3CEFHI"),
    (80, "1L", "3EHIJK"),
    (81, "1G", "3AEHIJ"),
    (82, "1D", "3BEFIJ"),
    (83, "1H", "2J"),
    (84, "2K", "2L"),
    (85, "1B", "3EFGIJ"),
    (86, "2D", "2G"),
    (87, "1J", "2H"),
    (88, "1K", "3DEIJL"),
)
R16 = ((89, 73, 75), (90, 74, 77), (91, 76, 78), (92, 79, 80), (93, 83, 84), (94, 81, 82), (95, 86, 88), (96, 85, 87))
QF = ((97, 89, 90), (98, 93, 94), (99, 91, 92), (100, 95, 96))
SF = ((101, 97, 98), (102, 99, 100))


def american_to_probability(odds: int) -> float:
    if odds < 0:
        return -odds / (-odds + 100.0)
    return 100.0 / (odds + 100.0)


def devig_three_way(odds_a: int, draw_odds: int, odds_b: int) -> tuple[float, float, float]:
    raw = (american_to_probability(odds_a), american_to_probability(draw_odds), american_to_probability(odds_b))
    total = sum(raw)
    return raw[0] / total, raw[1] / total, raw[2] / total


def all_teams() -> tuple[str, ...]:
    return tuple(team for group in GROUP_ORDER for team in GROUPS[group])


def result_for(fixture: Fixture) -> Result | None:
    direct = OBSERVED_RESULTS.get((fixture.team_a, fixture.team_b))
    if direct:
        return direct
    reverse = OBSERVED_RESULTS.get((fixture.team_b, fixture.team_a))
    if reverse:
        return Result(reverse.goals_b, reverse.goals_a)
    return None


def market_goal_diff(fixture: Fixture) -> float:
    p_a, _, p_b = devig_three_way(fixture.odds_a, fixture.draw_odds, fixture.odds_b)
    return max(-2.6, min(2.6, 1.05 * math.log(p_a / p_b)))


def fit_strengths(iterations: int = 900) -> dict[str, float]:
    teams = all_teams()
    ratings = {team: 0.0 for team in teams}
    prior_edges: list[tuple[str, float, float]] = []
    implied = {team: american_to_probability(odds) for team, odds in OUTRIGHT_ODDS.items()}
    mean_log = sum(math.log(p) for p in implied.values()) / len(implied)
    for team, probability in implied.items():
        prior_edges.append((team, 1.00 * (math.log(probability) - mean_log), 0.34))
    mean_rank_score = sum(-math.log(FIFA_RANK[team]) for team in teams) / len(teams)
    for team in teams:
        prior_edges.append((team, CALIBRATED_RANK_LOG_SCALE * (-math.log(FIFA_RANK[team]) - mean_rank_score), 0.24))

    match_edges: list[tuple[str, str, float, float]] = []
    result_edges: list[tuple[str, str, float, float]] = []
    for fixture in FIXTURES:
        result = result_for(fixture)
        if result is None:
            match_edges.append((fixture.team_a, fixture.team_b, market_goal_diff(fixture), 0.58))
        else:
            margin = result.goals_a - result.goals_b
            if margin == 0:
                target = 0.0
            else:
                target = math.copysign(0.34 + min(abs(margin), 4) * 0.18, margin)
            result_edges.append((fixture.team_a, fixture.team_b, target, 0.42))

    for _ in range(iterations):
        for team, target, weight in prior_edges:
            ratings[team] += 0.015 * weight * (target - ratings[team])
        for a, b, target, weight in match_edges:
            err = (ratings[a] - ratings[b]) - target
            step = 0.012 * weight * err
            ratings[a] -= step
            ratings[b] += step
        for a, b, target, weight in result_edges:
            err = (ratings[a] - ratings[b]) - target
            step = 0.010 * weight * err
            ratings[a] -= step
            ratings[b] += step

    mean = sum(ratings.values()) / len(ratings)
    return {team: value - mean for team, value in ratings.items()}


def expected_goals(team_a: str, team_b: str, ratings: dict[str, float]) -> tuple[float, float]:
    diff = max(-3.0, min(3.0, ratings[team_a] - ratings[team_b]))
    if team_a in HOSTS and team_b not in HOSTS:
        diff += CALIBRATED_HOST_ADVANTAGE
    elif team_b in HOSTS and team_a not in HOSTS:
        diff -= CALIBRATED_HOST_ADVANTAGE
    total = CALIBRATED_BASE_GOALS + CALIBRATED_TOTAL_GOALS_SLOPE * min(abs(diff), 2.5)
    goals_a = max(0.18, total / 2.0 + diff / 2.0)
    goals_b = max(0.18, total / 2.0 - diff / 2.0)
    return goals_a, goals_b


def poisson_pmf(mu: float, max_goals: int = 10) -> list[float]:
    values = [math.exp(-mu)]
    for goals in range(1, max_goals + 1):
        values.append(values[-1] * mu / goals)
    values[-1] += max(0.0, 1.0 - sum(values))
    return values


def score_distribution(team_a: str, team_b: str, ratings: dict[str, float], max_goals: int = 10) -> list[tuple[int, int, float]]:
    mu_a, mu_b = expected_goals(team_a, team_b, ratings)
    p_a = poisson_pmf(mu_a, max_goals)
    p_b = poisson_pmf(mu_b, max_goals)
    return [(ga, gb, pa * pb) for ga, pa in enumerate(p_a) for gb, pb in enumerate(p_b)]


def poisson_outcome_probabilities(team_a: str, team_b: str, ratings: dict[str, float]) -> tuple[float, float, float]:
    win = draw = loss = 0.0
    for ga, gb, probability in score_distribution(team_a, team_b, ratings):
        if ga > gb:
            win += probability
        elif ga == gb:
            draw += probability
        else:
            loss += probability
    total = win + draw + loss
    return win / total, draw / total, loss / total


def fixture_by_teams(team_a: str, team_b: str) -> Fixture | None:
    pair = {team_a, team_b}
    for fixture in FIXTURES:
        if {fixture.team_a, fixture.team_b} == pair:
            return fixture
    return None


def blended_outcome_probabilities(team_a: str, team_b: str, ratings: dict[str, float]) -> tuple[float, float, float]:
    model = poisson_outcome_probabilities(team_a, team_b, ratings)
    fixture = fixture_by_teams(team_a, team_b)
    if fixture is None or result_for(fixture) is not None:
        return model
    market = devig_three_way(fixture.odds_a, fixture.draw_odds, fixture.odds_b)
    if fixture.team_a != team_a:
        market = (market[2], market[1], market[0])
    return tuple(CALIBRATED_MARKET_WEIGHT * market[i] + (1.0 - CALIBRATED_MARKET_WEIGHT) * model[i] for i in range(3))  # type: ignore[return-value]


def predicted_score(team_a: str, team_b: str, ratings: dict[str, float], knockout: bool = False) -> tuple[int, int, str]:
    p_win, p_draw, p_loss = blended_outcome_probabilities(team_a, team_b, ratings)
    if knockout:
        desired = "A" if advance_probability(team_a, team_b, ratings) >= 0.5 else "B"
    elif p_draw >= p_win and p_draw >= p_loss:
        desired = "D"
    else:
        desired = "A" if p_win >= p_loss else "B"

    candidates = score_distribution(team_a, team_b, ratings, 8)
    if desired == "A":
        legal = [item for item in candidates if item[0] > item[1]]
    elif desired == "B":
        legal = [item for item in candidates if item[1] > item[0]]
    else:
        legal = [item for item in candidates if item[0] == item[1]]
    ga, gb, _ = max(legal, key=lambda item: item[2])
    winner = "Draw" if ga == gb else team_a if ga > gb else team_b
    return ga, gb, winner


def advance_probability(team_a: str, team_b: str, ratings: dict[str, float]) -> float:
    p_win, p_draw, _ = blended_outcome_probabilities(team_a, team_b, ratings)
    rating_gap = ratings[team_a] - ratings[team_b]
    shootout = 1.0 / (1.0 + math.exp(-0.7 * rating_gap))
    return p_win + p_draw * shootout


def deterministic_winner(team_a: str, team_b: str, ratings: dict[str, float]) -> str:
    return team_a if advance_probability(team_a, team_b, ratings) >= 0.5 else team_b


def table_sort_key(row: dict[str, int | str], ratings: dict[str, float]) -> tuple[int, int, int, float]:
    team = str(row["team"])
    return (int(row["points"]), int(row["gd"]), int(row["gf"]), ratings[team])


def group_stage_projection(ratings: dict[str, float]) -> tuple[list[Projection], dict[str, list[dict[str, int | str]]]]:
    projections: list[Projection] = []
    tables: dict[str, dict[str, dict[str, int | str]]] = {
        group: {team: {"team": team, "points": 0, "gf": 0, "ga": 0, "gd": 0, "wins": 0} for team in teams}
        for group, teams in GROUPS.items()
    }
    for number, fixture in enumerate(FIXTURES, start=1):
        observed = result_for(fixture)
        if observed:
            ga, gb = observed.goals_a, observed.goals_b
            winner = "Draw" if ga == gb else fixture.team_a if ga > gb else fixture.team_b
            note = "observed"
        else:
            ga, gb, winner = predicted_score(fixture.team_a, fixture.team_b, ratings)
            note = "predicted"
        projections.append(Projection(number, "Group", fixture.group, fixture.team_a, fixture.team_b, ga, gb, winner, note))
        apply_result(tables[fixture.group], fixture.team_a, fixture.team_b, ga, gb)

    ordered_tables: dict[str, list[dict[str, int | str]]] = {}
    for group, rows in tables.items():
        ordered_tables[group] = sorted(rows.values(), key=lambda row: table_sort_key(row, ratings), reverse=True)
    return projections, ordered_tables


def apply_result(table: dict[str, dict[str, int | str]], team_a: str, team_b: str, goals_a: int, goals_b: int) -> None:
    row_a = table[team_a]
    row_b = table[team_b]
    row_a["gf"] = int(row_a["gf"]) + goals_a
    row_a["ga"] = int(row_a["ga"]) + goals_b
    row_b["gf"] = int(row_b["gf"]) + goals_b
    row_b["ga"] = int(row_b["ga"]) + goals_a
    row_a["gd"] = int(row_a["gf"]) - int(row_a["ga"])
    row_b["gd"] = int(row_b["gf"]) - int(row_b["ga"])
    if goals_a > goals_b:
        row_a["points"] = int(row_a["points"]) + 3
        row_a["wins"] = int(row_a["wins"]) + 1
    elif goals_b > goals_a:
        row_b["points"] = int(row_b["points"]) + 3
        row_b["wins"] = int(row_b["wins"]) + 1
    else:
        row_a["points"] = int(row_a["points"]) + 1
        row_b["points"] = int(row_b["points"]) + 1


def knockout_seed(seed: str, tables: dict[str, list[dict[str, int | str]]], third_assignment: dict[str, str]) -> str:
    if seed[0] == "1":
        return str(tables[seed[1]][0]["team"])
    if seed[0] == "2":
        return str(tables[seed[1]][1]["team"])
    group = third_assignment[seed]
    return str(tables[group][2]["team"])


def allocate_thirds(tables: dict[str, list[dict[str, int | str]]], ratings: dict[str, float]) -> dict[str, str]:
    thirds = [(group, tables[group][2]) for group in GROUP_ORDER]
    qualified = {
        group
        for group, _ in sorted(thirds, key=lambda item: table_sort_key(item[1], ratings), reverse=True)[:8]
    }
    third_slots = [seed for _, _, seed in R32_SLOTS if seed.startswith("3")]
    ordered_slots = sorted(third_slots, key=lambda slot: sum(group in slot[1:] for group in qualified))
    assignment: dict[str, str] = {}
    used: set[str] = set()

    def backtrack(index: int) -> bool:
        if index == len(ordered_slots):
            return True
        slot = ordered_slots[index]
        candidates = [g for g in slot[1:] if g in qualified and g not in used]
        candidates.sort(key=lambda g: (ratings[str(tables[g][2]["team"])], -ord(g)), reverse=True)
        for group in candidates:
            used.add(group)
            assignment[slot] = group
            if backtrack(index + 1):
                return True
            used.remove(group)
            assignment.pop(slot, None)
        return False

    if not backtrack(0):
        raise RuntimeError(f"could not allocate third-place teams: {sorted(qualified)}")
    return assignment


def knockout_projection(ratings: dict[str, float], tables: dict[str, list[dict[str, int | str]]]) -> list[Projection]:
    projections: list[Projection] = []
    winners: dict[int, str] = {}
    losers: dict[int, str] = {}
    third_assignment = allocate_thirds(tables, ratings)

    def play(match_no: int, stage: str, team_a: str, team_b: str, group: str = "") -> None:
        ga, gb, _ = predicted_score(team_a, team_b, ratings, knockout=True)
        winner = deterministic_winner(team_a, team_b, ratings)
        if winner == team_b and ga > gb:
            ga, gb = gb, ga
        elif winner == team_a and gb > ga:
            ga, gb = gb, ga
        loser = team_b if winner == team_a else team_a
        winners[match_no] = winner
        losers[match_no] = loser
        projections.append(Projection(match_no, stage, group, team_a, team_b, ga, gb, winner))

    for match_no, left, right in R32_SLOTS:
        team_a = knockout_seed(left, tables, third_assignment)
        team_b = knockout_seed(right, tables, third_assignment)
        play(match_no, "Round of 32", team_a, team_b, f"{left} vs {right}")
    for match_no, left, right in R16:
        play(match_no, "Round of 16", winners[left], winners[right])
    for match_no, left, right in QF:
        play(match_no, "Quarterfinal", winners[left], winners[right])
    for match_no, left, right in SF:
        play(match_no, "Semifinal", winners[left], winners[right])
    play(103, "Third place", losers[101], losers[102])
    play(104, "Final", winners[101], winners[102])
    return projections


def full_path(ratings: dict[str, float]) -> tuple[list[Projection], dict[str, list[dict[str, int | str]]]]:
    group_projection, tables = group_stage_projection(ratings)
    return group_projection + knockout_projection(ratings, tables), tables


def simulate_score(team_a: str, team_b: str, ratings: dict[str, float], rng: random.Random) -> tuple[int, int]:
    dist = score_distribution(team_a, team_b, ratings, 9)
    threshold = rng.random()
    cumulative = 0.0
    for ga, gb, probability in dist:
        cumulative += probability
        if threshold <= cumulative:
            return ga, gb
    return dist[-1][0], dist[-1][1]


def simulate_match_winner(team_a: str, team_b: str, ratings: dict[str, float], rng: random.Random) -> str:
    ga, gb = simulate_score(team_a, team_b, ratings, rng)
    if ga > gb:
        return team_a
    if gb > ga:
        return team_b
    shootout = 1.0 / (1.0 + math.exp(-0.7 * (ratings[team_a] - ratings[team_b])))
    return team_a if rng.random() < shootout else team_b


def simulate_once(ratings: dict[str, float], rng: random.Random) -> str:
    tables = {
        group: {team: {"team": team, "points": 0, "gf": 0, "ga": 0, "gd": 0, "wins": 0} for team in teams}
        for group, teams in GROUPS.items()
    }
    for fixture in FIXTURES:
        observed = result_for(fixture)
        if observed:
            ga, gb = observed.goals_a, observed.goals_b
        else:
            ga, gb = simulate_score(fixture.team_a, fixture.team_b, ratings, rng)
        apply_result(tables[fixture.group], fixture.team_a, fixture.team_b, ga, gb)
    ordered_tables = {
        group: sorted(rows.values(), key=lambda row: table_sort_key(row, ratings), reverse=True)
        for group, rows in tables.items()
    }
    third_assignment = allocate_thirds(ordered_tables, ratings)
    winners: dict[int, str] = {}
    for match_no, left, right in R32_SLOTS:
        winners[match_no] = simulate_match_winner(
            knockout_seed(left, ordered_tables, third_assignment),
            knockout_seed(right, ordered_tables, third_assignment),
            ratings,
            rng,
        )
    for match_no, left, right in (*R16, *QF, *SF):
        winners[match_no] = simulate_match_winner(winners[left], winners[right], ratings, rng)
    return simulate_match_winner(winners[101], winners[102], ratings, rng)


def monte_carlo(ratings: dict[str, float], runs: int = 20000, seed: int = 20260618) -> dict[str, float]:
    rng = random.Random(seed)
    wins: dict[str, int] = defaultdict(int)
    for _ in range(runs):
        wins[simulate_once(ratings, rng)] += 1
    return {team: count / runs for team, count in sorted(wins.items(), key=lambda item: (-item[1], item[0]))}


def write_csv(path: Path, projections: Iterable[Projection]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("match_no", "stage", "group", "team_a", "team_b", "score", "winner", "note"))
        writer.writeheader()
        for projection in projections:
            writer.writerow(
                {
                    "match_no": projection.match_no,
                    "stage": projection.stage,
                    "group": projection.group,
                    "team_a": projection.team_a,
                    "team_b": projection.team_b,
                    "score": projection.score,
                    "winner": projection.winner,
                    "note": projection.note,
                }
            )


def load_csv_url(url: str) -> list[dict[str, str]]:
    with urllib.request.urlopen(url, timeout=30) as response:
        lines = (line.decode("utf-8") for line in response)
        return list(csv.DictReader(lines))


def historical_code(code: str) -> str:
    return HISTORICAL_CODE_ALIASES.get(code, code)


def historical_rankings_by_tournament(rank_rows: list[dict[str, str]], match_rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    starts = {
        tournament: min(row["match_date"] for row in match_rows if row["tournament_id"] == tournament)
        for tournament in BACKTEST_TOURNAMENTS
    }
    team_codes = {
        tournament: sorted(
            {historical_code(row["home_team_code"]) for row in match_rows if row["tournament_id"] == tournament}
            | {historical_code(row["away_team_code"]) for row in match_rows if row["tournament_id"] == tournament}
        )
        for tournament in BACKTEST_TOURNAMENTS
    }
    rankings: dict[str, dict[str, int]] = {}
    for tournament in BACKTEST_TOURNAMENTS:
        latest: dict[str, dict[str, str]] = {}
        for row in rank_rows:
            if row["rank_date"] <= starts[tournament]:
                latest[row["country_abrv"]] = row
        missing = [code for code in team_codes[tournament] if code not in latest]
        if missing:
            raise RuntimeError(f"missing FIFA rankings for {tournament}: {', '.join(missing)}")
        rankings[tournament] = {code: int(latest[code]["rank"]) for code in team_codes[tournament]}
    return rankings


def historical_rating(rank: int) -> float:
    return -CALIBRATED_RANK_LOG_SCALE * math.log(rank)


def historical_probabilities(home_code: str, away_code: str, tournament: str, ranks: dict[str, int]) -> tuple[float, float, float]:
    home = historical_code(home_code)
    away = historical_code(away_code)
    diff = historical_rating(ranks[home]) - historical_rating(ranks[away])
    hosts = BACKTEST_HOSTS[tournament]
    if home in hosts and away not in hosts:
        diff += CALIBRATED_HOST_ADVANTAGE
    elif away in hosts and home not in hosts:
        diff -= CALIBRATED_HOST_ADVANTAGE
    total = CALIBRATED_BASE_GOALS + CALIBRATED_TOTAL_GOALS_SLOPE * min(abs(diff), 2.5)
    mu_home = max(0.18, total / 2.0 + diff / 2.0)
    mu_away = max(0.18, total / 2.0 - diff / 2.0)
    home_pmf = poisson_pmf(mu_home)
    away_pmf = poisson_pmf(mu_away)
    win = draw = loss = 0.0
    for home_goals, home_prob in enumerate(home_pmf):
        for away_goals, away_prob in enumerate(away_pmf):
            probability = home_prob * away_prob
            if home_goals > away_goals:
                win += probability
            elif home_goals == away_goals:
                draw += probability
            else:
                loss += probability
    total_probability = win + draw + loss
    return win / total_probability, draw / total_probability, loss / total_probability

def historical_advance_pick(home_code: str, away_code: str, tournament: str, ranks: dict[str, int]) -> str:
    home = historical_code(home_code)
    away = historical_code(away_code)
    win, draw, _ = historical_probabilities(home_code, away_code, tournament, ranks)
    shootout = 1.0 / (1.0 + math.exp(-(historical_rating(ranks[home]) - historical_rating(ranks[away]))))
    return home if win + draw * shootout >= 0.5 else away



def run_historical_backtest() -> dict[str, object]:
    match_rows = [
        row
        for row in load_csv_url(HISTORICAL_MATCHES_URL)
        if row["tournament_id"] in BACKTEST_TOURNAMENTS
    ]
    rank_rows = load_csv_url(HISTORICAL_RANKINGS_URL)
    rankings = historical_rankings_by_tournament(rank_rows, match_rows)
    by_tournament: dict[str, dict[str, float | int | str]] = {}
    totals = {"matches": 0, "correct": 0, "log_loss": 0.0, "brier": 0.0, "group_matches": 0, "group_correct": 0}
    top_ranked_champion_hits = 0
    final_match_champion_hits = 0

    for tournament in BACKTEST_TOURNAMENTS:
        rows = [row for row in match_rows if row["tournament_id"] == tournament]
        ranks = rankings[tournament]
        tournament_totals = {"matches": 0, "correct": 0, "log_loss": 0.0, "brier": 0.0, "group_matches": 0, "group_correct": 0}
        entrant_codes = {
            historical_code(row["home_team_code"]) for row in rows
        } | {
            historical_code(row["away_team_code"]) for row in rows
        }
        top_ranked_champion_code = min(entrant_codes, key=lambda code: ranks[code])
        final = max(rows, key=lambda row: row["match_date"])
        actual_champion_code = historical_code(final["home_team_code"] if final["home_team_win"] == "1" else final["away_team_code"])
        final_match_pick_code = historical_advance_pick(final["home_team_code"], final["away_team_code"], tournament, ranks)
        top_ranked_champion_hits += top_ranked_champion_code == actual_champion_code
        final_match_champion_hits += final_match_pick_code == actual_champion_code

        for row in rows:
            probabilities = historical_probabilities(row["home_team_code"], row["away_team_code"], tournament, ranks)
            if int(row["home_team_score"]) > int(row["away_team_score"]):
                actual = 0
            elif int(row["home_team_score"]) == int(row["away_team_score"]):
                actual = 1
            else:
                actual = 2
            predicted = max(range(3), key=lambda index: probabilities[index])
            log_loss = -math.log(max(1e-9, probabilities[actual]))
            brier = sum((probabilities[index] - (1.0 if index == actual else 0.0)) ** 2 for index in range(3))
            tournament_totals["matches"] += 1
            tournament_totals["correct"] += int(predicted == actual)
            tournament_totals["log_loss"] += log_loss
            tournament_totals["brier"] += brier
            if row["group_stage"] == "1":
                tournament_totals["group_matches"] += 1
                tournament_totals["group_correct"] += int(predicted == actual)

        for key in totals:
            totals[key] += tournament_totals[key]
        by_tournament[tournament] = {
            "matches": tournament_totals["matches"],
            "accuracy": tournament_totals["correct"] / tournament_totals["matches"],
            "group_stage_accuracy": tournament_totals["group_correct"] / tournament_totals["group_matches"],
            "log_loss": tournament_totals["log_loss"] / tournament_totals["matches"],
            "brier": tournament_totals["brier"] / tournament_totals["matches"],
            "top_ranked_champion_code": top_ranked_champion_code,
            "final_match_pick_code": final_match_pick_code,
            "actual_champion_code": actual_champion_code,
            "top_ranked_champion_hit": int(top_ranked_champion_code == actual_champion_code),
            "final_match_champion_hit": int(final_match_pick_code == actual_champion_code),
        }

    return {
        "source_matches": HISTORICAL_MATCHES_URL,
        "source_rankings": HISTORICAL_RANKINGS_URL,
        "tournaments": list(BACKTEST_TOURNAMENTS),
        "calibration": calibration_summary(),
        "overall": {
            "matches": totals["matches"],
            "accuracy": totals["correct"] / totals["matches"],
            "group_stage_accuracy": totals["group_correct"] / totals["group_matches"],
            "log_loss": totals["log_loss"] / totals["matches"],
            "brier": totals["brier"] / totals["matches"],
            "top_ranked_champion_hit_rate": top_ranked_champion_hits / len(BACKTEST_TOURNAMENTS),
            "final_match_champion_hit_rate": final_match_champion_hits / len(BACKTEST_TOURNAMENTS),
        },
        "by_tournament": by_tournament,
    }


def print_backtest_report(backtest: dict[str, object]) -> None:
    overall = backtest["overall"]  # type: ignore[index]
    print("\nHistorical backtest, 1994-2018:")
    print(
        "  "
        f"{overall['matches']} matches, accuracy {overall['accuracy']:.2%}, "
        f"group accuracy {overall['group_stage_accuracy']:.2%}, "
        f"log loss {overall['log_loss']:.3f}, Brier {overall['brier']:.3f}, "
        f"top-ranked champion hit {overall['top_ranked_champion_hit_rate']:.2%}, "
        f"actual-final pick hit {overall['final_match_champion_hit_rate']:.2%}"
    )
    for tournament, metrics in backtest["by_tournament"].items():  # type: ignore[union-attr]
        print(
            "  "
            f"{tournament}: accuracy {metrics['accuracy']:.2%}, "
            f"log loss {metrics['log_loss']:.3f}, "
            f"champion prior {metrics['top_ranked_champion_code']} / final pick {metrics['final_match_pick_code']} -> {metrics['actual_champion_code']}"
        )


def calibration_summary() -> dict[str, float]:
    return {
        "rank_log_scale": CALIBRATED_RANK_LOG_SCALE,
        "host_advantage_goals": CALIBRATED_HOST_ADVANTAGE,
        "base_goals": CALIBRATED_BASE_GOALS,
        "total_goals_slope": CALIBRATED_TOTAL_GOALS_SLOPE,
        "market_weight_for_unplayed_2026_group_matches": CALIBRATED_MARKET_WEIGHT,
    }


def print_report(projections: list[Projection], tables: dict[str, list[dict[str, int | str]]], title_probs: dict[str, float]) -> None:
    final = projections[-1]
    print(f"Projected champion: {final.winner}")
    print(f"Projected final: {final.team_a} {final.score} {final.team_b}")
    print("\nTop title probabilities:")
    for team, probability in list(title_probs.items())[:12]:
        print(f"  {team:<22} {probability:6.2%}")
    print("\nProjected group tables:")
    for group in GROUP_ORDER:
        rows = tables[group]
        compact = ", ".join(f"{row['team']} {row['points']}pts" for row in rows)
        print(f"  Group {group}: {compact}")
    print("\nPredicted knockout path:")
    for projection in projections[72:]:
        print(f"  {projection.match_no:>3} {projection.stage:<13} {projection.team_a} {projection.score} {projection.team_b} -> {projection.winner}")


def build_summary(ratings: dict[str, float], projections: list[Projection], title_probs: dict[str, float]) -> dict[str, object]:
    final = projections[-1]
    return {
        "champion": final.winner,
        "final": {"team_a": final.team_a, "team_b": final.team_b, "score": final.score, "winner": final.winner},
        "top_title_probabilities": dict(list(title_probs.items())[:12]),
        "ratings": dict(sorted(ratings.items(), key=lambda item: item[1], reverse=True)),
        "calibration": calibration_summary(),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict the 2026 FIFA World Cup winner and every match score.")
    parser.add_argument("--runs", type=int, default=20000, help="Monte Carlo simulations for title probabilities.")
    parser.add_argument("--seed", type=int, default=20260618, help="Random seed for Monte Carlo reproducibility.")
    parser.add_argument("--write-csv", type=Path, help="Write the 104-match projected path to CSV.")
    parser.add_argument("--write-json", type=Path, help="Write champion summary, probabilities, ratings, and calibration to JSON.")
    parser.add_argument("--backtest", action="store_true", help="Run the 1994-2018 historical World Cup backtest.")
    parser.add_argument("--write-backtest", type=Path, help="Write historical backtest findings to JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ratings = fit_strengths()
    projections, tables = full_path(ratings)
    title_probs = monte_carlo(ratings, args.runs, args.seed)
    print_report(projections, tables, title_probs)
    if args.write_csv:
        write_csv(args.write_csv, projections)
    if args.write_json:
        args.write_json.write_text(json.dumps(build_summary(ratings, projections, title_probs), indent=2) + "\n", encoding="utf-8")
    if args.backtest or args.write_backtest:
        backtest = run_historical_backtest()
        print_backtest_report(backtest)
        if args.write_backtest:
            args.write_backtest.write_text(json.dumps(backtest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
