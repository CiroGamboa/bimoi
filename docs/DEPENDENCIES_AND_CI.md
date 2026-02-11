# Dependencies and CI: Review and Conventions

## Current setup

| Extra | Contents | Purpose |
|-------|----------|---------|
| **dev** | pytest, testcontainers[neo4j], pre-commit | Testing + lint/format tooling |
| **api** | fastapi, uvicorn | Run the API |
| **bot** | neo4j, python-telegram-bot, python-dotenv | Run the Telegram bot |

**Tests and what they need:**

- `test_contact_service.py`, `test_identity.py`: core package only.
- `test_neo4j_repository.py`: `testcontainers[neo4j]` (and transitive neo4j driver) — provided by **dev**.
- `test_api.py`: **fastapi** — provided by **api**.

**CI today:**

- **test** job: `pip install -e ".[dev,api]"` then pytest → runs full suite.
- **pre-commit** job: `pip install -e ".[dev]"` then pre-commit → lint/format only.

## Are we mixing things?

Yes, in a few ways:

1. **dev = testing + tooling**
   `dev` mixes test runtime (pytest, testcontainers) with development tooling (pre-commit). Many projects either:
   - Keep one “dev” that means “everything needed to develop and test” (current approach), or
   - Split into e.g. `dev` (pre-commit, ruff, mypy) and `test` (pytest, testcontainers) so CI can install only what each job needs.

2. **requirements-dev.txt is out of sync**
   It lists `neo4j` and says “install with pip install -e .[dev]”, but `[dev]` does not include `neo4j`. Neo4j is in `[bot]`. Testcontainers pulls in a neo4j driver for the integration tests, so the test job doesn’t need `.[bot]` for that. So either drop `neo4j` from requirements-dev.txt or document that it’s for “run the bot locally”, not for tests.

3. **Docs say “tests = .[dev]” but API tests need api**
   AGENTS.md says: “Tests: pip install -e '.[dev]' then pytest”. That fails when collecting `test_api.py` (no fastapi). So the documented “run tests” command should be “pip install -e '.[dev,api]' then pytest” for the full suite.

## Recommended conventions (without big refactors)

- **Treat extras by “how you run the app”:**
  - **api** = run the API.
  - **bot** = run the bot.
  - **dev** = everything needed to work on the repo without running app code: test runner, test helpers, and tooling (pre-commit). So “dev” = “develop + test + lint” in one extra.

- **CI:**
  - **test job:** install `.[dev,api]` and run pytest. That runs all tests (including API tests). No need to install `.[bot]` unless you add tests that require the full bot stack.
  - **pre-commit job:** install `.[dev]` and run pre-commit. No api/bot needed.

- **Document one canonical “run full test suite”:**
  - Local and CI: `pip install -e ".[dev,api]"` then `pytest tests/ -v`.
  - Update AGENTS.md (and README if it mentions tests) to use this.

- **requirements-dev.txt:**
  - Either remove it and point everyone to `pip install -e ".[dev,api]"` for tests, or
  - Keep it as an alternative and sync it: e.g. “pre-commit, pytest, testcontainers[neo4j]” (and note that API tests need the api extra: `.[dev,api]`).

## Optional: split “dev” and “test”

If you want a clearer separation:

- **dev:** pre-commit only (or pre-commit + ruff/mypy if you add them).
- **test:** pytest, testcontainers[neo4j].
- **api**, **bot:** unchanged.

Then:

- Lint/format CI: `.[dev]`.
- Test CI: `.[test,api]` (and `.[test,bot]` only if you add bot-only tests).
- Local “I want to run tests and hooks”: `.[dev,test,api]` or a single **all** extra that composes them.

For the current MVP size, keeping **dev** as “testing + tooling” and installing **.[dev,api]** in the test job is a good balance; the main fix is documenting the correct install and aligning requirements-dev.txt with that.
