"use client";

import { useState } from "react";
import PlacePicksList from "./PlacePicksList";
import { ApiError, findPlaces, rankPlaces } from "@/lib/api";
import { clock, dayLabel, spanLabel } from "@/lib/format";
import type { PlacePick, Suggestion, Verdict } from "@/lib/types";

const EDGE: Record<Verdict, string> = {
  good: "border-l-good",
  risky: "border-l-risky",
  avoid: "border-l-avoid",
};

const BADGE: Record<Verdict, string> = {
  good: "bg-good/15 text-good",
  risky: "bg-risky/15 text-risky",
  avoid: "bg-avoid/15 text-avoid",
};

export default function WindowCard({
  suggestion,
  location,
  onNeedLocation,
}: {
  suggestion: Suggestion;
  location: string;
  onNeedLocation: () => void;
}) {
  const [picks, setPicks] = useState<PlacePick[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [bad, setBad] = useState(false);
  const [busy, setBusy] = useState(false);

  async function handleFindPlaces() {
    if (!location.trim()) {
      setBad(true);
      setNote("Fill in where you are looking first.");
      onNeedLocation();
      return;
    }

    setBusy(true);
    setBad(false);
    setPicks(null);
    setNote("Looking for places…");

    try {
      const { places } = await findPlaces(
        location.trim(),
        clock(suggestion.start),
        clock(suggestion.end),
      );
      if (places.length === 0) {
        setNote(`Nothing came back for “${location.trim()}”.`);
        return;
      }

      setNote(`Ranking ${places.length} places…`);
      const { picks: ranked } = await rankPlaces({
        day: dayLabel(suggestion.start),
        start: suggestion.start,
        end: suggestion.end,
        verdict: suggestion.verdict,
        places,
      });

      if (ranked.length === 0) {
        // invalid picks are dropped rather than retried, so none may survive
        setNote("The model did not pick any of those places. Try again.");
        return;
      }
      setNote(null);
      setPicks(ranked);
    } catch (err) {
      setBad(true);
      setNote(
        err instanceof ApiError
          ? `${err.message} (${err.where})`
          : "Something went wrong.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <article
      className={`rounded-xl border border-l-[3px] border-line bg-panel px-5 py-5 ${EDGE[suggestion.verdict]}`}
    >
      <div className="mb-2.5 flex flex-wrap items-center gap-3.5">
        <span className="font-semibold">
          {dayLabel(suggestion.start)}, {clock(suggestion.start)}&ndash;
          {clock(suggestion.end)}
        </span>
        <span className="text-[13px] text-faint">
          {spanLabel(suggestion.start, suggestion.end)}
        </span>
        <span
          className={`ml-auto rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-[0.08em] uppercase ${BADGE[suggestion.verdict]}`}
        >
          {suggestion.verdict}
        </span>
      </div>

      <p className="text-[14.5px] text-muted">{suggestion.reason}</p>

      {/* nowhere is worth going when the verdict is avoid */}
      {suggestion.verdict !== "avoid" && (
        <>
          <button
            type="button"
            onClick={handleFindPlaces}
            disabled={busy}
            className="mt-3.5 rounded-lg border border-line px-3.5 py-1.5 text-[13px] font-medium text-muted transition-colors hover:bg-lift hover:text-ink disabled:cursor-not-allowed disabled:text-faint disabled:hover:bg-transparent"
          >
            {picks ? "Find other places" : "Find places"}
          </button>
          {note && (
            <p className={`mt-3 text-[13px] ${bad ? "text-avoid" : "text-faint"}`}>
              {note}
            </p>
          )}
          {picks && <PlacePicksList picks={picks} />}
        </>
      )}
    </article>
  );
}
