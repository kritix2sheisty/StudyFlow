/**
 * src/today/attention.ts
 * The "needs attention" strip on Today, from the progress answer the
 * app already holds: overdue assignments first (most overdue on top),
 * then the plan's CRITICAL and HIGH risks by due date. MODERATE and
 * LOW are the plan working as intended and are left out. The risk
 * words are the engine's, shown as sent. Pure; the date is passed in.
 */

import type { ProgressAssignment } from "../progress/store";

export interface AttentionRow {
  id: number;
  name: string;
  kind: "overdue" | "risk";
  risk: string;
  detail: string;
}

const RISK_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1 };

function daysBetween(fromIso: string, toIso: string): number {
  const [fy, fm, fd] = fromIso.split("-").map(Number);
  const [ty, tm, td] = toIso.split("-").map(Number);
  return Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(fy, fm - 1, fd)) / 86_400_000);
}

export function dueWords(days: number): string {
  if (days < 0) return `${-days} day${days === -1 ? "" : "s"} overdue`;
  if (days === 0) return "due today";
  if (days === 1) return "due tomorrow";
  return `due in ${days} days`;
}

export function attention(assignments: ProgressAssignment[], today: string): AttentionRow[] {
  const overdue: (AttentionRow & { days: number })[] = [];
  const risky: (AttentionRow & { days: number })[] = [];
  for (const a of assignments) {
    const days = daysBetween(today, a.due_date);
    if (days < 0) {
      overdue.push({ id: a.id, name: a.name, kind: "overdue", risk: a.risk, detail: dueWords(days), days });
    } else if (a.risk in RISK_ORDER) {
      risky.push({ id: a.id, name: a.name, kind: "risk", risk: a.risk, detail: `${a.risk} · ${dueWords(days)}`, days });
    }
  }
  overdue.sort((x, y) => x.days - y.days);
  risky.sort((x, y) => RISK_ORDER[x.risk] - RISK_ORDER[y.risk] || x.days - y.days);
  return [...overdue, ...risky].map(({ days: _days, ...row }) => row);
}
