const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell,
  WidthType, AlignmentType, BorderStyle, ShadingType, PageOrientation,
  TableOfContents, StyleLevel, convertInchesToTwip, ImageRun,
} = require("docx");
const fs = require("fs");

// ─── Palette ──────────────────────────────────────────────
const C = {
  navy:    "0A1628",
  blue:    "1A56DB",
  teal:    "0891B2",
  green:   "059669",
  amber:   "D97706",
  red:     "DC2626",
  slate:   "475569",
  light:   "E8F4FD",
  white:   "FFFFFF",
  bg:      "F8FAFC",
  border:  "CBD5E1",
};

// ─── Helpers ──────────────────────────────────────────────
const gap = (pt = 6) => new Paragraph({ spacing: { after: pt * 20 } });

const h1 = (text) => new Paragraph({
  text,
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 480, after: 200 },
  border: { bottom: { style: BorderStyle.THICK, size: 6, color: C.blue, space: 4 } },
});

const h2 = (text) => new Paragraph({
  text,
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 320, after: 160 },
});

const h3 = (text) => new Paragraph({
  text,
  heading: HeadingLevel.HEADING_3,
  spacing: { before: 240, after: 120 },
});

const body = (text, opts = {}) => new Paragraph({
  children: [new TextRun({ text, size: 22, font: "Calibri", color: "1E293B", ...opts })],
  spacing: { after: 160 },
});

const bullet = (text, level = 0) => new Paragraph({
  children: [new TextRun({ text, size: 21, font: "Calibri", color: "334155" })],
  bullet: { level },
  spacing: { after: 100 },
});

const code = (text) => new Paragraph({
  children: [new TextRun({ text, font: "Courier New", size: 18, color: "1E293B" })],
  spacing: { after: 60 },
  shading: { type: ShadingType.CLEAR, color: "auto", fill: "F1F5F9" },
  indent: { left: 360 },
});

const badge = (text, color) => new TextRun({
  text: ` ${text} `,
  bold: true,
  color: C.white,
  highlight: undefined,
  size: 18,
  font: "Calibri",
  shading: { type: ShadingType.CLEAR, color: "auto", fill: color },
});

// ─── Table builder ────────────────────────────────────────
function makeTable(headers, rows, colWidths) {
  const totalWidth = 9360; // ~6.5 inches in DXA
  const widths = colWidths || headers.map(() => Math.floor(totalWidth / headers.length));

  const headerRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) =>
      new TableCell({
        width: { size: widths[i], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, color: "auto", fill: C.navy },
        children: [new Paragraph({
          children: [new TextRun({ text: h, bold: true, color: C.white, size: 20, font: "Calibri" })],
          alignment: AlignmentType.LEFT,
          spacing: { before: 80, after: 80 },
        })],
      })
    ),
  });

  const dataRows = rows.map((row, ri) =>
    new TableRow({
      children: row.map((cell, ci) =>
        new TableCell({
          width: { size: widths[ci], type: WidthType.DXA },
          shading: { type: ShadingType.CLEAR, color: "auto", fill: ri % 2 === 0 ? C.white : "F8FAFC" },
          children: [new Paragraph({
            children: [new TextRun({ text: String(cell), size: 20, font: "Calibri", color: "1E293B" })],
            spacing: { before: 60, after: 60 },
          })],
        })
      ),
    })
  );

  return new Table({
    width: { size: totalWidth, type: WidthType.DXA },
    columnWidths: widths,
    rows: [headerRow, ...dataRows],
    borders: {
      top:           { style: BorderStyle.SINGLE, size: 2, color: C.border },
      bottom:        { style: BorderStyle.SINGLE, size: 2, color: C.border },
      left:          { style: BorderStyle.SINGLE, size: 2, color: C.border },
      right:         { style: BorderStyle.SINGLE, size: 2, color: C.border },
      insideH:       { style: BorderStyle.SINGLE, size: 1, color: C.border },
      insideV:       { style: BorderStyle.SINGLE, size: 1, color: C.border },
    },
  });
}

