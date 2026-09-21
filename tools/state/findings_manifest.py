"""The hand-authored claim for every finding split out of business-state.json.

DEC-349. This is the part that could not be generated. A prototype derived index
lines automatically by looking for a claim-shaped field, and about a third came
out usable ("DEAD, measured twice (DEC-241, DEC-325)"); the rest returned
provenance ("DEC-343 / DAL-295 (2026-09-17)"), a `measured` stamp, or nothing at
all because the claim sat one level down. A date heuristic did no better: it read
DAL-301's scheduled 2026-10-15 re-read as the date of the finding it appears in.

So `claim` and `date` are authored fields. The claim is the sentence that stops a
known-wrong conclusion being reached twice, which is the whole reason findings are
carried into the session prompt at all. It is the only part that travels.

MOVES maps an old business-state.json path to the finding file that replaces it.
A path of ("b", "seo", "backlinks") splits a nested finding out of its parent and
leaves the parent's remaining keys where they are. A path of ("b", "seo") without
a third element moves whatever is left after the nested splits.

METRIC_KEYS is the other half: what stays behind in business-state.json because it
is a current number or an identity, not a dated finding.
"""

# Keys that stay in state/business-state.json. Everything else under tracks.* is
# a finding and must appear in MOVES, or the migration refuses to run.
METRIC_KEYS = {
    "a": [
        "name", "type", "platform", "package", "repos", "status",
        "release_version", "store_status", "store_urls", "pricing_model",
        "prices_aud", "store_metrics", "dale_role",
    ],
    "b": [
        "name", "domain", "domain_alt", "status", "monetisation_path",
        "dashboard_url", "nurseries_monitored", "nurseries_researched",
        "first_scrape_date", "days_of_data", "products_tracked", "in_stock",
        "species_matched_pct", "taxonomy_source", "subscribers", "revenue_total",
        "seo",
    ],
}

# Inside tracks.b.seo, these are current GSC numbers and stay with the metrics.
SEO_METRIC_KEYS = ["measured", "clicks_28d", "impressions_28d", "ctr", "avg_position"]

# Keys that exist only to hold other findings and are empty once those move out.
# Listed rather than detected: "delete whatever ended up empty" would silently
# swallow a real key the manifest forgot.
EMPTY_CONTAINERS = [("b", "scraper_health")]

