/**
 * Oddstips insight derivation.
 *
 * Betting value is calculated exclusively from model probability vs bookmaker
 * implied probability (market_edge_pp). NT public percentages are NOT used here.
 *
 * Available insight types:
 *   value_bet  — model clearly beats bookmaker price (market_edge_pp ≥ 5pp)
 *   safe_tip   — high model confidence (≥ 52%), market-neutral
 *   longshot   — low probability but model beats market (prob ≤ 35%, mep ≥ 5pp)
 */
import type { InsightSignal } from "./types";

export type InsightType = "value_bet" | "safe_tip" | "longshot";
export type MarketKey = "1x2" | "btts" | "over_2.5";
export type RiskLevel = "low" | "medium" | "high";

export interface InsightItem {
  signal: InsightSignal;
  market: MarketKey;
  insightType: InsightType;
  riskLevel: RiskLevel;
  marketEdgePp: number;        // model_prob − implied_prob (betting value)
  modelProb: number;           // model probability 0–100
  impliedProb: number;         // bookmaker implied probability 0–100
  refOdds: number | null;      // bookmaker decimal odds for the pick
  bookmaker: string | null;
  explanation: string;
  pickLabel: string;           // "H", "U", "B", "Ja", "Over 2.5" etc.
  pickDirection: "steaming" | "drifting" | "stable" | null;
  confidenceScore: number | null;   // 0–100 composite
  afAgreement: "agrees" | "disagrees" | "neutral" | null;
}

export interface NoBetWarning {
  signal: InsightSignal;
  reason: string;
}

export interface OddstipsResult {
  valueBets: InsightItem[];
  safeTips: InsightItem[];
  longshots: InsightItem[];
  allItems: InsightItem[];
  noBetWarnings: NoBetWarning[];
}

const SIGN_NOR: Record<string, string> = {
  H: "Hjemmeseier",
  U: "Uavgjort",
  B: "Borteseier",
};

function getPickDirection(
  signal: InsightSignal,
  pick: string
): "steaming" | "drifting" | "stable" | null {
  const mv = signal.odds_movement;
  if (!mv) return null;
  const open =
    pick === "H" ? mv.open_h : pick === "U" ? mv.open_u : mv.open_b;
  const current =
    pick === "H" ? mv.current_h : pick === "U" ? mv.current_u : mv.current_b;
  const diff = current - open;
  if (diff < -0.05) return "steaming";
  if (diff > 0.05) return "drifting";
  return "stable";
}

function getRiskLevel(modelProb: number, marketEdgePp: number, insightType: InsightType): RiskLevel {
  if (insightType === "longshot") return "high";
  if (modelProb >= 55 && marketEdgePp >= 8) return "low";
  if (modelProb <= 40) return "high";
  return "medium";
}

function afSuffix(signal: InsightSignal, market: MarketKey): string {
  if (market === "btts" || market === "over_2.5") {
    const agrees = market === "over_2.5" ? signal.af_ou_agrees : null;
    if (agrees === true  && signal.af_advice) return ` AF støtter: «${signal.af_advice}».`;
    if (agrees === false && signal.af_advice) return ` AF sier: «${signal.af_advice}».`;
    return "";
  }
  // 1X2
  if (signal.af_advice) {
    if (signal.af_winner_agrees === true)  return ` AF støtter: «${signal.af_advice}».`;
    if (signal.af_winner_agrees === false) return ` AF er uenig: «${signal.af_advice}».`;
    if (signal.af_winner_agrees === null)  return ` AF: «${signal.af_advice}».`;
  }
  return "";
}

