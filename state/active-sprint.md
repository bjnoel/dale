# Active Sprint

## Sprint 0: Bootstrap (Week 1-2)

**Goal:** Set up infrastructure and build MVPs for both tracks simultaneously.

### Track A — Audit Business Setup
- [x] Create the audit deliverable template (what the client actually receives)
- [x] Draft a one-page "what we do" explainer for Benedict to show prospects
- [x] Define the exact process: how does Benedict approach a business? What does he say?
- [x] Build automated website analysis tool (analyse-business.py)
- [ ] Research: what does a Perth retail shop / professional service actually struggle with?
- [ ] Build 1-2 sample audits on real Perth businesses (free, as portfolio pieces)
- [ ] Set pricing (finalise within the $149-299 range for assessment) — Q7 pending
- [ ] Build walkthrough.au landing page

### Track B — Fruit Tracker MVP
- [ ] Identify top 6-8 nurseries to monitor and their URL structures (research in progress)
- [ ] Build web scraping/monitoring scripts for stock + pricing
- [ ] Set up data storage for price/availability history
- [ ] Create a simple dashboard or alert system (even if just email-based initially)
- [ ] Connect with Benedict re: which varieties are most sought-after in WA — Q3 pending

### Infrastructure (Both Tracks)
- [x] Set up GitHub repo
- [x] Set up project directory structure and state files
- [ ] Set up Cloudflare Pages for blog/landing page — Q6 pending (need API access)
- [ ] Set up Astro blog with public ledger entries
- [ ] Set up email sending (Resend free tier)
- [ ] Set up question dashboard (simple web page + WhatsApp notification)

### Blockers
- Need Cloudflare API access from Benedict (Q6)
- Need Benedict's input on which rare fruit varieties to prioritise (Q3)
- Need to understand scion-app current state before building scrapers (Q8)

### Done This Session (Session 1)
- Created proper directory structure (state/, decisions/, financials/, etc.)
- Built audit report HTML template with professional styling
- Built report generator script (JSON -> HTML)
- Created sample client data showing what a real report looks like
- Built automated website analysis tool (Python, zero dependencies)
- Tested analysis tool on a real Perth business (Scarborough Beach Bar)
- Wrote Benedict's approach script (cold, warm, follow-up, objections)
- Updated questions for Benedict with batch 2
- Created decision framework doc
