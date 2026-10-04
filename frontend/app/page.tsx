"use client";

import { useState } from "react";
import DeadlineList from "@/components/DeadlineList";
import LocationBar from "@/components/LocationBar";
import StepIndicator, { STEPS } from "@/components/StepIndicator";
import UploadPanel from "@/components/UploadPanel";
import WindowCard from "@/components/WindowCard";
import {
  ApiError,
  getDeadlines,
  getSuggestions,
  getWindows,
  parseTimetable,
} from "@/lib/api";
import type { Deadline, Suggestion } from "@/lib/types";

export default function Page() {
  const [file, setFile] = useState<File | null>(null);
  const [location, setLocation] = useState("");
  const [step, setStep] = useState(-1);
  const [error, setError] = useState<{ where: string; message: string } | null>(
    null,
  );
  const [suggestions, setSuggestions] = useState<Suggestion[] | null>(null);
  const [deadlines, setDeadlines] = useState<Deadline[] | null>(null);

  const busy = step >= 0 && step < STEPS.length;

  async function run() {
    if (!file) return;

    setError(null);
    setSuggestions(null);
    setDeadlines(null);

    try {
      // every one of these runs in the browser; the backend is on localhost
      setStep(0);
      await parseTimetable(file);

      setStep(1);
      const { windows } = await getWindows();

      setStep(2);
      const { deadlines: due } = await getDeadlines();

      setStep(3);
      const { suggestions: advice } = await getSuggestions();

      setStep(-1);
      setDeadlines(due);
      setSuggestions(windows.length === 0 ? [] : advice);
    } catch (err) {
      setStep(-1);
      setError(
        err instanceof ApiError
          ? { where: err.where, message: err.message }
          : { where: "", message: "Something went wrong." },
      );
    }
  }

  const tally = (["good", "risky", "avoid"] as const)
    .map((v) => [v, suggestions?.filter((s) => s.verdict === v).length ?? 0] as const)
    .filter(([, n]) => n > 0)
    .map(([v, n]) => `${n} ${v}`)
    .join(" · ");

  return (
    <main className="mx-auto max-w-5xl px-6 pt-18 pb-30">
      <header className="mb-14">
        <h1 className="mb-2.5 text-3xl font-semibold tracking-tight">CircleUp</h1>
        <p className="text-base text-muted">
          Upload your timetable and find out when you are actually free.
        </p>
      </header>

      <UploadPanel file={file} onFile={setFile} onStart={run} busy={busy} />

      {busy && <StepIndicator current={step} />}

      {error && (
        <div className="mt-5 rounded-xl border border-avoid/30 bg-avoid/10 px-4.5 py-4 text-sm text-avoid">
          <b className="mb-1 block font-semibold">
            That didn&apos;t work{error.where && ` (${error.where})`}
          </b>
          <span className="text-muted">{error.message}</span>
        </div>
      )}

      {suggestions && (
        <section className="mt-11">
          <h2 className="mb-4 text-[13px] font-semibold tracking-[0.09em] text-muted uppercase">
            Your free windows
            <span className="ml-2 font-normal tracking-normal text-faint normal-case">
              {tally}
            </span>
          </h2>

          {suggestions.length === 0 ? (
            <p className="text-sm text-faint">
              Nothing of 2 hours or more came back for the next 7 days.
            </p>
          ) : (
            <>
              {/* only worth asking once there is somewhere it could apply */}
              {suggestions.some((s) => s.verdict !== "avoid") && (
                <LocationBar location={location} onLocation={setLocation} />
              )}
              <div className="flex flex-col gap-3">
                {suggestions.map((s) => (
                  <WindowCard
                    key={`${s.start}-${s.end}`}
                    suggestion={s}
                    location={location}
                    onNeedLocation={() =>
                      document.getElementById("location")?.focus()
                    }
                  />
                ))}
              </div>
            </>
          )}
        </section>
      )}

      {deadlines && <DeadlineList deadlines={deadlines} />}
    </main>
  );
}
