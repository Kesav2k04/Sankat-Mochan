"""Unit tests for the TAGS wire-format gate + helpers in intelligence.py.
parse_tags is the enum whitelist for UNTRUSTED mesh/LLM output (rule #8)."""
from __future__ import annotations

import pytest

from intelligence import (TAG_LM_MAX, haversine_km, humanize_tags, parse_tags)


# ---- parse_tags: acceptance ---------------------------------------------------

def test_full_line_round_trip():
    tags = parse_tags("TAGS c:3 inj:bleed trap:y hz:water mob:n unresp:y lm:old temple gate")
    assert tags == {"c": 3, "inj": "bleed", "trap": "y", "hz": "water",
                    "mob": "n", "unresp": "y", "lm": "old temple gate"}


def test_landmark_consumes_the_remainder_and_is_capped():
    tags = parse_tags("TAGS lm:" + "x" * 200)
    assert len(tags["lm"]) == TAG_LM_MAX
    # lm swallows everything after it — keys can't hide behind a landmark
    tags = parse_tags("TAGS lm:behind the bus stand trap:y")
    assert tags == {"lm": "behind the bus stand trap:y"[:TAG_LM_MAX]}


def test_case_and_spacing_of_values():
    assert parse_tags("TAGS inj:BLEED") == {"inj": "bleed"}
    assert parse_tags("TAGS   c:2    trap:y") == {"c": 2, "trap": "y"}


# ---- parse_tags: rejection / dropping ------------------------------------------

@pytest.mark.parametrize("not_tags", [
    "help, water rising",       # ordinary gist
    "TAGS",                     # no body at all (prefix requires the space)
    "TAGS ",                    # empty body
    "TAGS :::",                 # malformed head
    "TAGS 123:y",               # non-alpha key first
])
def test_non_tags_input_returns_none(not_tags):
    assert parse_tags(not_tags) is None


def test_unknown_keys_and_bad_values_are_dropped_not_fatal():
    assert parse_tags("TAGS weapon:knife c:2") == {"c": 2}
    assert parse_tags("TAGS hz:lava trap:y") == {"trap": "y"}
    assert parse_tags("TAGS c:0 trap:y") == {"trap": "y"}       # count below 1
    assert parse_tags("TAGS c:100 trap:y") == {"trap": "y"}     # count above 99
    assert parse_tags("TAGS unresp:n") is None                  # only 'y' is whitelisted


def test_trimmed_tail_keeps_earlier_pairs():
    # the phone's 244-byte trim can cut mid-pair; earlier pairs must survive
    assert parse_tags("TAGS c:4 inj:fracture tr") == {"c": 4, "inj": "fracture"}


def test_valueless_pair_mid_line_does_not_poison_earlier_pairs():
    tags = parse_tags("TAGS trap:y inj: hz:water")
    assert tags is not None and tags["trap"] == "y"


# ---- humanize_tags --------------------------------------------------------------

def test_humanize_full():
    line = humanize_tags({"c": 3, "inj": "breath", "trap": "y", "hz": "water",
                          "mob": "n", "unresp": "y", "lm": "temple"})
    assert line == ("3 people · breathing difficulty · trapped · rising water · "
                    "cannot move · UNRESPONSIVE · near temple")


def test_humanize_singular_and_empty():
    assert humanize_tags({"c": 1}) == "1 person"
    assert humanize_tags({}) == "situation update"
    assert humanize_tags({"inj": "none", "hz": "none"}) == "situation update"


# ---- haversine -------------------------------------------------------------------

def test_haversine_zero_and_known_distance():
    assert haversine_km(12.97, 77.59, 12.97, 77.59) == 0
    # Bengaluru -> Chennai is ~290 km as the crow flies
    d = haversine_km(12.9716, 77.5946, 13.0827, 80.2707)
    assert 280 < d < 300
