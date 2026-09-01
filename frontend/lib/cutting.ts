// Types and the live calculation for the cutting module.
//
// The formulas here are a deliberate second copy of backend/cutting/services.py.
// They exist so the calculation bar under the new-lay screen updates as the
// supervisor types, with no server round trip (SRS section 10: under 200ms).
//
// THE BACKEND IS THE AUTHORITY. Whatever these functions show is a preview;
// what gets stored is what services.recalculate computes at closing time. If
// the two ever disagree, the backend is right and this file is the bug.
// The backend's numbers are the ones under test in cutting/tests/.

export type RollEndAction = "splice" | "new_roll" | "stored";

export const ROLL_END_LABEL: Record<RollEndAction, string> = {
  new_roll: "توب جديد",
  splice: "وصل",
  stored: "اتخزن",
};

export type LineDraft = {
  key: string; // client-side row identity, never sent
  roll_length_m: string;
  plies: string;
  remnant_m: string;
  shade_note: string;
  roll_end_action: RollEndAction;
};

export type SizeChip = { size: string; pieces_in_ply: number };

export type Issue = {
  code: string;
  level: "error" | "warning" | "info";
  message: string;
  field: string | null;
  line_no: number | null;
};

// Arabic-Indic digits, so a keyboard set to Arabic produces usable sizes.
const ARABIC_DIGITS: Record<string, string> = {
  "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
  "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
};

/**
 * Split whatever was typed into individual sizes.
 *
 * Accepts what the notebook uses — "(32)(34)" — and what a desktop keyboard
 * can type — "30 32 32". On a phone the numeric keypad has no space bar at
 * all, which is why sizes are added one at a time from a staging box rather
 * than typed as one string; this still parses a whole string when it gets one.
 */
export function splitSizes(text: string): string[] {
  const normalized = (text ?? "")
    .split("")
    .map((ch) => ARABIC_DIGITS[ch] ?? ch)
    .join("");
  return normalized
    .split(/[^0-9A-Za-z\u0621-\u064A]+/)
    .map((t) => (/^[a-z]+$/i.test(t) ? t.toUpperCase() : t))
    .filter(Boolean);
}

/** Remove the last occurrence of a size, so tapping × on a ×2 chip leaves ×1. */
export function removeOneSize(tokens: string[], size: string): string[] {
  const index = tokens.lastIndexOf(size);
  if (index === -1) return tokens;
  return [...tokens.slice(0, index), ...tokens.slice(index + 1)];
}

export function emptyLine(): LineDraft {
  return {
    key: Math.random().toString(36).slice(2),
    roll_length_m: "",
    plies: "",
    remnant_m: "",
    shade_note: "",
    roll_end_action: "new_roll",
  };
}

/** Tolerant number parse: blank, "-" and half-typed values read as 0. */
export function num(value: string): number {
  const n = parseFloat((value ?? "").toString().replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

export type LiveTotals = {
  totalPlies: number;
  spliceCount: number;
  theoreticalPieces: number;
  totalRollLength: number;
  totalRemnant: number;
  consumed: number;
  shortage: number;
  expectedMetrage: number;
};

/**
 * Mirrors services.calculate. One splice subtracts one ply: the roll ran out
 * mid-ply and the next roll finished it, so that ply is written on both rows.
 */
export function liveTotals(
  lines: LineDraft[],
  layLengthM: number,
  piecesPerPly: number
): LiveTotals {
  const spliceCount = lines.filter((l) => l.roll_end_action === "splice").length;
  const pliesSum = lines.reduce((s, l) => s + num(l.plies), 0);
  const totalPlies = Math.max(pliesSum - spliceCount, 0);

  const totalRollLength = lines.reduce((s, l) => s + num(l.roll_length_m), 0);
  const totalRemnant = lines.reduce((s, l) => s + num(l.remnant_m), 0);
  const consumed = totalPlies * layLengthM;

  return {
    totalPlies,
    spliceCount,
    theoreticalPieces: totalPlies * piecesPerPly,
    totalRollLength,
    totalRemnant,
    consumed,
    shortage: totalRollLength - (consumed + totalRemnant),
    expectedMetrage: piecesPerPly > 0 ? layLengthM / piecesPerPly : 0,
  };
}

/** Quick mode: one aggregate row of total metres and total plies. */
export function quickTotals(
  totalMetres: number,
  totalPlies: number,
  layLengthM: number,
  piecesPerPly: number
): LiveTotals {
  const consumed = totalPlies * layLengthM;
  return {
    totalPlies,
    spliceCount: 0,
    theoreticalPieces: totalPlies * piecesPerPly,
    totalRollLength: totalMetres,
    totalRemnant: 0,
    consumed,
    shortage: totalMetres - consumed,
    expectedMetrage: piecesPerPly > 0 ? layLengthM / piecesPerPly : 0,
  };
}

/** SRS 5.4: under the threshold it is waste, at or above it is reusable. */
export function remnantIsWaste(remnantM: number, thresholdM = 1): boolean {
  return remnantM > 0 && remnantM < thresholdM;
}

/**
 * The notebook writes the lay width in metres ("1.62 م") while the API stores
 * centimetres. Rather than force one or the other on the supervisor, read
 * whichever he typed: nothing on this floor is 20 cm wide or 20 m wide, so the
 * magnitude tells us which he meant. The screen always shows the value that
 * will actually be sent.
 */
export function widthToCm(raw: string): number | null {
  const n = num(raw);
  if (!n) return null;
  return n < 20 ? Math.round(n * 100 * 100) / 100 : Math.round(n * 100) / 100;
}

export function fmt(n: number, digits = 2): string {
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits).replace(/\.?0+$/, "") || "0";
}

/** Pull the structured issues out of an ApiError payload, if it carries any. */
export function issuesOf(data: unknown): Issue[] {
  if (data && typeof data === "object" && Array.isArray((data as any).issues)) {
    return (data as any).issues as Issue[];
  }
  return [];
}
