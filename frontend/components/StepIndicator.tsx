"use client";

export const STEPS = [
  { key: "parse", label: "Reading your timetable", note: "a vision model looks at the image — this is the slow one" },
  { key: "windows", label: "Working out your free windows", note: "" },
  { key: "deadlines", label: "Checking your Moodle deadlines", note: "" },
  { key: "suggest", label: "Weighing up each window", note: "one model call per window" },
] as const;

export type StepKey = (typeof STEPS)[number]["key"];

export default function StepIndicator({ current }: { current: number }) {
  return (
    <section
      aria-live="polite"
      className="mt-5 rounded-2xl border border-line bg-panel p-7"
    >
      {STEPS.map((step, i) => {
        const done = i < current;
        const running = i === current;

        return (
          <div
            key={step.key}
            className={`flex items-center gap-3.5 py-2 text-sm ${
              running ? "text-ink" : done ? "text-muted" : "text-faint"
            }`}
          >
            <span
              className={`size-2.5 shrink-0 rounded-full border ${
                running
                  ? "animate-pulse border-accent bg-accent"
                  : done
                    ? "border-good bg-good"
                    : "border-current"
              }`}
            />
            <span>{step.label}</span>
            {running && step.note && (
              <span className="text-[13px] text-faint">{step.note}</span>
            )}
          </div>
        );
      })}
    </section>
  );
}
