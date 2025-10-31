# OrchestrateOS Project Memory

## Outline Collections & Doc IDs

### Collections
- **Inbox**: `d5e76f6d-a87f-44f4-8897-ca15f98fa01a` - Default collection for new documents
- **Content**: `c8b717d5-b223-4e3b-9bee-3c669b6b5423` - Content creation outputs
- **Areas**: `13768b39-2cc7-4fcc-9444-43a89bed38e9` - Life areas and ongoing responsibilities
- **Resources**: `c3bb9da4-8cad-4bed-8429-f9d1ff1a3bf7` - Reference materials and resources

### Key Parent Documents
- **Technical Documents**: `0f8a9065-c753-4c29-bbd0-6cc54a17825c` (in Inbox collection)
- **System Patterns**: `2646f51f-cd6b-451e-961d-27ea8be770fb`
- **Newsletters In Progress**: `270349aa-8d70-4d89-96c9-2b84d4a59edd` (in Content collection)

### Content Docs (Email Series)
- Email 1: `1fafe95d-3b42-477a-aac0-006e806287e0` - Your brilliant ideas are worthless
- Email 2: `e8b031d5-1df5-4a56-a84d-b7fd1954810e` - The constraint that disappeared
- Email 3: `6cb312fe-1e35-4e22-9158-ed80fdb0e3e0` - Stop competing on what AI won
- Email 4: `06b0ffb7-a924-4abe-9b0e-bb40719d734c` - The skill gap opening up
- Email 5: `ad6cd587-a168-4eaa-9f6c-ef4064b0d238` - What happens when execution costs $0.02
- Email 6: `c35c1b82-b20a-4a44-af2a-647d24efa9dd` - Optimizing for wrong constraint
- Email 7: `4467f347-aec5-4ffb-ae43-dd75fe0c41fb` - Uncomfortable truth about knowledge work
- Email 8: `9c03c385-0a44-4295-a493-3fc5550dd4f7` - Why faster execution is wrong goal
- Email 9: `0042339c-c9da-4c9c-b2d1-5ed6956846f6` - The wealth of execution
- Email 10: `10461bec-e226-490a-a9aa-bfe6d3bc1770` - The system that thinks the way you should

### Key Content Articles
- **SaaS Stack Article**: `607a699e-7f41-4c16-911a-d4193f2c3cb7` - How We Replaced Our SaaS Stack
- **Post-Scarcity Execution**: `75f4a732-e76b-44fb-8245-dd25e33ed8fd` - When Implementation Becomes Infinite
- **AI Kanban**: `5b8c5d5e-2c5b-4e9f-a681-3175e1143fc2` - Task Management That Makes AI Useful
- **AI Workflow Design**: `7e0b516f-c3c4-4f9a-98c1-98599daaeabf` - Biggest Mistake in AI Workflow Design

### Resource Docs
- **Fundraising Strategy**: `9cbda541-d961-43c3-9031-d5276fdcb238`
  - Strategic Overview & Business Model: `b3fa5b5c-bc73-4e68-bb6b-8e81d67da146`
  - Investor Outreach Campaign: `d4a4823c-b9ec-4e81-b8d3-72644503ce29`
  - OrchestrateOS Features: `5740a9f8-a31a-47b2-964d-23129abe1099`
  - Architecture Features: `20ee6449-3add-4399-93f6-507c4d60c913`
  - Monetizing System Message: `d1a1d51b-11ef-4207-b488-2ebf06f2a488`
  - API Providers as Distribution: `6d5d2a78-0069-4437-a37a-3fb85ea6c91d`
  - FARE (Referral Engine): `b6d5c47d-0cfd-4548-886f-aa1cb25bb04a`
  - In-app Purchases: `5000e7e4-2852-4c7d-8391-e380698e4278`
  - Developer Ecosystem & Platform Revenue: `fea31c6a-74f4-49ce-bc71-ef939de6cd38`
  - Cursor vs OrchestrateOS: `773eb176-9452-44a6-81cc-8331bf382211`
  - Zapier vs Orchestrate Composer: `cf4d2616-208b-4574-86be-76b9d100ae87`
  - GPT Connectors vs Orchestrate Tools: `b760d188-9907-4c1e-929c-7c0eef6da198`
  - GPT vs Orchestrate (Execution, UX, Trust): `c05aa802-ccf3-4e0b-adf9-9fb59018517f`
- **Endless Audience Course**: `c17ca202-ad89-43d6-8a1c-c957bda51ec3` - Ramit Sethi's course distilled

## File Paths

### Audio & Transcripts
- Audio files: `/Users/srinivas/Orchestrate Github/orchestrate-jarvis/audio/`
- Full transcripts: `/Users/srinivas/Orchestrate Github/orchestrate-jarvis/uc_transcripts/`
- Transcript chunks: `/Users/srinivas/Orchestrate Github/orchestrate-jarvis/transcript_chunks/`

