import type { Json } from "./protocol";
import { texts, statusLabel } from "./i18n";

type Labels = ReturnType<typeof texts>;
type Metric = readonly [string, string | number];
type Data = Record<string, Json>;

function record(value: Json | undefined): Data {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}
function count(value: Json | undefined): number | undefined {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}
export function measuredRatio(numerator: Json | undefined, denominator: Json | undefined, missing: string): string {
  const a = count(numerator), b = count(denominator);
  return a === undefined || b === undefined || b === 0 || a > b ? missing : `${a}/${b} (${Math.round(100*a/b)}%)`;
}
function ratio(row: Data, a: string, b: string, t: Labels): string {
  return measuredRatio(row[a], row[b], t.gameNotMeasured);
}
function MetricRows({rows}: {rows: readonly Metric[]}) {
  return <tbody>{rows.map(([label, value]) => <tr key={label}><th scope="row">{label}</th><td>{value}</td></tr>)}</tbody>;
}
function opportunityMetrics(row: Data, t: Labels): Metric[] {
  return [
    [t.gameLegalUse, ratio(row, "legal_moves", "proposals", t)],
    [t.gameOptimalUse, ratio(row, "optimal_moves", "legal_moves", t)],
    [t.gameWinUse, ratio(row, "wins_taken", "win_opportunities", t)],
    [t.gameBlockUse, ratio(row, "blocks_taken", "block_opportunities", t)],
    [t.gameRuleUse, ratio(row, "rule_followed", "rule_opportunities", t)],
  ];
}
function gameStatus(value: Json | undefined, t: Labels): string {
  if (value === "in_progress") return statusLabel(t, "running");
  if (value === "incomplete") return t.gameIncomplete;
  return typeof value === "string" ? statusLabel(t, value) : t.unknown;
}
function PerGameMeasurements({games, t}: {games: Data[]; t: Labels}) {
  if (!games.length) return null;
  return <details><summary>{t.gamePerGame}</summary>{games.map((row, index) => {
    const number = count(row.number);
    const label = number === undefined ? t.unknown : String(number);
    const metrics: Metric[] = [...opportunityMetrics(row, t),
      [t.gameRepeatedErrors, count(row.repeated_tactical_errors) ?? t.gameNotMeasured]];
    return <div key={number ?? index}>
      <h3>{t.gameRound} {label} · {gameStatus(row.status, t)}</h3>
      <table aria-label={`${t.gameRound} ${label}`}><MetricRows rows={metrics}/></table>
    </div>;
  })}</details>;
}
function RuleComparisons({rules, t}: {rules: Data; t: Labels}) {
  if (!Object.keys(rules).length) return null;
  return <details><summary>{t.gameRuleComparison}</summary>{Object.entries(rules).map(([player, value]) => <div key={player}>
    {Object.entries(record(value)).map(([rule, groups]) => {
      const metrics: Metric[] = [
        [t.gameWithoutReminder, ratio(record(record(groups).without_reminder), "followed", "opportunities", t)],
        [t.gameWithReminder, ratio(record(record(groups).with_reminder), "followed", "opportunities", t)],
      ];
      return <table key={rule} aria-label={`${player} · ${rule}`}><caption>{player} · {rule}</caption><MetricRows rows={metrics}/></table>;
    })}
  </div>)}</details>;
}
function TransferMeasurements({transfer, t}: {transfer: Data; t: Labels}) {
  return Object.entries(transfer).map(([player, value]) => {
    const metrics: Metric[] = [
      [t.gameTransferEquivalent, ratio(record(record(value).source_equivalent), "followed", "opportunities", t)],
      [t.gameTransferNew, ratio(record(record(value).new_position), "followed", "opportunities", t)],
    ];
    return <table key={player} aria-label={`${player} · ${t.gameRuleUse}`}><caption>{player} · {t.gameRuleUse}</caption><MetricRows rows={metrics}/></table>;
  });
}

export function GameMeasurements({measurement, language}: {measurement: Json | undefined; language: string}) {
  const t = texts(language), data = record(measurement);
  if (data.version !== "live-tactical-measurement-v1") return <p className="coop-message-meta">{t.gameNoMeasurement}</p>;
  const totals = record(data.totals);
  const metrics: Metric[] = [...opportunityMetrics(totals, t),
    [t.gameFirstEmpty, ratio(totals, "first_empty_choices", "legal_moves", t)],
    ...([[t.gameFormatErrors, "invalid_format"], [t.gameIllegalMoves, "illegal_moves"],
      [t.gameUnavoidableThreats, "unavoidable_threats"], [t.gameRepeatedErrors, "repeated_tactical_errors"]] as const)
      .map(([label, key]): Metric => [label, count(totals[key]) ?? t.gameNotMeasured]),
  ];
  const games = Array.isArray(data.games) ? data.games.map(record) : [];
  const category = typeof data.failure_category === "string" ? data.failure_category : "";
  const failure = ({format: t.gameFailureFormat, illegal_move: t.gameFailureIllegal, infrastructure: t.gameFailureInfrastructure, cancelled: t.gameFailureCancelled} as Record<string, string>)[category];
  return <>
    <p className="coop-message-meta">{t.gameMeasurementScope}</p>
    {failure && <output>{failure}</output>}
    <table className="coop-game-metrics" aria-label={t.gameStrategyMetrics}><MetricRows rows={metrics}/></table>
    <PerGameMeasurements games={games} t={t}/>
    <RuleComparisons rules={record(data.rules)} t={t}/>
    <TransferMeasurements transfer={record(data.transfer)} t={t}/>
  </>;
}
