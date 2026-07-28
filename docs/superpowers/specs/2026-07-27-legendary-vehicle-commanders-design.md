# Legendary Vehicles & Spacecraft as Commanders — Design

**Date:** 2026-07-27
**Status:** Approved (option: Vehicles + Spacecraft)

## Problem

The commander card-search filter only offers legendary Creatures (plus cards whose
oracle text says "can be your commander"). Since the 2025 Commander rules change,
legendary Vehicles and legendary Spacecraft are also legal commanders, but they never
appear in the commander pickers (upload form, deck edit, event forms).

## Design

Commander eligibility is decided in exactly one place: `_card_role_predicate("commander")`
in `api/db.py`. The frontend (`CardSearchInput role="commander"` →
`GET /api/v1/cards/search?role=commander` → `search_card_names`) passes the role through
untouched, so a backend-only predicate change covers every commander picker.

Change the `commander` branch from:

- `type_line ILIKE '%legendary%' AND type_line ILIKE '%creature%'` OR "can be your commander"

to:

- `type_line ILIKE '%legendary%' AND (type_line ILIKE '%creature%' OR '%vehicle%' OR '%spacecraft%')`
  OR "can be your commander"

No schema, API, or frontend changes. Partner/background/etc. roles are untouched.

## Testing

Extend `tests/test_card_search.py`: assert the compiled commander predicate SQL includes
`vehicle` and `spacecraft` alongside the existing `legendary` / `creature` /
`can be your commander` assertions.
