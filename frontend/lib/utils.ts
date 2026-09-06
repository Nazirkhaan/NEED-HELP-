import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function pct(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined) return "—";
  return `${Number(n).toFixed(digits)}%`;
}

export const STATE_LABEL: Record<string, string> = {
  claimed: "Claimed",
  institution_cosigned: "Co-signed",
  verified: "Verified",
};