// ─── Flow diagram as text art ─────────────────────────────
function flowBox(label, color = C.navy) {
  return new Paragraph({
    children: [
      new TextRun({ text: `  ${label}  `, bold: true, color: C.white,
        size: 20, font: "Calibri",
        shading: { type: ShadingType.CLEAR, color: "auto", fill: color } }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { before: 40, after: 40 },
  });
}

function arrow() {
  return new Paragraph({
    children: [new TextRun({ text: "↓", size: 28, bold: true, color: C.slate, font: "Calibri" })],
    alignment: AlignmentType.CENTER,
    spacing: { before: 20, after: 20 },
  });
}

function diamond(label) {
  return new Paragraph({
    children: [
      new TextRun({ text: `◆ ${label} ◆`, bold: true, size: 20, color: C.amber, font: "Calibri" }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { before: 40, after: 40 },
  });
}

// ─── Section divider ──────────────────────────────────────
function sectionHeader(text, sub) {
  return [
    new Paragraph({
      children: [
        new TextRun({ text, bold: true, size: 32, color: C.navy, font: "Calibri" }),
      ],
      shading: { type: ShadingType.CLEAR, color: "auto", fill: C.light },
      spacing: { before: 480, after: 120 },
      indent: { left: 240, right: 240 },
      border: {
        left: { style: BorderStyle.THICK, size: 12, color: C.blue, space: 8 },
      },
    }),
    sub ? new Paragraph({
      children: [new TextRun({ text: sub, size: 20, color: C.slate, font: "Calibri", italics: true })],
      indent: { left: 240 },
      spacing: { after: 240 },
    }) : gap(4),
  ];
}

// ─── Build document ───────────────────────────────────────
async function buildDoc() {
  const children = [

    // ══════════════════════════════════════════
    // COVER
    // ══════════════════════════════════════════
    new Paragraph({
      children: [new TextRun({ text: "JobBot", bold: true, size: 72, color: C.navy, font: "Calibri" })],
      alignment: AlignmentType.CENTER,
      spacing: { before: 1440, after: 120 },
    }),
    new Paragraph({
      children: [new TextRun({ text: "AI-Powered Job Application Platform", size: 32, color: C.blue, font: "Calibri" })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 },
    }),
    new Paragraph({
      children: [new TextRun({ text: "Architecture & Technical Reference", size: 24, color: C.slate, font: "Calibri", italics: true })],
      alignment: AlignmentType.CENTER,
      spacing: { after: 2880 },
    }),

    makeTable(
      ["Component", "Technology"],
      [
        ["Backend API",       "Python · FastAPI · SQLAlchemy"],
        ["AI Engine",         "Anthropic Claude Sonnet 4.6"],
        ["Database",          "PostgreSQL 16"],
        ["Job Sources",       "Adzuna · Remotive · Greenhouse · Lever"],
        ["Scheduler",         "APScheduler"],
        ["Form Automation",   "Playwright"],
        ["Frontend",          "Next.js 14 · TypeScript · Tailwind"],
        ["Infrastructure",    "Docker Compose"],
      ],
      [3200, 6160]
    ),

    gap(12),

    // ══════════════════════════════════════════
    // 1. SYSTEM OVERVIEW
    // ══════════════════════════════════════════
    ...sectionHeader("1. System Overview",
      "End-to-end flow from job ingestion to application submission"),

    body("JobBot is a fully automated job application system. It continuously pulls job listings from multiple sources, uses Claude to score each listing against all uploaded resumes, selects the best resume per job, and auto-applies to any match scoring ≥70%. A deduplication layer ensures each job is applied to exactly once."),
    gap(4),

    h2("1.1 High-Level Architecture"),

    // Architecture diagram
    new Paragraph({
      children: [new TextRun({ text: "EXTERNAL SOURCES", bold: true, size: 20, color: C.slate, font: "Calibri" })],
      alignment: AlignmentType.CENTER,
    }),
    makeTable(
      ["Adzuna API", "Remotive API", "Greenhouse ATS", "Lever ATS"],
      [["Free · 50-500/day", "Free · 30/day", "Per company · free", "Per company · free"]],
      [2340, 2340, 2340, 2340]
    ),
    arrow(),
    flowBox("INGESTION PIPELINE  →  Pre-filter  →  Dedup  →  PostgreSQL", C.navy),
    arrow(),
    flowBox("CLAUDE MATCHING ENGINE  →  Score job × each resume (parallel)", C.blue),
    arrow(),
    diamond("Best score ≥ 70%?"),
    arrow(),
    flowBox("CHECK applied_jobs  →  Already applied? STOP", C.amber),
    arrow(),
    flowBox("GENERATE COVER LETTER  (Claude, tailored per job+resume)", C.teal),
    arrow(),
    flowBox("AUTO-APPLY  →  Greenhouse API / Lever API / Playwright", C.green),
    arrow(),
    flowBox("LOG TO applied_jobs  →  Status tracked in dashboard", C.slate),
    gap(8),

    // ══════════════════════════════════════════
    // 2. DATA FLOW
    // ══════════════════════════════════════════
    ...sectionHeader("2. Detailed Data Flow", "Step-by-step pipeline walkthrough"),

    h2("2.1 Ingestion Phase"),
    body("The scheduler triggers ingestion on a per-source cadence. Each source adapter normalizes raw API responses into a common Job schema."),

    makeTable(
      ["Step", "Action", "Dedup Guard"],
      [
        ["1", "Fetch raw listings from source API",          "—"],
        ["2", "Normalize to common Job dict",                "—"],
        ["3", "Pre-filter: title block / salary / keywords", "Saves Claude API cost"],
        ["4", "INSERT INTO jobs (source, external_id, …)",   "UNIQUE(source, external_id) — silently skips dupes"],
        ["5", "Return list of newly inserted Job rows",      "Only new jobs proceed to matching"],
      ],
      [800, 4960, 3600]
    ),
    gap(6),

    h2("2.2 Matching Phase"),
    body("Each new job is scored against every active resume simultaneously using Claude's API in a thread pool. All scores are saved to job_matches for dashboard visibility, even for jobs that don't meet the threshold."),

    makeTable(
      ["Step", "Action", "Detail"],
      [
        ["1", "Load all active resumes",       "Fetched once per pipeline run"],
        ["2", "Check applied_jobs",            "Skip job if already applied — first dedup check"],
        ["3", "Score resume × job (×N parallel)", "Thread pool, one Claude call per resume"],
        ["4", "Parse Claude JSON response",    "score, reasoning, missing_skills, selling_points"],
        ["5", "Save all scores to job_matches","UPSERT — overwrites if re-scored"],
        ["6", "Select highest scoring resume", "sort by score desc → scores[0]"],
        ["7", "Threshold check: score ≥ 0.70","Below threshold → logged, skipped"],
      ],
      [600, 3600, 5160]
    ),
    gap(6),

    h2("2.3 Apply Phase"),
    body("Only jobs that cleared the threshold and passed the dedup check reach this phase. The apply strategy is determined by job source."),

    makeTable(
      ["Source", "Apply Strategy", "How It Works"],
      [
        ["greenhouse", "Greenhouse Board API",  "POST to boards.greenhouse.io/apply/{id}"],
        ["lever",      "Lever Apply API",       "POST to jobs.lever.co/{company}/{id}/apply"],
        ["adzuna",     "Playwright form fill",  "Browser automation fills apply form fields"],
        ["remotive",   "Playwright form fill",  "Redirects to employer site, fills form"],
      ],
      [1800, 2800, 4760]
    ),
    gap(6),

    // ══════════════════════════════════════════
    // 3. DEDUPLICATION STRATEGY
    // ══════════════════════════════════════════
    ...sectionHeader("3. Deduplication Strategy", "Three independent layers prevent double-applying"),

    body("Duplicate prevention is the most critical correctness property of the system. Three independent guards ensure a job is never applied to twice, even under concurrent runs or retries."),
    gap(4),

    makeTable(
      ["Layer", "Where", "Mechanism", "Prevents"],
      [
        ["1 — Ingestion",  "jobs table",         "UNIQUE(source, external_id)\nSilent INSERT conflict", "Same job scraped twice from same source"],
        ["2 — Matching",   "matching/engine.py",  "Query applied_jobs before scoring\nSkip if row exists",  "Re-scoring a job already applied to"],
        ["3 — Applying",   "applying/applicator.py", "Query applied_jobs before apply\nSkip if row exists", "Race condition / concurrent pipeline run"],
      ],
      [1400, 2200, 3000, 2760]
    ),
    gap(4),
    body("Once a job is logged in applied_jobs (regardless of success or failure), it will never be re-attempted. To retry a failed application, delete the applied_jobs row manually and re-trigger the pipeline."),
    gap(6),

    // ══════════════════════════════════════════
    // 4. CLAUDE INTEGRATION
    // ══════════════════════════════════════════
    ...sectionHeader("4. Claude AI Integration", "How Claude scores and writes for each application"),

    h2("4.1 Resume × Job Scoring"),
    body("Claude receives the full resume text and job description, then returns a structured JSON response. The prompt instructs Claude to behave as a senior technical recruiter — strict about 0.7 meaning genuinely qualified, not keyword overlap."),
    gap(4),

    h3("Scoring Response Schema"),
    code('{'),
    code('  "score":            0.82,          // 0.0–1.0, strict'),
    code('  "reasoning":        "...",          // one paragraph'),
    code('  "missing_skills":   ["k8s", "..."],// gaps in resume'),
    code('  "selling_points":   ["5yr Python"],// strengths for this role'),
    code('  "seniority_fit":    "good",        // good | over | under'),
    code('  "recommended_resume": true         // is this the best resume?'),
    code('}'),
    gap(6),

    h2("4.2 Multi-Resume Parallel Scoring"),
    body("If a user has 4 resumes, one job triggers 4 simultaneous Claude API calls via a ThreadPoolExecutor. The highest score wins and that resume is used for the application."),

    makeTable(
      ["Resume", "Score", "Outcome"],
      [
        ["Backend Engineer",  "91%",  "✅ Selected — used for application"],
        ["Full Stack Resume", "74%",  "Saved to dashboard, not used"],
        ["Data Analyst",      "38%",  "Saved, below threshold"],
        ["Product Manager",   "22%",  "Saved, poor match"],
      ],
      [2800, 1400, 5160]
    ),
    gap(6),

    h2("4.3 Cover Letter Generation"),
    body("Claude generates a custom cover letter for every application using the specific resume's selling points and the job's description. The prompt enforces: no hollow phrases, company-specific opening, concrete achievements, 90-day close."),
    gap(6),

    h2("4.4 Token Budget & Cost Estimate"),
    makeTable(
      ["Operation", "~Tokens/Call", "Calls/Day", "~Daily Cost"],
      [
        ["Resume scoring (4 resumes × 50 jobs)", "~2,000", "200",     "~$0.12"],
        ["Cover letter generation (10 applies)", "~1,500", "10",      "~$0.02"],
        ["Total estimate",                        "—",      "210 calls", "~$0.14/day"],
      ],
      [3500, 2000, 1800, 2060]
    ),
    gap(6),

    // ══════════════════════════════════════════
    // 5. JOB SOURCES
    // ══════════════════════════════════════════
    ...sectionHeader("5. Job Sources & Schedule", "What we pull, when, and how often"),

    makeTable(
      ["Source", "Type", "Auth", "Volume/Day", "Pull Frequency"],
      [
        ["Adzuna",      "Public API", "API key (free)", "50–500",  "Every 1 hour"],
        ["Remotive",    "Public API", "None",           "10–30",   "Every 1 hour"],
        ["Greenhouse",  "ATS API",    "None (public)",  "5–50",    "Every 2 hours"],
        ["Lever",       "ATS API",    "None (public)",  "5–30",    "Every 2 hours"],
        ["All sources", "Full sync",  "—",              "70–600",  "Daily at 6am"],
      ],
      [1800, 1400, 2000, 1600, 2560]
    ),
    gap(4),

    h2("5.1 Pre-Filter (Before Claude)"),
    body("To reduce Claude API costs by 60–70%, cheap pre-filters run before any job reaches the matching engine:"),
    bullet("Blocked title patterns: 'intern', 'VP', 'unpaid', 'C-level'"),
    bullet("Required keyword presence in description (configurable)"),
    bullet("Salary floor: skip if max salary is below configured minimum"),
    bullet("Minimum description length: 100 characters"),
    bullet("Must have a valid apply URL"),
    gap(6),

    // ══════════════════════════════════════════
    // 6. DATABASE SCHEMA
    // ══════════════════════════════════════════
    ...sectionHeader("6. Database Schema", "PostgreSQL tables and relationships"),

    makeTable(
      ["Table", "Purpose", "Key Columns"],
      [
        ["resumes",       "Uploaded resume files + extracted text",  "id, label, content, active"],
        ["jobs",          "All fetched job listings",                "id, source, external_id, title, company, description"],
        ["job_matches",   "Claude scores: every resume × every job", "job_id, resume_id, score, reasoning, missing_skills"],
        ["applied_jobs",  "Application log + dedup guard",           "job_id (UNIQUE), resume_id, status, cover_letter"],
        ["ingestion_logs","Pipeline run history",                     "source, jobs_found, jobs_new, duration_s"],
      ],
      [1800, 3500, 4060]
    ),
    gap(4),

    h2("6.1 Key Constraints"),
    bullet("jobs: UNIQUE(source, external_id) — prevents duplicate ingestion"),
    bullet("job_matches: UNIQUE(job_id, resume_id) — one score per pair"),
    bullet("applied_jobs.job_id is UNIQUE — a job can only be applied to once, ever"),
    gap(6),

    // ══════════════════════════════════════════
    // 7. API ENDPOINTS
    // ══════════════════════════════════════════
    ...sectionHeader("7. REST API Reference", "FastAPI endpoints"),

    makeTable(
      ["Method", "Endpoint", "Description"],
      [
        ["POST",   "/resumes",                     "Upload resume (PDF/DOCX), extract text, save"],
        ["GET",    "/resumes",                     "List all active resumes"],
        ["DELETE", "/resumes/{id}",                "Soft-delete a resume"],
        ["GET",    "/jobs",                        "List fetched jobs (filter by source)"],
        ["GET",    "/matches",                     "List all match scores (filter by min_score)"],
        ["GET",    "/applications",               "Full application history with status"],
        ["PATCH",  "/applications/{id}/status",   "Update status: interview / rejected / offer"],
        ["POST",   "/pipeline/run",               "Manually trigger ingest → match → apply"],
        ["GET",    "/stats",                       "Dashboard summary: counts by status"],
      ],
      [1000, 2800, 5560]
    ),
    gap(6),

    // ══════════════════════════════════════════
    // 8. SCHEDULER
    // ══════════════════════════════════════════
    ...sectionHeader("8. Scheduler & Pipeline Orchestration"),

    makeTable(
      ["Job Name", "Sources", "Trigger", "Reason"],
      [
        ["Fast sources",    "Adzuna + Remotive",       "Every 1 hour",       "Fast-moving, early applicant advantage"],
        ["ATS sources",     "Greenhouse + Lever",      "Every 2 hours",      "Slower-moving, larger target company list"],
        ["Daily full sync", "All 4 sources",           "Daily at 06:00 UTC", "Catch edits, expirations, missed jobs"],
      ],
      [2000, 2400, 2200, 2760]
    ),
    gap(4),
    body("APScheduler runs as a separate Docker service alongside the FastAPI server. max_instances=1 and coalesce=True prevent overlapping pipeline runs if a cycle takes longer than expected."),
    gap(6),

    // ══════════════════════════════════════════
    // 9. DIRECTORY STRUCTURE
    // ══════════════════════════════════════════
    ...sectionHeader("9. Project Structure"),

    code("jobbot/"),
    code("├── backend/"),
    code("│   ├── src/"),
    code("│   │   ├── api/routes.py          # FastAPI endpoints"),
    code("│   │   ├── db/models.py           # SQLAlchemy models"),
    code("│   │   ├── ingestion/"),
    code("│   │   │   ├── sources.py         # Adzuna, Remotive, Greenhouse, Lever"),
    code("│   │   │   └── pipeline.py        # Pre-filter, dedup, save"),
    code("│   │   ├── matching/"),
    code("│   │   │   ├── engine.py          # Claude scoring (parallel)"),
    code("│   │   │   └── resume_parser.py   # PDF / DOCX extraction"),
    code("│   │   ├── applying/"),
    code("│   │   │   └── applicator.py      # Cover letter + apply strategy"),
    code("│   │   └── scheduler.py           # APScheduler cron jobs"),
    code("│   ├── requirements.txt"),
    code("│   └── .env.example"),
    code("├── frontend/                       # Next.js dashboard"),
    code("├── docker-compose.yml"),
    code("└── docs/                           # This document"),
    gap(6),

    // ══════════════════════════════════════════
    // 10. SETUP GUIDE
    // ══════════════════════════════════════════
    ...sectionHeader("10. Setup & Deployment"),

    h2("10.1 Prerequisites"),
    bullet("Docker Desktop installed"),
    bullet("Anthropic API key (console.anthropic.com)"),
    bullet("Adzuna API credentials (developer.adzuna.com — free)"),
    bullet("Applicant details ready (.env file)"),
    gap(4),

    h2("10.2 Quick Start"),
    code("git clone <repo> && cd jobbot"),
    code("cp backend/.env.example backend/.env   # fill in your keys"),
    code("docker compose up --build              # starts API + scheduler + DB + frontend"),
    code("# Open http://localhost:3000           # dashboard"),
    code("# Open http://localhost:8000/docs      # API explorer"),
    gap(4),

    h2("10.3 First Run"),
    bullet("Upload your resumes at /resumes (PDF or DOCX, give each a label)"),
    bullet("Configure target companies in sources.py → GREENHOUSE_COMPANIES / LEVER_COMPANIES"),
    bullet("Set keywords and blocked_titles in the pre-filter config"),
    bullet("Trigger a manual pipeline run from the dashboard or POST /pipeline/run"),
    bullet("Watch the Applications tab populate within minutes"),
    gap(6),

    // ══════════════════════════════════════════
    // 11. KNOWN LIMITATIONS
    // ══════════════════════════════════════════
    ...sectionHeader("11. Known Limitations & Roadmap"),

    makeTable(
      ["Limitation", "Impact", "Planned Solution"],
      [
        ["LinkedIn/Indeed blocked",         "Can't scrape largest job boards",      "Use their official (paid) API programs"],
        ["CAPTCHA on some apply forms",      "Playwright apply may fail",             "2Captcha integration or human review queue"],
        ["Playwright submit disabled",       "Forms filled but not submitted",        "Enable after manual testing of each ATS"],
        ["Single-user MVP",                  "No auth / multi-user",                  "Add NextAuth + user_id scoping"],
        ["No email parsing",                 "Can't auto-update status from replies", "Gmail API integration for reply detection"],
        ["Greenhouse/Lever resume upload",   "API apply may not attach PDF",          "Multipart form-data file upload support"],
      ],
      [2400, 2800, 4160]
    ),
    gap(8),

    new Paragraph({
      children: [new TextRun({ text: "JobBot · Architecture Reference · v1.0", size: 18, color: C.slate, font: "Calibri" })],
      alignment: AlignmentType.CENTER,
      spacing: { before: 720 },
      border: { top: { style: BorderStyle.SINGLE, size: 2, color: C.border, space: 4 } },
    }),
  ];

  const doc = new Document({
    styles: {
      default: {
        document: {
          run: { font: "Calibri", size: 22, color: "1E293B" },
        },
      },
      paragraphStyles: [
        {
          id: "Heading1",
          name: "Heading 1",
          basedOn: "Normal",
          next: "Normal",
          run: { size: 36, bold: true, color: C.navy, font: "Calibri" },
          paragraph: { spacing: { before: 480, after: 200 } },
        },
        {
          id: "Heading2",
          name: "Heading 2",
          basedOn: "Normal",
          next: "Normal",
          run: { size: 28, bold: true, color: C.blue, font: "Calibri" },
          paragraph: { spacing: { before: 320, after: 160 } },
        },
        {
          id: "Heading3",
          name: "Heading 3",
          basedOn: "Normal",
          next: "Normal",
          run: { size: 24, bold: true, color: C.teal, font: "Calibri" },
          paragraph: { spacing: { before: 240, after: 120 } },
        },
      ],
    },
    sections: [{
      properties: {
        page: {
          size: { width: 12240, height: 15840 },   // US Letter
          margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 },
        },
      },
      children,
    }],
  });

  const buf = await Packer.toBuffer(doc);
  fs.writeFileSync("/mnt/user-data/outputs/JobBot_Architecture.docx", buf);
  console.log("✅ Written: JobBot_Architecture.docx");
}

buildDoc().catch(e => { console.error(e); process.exit(1); });
