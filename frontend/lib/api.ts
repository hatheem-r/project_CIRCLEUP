import type {
  ClassBlock,
  Deadline,
  FreeWindow,
  Place,
  PlacePick,
  Suggestion,
} from "./types";

// Inlined at build time, so they must be read as whole expressions, not indexed.
export const LOCAL_API =
  process.env.NEXT_PUBLIC_LOCAL_API ?? "http://localhost:8000";
export const PLACES_API =
  process.env.NEXT_PUBLIC_PLACES_API ?? "http://localhost:8001";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly where: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Every call in this app goes through here, and every one runs in the browser. */
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const where = new URL(url).pathname;

  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    // a dead backend or a blocked origin never reaches the handler below
    throw new ApiError(`Could not reach ${new URL(url).origin}.`, where);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    /* some errors carry no JSON */
  }

  if (!response.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new ApiError(
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `${response.status} ${response.statusText}`,
      where,
    );
  }
  return body as T;
}

export const parseTimetable = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return request<{ classes: ClassBlock[] }>(`${LOCAL_API}/parse`, {
    method: "POST",
    body: form,
  });
};

export const getWindows = () =>
  request<{ windows: FreeWindow[] }>(`${LOCAL_API}/windows`);

export const getDeadlines = () =>
  request<{ deadlines: Deadline[] }>(`${LOCAL_API}/deadlines`);

export const getSuggestions = () =>
  request<{ suggestions: Suggestion[] }>(`${LOCAL_API}/suggest`, {
    method: "POST",
  });

export const findPlaces = (location: string, start: string, end: string) => {
  const url = new URL("/places", PLACES_API);
  url.searchParams.set("location", location);
  url.searchParams.set("start", start);
  url.searchParams.set("end", end);
  return request<{ places: Place[] }>(url.toString());
};

export const rankPlaces = (body: {
  day: string;
  start: string;
  end: string;
  verdict: string;
  places: Place[];
}) =>
  request<{ picks: PlacePick[] }>(`${LOCAL_API}/suggest-places`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
