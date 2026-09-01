"use client";
import Head from "next/head";
import { useState, useEffect, useCallback, useRef } from "react";
import {
  getStats, getMatches, getApplications, getResumes, triggerPipeline, getPipelineStatus, getRunStatus, matchAllJobs, matchSelectedJobs, stopMatchAll,
  type Stats, type Match, type Application, type Resume, type PipelineStatus,
} from "../lib/api";
import { Sidebar, type Tab } from "../components/Sidebar";
import { StatsStrip } from "../components/StatsStrip";
import { DashboardTab } from "../components/tabs/DashboardTab";
import { MatchesTab } from "../components/tabs/MatchesTab";
import { ApplicationsTab } from "../components/tabs/ApplicationsTab";
import { ResumesTab } from "../components/tabs/ResumesTab";
import { JobsTab } from "../components/tabs/JobsTab";

const IN_PROGRESS_STATUSES = ["running", "ingesting", "matching", "applying", "stopping"];

export default function Home() {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [stats, setStats] = useState<Stats | null>(null);
  const [matches, setMatches] = useState<Match[]>([]);
  const [apps, setApps] = useState<Application[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>(null);
  const [lastRun, setLastRun] = useState<string | null>(null);
  const [focusedAppId, setFocusedAppId] = useState<string | null>(null);
  const [jobsVersion, setJobsVersion] = useState(0);
  const [matchAllLogId, setMatchAllLogId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function viewApplication(applicationId: string) {
    setFocusedAppId(applicationId);
    setTab("applications");
  }

  const load = useCallback(async () => {
    const s = await getStats().catch(() => null);
    if (s) setStats(s);

    const [m, a, r] = await Promise.allSettled([
      getMatches(s?.score_threshold ?? 0.7), getApplications(), getResumes(),
    ]);
    if (m.status === "fulfilled") setMatches(m.value);
    if (a.status === "fulfilled") setApps(a.value);
    if (r.status === "fulfilled") setResumes(r.value);
  }, []);

  useEffect(() => { load(); }, [load]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollStatus = useCallback((fetchStatus: () => Promise<PipelineStatus>, onDone: () => void) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      const status = await fetchStatus().catch(() => null);
      setPipelineStatus(status);
      if (!status || !IN_PROGRESS_STATUSES.includes(status.status)) {
        stopPolling();
        setLastRun(new Date().toLocaleTimeString());
        onDone();
      }
    }, 1500);
  }, [stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  // Log a progress snapshot every 5 minutes while a run is in progress, so
  // long-running matches/ingestion have a visible trail in the browser
  // console for diagnosing whether they're actually advancing. Reads
  // pipelineStatus via a ref so the 5-minute interval isn't torn down and
  // recreated on every 1.5s poll tick.
  const statusRef = useRef<PipelineStatus>(null);
  statusRef.current = pipelineStatus;
  const runStartRef = useRef<number | null>(null);

  useEffect(() => {
    const inProgress = pipelineStatus != null && IN_PROGRESS_STATUSES.includes(pipelineStatus.status);
    if (!inProgress) {
      runStartRef.current = null;
      return;
    }
    if (runStartRef.current != null) return; // logging interval already running for this run

    runStartRef.current = Date.now();
    const startedAt = runStartRef.current;

    const logInterval = setInterval(() => {
      const status = statusRef.current;
      if (!status || !IN_PROGRESS_STATUSES.includes(status.status)) return;
      const elapsedMin = ((Date.now() - startedAt) / 60000).toFixed(1);
      const done = status.matches_found ?? 0;
      const total = status.jobs_found ?? 0;
      const rate = done > 0 ? (Number(elapsedMin) / done).toFixed(2) : "n/a";
      console.log(
        `[pipeline ${status.id}] ${status.status} — ${done}/${total} ` +
        `after ${elapsedMin}min (~${rate} min/job)`
      );
    }, 5 * 60 * 1000);

    return () => clearInterval(logInterval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineStatus?.status]);

  // On mount (including a page refresh), check whether a run is already in
  // progress on the backend and resume polling it instead of leaving the UI
  // unaware — otherwise a refresh mid-run would let the user start a
  // duplicate run.
  useEffect(() => {
    getPipelineStatus().then(status => {
      if (status && IN_PROGRESS_STATUSES.includes(status.status)) {
        setPipelineStatus(status);
        if (status.run_type === "match_all") setMatchAllLogId(status.id);
        pollStatus(() => getRunStatus(status.id), () => {
          load();
          setJobsVersion(v => v + 1);
          setMatchAllLogId(null);
        });
      }
    }).catch(() => {});
  }, [pollStatus, load]);

  async function handlePipeline() {
    setPipelineRunning(true);
    try {
      await triggerPipeline();
      pollStatus(getPipelineStatus, load);
    } finally {
      setPipelineRunning(false);
    }
  }

  function startMatchRun(trigger: () => Promise<{ log_id: string }>) {
    return async () => {
      setPipelineRunning(true);
      try {
        const { log_id } = await trigger();
        setMatchAllLogId(log_id);
        pollStatus(() => getRunStatus(log_id), () => {
          load();
          setJobsVersion(v => v + 1);
          setMatchAllLogId(null);
        });
      } finally {
        setPipelineRunning(false);
      }
    };
  }

  const handleMatchAll = startMatchRun(matchAllJobs);
  const handleMatchSelected = (jobIds: string[]) => startMatchRun(() => matchSelectedJobs(jobIds))();

  async function handleStopMatchAll() {
    if (!matchAllLogId) return;
    try {
      await stopMatchAll(matchAllLogId);
    } catch {
      // ignore — polling will reflect whatever the backend ends up reporting
    }
  }

  const pendingMatches = matches.filter(m => !m.applied).length;

  const navItems: { id: Tab; icon: string; label: string; badge?: number }[] = [
    { id: "dashboard",    icon: "◈",  label: "Overview" },
    { id: "matches",      icon: "⟐",  label: "Matches",      badge: pendingMatches },
    { id: "applications", icon: "✉",  label: "Applications", badge: apps.filter(a => a.status === "interview").length },
    { id: "resumes",      icon: "📄", label: "Resumes",      badge: resumes.length },
    { id: "jobs",         icon: "⊞",  label: "Jobs feed" },
  ];

  return (
    <div className="flex h-screen overflow-hidden bg-paper">
      <Head>
        <title>JobBot — AI application engine</title>
      </Head>
      <Sidebar
        tab={tab}
        onTabChange={setTab}
        navItems={navItems}
        pipelineRunning={pipelineRunning}
        onRunPipeline={handlePipeline}
        lastRun={lastRun}
        pipelineStatus={pipelineStatus}
      />

      <main className="flex-1 flex flex-col overflow-hidden">
        <StatsStrip stats={stats} />

        <div className="flex-1 overflow-y-auto px-8 pb-8">
          {tab === "dashboard"    && <DashboardTab stats={stats} />}
          {tab === "matches"      && <MatchesTab matches={matches} resumes={resumes} onRefresh={load} onViewApplication={viewApplication} />}
          {tab === "applications" && <ApplicationsTab apps={apps} onRefresh={load} focusedAppId={focusedAppId} onFocusHandled={() => setFocusedAppId(null)} />}
          {tab === "resumes"      && <ResumesTab resumes={resumes} onRefresh={load} />}
          {tab === "jobs"         && (
            <JobsTab
              onViewApplication={viewApplication}
              onMatchAll={handleMatchAll}
              onMatchSelected={handleMatchSelected}
              onStopMatchAll={handleStopMatchAll}
              matching={pipelineRunning || (pipelineStatus != null && IN_PROGRESS_STATUSES.includes(pipelineStatus.status))}
              canStop={matchAllLogId != null && pipelineStatus?.run_type === "match_all" && IN_PROGRESS_STATUSES.includes(pipelineStatus.status)}
              matchProgress={pipelineStatus}
              reloadKey={jobsVersion}
              totalScoredJobs={stats?.total_scored_jobs ?? 0}
            />
          )}
        </div>
      </main>
    </div>
  );
}
