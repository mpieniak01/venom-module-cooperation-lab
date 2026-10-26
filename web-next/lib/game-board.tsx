import type { LabEvent, Json } from "./protocol";
import { texts } from "./i18n";
import { Conversation } from "./chat";

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


export function GameReflections({events,language}:{events:LabEvent[];language:string}) {
  const t=texts(language);
  const notes=events.filter(event=>event.kind==="reflection");
  if(!notes.length)return null;
  return <section className="coop-panel" aria-label={t.gameReflections}><h2>{t.gameReflections}</h2>
    {notes.map((event,index)=>{
      const feedback=event.payload.feedback;
      const lessons=feedback&&typeof feedback==="object"&&!Array.isArray(feedback)&&Array.isArray(feedback.lessons)?feedback.lessons:[];
      return <details key={event.seq} open={index>=notes.length-2}>
        <summary>{t.gameRound} {String(event.payload.game_number)} · {String(event.payload.player)}</summary>
        <p style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{typeof event.payload.content==="string"?event.payload.content:t.unknown}</p>
        {lessons.map((lesson,i)=>{
          if(!lesson||typeof lesson!=="object"||Array.isArray(lesson))return null;
          const proposed=lesson.model_action;const better=lesson.better_action;
          const square=(action:typeof proposed)=>action&&typeof action==="object"&&!Array.isArray(action)&&typeof action.square==="string"?action.square:"?";
          return <p key={i} className="coop-message-meta">{t.gameModelProposal}: {square(proposed)} → {t.gameBetterMove}: {square(better)}</p>;
        })}
      </details>;
    })}
  </section>;
}


export function GameSeriesResults({event,events,language}:{event?:LabEvent;events:LabEvent[];language:string}) {
  const t=texts(language);
  const state=event?.payload;
  const series=state?.series&&typeof state.series==="object"&&!Array.isArray(state.series)?state.series:null;
  const candidates:Json[]=Array.isArray(series?.results)?series.results:state?.finished===true?[{number:1,winner:state.winner,draw:state.draw,moves:events.filter(e=>e.kind==="message"&&typeof e.payload.game_move==="string").map(e=>e.payload.game_move)}]:[];
  const results=candidates.filter((row):row is Record<string,import("./protocol").Json>=>!!row&&typeof row==="object"&&!Array.isArray(row)&&Number.isInteger(row.number)&&(row.winner==="A"||row.winner==="B"||row.draw===true));
  return <section className="coop-panel coop-game-results" aria-label={t.gameResults}>
    <h2>{t.gameResults}</h2>
    {state?.strategy&&typeof state.strategy==="object"&&!Array.isArray(state.strategy)&&<div aria-live="polite">
      <p>{t.gameModelMoves}: {String(state.strategy.model_moves??0)} · {t.gameWorseMoves}: {String(state.strategy.worse_moves??0)} · {t.gameMissedWins}: {String(state.strategy.missed_wins??0)} · {t.gameSolverIntervention}: {String(state.strategy.solver_interventions??0)}</p>
      {state.strategy.result_scope==="assisted"&&<p>{t.gameAssistedResult}</p>}
    </div>}

    {!results.length?<p className="coop-message-meta">{t.gameNoResults}</p>:<>
      <p>A: {results.filter(row=>row.winner==="A").length} · B: {results.filter(row=>row.winner==="B").length} · {t.gameDraw}: {results.filter(row=>row.draw===true).length}</p>
      {results.map(row=>{
        const archived=eventsForGame(events,Number(row.number));
        return <details key={String(row.number)} open={state?.finished===true&&(series?.number??1)===row.number}>
          <summary>{t.gameRound} {String(row.number)}: {row.draw===true?t.gameDraw:t.gameWinner+": "+String(row.winner)} · {t.gameMoves}: {Array.isArray(row.moves)?row.moves.length:"?"}</summary>
          <Conversation events={archived.filter(e=>e.kind==="message")} language={language}/>
          <GameReflections events={archived} language={language}/>
        </details>;
      })}
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
