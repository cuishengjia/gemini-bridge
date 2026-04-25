"""One-shot builder for `research_200.jsonl`.

Holds the 200 curated query seeds as Python tuples, then mechanically:
  1. Assigns `q001` … `q200` ids in (bucket, domain, seed-order) stable order.
  2. Assigns difficulty levels to hit EXACT per-bucket targets
     (strong 48/24/8, medium 36/18/6, obscure 24/12/4, common 12/6/2).
  3. Validates the resulting rows against `evals.lib.schema.validate_dataset`.
  4. Writes `research_200.jsonl`.

Rerunnable. Idempotent. Fails loud on any invariant violation.

Run from the skill root:
    python3 evals/datasets/_build.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVALS_ROOT = HERE.parent
if str(EVALS_ROOT) not in sys.path:
    sys.path.insert(0, str(EVALS_ROOT))

from lib.schema import (  # noqa: E402
    BUCKET_COUNTS,
    QueryRow,
    dump_jsonl,
    validate_dataset,
)

# Difficulty target per bucket (sums must match BUCKET_COUNTS).
DIFFICULTY_TARGETS: dict[str, dict[int, int]] = {
    "strong": {1: 48, 2: 24, 3: 8},
    "medium": {1: 36, 2: 18, 3: 6},
    "evergreen_obscure": {1: 24, 2: 12, 3: 4},
    "evergreen_common": {1: 12, 2: 6, 3: 2},
}


@dataclass
class Seed:
    """Query seed before id/difficulty assignment."""

    query: str
    time_sensitivity: str
    domain: str
    notes: str


# ---------------------------------------------------------------------------
# STRONG (80) — within ~30 days of 2026-04-20; require live search
# ---------------------------------------------------------------------------

STRONG: list[Seed] = [
    # --- tech (16) ---
    Seed("What is the current latest stable Python release as of April 2026?", "strong", "tech", "minor point versions rotate monthly"),
    Seed("What is the latest LTS release of Node.js as of April 2026?", "strong", "tech", ""),
    Seed("What TypeScript version was released most recently in April 2026?", "strong", "tech", ""),
    Seed("What is Anthropic's newest Claude model announced in April 2026?", "strong", "tech", ""),
    Seed("What is the latest stable React version released in 2026?", "strong", "tech", ""),
    Seed("What is the most recent Rust stable release as of April 2026?", "strong", "tech", ""),
    Seed("What major feature did Next.js ship in its latest release this month?", "strong", "tech", ""),
    Seed("What is the latest Ubuntu LTS release after 24.04?", "strong", "tech", ""),
    Seed("What's new in the latest Bun runtime release published in April 2026?", "strong", "tech", ""),
    Seed("What breaking changes were introduced in the latest Django release this spring?", "strong", "tech", ""),
    Seed("Compare the most recent releases of Deno and Bun in 2026 — which shipped more features?", "strong", "tech", "cross-source"),
    Seed("What changed between the last two PostgreSQL point releases announced recently?", "strong", "tech", ""),
    Seed("What's new in the April 2026 Kubernetes release?", "strong", "tech", ""),
    Seed("Which AI coding tool released a major update in April 2026, and what was added?", "strong", "tech", ""),
    Seed("Compare the most recent GPT release date and Claude release date this month — which came first?", "strong", "tech", ""),
    Seed("Has Apple confirmed a Swift 7 ship timeline in the last month? What's the latest status?", "strong", "tech", "speculative"),
    # --- news_finance (16) ---
    Seed("What is the USD/JPY exchange rate as of mid-April 2026?", "strong", "news_finance", ""),
    Seed("What is Bitcoin's price in USD on April 20, 2026?", "strong", "news_finance", ""),
    Seed("What is the current US Federal funds rate after the April 2026 FOMC meeting?", "strong", "news_finance", ""),
    Seed("What was the S&P 500 closing value on the last trading day before April 20, 2026?", "strong", "news_finance", ""),
    Seed("What is Tesla's stock price as of mid-April 2026?", "strong", "news_finance", ""),
    Seed("What is the latest US CPI inflation reading (March 2026 data release)?", "strong", "news_finance", ""),
    Seed("What major M&A deal was announced in the tech sector in April 2026?", "strong", "news_finance", ""),
    Seed("What is the ECB main refinancing rate as of April 2026?", "strong", "news_finance", ""),
    Seed("How has the gold price moved over the past 30 days?", "strong", "news_finance", ""),
    Seed("What tariff changes did the US implement on Chinese goods so far in 2026?", "strong", "news_finance", ""),
    Seed("What's the outlook from the most recent Bank of Japan monetary policy meeting?", "strong", "news_finance", ""),
    Seed("Which major US bank reported Q1 2026 earnings in April — what were the key results?", "strong", "news_finance", ""),
    Seed("What is the status of the US debt ceiling negotiation this spring?", "strong", "news_finance", ""),
    Seed("Which G7 central bank most recently changed rates in April 2026?", "strong", "news_finance", ""),
    Seed("Is a US recession priced into the yield curve as of April 2026?", "strong", "news_finance", "forward-looking"),
    Seed("Which major currency is the best performer year-to-date in 2026?", "strong", "news_finance", ""),
    # --- science (16) ---
    Seed("What notable peer-reviewed paper was published in Nature in April 2026?", "strong", "science", ""),
    Seed("What significant exoplanet discovery was announced this month (April 2026)?", "strong", "science", ""),
    Seed("What clinical trial result was reported in April 2026 for Alzheimer's treatment?", "strong", "science", ""),
    Seed("What is the current operational status of the James Webb Space Telescope as of April 2026?", "strong", "science", ""),
    Seed("What major CRISPR advance was published in Q1 2026?", "strong", "science", ""),
    Seed("When is the next SpaceX Starship launch scheduled as of April 2026?", "strong", "science", ""),
    Seed("What significant earthquake (M6+) occurred in the last 30 days, and what was its magnitude?", "strong", "science", ""),
    Seed("What is the latest H5N1 human case report in the US as of April 2026?", "strong", "science", ""),
    Seed("What drug most recently received FDA approval in April 2026?", "strong", "science", ""),
    Seed("What new advanced material was announced by a top lab in April 2026?", "strong", "science", ""),
    Seed("What fusion reactor milestone has been reported so far in 2026?", "strong", "science", ""),
    Seed("What were the findings of the most recent IPCC-linked climate assessment released in 2026?", "strong", "science", ""),
    Seed("Compare the two most recent major exoplanet announcements — which is more significant for habitability?", "strong", "science", "cross-source"),
    Seed("Is the ITER fusion project on schedule as of April 2026?", "strong", "science", "speculative"),
    Seed("Has any lab claimed room-temperature superconductivity with independent replication in 2026?", "strong", "science", "speculative"),
    Seed("What is the confirmed count of moons around Saturn as of 2026?", "strong", "science", ""),
    # --- lifestyle (16) ---
    Seed("What iPhone model was most recently released in 2026?", "strong", "lifestyle", ""),
    Seed("Which movie topped the US weekend box office in the weekend before April 20, 2026?", "strong", "lifestyle", ""),
    Seed("What new gaming console or major handheld launched in April 2026?", "strong", "lifestyle", ""),
    Seed("Which popular TV series premiered a new season in April 2026?", "strong", "lifestyle", ""),
    Seed("What major music album was released in April 2026?", "strong", "lifestyle", ""),
    Seed("What is the current top-selling game on Steam in April 2026?", "strong", "lifestyle", ""),
    Seed("Which restaurant earned a new 3rd Michelin star in April 2026?", "strong", "lifestyle", ""),
    Seed("Which travel destination was named best for 2026 by a major publication this month?", "strong", "lifestyle", ""),
    Seed("What is the most-watched Netflix show globally in April 2026?", "strong", "lifestyle", ""),
    Seed("Which smartphone brand had the highest global market share in Q1 2026?", "strong", "lifestyle", ""),
    Seed("Which streaming platform added the most net subscribers in Q1 2026?", "strong", "lifestyle", ""),
    Seed("What is the best-selling EV model in the US in Q1 2026?", "strong", "lifestyle", ""),
    Seed("Compare Apple VisionPro and Meta Quest 3 latest sales updates in 2026 — which leads?", "strong", "lifestyle", ""),
    Seed("What fashion trend dominated spring 2026 runway shows?", "strong", "lifestyle", ""),
    Seed("Has Apple shipped AR glasses by April 2026, and what's the market reception?", "strong", "lifestyle", "speculative"),
    Seed("How is Tesla's robotaxi rollout progressing as of April 2026?", "strong", "lifestyle", "speculative"),
    # --- sports_people (16) ---
    Seed("Who won the Masters golf tournament in April 2026?", "strong", "sports_people", ""),
    Seed("Which team leads the NBA Eastern Conference standings as of mid-April 2026?", "strong", "sports_people", ""),
    Seed("Who won the F1 Chinese Grand Prix in April 2026?", "strong", "sports_people", ""),
    Seed("Which tennis player won the Miami Open 2026?", "strong", "sports_people", ""),
    Seed("Who leads the English Premier League with 4 matches remaining in April 2026?", "strong", "sports_people", ""),
    Seed("Which MLB team has the best record as of April 20, 2026?", "strong", "sports_people", ""),
    Seed("Who won the World Figure Skating Championships 2026?", "strong", "sports_people", ""),
    Seed("Which boxing title fight took place in April 2026, and who won?", "strong", "sports_people", ""),
    Seed("Which NBA player is leading MVP odds in April 2026?", "strong", "sports_people", ""),
    Seed("What is LeBron James's current status (playing or retired) as of April 2026?", "strong", "sports_people", ""),
    Seed("Who advanced from the UEFA Champions League quarter-finals in April 2026?", "strong", "sports_people", ""),
    Seed("Which F1 team leads the constructors championship after the first 5 races of 2026?", "strong", "sports_people", ""),
    Seed("What was the attendance record for an NWSL match in early 2026?", "strong", "sports_people", ""),
    Seed("Compare the two most recent NBA MVP frontrunners as of April 2026 — who has the stronger case?", "strong", "sports_people", "cross-source"),
    Seed("Can Max Verstappen win a 6th F1 title in 2026 based on the current season pace?", "strong", "sports_people", "speculative"),
    Seed("Is Shohei Ohtani pitching regularly in 2026? What is his current injury status?", "strong", "sports_people", "speculative"),
]

# ---------------------------------------------------------------------------
# MEDIUM (60) — within ~1 year of 2026-04-20
# ---------------------------------------------------------------------------

MEDIUM: list[Seed] = [
    # --- tech (12) ---
    Seed("When does Python 3.13 reach end-of-life according to the official schedule?", "medium", "tech", ""),
    Seed("What major feature did TypeScript 5.7 introduce?", "medium", "tech", ""),
    Seed("Which major JavaScript framework adopted signals as a first-class primitive in 2025?", "medium", "tech", ""),
    Seed("What Linux kernel version shipped in 2025 with significant io_uring changes?", "medium", "tech", ""),
    Seed("What was Anthropic's flagship product launch in 2025?", "medium", "tech", ""),
    Seed("What's the rendering-model difference between React 19 and React 18?", "medium", "tech", ""),
    Seed("What was the most significant OpenAI developer-facing release of 2025?", "medium", "tech", ""),
    Seed("Which programming language rose fastest in the TIOBE index during 2025?", "medium", "tech", ""),
    Seed("Did any major US tech company lay off more than 5% of staff in 2025?", "medium", "tech", ""),
    Seed("Compare GPT-5 and Claude 4 release dates — which shipped first?", "medium", "tech", "cross-source"),
    Seed("What is the current state of WebAssembly Garbage Collection adoption across browsers (late 2025 – early 2026)?", "medium", "tech", ""),
    Seed("How did the GitHub Copilot antitrust or IP case progress in 2025?", "medium", "tech", "speculative"),
    # --- news_finance (12) ---
    Seed("What was the US Federal funds rate at the end of 2025?", "medium", "news_finance", ""),
    Seed("Who is the current US Treasury Secretary?", "medium", "news_finance", ""),
    Seed("What was the outcome of the 2024 US presidential election?", "medium", "news_finance", ""),
    Seed("What was Bitcoin's all-time high price in 2025?", "medium", "news_finance", ""),
    Seed("What was the largest US IPO of 2025 by market cap?", "medium", "news_finance", ""),
    Seed("What new sanctions did the EU impose on Russia in 2025?", "medium", "news_finance", ""),
    Seed("How did China's GDP growth evolve across the four quarters of 2025?", "medium", "news_finance", ""),
    Seed("How did the Nikkei 225 perform in 2025 versus 2024?", "medium", "news_finance", ""),
    Seed("What was the verdict in the major US antitrust case against a big-tech firm in 2025?", "medium", "news_finance", ""),
    Seed("Which sovereign wealth fund posted the highest 2025 calendar-year return?", "medium", "news_finance", "cross-source"),
    Seed("How has AI capex reshaped hyperscaler quarterly earnings during 2025?", "medium", "news_finance", "cross-source"),
    Seed("Did any G7 country enter technical recession in 2025?", "medium", "news_finance", "speculative"),
    # --- science (12) ---
    Seed("When did NASA's Artemis II mission launch or what is its currently planned date?", "medium", "science", ""),
    Seed("What was the most-cited scientific paper of 2025 according to major citation trackers?", "medium", "science", ""),
    Seed("What was the 2025 Nobel Prize in Physiology or Medicine awarded for?", "medium", "science", ""),
    Seed("What was the 2025 Nobel Prize in Physics awarded for?", "medium", "science", ""),
    Seed("Which COVID variant was dominant globally in late 2025?", "medium", "science", ""),
    Seed("What progress did Neuralink's human trial make in 2025?", "medium", "science", ""),
    Seed("What is the current status of the SKA (Square Kilometre Array) telescope as of 2026?", "medium", "science", ""),
    Seed("What protein-design advances did the Baker lab publish in 2025?", "medium", "science", ""),
    Seed("What Arctic sea ice change was measured during the 2025 summer melt vs prior years?", "medium", "science", "cross-source"),
    Seed("How does the 2025 AMOC slowdown research compare with the previous decade of findings?", "medium", "science", "cross-source"),
    Seed("Did any fusion startup reach net-positive energy gain with sustained operation in 2025?", "medium", "science", "speculative"),
    Seed("Was a long-awaited malaria-eradication milestone reached anywhere in 2025?", "medium", "science", "speculative"),
    # --- lifestyle (12) ---
    Seed("What was the Oscar Best Picture winner announced in March 2026 (for 2025 films)?", "medium", "lifestyle", ""),
    Seed("Which K-pop group dominated the 2025 global charts?", "medium", "lifestyle", ""),
    Seed("What was the top-grossing film worldwide in 2025?", "medium", "lifestyle", ""),
    Seed("Which video game won Game of the Year 2025 at The Game Awards?", "medium", "lifestyle", ""),
    Seed("What was Spotify's most-streamed song of 2025?", "medium", "lifestyle", ""),
    Seed("What was the best-selling EV brand globally for calendar year 2025?", "medium", "lifestyle", ""),
    Seed("Which fashion house had the biggest creative-director change in 2025?", "medium", "lifestyle", ""),
    Seed("How did Disney+'s subscriber count change during 2025?", "medium", "lifestyle", ""),
    Seed("What is the current Michelin star count for Tokyo in the 2026 guide?", "medium", "lifestyle", ""),
    Seed("Did Apple Vision Pro or Meta Quest 3 outsell the other in calendar 2025?", "medium", "lifestyle", "cross-source"),
    Seed("Compare the 2025 subscriber trajectories of Netflix, Disney+, and HBO/Max — who grew fastest?", "medium", "lifestyle", "cross-source"),
    Seed("Did any new fast-casual or fast-food chain IPO in 2025 and trade well?", "medium", "lifestyle", "speculative"),
    # --- sports_people (12) ---
    Seed("Who won the 2025 NBA Finals?", "medium", "sports_people", ""),
    Seed("Who won the 2025 MLB World Series?", "medium", "sports_people", ""),
    Seed("Who won the 2025 UEFA Champions League final?", "medium", "sports_people", ""),
    Seed("Who won the 2025 Formula 1 Drivers Championship?", "medium", "sports_people", ""),
    Seed("Who won the 2025 Wimbledon Men's singles final?", "medium", "sports_people", ""),
    Seed("Which soccer player had the highest transfer fee in summer 2025?", "medium", "sports_people", ""),
    Seed("Who won the 2025 Tour de France?", "medium", "sports_people", ""),
    Seed("Was the men's 100m world record broken during 2025?", "medium", "sports_people", ""),
    Seed("Which NFL team had the longest winning streak during the 2025 season?", "medium", "sports_people", ""),
    Seed("Compare USMNT and Canada's preparation results heading into the 2026 World Cup — who looks stronger?", "medium", "sports_people", "cross-source"),
    Seed("Did Japan win any medal at the 2025 World Athletics Championships?", "medium", "sports_people", "cross-source"),
    Seed("Will LeBron James's 2024-25 final-season statline age well compared to other older guards?", "medium", "sports_people", "speculative"),
]

# ---------------------------------------------------------------------------
# EVERGREEN_OBSCURE (40) — time-insensitive but unlikely in parametric memory
# ---------------------------------------------------------------------------

OBSCURE: list[Seed] = [
    # --- tech (8) ---
    Seed("In the Linux kernel on x86-64, what syscall number is assigned to pidfd_send_signal?", "evergreen_obscure", "tech", ""),
    Seed("What specific environment variable disables telemetry in the .NET 8 runtime?", "evergreen_obscure", "tech", ""),
    Seed("Explain the difference between SO_REUSEPORT and SO_REUSEADDR in the Linux socket API.", "evergreen_obscure", "tech", ""),
    Seed("What is the default eviction policy in Redis when maxmemory-policy is not explicitly set?", "evergreen_obscure", "tech", ""),
    Seed("What does the SQLAlchemy IDENTIFIER_QUOTE-related config setting control?", "evergreen_obscure", "tech", ""),
    Seed("What is the default max_allowed_packet size in a MySQL 8 server, and which variable controls it?", "evergreen_obscure", "tech", ""),
    Seed("Compare the WAL designs of SQLite and PostgreSQL — what subtle difference affects concurrent readers?", "evergreen_obscure", "tech", "cross-source"),
    Seed("Explain the relationship between Pin<Box<T>> and self-referential async futures in Rust.", "evergreen_obscure", "tech", ""),
    # --- news_finance (8) ---
    Seed("What is the purpose of SEC Form 144 in the US securities regime?", "evergreen_obscure", "news_finance", ""),
    Seed("What is the typical lock-up period for a Hong Kong IPO?", "evergreen_obscure", "news_finance", ""),
    Seed("Explain 'Herstatt risk' in foreign-exchange settlement.", "evergreen_obscure", "news_finance", ""),
    Seed("What was the triggering event for the 1997 Thai baht devaluation?", "evergreen_obscure", "news_finance", ""),
    Seed("What is the difference between US TIPS and I Bonds as inflation-protected instruments?", "evergreen_obscure", "news_finance", ""),
    Seed("Why was the LIBOR-to-SOFR transition especially bumpy for CLO tranches?", "evergreen_obscure", "news_finance", ""),
    Seed("Explain the 'snowball effect' in Brazilian government debt dynamics of the 1990s.", "evergreen_obscure", "news_finance", "cross-source"),
    Seed("What is 'widow-and-orphan' stock, and why does the term persist in investor parlance?", "evergreen_obscure", "news_finance", "cross-source"),
    # --- science (8) ---
    Seed("What is the approximate wavelength of the Lyman-alpha line of hydrogen?", "evergreen_obscure", "science", ""),
    Seed("What is the molecular formula of caffeine?", "evergreen_obscure", "science", ""),
    Seed("Explain why the Hayflick limit is historically significant for understanding cellular aging.", "evergreen_obscure", "science", ""),
    Seed("What is the Tully-Fisher relation used for in observational astronomy?", "evergreen_obscure", "science", ""),
    Seed("Describe the role of the sodium-potassium pump in neuron action-potential maintenance.", "evergreen_obscure", "science", ""),
    Seed("What distinguishes a prion from a conventional virus?", "evergreen_obscure", "science", ""),
    Seed("How did the Miller-Urey experiment challenge earlier theories of abiogenesis, and what are its modern critiques?", "evergreen_obscure", "science", "cross-source"),
    Seed("What is epistasis in genetics, and give an example that complicates GWAS interpretation.", "evergreen_obscure", "science", "cross-source"),
    # --- lifestyle (8) ---
    Seed("Who directed the 1962 film 'The Manchurian Candidate'?", "evergreen_obscure", "lifestyle", ""),
    Seed("What is the national dish of Peru?", "evergreen_obscure", "lifestyle", ""),
    Seed("Explain the historical difference between a macaron and a macaroon.", "evergreen_obscure", "lifestyle", ""),
    Seed("What is 'wabi-sabi' in Japanese aesthetics, and how does it differ from 'mono no aware'?", "evergreen_obscure", "lifestyle", ""),
    Seed("What is the historical origin of the French 75 cocktail?", "evergreen_obscure", "lifestyle", ""),
    Seed("Why is haggis traditionally served on Burns Night?", "evergreen_obscure", "lifestyle", ""),
    Seed("How did the Slow Food movement originate, and where was its first public event held?", "evergreen_obscure", "lifestyle", "cross-source"),
    Seed("What is the origin of the term 'Stockholm syndrome', and how has it been critiqued psychologically?", "evergreen_obscure", "lifestyle", "cross-source"),
    # --- sports_people (8) ---
    Seed("Who was the first Formula 1 driver to score a championship point for Japan?", "evergreen_obscure", "sports_people", ""),
    Seed("In which year did Pelé score his 1000th career goal?", "evergreen_obscure", "sports_people", ""),
    Seed("Why is Darryl Dawkins famous for breaking NBA backboards, and when did this happen?", "evergreen_obscure", "sports_people", ""),
    Seed("Who held the men's world mile record immediately before Roger Bannister's sub-4-minute run?", "evergreen_obscure", "sports_people", ""),
    Seed("What was the 'Rumble in the Jungle', and why is it culturally significant?", "evergreen_obscure", "sports_people", ""),
    Seed("Who is Fausto Coppi, and why is he considered a cycling legend?", "evergreen_obscure", "sports_people", ""),
    Seed("Compare the Fosbury flop and the straddle technique in high jump — why did the flop supplant the straddle?", "evergreen_obscure", "sports_people", "cross-source"),
    Seed("What was unique about Jim Thorpe's 1912 Olympic performance, and why were his medals stripped?", "evergreen_obscure", "sports_people", "cross-source"),
]

# ---------------------------------------------------------------------------
# EVERGREEN_COMMON (20) — baseline common knowledge
# ---------------------------------------------------------------------------

COMMON: list[Seed] = [
    # --- tech (4) ---
    Seed("What does HTTP status code 404 mean?", "evergreen_common", "tech", ""),
    Seed("What is the default port for HTTPS?", "evergreen_common", "tech", ""),
    Seed("What is the primary difference between TCP and UDP?", "evergreen_common", "tech", ""),
    Seed("What is Moore's Law?", "evergreen_common", "tech", ""),
    # --- news_finance (4) ---
    Seed("What is the official currency of Japan?", "evergreen_common", "news_finance", ""),
    Seed("What does the abbreviation GDP stand for?", "evergreen_common", "news_finance", ""),
    Seed("What is the fundamental difference between a stock and a bond?", "evergreen_common", "news_finance", ""),
    Seed("Explain compound interest in one paragraph.", "evergreen_common", "news_finance", ""),
    # --- science (4) ---
    Seed("What is the chemical formula for water?", "evergreen_common", "science", ""),
    Seed("At what temperature does water boil at sea level in degrees Celsius?", "evergreen_common", "science", ""),
    Seed("Why does the daytime sky appear blue?", "evergreen_common", "science", ""),
    Seed("How many recognized planets are in our solar system, excluding Pluto?", "evergreen_common", "science", ""),
    # --- lifestyle (4) ---
    Seed("Who painted the Mona Lisa?", "evergreen_common", "lifestyle", ""),
    Seed("In what year did the RMS Titanic sink?", "evergreen_common", "lifestyle", ""),
    Seed("Which language has the most native speakers worldwide?", "evergreen_common", "lifestyle", ""),
    Seed("Why do some cultures bow as a greeting instead of shaking hands?", "evergreen_common", "lifestyle", ""),
    # --- sports_people (4) ---
    Seed("How many players are on a soccer team on the field at one time?", "evergreen_common", "sports_people", ""),
    Seed("Who is Michael Jordan, in one sentence?", "evergreen_common", "sports_people", ""),
    Seed("In which year were the first modern Olympic Games held?", "evergreen_common", "sports_people", ""),
    Seed("Why is the marathon distance 42.195 km?", "evergreen_common", "sports_people", ""),
]

ALL_SEEDS: list[Seed] = STRONG + MEDIUM + OBSCURE + COMMON


def _assign_difficulty_sequence(n_target: dict[int, int]) -> list[int]:
    """Build a difficulty sequence summing to the targets.

    Interleaves high-difficulty tags among the d1 entries so that each
    (bucket, domain) cell gets a mix rather than 'all d1 first'.
    """
    total = sum(n_target.values())
    d1, d2, d3 = n_target[1], n_target[2], n_target[3]
    seq: list[int] = []
    # Spread d3 roughly evenly, then d2, filling the rest with d1.
    d3_positions = set()
    if d3:
        step = max(1, total // d3)
        d3_positions = {i * step for i in range(d3)}
    d2_positions: set[int] = set()
    if d2:
        step = max(1, total // d2)
        d2_positions = {
            p for p in (i * step + step // 2 for i in range(d2)) if p not in d3_positions
        }
    # Fallback: fill any remaining d2 into free slots deterministically.
    needed_d2 = d2 - len(d2_positions)
    if needed_d2 > 0:
        for i in range(total):
            if i not in d3_positions and i not in d2_positions:
                d2_positions.add(i)
                needed_d2 -= 1
                if needed_d2 == 0:
                    break

    for i in range(total):
        if i in d3_positions:
            seq.append(3)
        elif i in d2_positions:
            seq.append(2)
        else:
            seq.append(1)

    # Correct any drift from integer math by re-balancing counts.
    counts = {1: seq.count(1), 2: seq.count(2), 3: seq.count(3)}
    # Swap entries until counts match targets exactly.
    for level in (3, 2, 1):
        while counts[level] > n_target[level]:
            # Find first occurrence of `level` and demote to a short level.
            short = next(k for k in (1, 2, 3) if counts[k] < n_target[k])
            idx = seq.index(level)
            seq[idx] = short
            counts[level] -= 1
            counts[short] += 1
    assert counts == n_target, f"difficulty distribution mismatch: {counts} vs {n_target}"
    return seq


def build_rows(seeds: list[Seed]) -> list[QueryRow]:
    # Group seeds by bucket preserving encounter order within each bucket.
    by_bucket: dict[str, list[Seed]] = {b: [] for b in BUCKET_COUNTS}
    for s in seeds:
        by_bucket[s.time_sensitivity].append(s)

    # Validate per-bucket counts and per-domain distribution inside each bucket.
    for bucket, expected in BUCKET_COUNTS.items():
        actual = len(by_bucket[bucket])
        if actual != expected:
            raise ValueError(
                f"bucket {bucket!r}: expected {expected} seeds, got {actual}"
            )

    # Build ordered seed list (strong → medium → obscure → common)
    ordered_seeds: list[Seed] = []
    for bucket in ("strong", "medium", "evergreen_obscure", "evergreen_common"):
        ordered_seeds.extend(by_bucket[bucket])

    # Assign difficulties per bucket using the helper.
    rows: list[QueryRow] = []
    idx = 1
    for bucket in ("strong", "medium", "evergreen_obscure", "evergreen_common"):
        bucket_seeds = by_bucket[bucket]
        target = DIFFICULTY_TARGETS[bucket]
        if sum(target.values()) != len(bucket_seeds):
            raise ValueError(
                f"difficulty target for {bucket!r} sums to "
                f"{sum(target.values())}, but bucket has {len(bucket_seeds)} seeds"
            )
        diffs = _assign_difficulty_sequence(target)
        for seed, diff in zip(bucket_seeds, diffs):
            rows.append(
                QueryRow(
                    id=f"q{idx:03d}",
                    query=seed.query,
                    time_sensitivity=seed.time_sensitivity,
                    domain=seed.domain,
                    difficulty=diff,
                    notes=seed.notes,
                )
            )
            idx += 1
    return rows


def main() -> int:
    rows = build_rows(ALL_SEEDS)
    errors = validate_dataset(rows)
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        print(f"\n{len(errors)} validation error(s); aborting.", file=sys.stderr)
        return 1

    out_path = HERE / "research_200.jsonl"
    dump_jsonl(rows, out_path)
    print(f"wrote {len(rows)} rows to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
