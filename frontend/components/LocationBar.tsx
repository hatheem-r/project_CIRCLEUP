"use client";

/** Sits above the windows, next to the buttons that use it. */
export default function LocationBar({
  location,
  onLocation,
}: {
  location: string;
  onLocation: (value: string) => void;
}) {
  return (
    <div className="mb-4 flex flex-col gap-2.5 rounded-xl border border-line bg-panel px-5 py-4 sm:flex-row sm:items-center sm:gap-4">
      <label htmlFor="location" className="shrink-0 text-[13px] text-muted">
        Where are you looking for places?
      </label>
      <input
        id="location"
        type="text"
        value={location}
        onChange={(e) => onLocation(e.target.value)}
        placeholder="cafes in Colombo 7"
        autoComplete="off"
        className="w-full rounded-lg border border-line bg-lift px-3.5 py-2.5 text-sm outline-none placeholder:text-faint focus:border-accent"
      />
    </div>
  );
}
