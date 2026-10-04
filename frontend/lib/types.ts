export type Verdict = "good" | "risky" | "avoid";

export interface ClassBlock {
  day: string;
  start: string;
  end: string;
  code: string | null;
  name: string;
  type: string;
  venue: string | null;
}

export interface FreeWindow {
  start: string;
  end: string;
  duration_hours: number;
}

export interface Deadline {
  name: string;
  due_at: string;
  course: string | null;
  all_day: boolean;
  urgency_at: string;
}

export interface Suggestion {
  start: string;
  end: string;
  verdict: Verdict;
  reason: string;
}

export interface Place {
  name: string;
  address: string | null;
  rating: number | null;
  maps_url: string;
}

export interface PlacePick extends Place {
  why: string;
}
