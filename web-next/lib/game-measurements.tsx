import type { Json } from "./protocol";
import { texts, statusLabel } from "./i18n";

function record(value:Json|undefined):Record<string,Json> {
  return value&&typeof value==="object"&&!Array.isArray(value)?value:{};
}
function count(value:Json|undefined):number|undefined {
  return typeof value==="number"&&Number.isInteger(value)&&value>=0?value:undefined;
}
export function measuredRatio(numerator:Json|undefined,denominator:Json|undefined,missing:string):string {
  const a=count(numerator),b=count(denominator);
  return a===undefined||b===undefined||b===0||a>b?missing:`${a}/${b} (${Math.round(100*a/b)}%)`;
}

export function GameMeasurements({measurement,language}:{measurement:Json|undefined;language:string}) {
  const t=texts(language),data=record(measurement);
  if(data.version!=="live-tactical-measurement-v1")return <p className="coop-message-meta">{t.gameNoMeasurement}</p>;
  const totals=record(data.totals);
  const ratio=(row:Record<string,Json>,a:string,b:string)=>measuredRatio(row[a],row[b],t.gameNotMeasured);
  const metrics:[string,string|number][]=[
    [t.gameLegalUse,ratio(totals,"legal_moves","proposals")],
    [t.gameOptimalUse,ratio(totals,"optimal_moves","legal_moves")],
    [t.gameWinUse,ratio(totals,"wins_taken","win_opportunities")],
    [t.gameBlockUse,ratio(totals,"blocks_taken","block_opportunities")],
    [t.gameRuleUse,ratio(totals,"rule_followed","rule_opportunities")],
    [t.gameFirstEmpty,ratio(totals,"first_empty_choices","legal_moves")],
    ...([ [t.gameFormatErrors,"invalid_format"],[t.gameIllegalMoves,"illegal_moves"],
      [t.gameUnavoidableThreats,"unavoidable_threats"],[t.gameRepeatedErrors,"repeated_tactical_errors"] ] as const)
      .map(([label,key]):[string,string|number]=>[label,count(totals[key])??t.gameNotMeasured]),
  ];
  const games=Array.isArray(data.games)?data.games.map(record):[];
  const rules=record(data.rules),transfer=record(data.transfer);
  const failure=({format:t.gameFailureFormat,illegal_move:t.gameFailureIllegal,infrastructure:t.gameFailureInfrastructure,cancelled:t.gameFailureCancelled} as Record<string,string>)[String(data.failure_category)];
  return <>
    <p className="coop-message-meta">{t.gameMeasurementScope}</p>
    {failure&&<p role="status">{failure}</p>}
    <table className="coop-game-metrics" aria-label={t.gameStrategyMetrics}><tbody>{metrics.map(([label,value])=><tr key={label}><th scope="row">{label}</th><td>{value}</td></tr>)}</tbody></table>
    {games.length>0&&<details><summary>{t.gamePerGame}</summary>{games.map(row=><div key={String(row.number)}>
      <h3>{t.gameRound} {String(row.number)} · {row.status==="completed"?statusLabel(t,"completed"):row.status==="in_progress"?statusLabel(t,"running"):row.status==="incomplete"?t.gameIncomplete:statusLabel(t,String(row.status))}</h3>
      <table aria-label={`${t.gameRound} ${row.number}`}><tbody>
        {[[t.gameLegalUse,ratio(row,"legal_moves","proposals")],[t.gameOptimalUse,ratio(row,"optimal_moves","legal_moves")],
          [t.gameWinUse,ratio(row,"wins_taken","win_opportunities")],[t.gameBlockUse,ratio(row,"blocks_taken","block_opportunities")],
          [t.gameRuleUse,ratio(row,"rule_followed","rule_opportunities")],
          [t.gameRepeatedErrors,count(row.repeated_tactical_errors)??t.gameNotMeasured]].map(([label,value])=><tr key={String(label)}><th scope="row">{label}</th><td>{value}</td></tr>)}
      </tbody></table>
    </div>)}</details>}
    {Object.keys(rules).length>0&&<details><summary>{t.gameRuleComparison}</summary>{Object.entries(rules).map(([player,value])=><div key={player}>
      {Object.entries(record(value)).map(([rule,groups])=><table key={rule} aria-label={`${player} · ${rule}`}><caption>{player} · {rule}</caption><tbody>
        {[[t.gameWithoutReminder,record(record(groups).without_reminder)],[t.gameWithReminder,record(record(groups).with_reminder)]].map(([label,row])=><tr key={String(label)}><th scope="row">{String(label)}</th><td>{ratio(row as Record<string,Json>,"followed","opportunities")}</td></tr>)}
      </tbody></table>)}
    </div>)}</details>}
    {Object.entries(transfer).map(([player,value])=><table key={player} aria-label={`${player} · ${t.gameRuleUse}`}><caption>{player} · {t.gameRuleUse}</caption><tbody>
      {[[t.gameTransferEquivalent,"source_equivalent"],[t.gameTransferNew,"new_position"]].map(([label,key])=><tr key={key}><th scope="row">{label}</th><td>{ratio(record(record(value)[key]),"followed","opportunities")}</td></tr>)}
    </tbody></table>)}
  </>;
}
