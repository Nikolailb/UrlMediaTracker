# Source regression cases

These saved cases cover the concrete series and URL shapes discussed during the checker overhaul. Fixtures contain only the minimal page structure needed for a check; tests do not depend on a live site's current chapter count.

| Source example | Expected behavior | Test |
|---|---|---|
| FreeWebNovel `harem-system-in-a-fantasy-world` | Chapter 644 wins over unrelated chapter 5682 | `test_freewebnovel_checker.py`, `test_upgrade_contract.py` |
| FreeWebNovel `as-a-mafia-boss-i-refuse-to-be-an-extra` | Series metadata and latest list agree on chapter 546 | `test_freewebnovel_checker.py` |
| FreeWebNovel `my-taboo-harem` | Series metadata and latest list agree on chapter 1314 | `test_freewebnovel_checker.py` |
| FreeWebNovel `reborn-as-the-genius-son-of-the-richest-family` | Chapter 1416 link; unstarted progress opens chapter 1 | `test_freewebnovel_checker.py`, `test_unstarted_reading.py` |
| Comix `39w1n-the-mating-of-elves` | Metadata returns chapter 73; example links 73 and 71 cannot make an empty generic HTML ToC succeed; opaque chapter IDs are not probed | `test_toc_overhaul.py`, `test_opaque_chapter_url.py` |
| Webtoons `unordinary` | Visible episode 393 wins over `episode_no=412`; links from other series stay excluded | `test_toc_overhaul.py` |
| Hentai20 `i-became-a-pornhwa-npc` | ToC outside-path links require the supplied chapter-75 URL shape; then chapter 80 and its exact URL are found; the advanced example survives saving | `test_toc_overhaul.py`, `test_add_chapter_example.py` |
| Manhwaread `the-mating-of-elves` | Sequential chapter-60 example finds 63 through bounded probing | `test_incremental_probe_sites.py` |
| WebNovel `35844914500239705` | Embedded catalog yields exact chapter IDs; auxiliary count and title number do not replace chapter index; opaque IDs never become progress or a probe template | `test_webnovel_checker.py` |
| Royal Road `107917` Sky Pride | Fiction ID survives slug changes; complete embedded catalog wins over first rendered page; volume title numbers restart and bonus posts count | `test_royalroad_checker.py` |
| Royal Road `65629` The Game at Carousel | Earlier stubbed chapters do not lower the tracker number; missing latest chapter ID requires review | `test_royalroad_checker.py` |
| Scribble Hub `2388343` Magical Girls | Latest row order is 126 despite title Chapter 125; verified first/latest links, wrong-series exclusion, partial-page and changed-link issues | `test_scribblehub_checker.py` |

`test_toc_overhaul.py` also protects ascending and descending ToCs, pagination rollover, duplicate groups, unrelated links, changed layouts, truncation, and no probing after an uncertain result. REQ-005, REQ-007, REQ-011, REQ-016.