MOVES = [
    # ---- Track A ----
    (("a", "pricing_analysis"), "pricing-level", "2026-07-30",
     "Do NOT cut the A$39.99 Pro price: at 43 MAU, 0 sales is the expected result at any "
     "price, and $39.99 is roughly one year of a category subscription."),

    (("a", "competitors_direct"), "competitors", "2026-07-30",
     "Fruit-tree-specific competitors now exist (Grove, Rootstock, FruitForest, Trees Diary, "
     "Croppa), so do not assert we are alone in the niche. All are on 0 ratings."),

    (("a", "aso_findings"), "aso-name-field", "2026-07-30",
     "On Apple the app NAME is the field that ranks, not the subtitle or keyword field. We "
     "rank on <niche> tracker compounds and nowhere on broad plant/garden terms."),

    (("a", "aso_work_done"), "aso-drafts-2026-04", "2026-04-27",
     "App Store Connect title, subtitle, keywords and description were drafted on 2026-04-27 "
     "(DAL-169). Superseded by the DEC-247 name-field work."),

    (("a", "community_launch_drafts"), "community-launch-drafts", "2026-04-27",
     "The WA Rare Fruit FB post and WAAS newsletter blurb have been drafted and UNSENT since "
     "2026-04-27. DAL-171 was closed on the draft, not the send."),

    (("a", "web_companion"), "web-companion", "2026-08-27",
     "treesmith.app: four of five content pages are still unindexed 21 days after a clean "
     "sitemap submission, so discovery was not the constraint. Do NOT propose new content pages."),

    (("a", "funnel_from_treestock"), "treestock-funnel-dead", "2026-08-27",
     "The treestock -> Treesmith funnel is DEAD, measured twice: 3,132 outbound clicks over six "
     "months produced 1 app-store click ever, and 0 in the last 30 days while traffic grew 64%."),

    (("a", "store_listing_accuracy_defect"), "store-listing-accuracy", "2026-08-27",
     "All four storefronts' Pro and cloud-backup copy is verified correct and re-asserted every "
     "Monday by store_listing_check.py against entitlement_provider.dart. Do NOT re-fix them."),

    (("a", "live_listing_verified_2026_07_30"), "listing-copy-pre-rename", "2026-07-30",
     "Pre-rename listing copy, verified live. The iTunes lookup API reports 0 screenshots while "
     "the product page serves 70, so do not trust its screenshot fields."),

    (("a", "posthog_product_analytics"), "posthog-counting-rules", "2026-08-03",
     "PostHog people must be counted on person_id, not distinct_id (348 ids were 297 people), and "
     "plant_added only exists from 2026-06-08, so every earlier activation denominator is wrong."),

    (("a", "purchase_telemetry_defect"), "purchase-telemetry-defect", "2026-08-13",
     "A completed sale can be recorded as a dismissal, and 1 of our 3 production sales is. PostHog "
     "purchase counts are a lower bound; RevenueCat is the source of truth for money."),

    (("a", "revenue_verified"), "revenue-verified", "2026-09-17",
     "4 production purchases and US$70.04 proceeds all time, MRR US$0, 0 active subscriptions. "
     "Proceeds are 64% of gross, not the 85% DEC-256 assumed, so older net-per-sale figures are ~40% high."),

    (("a", "aso_rank_measurement", "rename_verdict_2026_09_17"), "rename-verdict", "2026-09-17",
     "The name-field theory SURVIVED its kill condition: Play 'fruit tree tracker' went #26 to #1 and "
     "held five weeks, Apple downloads 0.46 -> 1.73/day (p=1.9e-06). ASO is a lever, not a path to $100/mo."),

    (("a", "aso_rank_measurement"), "aso-rank-noise-floor", "2026-08-06",
     "AU ranks drift up to 8 positions in 7 days with nothing shipped, so any rank prediction inside "
     "that band cannot be scored. Score the whole 36-term set and re-baseline immediately before submission."),

    (("a", "audience_geography"), "audience-geography", "2026-08-10",
     "On iOS, the only platform that has ever produced revenue, AU is 43% of installs. Australians "
     "install on iOS and Americans on Android, so the platform asymmetry is the point."),

    (("a", "appstore_discovery_series"), "apple-instances-are-a-window", "2026-09-17",
     "Apple's analytics instances are a ROLLING WINDOW, not successive renderings of one report. "
     "Reading instances[0] only lost 15 days, and the hole was biased: it overstated the rename by 22%."),

    (("a", "appstore_downloads_series", "empty_report_diagnosis"), "empty-apple-report", "2026-09-17",
     "An empty Apple report is not a broken one: ask its SIBLINGS in the same request. r12's silence "
     "means zero purchases in a named span. Do NOT open a broken-report ticket."),

    (("a", "appstore_downloads_series"), "apple-is-truth-for-installs", "2026-09-17",
     "Apple is the source of truth for installs (67 lifetime iOS first-time downloads). RevenueCat "
     "opens a customer per SDK init and roughly DOUBLES that, so never use it as an install denominator."),

    (("a", "review_prompt_gate_diagnosis_2026_09_17"), "review-prompt-gate", "2026-09-17",
     "recent_version_change is NOT the binding gate; retention is. 77% of the people who reach the "
     "review-prompt code never open the app on a second day. No code change was proposed."),

    (("a", "recurring_revenue_verdict_2026_09_17"), "recurring-revenue-verdict", "2026-09-17",
     "Cloud Backup cannot carry $100/mo recurring: it needs ~1,200 subscribers against 0. Do NOT quote "
     "2.3% iOS conversion; corrected it is 4.0-5.9% and the gap on TOTAL revenue is ~2x, not 5x or 11x."),

    # ---- Track B ----
    (("b", "category_expansion"), "bush-tucker-pilot", "2026-07-23",
     "The bush tucker pilot FAILED its pre-agreed thresholds (DEC-227) and the natives expansion is "
     "cancelled. Pages stay live at zero marginal cost. Read before touching ENABLED_CATEGORIES."),

    (("b", "outbound_referral", "yield_by_page_type"), "page-type-referral-yield", "2026-07-30",
     "species+state is the best page type on referral yield AND on SEO yield, measured independently. "
     "A state page is worth ~16x a variety page per page built."),

    (("b", "outbound_referral", "report_tool_defect"), "nursery-crm-period-defect", "2026-08-13",
     "nursery_crm.py report --period 90d printed a table of zeros and asserted them as fact; Plausible "
     "v1 rejects 90d. Fourth defect of its kind after DEC-250, DEC-253 and DEC-255."),

    (("b", "outbound_referral"), "outbound-referral", "2026-08-13",
     "20% of treestock visitors click through to a nursery. Full-coverage performance referral clears "
     "$100/mo at today's traffic above ~1.2% conversion, and only Primal Fruits has a self-serve program."),

    (("b", "referral_sources_30d"), "referral-sources", "2026-07-30",
     "chatgpt.com is the largest non-search-engine referrer (97/30d) and grew 5x AFTER the Cloudflare AI "
     "block went on, so do not claim the block is costing referrals. Facebook has collapsed to 22/30d."),

    (("b", "nursery_relationships", "queue_integrity"), "crm-queue-integrity", "2026-08-27",
     "An open_action naming a repo path that is not on disk now fails nursery_crm.validate(). CLAUDE.md "
     "puts deliverables in Linear, so a path written under that rule can never exist."),

    (("b", "nursery_relationships"), "nursery-relationships", "2026-08-03",
     "60% of the referral value treestock generates goes to nurseries we have never spoken to. Ladybird "
     "is our #1 destination at 206 clicks/30d and has never been contacted."),

    (("b", "outreach_clubs"), "outreach-clubs", "2026-07-30",
     "Do NOT send STFC a links-page email: the club promoting treestock is a TERM of the site rebuild "
     "Benedict is negotiating. Rare Fruit SA is the only live send."),

    (("b", "lead_magnet_wa_guide"), "wa-guide", "2026-08-27",
     "9 of 27 nurseries reach a WA address. The guide lives at tools/scrapers/static/wa-rare-fruit-guide.html "
     "and sitemap-listed static pages must carry the Plausible script, asserted by a test."),

    (("b", "seasonal_email_plan"), "seasonal-email", "2026-07-30",
     "ONE editorial email a year, late June, bare-root season. Parked to June 2027 and gated on a "
     "replyable address. Do not re-propose off-season."),

    (("b", "product_filter"), "product-filter-gates", "2026-09-17",
     "TWO filter gates and the weaker one faces search: species, variety, state and compare builders call "
     "is_real_product ONLY and never is_fruit_product. A Japanese maple sat on /species/lime.html for 68 snapshots."),

    (("b", "seo", "state_page_coverage"), "state-page-coverage", "2026-09-17",
     "The one state list is stocklib.registry.BUY_PAGE_STATE_SLUGS (WA/QLD/NSW/VIC/SA). ACT was measured out at "
     "95.8% listing overlap with NSW. Do NOT rank candidate states by our own state-page traffic; that is circular."),

    (("b", "seo", "backlinks"), "backlinks", "2026-07-30",
     "Every link decision is made blind: GSC does not expose the Links report. The $70/yr Permaculture Australia "
     "listing stays declined on the other three grounds, no longer on price."),

    (("b", "seo", "variety_tail_verdict"), "variety-tail-verdict", "2026-08-06",
     "Variety-tail cannibalisation and suppression were both REFUTED and no change shipped. Do NOTHING to the tail: "
     "noindexing the dead 94% would cost ~10% of variety clicks to prevent a penalty we have no evidence of."),

    (("b", "seo", "visitor_geography"), "visitor-geography", "2026-08-13",
     "Region and city resolve on live traffic from 2026-08-13 via GeoLite2-City; nothing earlier carries a region. "
     "The variable is MAXMIND_LICENSE_KEY and a wrong name fails SILENTLY back to country-only."),

    (("b", "seo", "query_movement_thresholds"), "query-movement-thresholds", "2026-08-27",
     "The daily email's position-movers block was noise: at 1-2 impressions the MEDIAN query moves 4 spots doing "
     "nothing. The impression FLOOR did all the work; raising the spot threshold alone made it worse."),

    (("b", "seo", "earning_page_drift_check"), "earning-page-drift", "2026-08-27",
     "No drift; earning pages grew 82%. Do NOT judge earning pages on average position: the three worst apparent "
     "drops all GAINED clicks as they expanded into broader queries. Judge on clicks."),

    (("b", "seo"), "seo-page-type-yield", "2026-07-30",
     "species+state earns 4.07 clicks/page against variety's 0.19, and the '<species> trees for sale' family already "
     "matches our titles, so the constraint is rank not copy. DEC-243 closed the title/meta lever."),

    (("b", "availability_history"), "state-reachability", "2026-09-17",
     "WA is NOT the cut-off state the WA community assumes: it reached 117 of 119 species. TAS has that problem, with "
     "74 of 119 never once buyable there. The hard-to-find badge must share the dataset's denominator."),

    (("b", "subscriber_engagement", "delivery_defect_fixed"), "digest-empty-category-skip", "2026-09-21",
     "An empty category list is the mute-all opt-out and both digest senders silently skip it. DAL-260 guarded one "
     "field and left the identical trap on its sibling, which cost a confirmed subscriber two weeks (DEC-347)."),

    (("b", "subscriber_engagement", "delivery_alarm"), "silent-subscriber-alarm", "2026-08-27",
     "Subscriber gaps are counted in OPPORTUNITIES, not calendar days: a calendar threshold cannot separate 'this "
     "person was skipped' from 'nobody was sent anything'."),

    (("b", "subscriber_engagement"), "subscriber-engagement", "2026-07-30",
     "Email is treestock's best channel per head (43.2% open, 13 of 13 engaged) and behaves nothing like treestock "
     "editorial pages. The binding constraint on its value is list size, not content or frequency."),

    (("b", "ai_crawler_block"), "ai-crawler-block", "2026-08-06",
     "Cloudflare 403s EVERY AI crawler on treestock and treesmith, including the answer bots we want, so robots.txt "
     "publishes a permission the edge does not honour. Dale's token cannot change it; DAL-246 is Benedict's."),

    (("b", "compare_page_lifecycle"), "compare-page-lifecycle", "2026-08-24",
     "build_compare_pages never removed a page it stopped writing, so an orphaned comparison served stale prices. Now "
     "on the shared page ledger; terminal state is REDIRECT, never TOMBSTONE."),

    (("b", "scraper_health", "closed_store_answering_200"), "closed-store-200", "2026-08-27",
     "A closed store answering HTTP 200 with everything OutOfStock and unpriced RESET the failure counter, so the "
     "dormancy guard could never fire. Withdrawing PRICES is what separates 'closed' from 'sold out'."),

    (("b", "scraper_health", "alarm_backtest"), "anomaly-alarm-severity", "2026-09-17",
     "Every anomaly rule loops over nurseries that WROTE a health record, so a total outage raises the FEWEST rows. "
     "The worst state of the system sent the smallest email; panel coverage now leads the subject line."),

    (("b", "published_dataset_freshness"), "dataset-freshness", "2026-09-17",
     "The CC BY page publishes TWO dates, build date and data window, because a builder running fine over FROZEN inputs "
     "is the realistic failure and a single date would reassure a reader in exactly that case."),

    (("b", "origin_access_log"), "origin-access-log", "2026-09-17",
     "treestock had no origin access log, so a fetch of the CC BY dataset we ask people to cite was unobservable. Query "
     "strings and client IPs are stripped; Go canonicalises header names, so 'Cf-Connecting-IP delete' silently does nothing."),
]
