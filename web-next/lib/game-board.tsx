import type { LabEvent, Json } from "./protocol";
import { texts, noteReasonLabel } from "./i18n";
import { GameMeasurements } from "./game-measurements";

export function GameBoard({event, ended, language}: {event?:LabEvent; ended:boolean; language:string}) {
  const t=texts(language);
  const candidate=event?.payload.board;
  if(event && (!Array.isArray(candidate)||candidate.length!==9||candidate.some(value=>value!==""&&value!=="X"&&value!=="O"))) {
    return <section className="coop-panel"><p>{t.gameStateUnknown}</p></section>;
  }
  const board=Array.isArray(candidate)?candidate:Array<string>(9).fill("");
  const state=event?.payload;
  const series=state?.series&&typeof state.series==="object"&&!Array.isArray(state.series)?state.series:null;
  const winner=state?.finished===true&&(state.winner==="A"||state.winner==="B")?state.winner:null;
  const draw=state?.finished===true&&state.draw===true;
  const next=state?.next_player==="B"?"B":"A";
  const status=winner?t.gameWinner+": "+winner+" ("+(winner==="A"?"X":"O")+")"
    :draw?t.gameDraw:ended?t.gameIncomplete:t.gameNext+": "+next+" ("+(next==="A"?"X":"O")+")";
  return <section className="coop-panel" aria-label={t.scenarioTicTacToe}>
    <h2>{t.scenarioTicTacToe} · A = X / B = O</h2>
    {series&&<p aria-live="polite">{t.gameRound} {String(series.number)} / {String(series.total)} · {t.gameMemory}: {series.remember_games===true?"ON":"OFF"}</p>}
    <table className="coop-game-board"><caption>{t.gameBoard}</caption>
      <thead><tr><th aria-label={t.gameBoard}/>{[1,2,3].map(column=><th key={column} scope="col">{column}</th>)}</tr></thead>
      <tbody>{["A","B","C"].map((row,index)=><tr key={row}><th scope="row">{row}</th>
        {[0,1,2].map(column=><td key={column} aria-label={row+(column+1)}>{String(board[index*3+column])||"·"}</td>)}
      </tr>)}</tbody>
    </table>
    <p className="coop-game-state" aria-live="polite">{status}</p>

  </section>;
}


type Labels = ReturnType<typeof texts>;
function eventText(value: Json | undefined, t: Labels): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : t.unknown;
}
function RawReflection({payload, t}: {payload: LabEvent["payload"]; t: Labels}) {
  return <details><summary>{t.gameNoteRaw}</summary><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{typeof payload.raw_content === "string" ? payload.raw_content : t.unknown}</pre></details>;
}
function ReflectionContent({payload, t}: {payload: LabEvent["payload"]; t: Labels}) {
  if (payload.skipped === true) return <output>{t.gameNoteSkipped}: {noteReasonLabel(t,payload.reason_code)}</output>;
  if (payload.accepted === false) return <>
    <output>{t.gameNoteRejected}: {noteReasonLabel(t,payload.reason_code)}</output>
    <RawReflection payload={payload} t={t}/>
  </>;
  const catalog = payload.note_source === "model_selected_host_catalog_rule";
  const selected = catalog ? t.gameRuleSelected : t.gameNoteAccepted;
  const validation = payload.validation ? t.gameNoteEvidence : t.gameNoteFormat;
  return <>
    <p style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{typeof payload.content === "string" ? payload.content : t.unknown}</p>
    {payload.accepted === true && <p className="coop-message-meta">{selected} · {validation}</p>}
    {catalog && payload.accepted === true && <><p className="coop-message-meta">{t.gameNoteCatalog}</p><RawReflection payload={payload} t={t}/></>}
  </>;
}
function ReflectionLessons({payload, t}: {payload: LabEvent["payload"]; t: Labels}) {
  const feedback = payload.feedback;
  const lessons = feedback && typeof feedback === "object" && !Array.isArray(feedback) && Array.isArray(feedback.lessons) ? feedback.lessons : [];
  const square = (action: Json | undefined) => action && typeof action === "object" && !Array.isArray(action) && typeof action.square === "string" ? action.square : "?";
  return lessons.map((lesson, index) => {
    if (!lesson || typeof lesson !== "object" || Array.isArray(lesson)) return null;
    return <p key={index} className="coop-message-meta">{t.gameModelProposal}: {square(lesson.model_action)} → {t.gameBetterMove}: {square(lesson.better_action)}</p>;
  });
}
export function GameReflections({events,language}:{events:LabEvent[];language:string}) {
  const t = texts(language);
  const notes = events.filter(event => event.kind === "reflection");
  if (!notes.length) return null;
  return <section className="coop-panel" aria-label={t.gameReflections}><h2>{t.gameReflections}</h2>
    {notes.map((event,index) => <details key={event.seq} open={index >= notes.length-2}>
      <summary>{t.gameRound} {eventText(event.payload.game_number,t)} · {eventText(event.payload.player,t)}</summary>
      <ReflectionContent payload={event.payload} t={t}/>
      <ReflectionLessons payload={event.payload} t={t}/>
    </details>)}
  </section>;
}


