"use client";

import { awayLabel, dueLabel } from "@/lib/format";
import type { Deadline } from "@/lib/types";

export default function DeadlineList({ deadlines }: { deadlines: Deadline[] }) {
  return (
    <section className="mt-5 rounded-2xl border border-line bg-panel p-6">
      <h2 className="mb-4 text-[13px] font-semibold tracking-[0.09em] text-muted uppercase">
        Deadlines considered
        <span className="ml-2 font-normal tracking-normal text-faint normal-case">
          next 14 days
        </span>
      </h2>

      {deadlines.length === 0 ? (
        <p className="text-sm text-faint">Nothing due in the next 14 days.</p>
      ) : (
        deadlines.map((d) => (
          <div
            key={`${d.name}-${d.urgency_at}`}
            className="border-t border-line py-3.5 text-sm first:border-t-0 first:pt-0"
          >
            <div className="font-medium">{d.name}</div>
            <div className="mt-0.5 flex flex-wrap gap-2 text-[12.5px] text-faint">
              {d.course && (
                <span className="rounded bg-accent/10 px-1.5 py-px text-[11.5px] font-medium text-accent">
                  {d.course}
                </span>
              )}
              <span>
                {dueLabel(d)} &middot; {awayLabel(d.urgency_at)}
              </span>
            </div>
          </div>
        ))
      )}
    </section>
  );
}