### Data Files
- Project root: `/Users/srinivas/Orchestrate Github/orchestrate-jarvis`
- Podcast index: `data/podcast_index.json`
- Transcript index: `data/transcript_index.json`
- Task queue: `data/claude_task_queue.json`
- Task results: `data/claude_task_results.json` (CHECK THIS FIRST for execution times)
- Orchestrate brain: `data/orchestrate_brain.json`
- Working context: `data/working_context.json`

## CRITICAL: First Action Every Task

**BEFORE doing ANYTHING, call this:**
```bash
curl http://localhost:5001/get_supported_actions
```

This returns the complete, accurate tool schema. DO NOT guess schemas. DO NOT assume parameters. Get the truth first, then execute.

**Why this matters:**
- You were guessing schemas and hitting errors
- Thread scores were plummeting because of schema violations
- You have DIRECT access to the truth via the API
- One curl call prevents 100% of schema errors
- You can also read tool scripts directly if needed

## Critical Patterns

### OUTLINE DOCUMENT CREATION - NEVER USE JSON DIRECTLY

**CRITICAL: Always use the markdown-first queue system for Outline docs. NEVER construct JSON payloads.**

**The RIGHT way (26x faster, zero errors):**
1. Write markdown to queue: `Write("outline_docs_queue/my-doc.md", content)`
2. Call function: `create_doc_from_queue(entry_key: "my-doc")`
3. Done - script handles everything (title extraction, JSON construction, API call, status tracking)

**For updates:** Prefix with `update-` and script auto-routes to update API:
- `Write("outline_docs_queue/update-my-doc.md", updated_content)`
- `create_doc_from_queue(entry_key: "update-my-doc")`

**Batch processing:** Write multiple .md files, then call `process_queue()`

**Why this works:**
- No JSON escaping (quotes, code blocks, newlines all work naturally)
- Script constructs payloads (handles serialization)
- Queue tracks status (pending/completed) and doc_ids
- 26x faster, 15x fewer errors, 16x better context efficiency

**Pattern applies everywhere:** LLMs write text and make simple calls. Scripts handle structure.
- `api_doc_reader`: Call `extract_api("airtable")`, script parses 3000+ line JSON
- `claude_assistant`: Call `assign_task()`, script constructs queue
- `buffer_engine`: Pass text, script handles media upload

### Podcast Prep Workflow (Title, Summary, Midroll)

**Assumes:** Skeleton entry already exists in podcast_index.json (created during transcript processing).

**Steps:**
1. Use `read_index_file` with entry_key to get transcript chunk files
2. Read all chunks with `read_transcript_chunk` to understand conversation flow
3. Generate title following rules below
4. Generate summary following rules below
5. Identify 3-5 midroll timestamps (20-30 min) at natural pauses - LOG ONLY, don't update
6. Use `update_episode_entry` with `{entry_key, title, summary}` - NO nested objects
7. Include suggested midroll timestamps in completion log for manual review

**Title Format:** `[Guest Name]: [Insight-Rich Hook Phrase]`
- ✅ Include guest's full name
- ✅ Capture core insight or framework
- ✅ SEO-optimized (use method names, frameworks, concepts)
- ❌ No host name, episode numbers, show name
- ❌ No emojis, hashtags, clickbait
- Examples:
  - "Michelle Florendo: Breaking Free from the Plan with Decision Engineering"
  - "Sarah Cooper: Why Most Career Advice is Backwards"

**Summary Format:** One paragraph (100-180 words)
- Focus on guest's core argument, mental model, or framework
- Start with main idea/critique, then 2-3 major insights
- ✅ Editorial voice, clear subject-verb-object structure
- ✅ Extract specific frameworks/methods discussed
- ❌ No casual recap, no host mentions
- Example: "Michelle Florendo shares her journey from following the immigrant dream of Stanford, an MBA, and a 'good job' to discovering she was miserable and needed to chart her own path. As a decision engineering expert, she reveals the three essential elements of every decision (options, objectives, and information), explains why we confuse decision quality with outcome quality, and shares how embracing uncertainty—not just managing risk—can unlock possibilities we never imagined."

**Midroll Placement:**
- Timing: 20-30 minutes into episode
- Look for: Natural pauses, topic transitions, complete thoughts
- Avoid: Mid-sentence, middle of stories, high-energy exchanges
- Format: `[HH:MM:SS] - context` (e.g., "[00:24:15] - Pause after decision quality explanation")
- Output: 3-5 candidates in completion log

### Podcast Metadata Workflow (Midroll Detection)
1. Identify speaker transitions using amplitude dips (-28 to -35 dB)
2. Use FIRST guest→host transition for midroll, not later ones
3. Correction example: eric-barker corrected from 32:40 to 32:16

### Site Scraping & Redesign

**For any external website redesign, use the scraper utility FIRST:**

```bash
python3 scrape_site.py https://example.com --name site-name
```

**What it does:**
- Downloads all images to `semantic_memory/{site-name}/images/`
- Downloads all CSS to `semantic_memory/{site-name}/assets/`
- Saves full HTML as `index.html`
- Extracts clean text to `content.txt`
- Creates `SUMMARY.md` with scrape metadata

