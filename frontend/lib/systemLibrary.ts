export type SystemPreset = {
  id: string;
  name: string;
  type: "U" | "MU" | "UE";
  utganger: number;
  reserver: number;
  rows: number;
  cost: number;
  // Category A: rows = 3^n_full × 2^n_half exactly — Cartesian product, fully implementable.
  // Category B: rows not factorable into only 2s and 3s — NT reduction table required.
  category: "A" | "B";
  // For Category A only: the unique factorization 3^n_full × 2^n_half = rows.
  // These are EXACT — verified against rows. Changing them will break row generation.
  n_full: number;
  n_half: number;
  description?: string;
};

// Sorted by rows ascending so the dropdown presents a natural cheap→expensive progression.
export const SYSTEM_LIBRARY: SystemPreset[] = [
  // ── Category A — Cartesian, fully implemented ─────────────────────────────────
  // rows = 3^n_full × 2^n_half exactly.
  { id: "u-7-0-36",     name: "U 7-0-36",     type: "U",  utganger: 7,  reserver: 0, rows: 36,   cost: 36,   category: "A", n_full: 2, n_half: 2 }, // 3²×2²=36
  { id: "mu-4-3-64",    name: "MU 4-3-64",    type: "MU", utganger: 4,  reserver: 3, rows: 64,   cost: 64,   category: "A", n_full: 0, n_half: 6 }, // 2⁶=64
  { id: "u-6-0-64",     name: "U 6-0-64",     type: "U",  utganger: 6,  reserver: 0, rows: 64,   cost: 64,   category: "A", n_full: 0, n_half: 6 }, // 2⁶=64
  { id: "mu-7-0-108",   name: "MU 7-0-108",   type: "MU", utganger: 7,  reserver: 0, rows: 108,  cost: 108,  category: "A", n_full: 3, n_half: 2 }, // 3³×2²=108
  { id: "mu-9-1-192",   name: "MU 9-1-192",   type: "MU", utganger: 9,  reserver: 1, rows: 192,  cost: 192,  category: "A", n_full: 1, n_half: 6 }, // 3×2⁶=192
  { id: "u-9-0-192",    name: "U 9-0-192",    type: "U",  utganger: 9,  reserver: 0, rows: 192,  cost: 192,  category: "A", n_full: 1, n_half: 6 }, // 3×2⁶=192
  { id: "mu-6-2-324",   name: "MU 6-2-324",   type: "MU", utganger: 6,  reserver: 2, rows: 324,  cost: 324,  category: "A", n_full: 4, n_half: 2 }, // 3⁴×2²=324
  { id: "u-8-2-432",    name: "U 8-2-432",    type: "U",  utganger: 8,  reserver: 2, rows: 432,  cost: 432,  category: "A", n_full: 3, n_half: 4 }, // 3³×2⁴=432
  { id: "mu-7-1-486",   name: "MU 7-1-486",   type: "MU", utganger: 7,  reserver: 1, rows: 486,  cost: 486,  category: "A", n_full: 5, n_half: 1 }, // 3⁵×2=486
  { id: "mu-5-5-864",   name: "MU 5-5-864",   type: "MU", utganger: 5,  reserver: 5, rows: 864,  cost: 864,  category: "A", n_full: 3, n_half: 5 }, // 3³×2⁵=864

  // ── Category B — NT reduction table required, not yet implemented ─────────────
  // rows is not factorable into only 2s and 3s; cannot be produced by sign-set Cartesian product.
  { id: "u-8-0-75",     name: "U 8-0-75",     type: "U",  utganger: 8,  reserver: 0, rows: 75,   cost: 75,   category: "B", n_full: 0, n_half: 0 },
  { id: "mu-6-1-80",    name: "MU 6-1-80",    type: "MU", utganger: 6,  reserver: 1, rows: 80,   cost: 80,   category: "B", n_full: 0, n_half: 0 },
  { id: "u-8-0-82",     name: "U 8-0-82",     type: "U",  utganger: 8,  reserver: 0, rows: 82,   cost: 82,   category: "B", n_full: 0, n_half: 0 },
  { id: "u-9-0-83",     name: "U 9-0-83",     type: "U",  utganger: 9,  reserver: 0, rows: 83,   cost: 83,   category: "B", n_full: 0, n_half: 0 },
  { id: "mu-6-0-84",    name: "MU 6-0-84",    type: "MU", utganger: 6,  reserver: 0, rows: 84,   cost: 84,   category: "B", n_full: 0, n_half: 0 },
  { id: "mu-5-3-88",    name: "MU 5-3-88",    type: "MU", utganger: 5,  reserver: 3, rows: 88,   cost: 88,   category: "B", n_full: 0, n_half: 0 },
  { id: "u-10-0-100",   name: "U 10-0-100",   type: "U",  utganger: 10, reserver: 0, rows: 100,  cost: 100,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-6-2-100",   name: "MU 6-2-100",   type: "MU", utganger: 6,  reserver: 2, rows: 100,  cost: 100,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-5-1-100",   name: "MU 5-1-100",   type: "MU", utganger: 5,  reserver: 1, rows: 100,  cost: 100,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-8-0-112",    name: "U 8-0-112",    type: "U",  utganger: 8,  reserver: 0, rows: 112,  cost: 112,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-7-0-188",    name: "U 7-0-188",    type: "U",  utganger: 7,  reserver: 0, rows: 188,  cost: 188,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-12-0-189",  name: "MU 12-0-189",  type: "MU", utganger: 12, reserver: 0, rows: 189,  cost: 189,  category: "B", n_full: 0, n_half: 0 },
  { id: "ue-8-0-191",   name: "UE 8-0-191",   type: "UE", utganger: 8,  reserver: 0, rows: 191,  cost: 191,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-6-1-195",    name: "U 6-1-195",    type: "U",  utganger: 6,  reserver: 1, rows: 195,  cost: 195,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-3-5-199",    name: "U 3-5-199",    type: "U",  utganger: 3,  reserver: 5, rows: 199,  cost: 199,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-5-2-204",   name: "MU 5-2-204",   type: "MU", utganger: 5,  reserver: 2, rows: 204,  cost: 204,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-9-0-222",    name: "U 9-0-222",    type: "U",  utganger: 9,  reserver: 0, rows: 222,  cost: 222,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-8-1-480",   name: "MU 8-1-480",   type: "MU", utganger: 8,  reserver: 1, rows: 480,  cost: 480,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-9-0-483",   name: "MU 9-0-483",   type: "MU", utganger: 9,  reserver: 0, rows: 483,  cost: 483,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-9-0-483",    name: "U 9-0-483",    type: "U",  utganger: 9,  reserver: 0, rows: 483,  cost: 483,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-6-3-488",   name: "MU 6-3-488",   type: "MU", utganger: 6,  reserver: 3, rows: 488,  cost: 488,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-8-0-544",    name: "U 8-0-544",    type: "U",  utganger: 8,  reserver: 0, rows: 544,  cost: 544,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-9-0-547",    name: "U 9-0-547",    type: "U",  utganger: 9,  reserver: 0, rows: 547,  cost: 547,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-10-0-584",   name: "U 10-0-584",   type: "U",  utganger: 10, reserver: 0, rows: 584,  cost: 584,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-10-0-587",   name: "U 10-0-587",   type: "U",  utganger: 10, reserver: 0, rows: 587,  cost: 587,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-6-4-784",   name: "MU 6-4-784",   type: "MU", utganger: 6,  reserver: 4, rows: 784,  cost: 784,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-9-0-788",   name: "MU 9-0-788",   type: "MU", utganger: 9,  reserver: 0, rows: 788,  cost: 788,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-9-3-792",   name: "MU 9-3-792",   type: "MU", utganger: 9,  reserver: 3, rows: 792,  cost: 792,  category: "B", n_full: 0, n_half: 0 },
  { id: "u-10-0-800",   name: "U 10-0-800",   type: "U",  utganger: 10, reserver: 0, rows: 800,  cost: 800,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-9-0-891",   name: "MU 9-0-891",   type: "MU", utganger: 9,  reserver: 0, rows: 891,  cost: 891,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-9-1-900",   name: "MU 9-1-900",   type: "MU", utganger: 9,  reserver: 1, rows: 900,  cost: 900,  category: "B", n_full: 0, n_half: 0 },
  { id: "mu-8-3-1000",  name: "MU 8-3-1000",  type: "MU", utganger: 8,  reserver: 3, rows: 1000, cost: 1000, category: "B", n_full: 0, n_half: 0 },
];