export function GameSeriesResults({event,events,language}:{event?:LabEvent;events:LabEvent[];language:string}) {
  const t=texts(language);
  const state=event?.payload;
  const series=state?.series&&typeof state.series==="object"&&!Array.isArray(state.series)?state.series:null;
  const candidates:Json[]=Array.isArray(series?.results)?series.results:state?.finished===true?[{number:1,winner:state.winner,draw:state.draw,moves:events.filter(e=>e.kind==="message"&&typeof e.payload.game_move==="string").map(e=>e.payload.game_move)}]:[];
  const results=candidates.filter((row):row is Record<string,import("./protocol").Json>=>!!row&&typeof row==="object"&&!Array.isArray(row)&&Number.isInteger(row.number)&&(row.winner==="A"||row.winner==="B"||row.draw===true));
  const strategy=state?.strategy&&typeof state.strategy==="object"&&!Array.isArray(state.strategy)?state.strategy:null;
  const metrics:[string,Json|undefined][]=strategy?[[t.gameModelMoves,strategy.model_moves],[t.gameWorseMoves,strategy.worse_moves],[t.gameMissedWins,strategy.missed_wins],[t.gameSolverIntervention,strategy.solver_interventions]]:[];
  if(strategy?.mode==="game_reflection")metrics.push([strategy.measurement?t.gameAcceptedNotes:t.gameHistoricalNotes,strategy.accepted_notes],[t.gameRejectedNotes,strategy.rejected_notes]);
  if(strategy?.mode==="game_reflection"&&typeof strategy.rule_opportunities==="number")metrics.push([t.gameRuleOpportunities,strategy.rule_opportunities],[t.gameRuleFollowed,strategy.rule_followed],[t.gameRuleIgnored,strategy.rule_ignored]);
  if(typeof strategy?.skipped_notes==="number")metrics.push([t.gameNoteSkipped,strategy.skipped_notes]);
  return <section className="coop-panel coop-game-results" aria-label={t.gameResults}>
    <h2>{t.gameResults}</h2>
    {!!metrics.length&&<table className="coop-game-metrics" aria-label={t.gameStrategyMetrics}><tbody>
      {metrics.map(([label,value])=><tr key={label}><th scope="row">{label}</th><td>{typeof value==="number"?value:t.gameNotMeasured}</td></tr>)}
    </tbody></table>}
    <GameMeasurements measurement={strategy?.measurement} language={language}/>
    {strategy?.result_scope==="assisted"&&<p className="coop-message-meta">{t.gameAssistedResult}</p>}
    {!results.length?<p className="coop-message-meta">{t.gameNoResults}</p>:<>
      <table className="coop-game-balance" aria-label={t.gameBalance}>
        <thead><tr><th scope="col">A (X)</th><th scope="col">B (O)</th><th scope="col">{t.gameDraw}</th></tr></thead>
        <tbody><tr><td>{results.filter(row=>row.winner==="A").length}</td><td>{results.filter(row=>row.winner==="B").length}</td><td>{results.filter(row=>row.draw===true).length}</td></tr></tbody>
      </table>
      <table className="coop-game-results-table" aria-label={t.gameResults}>
        <thead><tr><th scope="col">{t.gameRound}</th><th scope="col">{t.gameOutcome}</th><th scope="col">{t.gameMoveCount}</th></tr></thead>
        <tbody>{results.map(row=><tr key={String(row.number)}>
          <th scope="row">{String(row.number)}</th>
          <td>{row.draw===true?t.gameDraw:`${String(row.winner)} (${row.winner==="A"?"X":"O"})`}</td>
          <td>{Array.isArray(row.moves)?row.moves.length:"?"}</td>
        </tr>)}</tbody>
      </table>
    </>}
  </section>;
}


export function eventsForGame(events:LabEvent[],number:number):LabEvent[] {
  let current=1;
  return events.filter(event=>{
    const series=event.kind==="game"?event.payload.series:null;
    if(series&&typeof series==="object"&&!Array.isArray(series)&&typeof series.number==="number")current=series.number;
    return (typeof event.payload.game_number==="number"?event.payload.game_number:current)===number;
  });
}
