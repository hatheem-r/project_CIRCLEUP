"use client";

import { useRef, useState } from "react";

interface Props {
  file: File | null;
  onFile: (file: File | null) => void;
  onStart: () => void;
  busy: boolean;
}

export default function UploadPanel({ file, onFile, onStart, busy }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  return (
    <section className="rounded-2xl border border-line bg-panel p-7">
      <label
        htmlFor="timetable"
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          const dropped = e.dataTransfer.files?.[0];
          if (dropped) onFile(dropped);
        }}
        className={`flex cursor-pointer flex-col items-center gap-1.5 rounded-xl border border-dashed px-6 py-9 text-center transition-colors ${
          over
            ? "border-accent bg-accent/5"
            : "border-line hover:border-accent hover:bg-accent/5"
        }`}
      >
        <span className="mb-1.5 grid size-9 place-items-center rounded-full border border-line text-lg leading-none text-muted">
          +
        </span>
        <span className="font-medium">Choose a timetable image</span>
        <span className="text-[13px] text-faint">
          PNG, JPG or PDF &middot; or drop one here
        </span>
        <input
          id="timetable"
          ref={input}
          type="file"
          accept="image/*,application/pdf"
          hidden
          onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        />
      </label>

      {file && (
        <p className="mt-4 flex items-baseline gap-3 rounded-lg border border-line bg-lift px-3.5 py-3 text-sm">
          <span className="font-medium">{file.name}</span>
          <span className="ml-auto text-[13px] text-faint">
            {Math.round(file.size / 1024)} KB
          </span>
        </p>
      )}

      <button
        type="button"
        onClick={onStart}
        disabled={!file || busy}
        className="mt-5 w-full rounded-xl bg-ink px-5 py-3.5 font-semibold text-bg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:bg-lift disabled:text-faint disabled:opacity-100"
      >
        {busy ? "Working…" : "Find my free time"}
      </button>
    </section>
  );
}
