// The API answers in Colombo time; render it as sent, whatever the viewer's clock.
const TZ = "Asia/Colombo";

export const dayLabel = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "short",
    timeZone: TZ,
  });

/** "08:00" / "22:00". h23 rather than hour12:false, which can yield "24:00"
 *  on some engines -- this value is also sent to the places service. */
export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: TZ,
  });

export function spanLabel(start: string, end: string) {
  const mins = Math.round(
    (new Date(end).getTime() - new Date(start).getTime()) / 60000,
  );
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? `${h}h ${m}m free` : `${h}h free`;
}

export const dueLabel = (d: { due_at: string; all_day: boolean }) =>
  d.all_day
    ? `by end of ${dayLabel(d.due_at)}`
    : `${dayLabel(d.due_at)}, ${clock(d.due_at)}`;

export function awayLabel(iso: string) {
  const days = Math.round(
    (new Date(iso).getTime() - Date.now()) / 86_400_000,
  );
  if (days <= 0) return "today";
  return days === 1 ? "tomorrow" : `in ${days} days`;
}