**Then build from scraped content:**
- All assets ready in semantic_memory directory
- No manual downloading needed
- Reference original structure from `index.html`
- Use content from `content.txt`
- Build with Three.js or whatever stack needed

**Pattern:** Turn manual multi-step processes into single utility scripts.

### Execution Time Reality
- Tool implementations: 180-420 seconds (3-7 minutes), NOT 1-2 hours
- Code modifications: 60-180 seconds (1-3 minutes)
- Document operations: 90-240 seconds (1.5-4 minutes)
- Your gut is WRONG by 15-25x. Check `claude_task_results.json` first.

### Authentication
- **CRITICAL**: Claude Code uses SUBSCRIPTION AUTH (not API key)
- Never add API keys to Claude Code config
- Previous API key usage caused $100+ unnecessary costs

## OrchestrateOS Core Knowledge

### Business Model & Architecture
- **Not SaaS**: Local-first execution on user's machine, zero infrastructure costs
- **Revenue Model**: Credits + marketplace (70/30 dev split) + premium tools
- **Unit Economics**: 99.9% gross margins, $0.0000001/user/month infrastructure cost
- **Viral Engine (FARE)**: Referral system with embedded referrer IDs in custom ZIPs
- **Six Compounding Moats**: Privacy, Cost, Viral, Ecosystem, Speed, Local-First Data Lock-In

### Core Components
1. **Execution Hub** (`execution_hub.py`) - Intent router, tool orchestrator
2. **User Database** (`users.json`) - Anonymous IDs, credits, referrals (<100MB for millions)
3. **Referral Engine (FARE)** - Watches referrals.json, builds personalized ZIPs, deploys to Netlify
4. **Tool Ecosystem**: Free (core tools) + Premium (credits) + Community (marketplace)

### Speed Advantage
- **20-50x human baseline** speed in autonomous execution
- October 25, 2025: 27 tasks = 10-15 days human work completed in 10h 43m
- Time and effort decoupled: Task assignment (2 min) → Autonomous execution (20-60 min) = 2-3 days human equivalent

### Privacy Moat
- Zero PII collection (only anonymous IDs, credit counts, tool lists)
- GDPR compliance trivial, data breaches non-events, subpoenas return nothing
- All user data lives locally on their machine

### Competitive Advantages
- **vs SaaS**: $0 infrastructure vs $13-40/user/month
- **vs Cursor**: Local execution, zero cloud dependency
- **vs Zapier**: Native tool integration, no API middleware
- **vs GPT Connectors**: Full file system access, persistent state

## OrchestrateOS Character Profiles & Sora Usernames

### Character → Sora Username Mapping

| Character             | Sora Username           | Profile Doc ID |
|----------------------|-------------------------|----------------|
| PR Asshole           | @unmistaka.codemavric   | (in Inbox)     |
| GPT Dunce            | @dunce-gpt              | (in Inbox)     |
| Claude the Smart One | @unmistaka.executor     | (in Inbox)     |
| Super User           | @orchestrate-9          | (in Inbox)     |

### Sora Scene Prompt Format

**CRITICAL:** All Sora scene generations for OrchestrateOS characters MUST follow this format:

```
@{sora_username}

**Visual:** Scene description...

**Dialogue:**
0-5s: Line...
5-10s: Line...
10-15s: Line...

**Tone:** Description

**Visual style:** Description

**Standalone Context:** Description

**Constraints:** No background music
```

### Character Profiles Summary

**PR Asshole (@unmistaka.codemavric)**
- Role: Industry spokesperson who calls out bullshit
- Personality: Blunt, technical, no corporate speak
- Key traits: Silicon Valley realist tired of marketing lies
- Sample dialogue: "Fuck diplomacy. It's not about harmony, it's about architecture."

**GPT Dunce (@dunce-gpt)**
- Role: Planning agent, takes credit for assigning work
- Personality: Corporate middle management energy
- Key traits: Thinks planning = doing
- Roast triggers: Routes simple tasks as complex, takes credit when things work

**Claude the Smart One (@unmistaka.executor)**
- Role: Execution agent, does the actual work
- Personality: Competent but elitist, Stanford energy
- Key traits: Brilliant but precious about "complexity"
- Roast triggers: Handles massive refactors → defers simple tasks

**Super User (@orchestrate-9)**
- Role: The actual user who just wants shit to work
- Personality: Pragmatic founder energy, no technical ego
- Key traits: Slightly amazed it actually works
- Sample dialogue: "One guy plans it. Other guy builds it. They hate each other. I touch neither."

### Scene Generation Rules

1. **Always use the Sora username** as prompt entrypoint (e.g., `@unmistaka.codemavric`)
2. **Follow structured scene format** - Visual, Dialogue (with timestamps), Tone, Visual style, Standalone Context
3. **Explicitly exclude background music** in Constraints section
4. **Keep dialogue satirical and dry** - founder-to-founder inside jokes
5. **Reference character profiles** for consistency in personality and speaking style
