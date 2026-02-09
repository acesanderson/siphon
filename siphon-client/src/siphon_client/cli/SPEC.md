Here is the updated specification.

## FILE: SPEC.md

```markdown
# Specification: Siphon Query CLI & Printer Utility

**Status:** Draft
**Target Component:** `siphon-client`

## 1. Objective
Implement a "read" interface for the Siphon system, allowing users to search, filter, and retrieve ingested content via the CLI. This includes a new `query` command (modularized into its own script) and a TTY-aware `Printer` utility to support Unix-style piping.

## 2. User Experience (UX)

The `siphon query` command serves two distinct modes: **Interactive Discovery** (human-readable tables/summaries) and **Pipeline Integration** (raw data streams).

### Reference Commands
```bash
# 1. Interactive: List latest 5 YouTube videos
siphon query --type youtube --limit 5

# 2. Interactive: Semantic search with expansion
siphon query "AI Agents" --expand

# 3. Pipeline: Get raw content of the latest item to pipe into an LLM
siphon query --latest --return-type c | ask "Summarize this"

# 4. Action: Open the source of a specific search result
siphon query "The last board meeting" --latest --open

# 5. Filtering: Find items created after a specific date
siphon query --date ">2024-01-01"

```

## 3. Technical Architecture

### 3.1. The Printer Class (`src/siphon_client/cli/printer.py`)

**Purpose:** Decouple UI rendering (spinners, tables) from Data emission (text, JSON) based on `isatty`.

**Requirements:**

* **State:**
* `IS_TTY`: Boolean, detected via `sys.stdout.isatty()`.
* `raw`: Boolean flag override.


* **Methods:**
* `print_raw(data)`: Writes to `stdout`. Used when piping or when `-r` is explicit.
* `print_pretty(renderable)`: Writes to `stderr`. Used for Rich tables/markdown when in TTY.
* `status(msg)`: Returns a Rich spinner context manager (no-op if not TTY).


* **Signal Handling:** Must explicitly handle `SIGPIPE` to prevent stack traces when piped to tools like `head`.

### 3.2. SiphonClient Updates (`src/siphon_client/client.py`)

**Purpose:** Expose search and retrieval logic to the CLI.

**New Methods:**

* `search(query: str, mode: str = "semantic", limit: int = 10, filters: dict = None) -> Collection[ProcessedContent]`
* Interfaces with `HeadwaterClient` to perform the actual query.
* Returns a `Collection` object (monad) for further chaining.



### 3.3. Query Command Implementation (`src/siphon_client/cli/query.py`)

**Purpose:** A dedicated module for the `query` subcommand logic to maintain clean separation of concerns.

**Command Signature:**

```python
import click
from siphon_client.cli.printer import Printer

@click.command()
@click.argument("query_string", required=False)
@click.option("--type", "-t", type=click.Choice(["youtube", "doc", "audio", "web", "drive"]))
@click.option("--limit", "-n", default=10)
@click.option("--latest", "-l", is_flag=True)
@click.option("--history", is_flag=True)
@click.option("--date", "-d", help="Date filter (e.g. '>2024-01-01')")
@click.option("--mode", "-m", type=click.Choice(["semantic", "fuzzy", "sql"]), default="semantic")
@click.option("--expand", "-e", is_flag=True)
@click.option("--return-type", "-r", type=click.Choice(["c", "s", "t", "u", "json", "id"]), default="t")
@click.option("--open", "-o", is_flag=True)
def query(...): ...

```

**Logic Flow:**

1. **Initialize Printer:** Determine TTY status.
2. **Resolve Filters:**
* If `--latest` is set, override `limit=1` and set sort to `created_at DESC`.
* If `--history` is set, ignore `query_string` and sort by `created_at DESC`.
* Parse `--date` (handle `<`, `>` prefixes).


3. **Execute Search:**
* Call `client.search()`.
* If `--expand` is set, take top result and call `collection.expand()`.


4. **Action (Open):**
* If `--open` is set, extract `original_source` from the top result.
* Use `click.launch(url)` to open.
* Handle `headless` environments gracefully (print URL to stderr).


5. **Output Formatting:**
* **Single Result (`-l` or `limit=1`):**
* If `-r t` (default): Print Summary (special case for single result usability).
* Otherwise respect `-r`.


* **List Results:**
* `Printer.print_pretty()`: Render a Rich Table (ID, Title, Date, Score).
* `Printer.print_raw()`: Render newline-delimited data based on `-r`.





### 3.4. Main CLI Integration (`src/siphon_client/cli/siphon_cli.py`)

**Task:** Import the `query` command from `query.py` and register it with the main `siphon` group.

```python
from siphon_client.cli.query import query
# ...
siphon.add_command(query)

```

## 4. Data Models & Enums

**SourceType Enum:**
Ensure mapping matches `siphon_api.enums.SourceType`:

* `youtube` -> `SourceType.YOUTUBE`
* `doc` -> `SourceType.DOC`
* `audio` -> `SourceType.AUDIO`
* `web` -> `SourceType.ARTICLE` (Note mapping)

**Date Parsing Strategy:**

* Support simple ISO-8601 (`YYYY-MM-DD`).
* Regex pattern: `^([<>]=?)(.+)$` to capture operator and date string.

## 5. Dependencies

* `click` (Existing)
* `rich` (Existing)
* `python-dateutil` (May need to be added for robust date parsing, or use strict `datetime.fromisoformat`).

## 6. Testing Plan

* **Mocking:** Mock `HeadwaterClient` responses to return dummy `ProcessedContent`.
* **TTY Simulation:** Test `Printer` by monkeypatching `sys.stdout.isatty`.
* **Pipeline Test:** Verify `siphon query ... | cat` produces clean output without ANSI codes.

```

```
