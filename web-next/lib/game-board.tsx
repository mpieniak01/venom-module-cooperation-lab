import type { LabEvent } from "./protocol";
import { texts } from "./i18n";

export function GameBoard({event, ended, language}: {event?:LabEvent; ended:boolean; language:string}) {
  const t=texts(language);
  const candidate=event?.payload.board;
  if(event && (!Array.isArray(candidate)||candidate.length!==9||candidate.some(value=>value!==""&&value!=="X"&&value!=="O"))) {
    return <section className="coop-panel"><p>{t.gameStateUnknown}</p></section>;
  }
  const board=Array.isArray(candidate)?candidate:Array<string>(9).fill("");
  const state=event?.payload;
  const winner=state?.finished===true&&(state.winner==="A"||state.winner==="B")?state.winner:null;
  const draw=state?.finished===true&&state.draw===true;
  const next=state?.next_player==="B"?"B":"A";
  const status=winner?t.gameWinner+": "+winner+" ("+(winner==="A"?"X":"O")+")"
    :draw?t.gameDraw:ended?t.gameIncomplete:t.gameNext+": "+next+" ("+(next==="A"?"X":"O")+")";
  return <section className="coop-panel" aria-label={t.scenarioTicTacToe}>
    <h2>{t.scenarioTicTacToe} · A = X / B = O</h2>
    <table className="coop-game-board"><caption>{t.gameBoard}</caption>
      <thead><tr><th aria-label={t.gameBoard}/>{[1,2,3].map(column=><th key={column} scope="col">{column}</th>)}</tr></thead>
      <tbody>{["A","B","C"].map((row,index)=><tr key={row}><th scope="row">{row}</th>
        {[0,1,2].map(column=><td key={column} aria-label={row+(column+1)}>{String(board[index*3+column])||"·"}</td>)}
      </tr>)}</tbody>
    </table>
    <p className="coop-game-state" aria-live="polite">{status}</p>
  </section>;
}
