"use client";

import type { PlacePick } from "@/lib/types";

export default function PlacePicksList({ picks }: { picks: PlacePick[] }) {
  return (
    <div className="mt-4 border-t border-line pt-1">
      {picks.map((pick, i) => (
        <div key={pick.maps_url} className="flex gap-3 pt-3">
          <span className="w-5 shrink-0 text-xs tabular-nums text-faint">
            {i + 1}.
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline gap-2.5">
              <span className="text-sm font-medium">{pick.name}</span>
              {pick.rating !== null && (
                <span className="text-[12.5px] tabular-nums text-risky">
                  &#9733; {pick.rating}
                </span>
              )}
              <a
                href={pick.maps_url}
                target="_blank"
                rel="noopener noreferrer"
                className="border-b border-accent/30 text-[12.5px] text-accent hover:border-accent"
              >
                Open in Maps
              </a>
            </div>
            <p className="mt-0.5 text-[13.5px] text-muted">{pick.why}</p>
            {pick.address && (
              <p className="mt-0.5 text-xs text-faint">{pick.address}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