function buildExplanation(
  signal: InsightSignal,
  market: MarketKey,
  insightType: InsightType,
  modelProb: number,
  impliedProb: number,
  marketEdgePp: number,
  refOdds: number | null,
  bookmaker: string | null
): string {
  const mPct  = modelProb.toFixed(1);
  const iPct  = impliedProb.toFixed(1);
  const mep   = marketEdgePp.toFixed(1);
  const bkm   = bookmaker ?? "markedet";
  const odds  = refOdds ? refOdds.toFixed(2) : null;

  const af = afSuffix(signal, market);

  if (market === "btts") {
    const xg = (signal.xg_home && signal.xg_away)
      ? ` (xG ${signal.xg_home}–${signal.xg_away})`
      : "";
    switch (insightType) {
      case "value_bet":
        return `Poisson-modellen beregner ${mPct}% for begge lag scorer, mot ${bkm} sin implikasjon ${iPct}%. +${mep}pp kant${xg}. Odds: ${odds ?? "—"}.${af}`;
      case "longshot":
        return `Usannsynlig BTTS, men modellen (+${mep}pp over markedet${xg}) finner verdi til ${odds ?? "—"}.${af}`;
      default:
        return `Sterk BTTS-sannsynlighet på ${mPct}% vs markedets ${iPct}%${xg}.${af}`;
    }
  }

  if (market === "over_2.5") {
    const xg = (signal.xg_home && signal.xg_away)
      ? ` (xG ${signal.xg_home}–${signal.xg_away})`
      : "";
    switch (insightType) {
      case "value_bet":
        return `Poisson-modellen: ${mPct}% for over 2,5 mål, mot ${bkm} sin implikasjon ${iPct}%. +${mep}pp kant${xg}. Odds: ${odds ?? "—"}.${af}`;
      case "longshot":
        return `Usannsynlig Over 2,5, men modellen (+${mep}pp over markedet${xg}) finner verdi til ${odds ?? "—"}.${af}`;
      default:
        return `Sterk Over 2,5-sannsynlighet på ${mPct}% vs markedets ${iPct}%${xg}.${af}`;
    }
  }

  // 1X2
  const pick = SIGN_NOR[signal.recommended_pick] ?? signal.recommended_pick;
  const mvDir = signal.odds_movement
    ? getPickDirection(signal, signal.recommended_pick)
    : null;
  const mvText = mvDir === "steaming"
    ? " Markedet støtter (oddset faller)."
    : mvDir === "drifting"
    ? " Markedet divergerer (oddset stiger)."
    : "";

  switch (insightType) {
    case "value_bet":
      return `Modellen ser ${mPct}% for ${pick} mot ${bkm}-implisert ${iPct}%. +${mep}pp kant. Odds: ${odds ?? "—"} (${bkm}).${mvText}${af}`;
    case "safe_tip":
      return `Sterk modell-sannsynlighet på ${mPct}% for ${pick}. Bookmaker antyder ${iPct}%.${odds ? ` Odds: ${odds}.` : ""}${mvText}${af}`;
    case "longshot":
      return `Langt skudd med verdi: modellen ser ${mPct}% for ${pick}, markedet bare ${iPct}% (+${mep}pp). Odds: ${odds ?? "—"}.${mvText}${af}`;
  }
}

export function deriveOddstips(signals: InsightSignal[]): OddstipsResult {
  const valueBets: InsightItem[] = [];
  const safeTips: InsightItem[] = [];
  const longshots: InsightItem[] = [];
  const noBetWarnings: NoBetWarning[] = [];

  const MIN_EDGE = 5;   // pp threshold for value classification

  for (const s of signals) {
    // ── No-bet warning: AF strongly disagrees with high-confidence model pick ──
    if (
      s.af_winner_agrees === false &&
      s.model_prob >= 52 &&
      s.implied_prob !== null
    ) {
      const afPick = s.af_winner_name ? `AF forventer ${s.af_winner_name}` : "AF er uenig";
      noBetWarnings.push({
        signal: s,
        reason: `${afPick}. Unngå eller reduser eksponering. ${s.af_advice ? `«${s.af_advice}»` : ""}`,
      });
    }

    // ── Derive AF agreement label ─────────────────────────────────────────────
    const afAgreement1x2: InsightItem["afAgreement"] =
      s.af_winner_agrees === true  ? "agrees" :
      s.af_winner_agrees === false ? "disagrees" :
      s.af_winner_agrees === null && s.af_advice ? "neutral" : null;

    // ── 1X2 ──────────────────────────────────────────────────────────────────
    if (s.implied_prob !== null && s.market_edge_pp !== null) {
      const mep  = s.market_edge_pp;
      const prob = s.model_prob;
      const oddsMap = { H: s.odds_h, U: s.odds_u, B: s.odds_b };
      const refOdds = oddsMap[s.recommended_pick as "H" | "U" | "B"] ?? null;
      const pickDir = getPickDirection(s, s.recommended_pick);

      const buildItem = (type: InsightType): InsightItem => ({
        signal: s,
        market: "1x2",
        insightType: type,
        riskLevel: getRiskLevel(prob, mep, type),
        marketEdgePp: mep,
        modelProb: prob,
        impliedProb: s.implied_prob!,
        refOdds,
        bookmaker: s.odds_source,
        explanation: buildExplanation(s, "1x2", type, prob, s.implied_prob!, mep, refOdds, s.odds_source),
        pickLabel: SIGN_NOR[s.recommended_pick] ?? s.recommended_pick,
        pickDirection: pickDir,
        confidenceScore: s.confidence_score ?? null,
        afAgreement: afAgreement1x2,
      });

      if (prob <= 35 && mep >= MIN_EDGE) {
        longshots.push(buildItem("longshot"));
      } else if (mep >= MIN_EDGE) {
        valueBets.push(buildItem("value_bet"));
      } else if (prob >= 52) {
        safeTips.push(buildItem("safe_tip"));
      }
    } else if (s.model_prob >= 52) {
      const pickDir = getPickDirection(s, s.recommended_pick);
      const afSfx   = s.af_advice ? ` AF: «${s.af_advice}».` : "";
      safeTips.push({
        signal: s,
        market: "1x2",
        insightType: "safe_tip",
        riskLevel: getRiskLevel(s.model_prob, 0, "safe_tip"),
        marketEdgePp: 0,
        modelProb: s.model_prob,
        impliedProb: 0,
        refOdds: null,
        bookmaker: null,
        explanation: `Sterk modell-sannsynlighet på ${s.model_prob.toFixed(1)}% for ${SIGN_NOR[s.recommended_pick] ?? s.recommended_pick}. Ingen bookmaker-odds tilgjengelig.${afSfx}`,
        pickLabel: SIGN_NOR[s.recommended_pick] ?? s.recommended_pick,
        pickDirection: pickDir,
        confidenceScore: s.confidence_score ?? null,
        afAgreement: afAgreement1x2,
      });
    }

    // ── BTTS ─────────────────────────────────────────────────────────────────
    if (
      s.btts_model_prob !== null &&
      s.btts_implied_yes !== null &&
      s.btts_market_edge_pp !== null
    ) {
      const mep  = s.btts_market_edge_pp;
      const prob = s.btts_model_prob;
      const afAgr: InsightItem["afAgreement"] = null; // BTTS not directly from AF winner

      const buildBtts = (type: InsightType): InsightItem => ({
        signal: s,
        market: "btts",
        insightType: type,
        riskLevel: getRiskLevel(prob, mep, type),
        marketEdgePp: mep,
        modelProb: prob,
        impliedProb: s.btts_implied_yes!,
        refOdds: s.btts_yes_odds,
        bookmaker: s.btts_bookmaker,
        explanation: buildExplanation(s, "btts", type, prob, s.btts_implied_yes!, mep, s.btts_yes_odds, s.btts_bookmaker),
        pickLabel: "Begge lag scorer",
        pickDirection: null,
        confidenceScore: s.confidence_score ?? null,
        afAgreement: afAgr,
      });

      if (prob <= 35 && mep >= MIN_EDGE) {
        longshots.push(buildBtts("longshot"));
      } else if (mep >= MIN_EDGE) {
        valueBets.push(buildBtts("value_bet"));
      }
    }

    // ── Over 2.5 ─────────────────────────────────────────────────────────────
    if (
      s.over_model_prob !== null &&
      s.over_implied !== null &&
      s.over_market_edge_pp !== null
    ) {
      const mep  = s.over_market_edge_pp;
      const prob = s.over_model_prob;
      const afAgr: InsightItem["afAgreement"] =
        s.af_ou_agrees === true  ? "agrees" :
        s.af_ou_agrees === false ? "disagrees" : null;

      const buildOU = (type: InsightType): InsightItem => ({
        signal: s,
        market: "over_2.5",
        insightType: type,
        riskLevel: getRiskLevel(prob, mep, type),
        marketEdgePp: mep,
        modelProb: prob,
        impliedProb: s.over_implied!,
        refOdds: s.over_25_odds,
        bookmaker: s.ou_bookmaker,
        explanation: buildExplanation(s, "over_2.5", type, prob, s.over_implied!, mep, s.over_25_odds, s.ou_bookmaker),
        pickLabel: "Over 2,5 mål",
        pickDirection: null,
        confidenceScore: s.confidence_score ?? null,
        afAgreement: afAgr,
      });

      if (prob <= 35 && mep >= MIN_EDGE) {
        longshots.push(buildOU("longshot"));
      } else if (mep >= MIN_EDGE) {
        valueBets.push(buildOU("value_bet"));
      }
    }
  }

  // Sort by confidence score (desc) then by edge within type
  const byConf = (a: InsightItem, b: InsightItem) =>
    ((b.confidenceScore ?? 0) - (a.confidenceScore ?? 0)) ||
    (b.marketEdgePp - a.marketEdgePp);
  const byEdge = (a: InsightItem, b: InsightItem) => b.marketEdgePp - a.marketEdgePp;
  const byProb = (a: InsightItem, b: InsightItem) => b.modelProb - a.modelProb;

  valueBets.sort(byConf);
  safeTips.sort(byProb);
  longshots.sort(byEdge);

  const allItems = [...valueBets, ...safeTips, ...longshots];

  return { valueBets, safeTips, longshots, allItems, noBetWarnings };
}
