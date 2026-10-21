import type { LabEvent } from "./protocol";
import { messageKindLabel, texts } from "./i18n";

function text(event: LabEvent, key: string) {
  const value = event.payload[key];
  return typeof value === "string" ? value : "";
}
export function recordedTime(timestamp: number, language: string) {
  const date = new Date(timestamp * 1000);
  if (!Number.isFinite(date.getTime())) return null;
  const locale = language === "pl" ? "pl-PL" : language === "de" ? "de-DE" : "en-GB";
  return { iso:date.toISOString(), display:new Intl.DateTimeFormat(locale, {
    year:"numeric", month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit", second:"2-digit",
    fractionalSecondDigits:3, hour12:false, timeZoneName:"short",
  }).format(date) };
}
export function Conversation({ events, language }: { events:LabEvent[]; language:string }) {
  const t = texts(language);
  const byId = new Map(events.map((event) => [text(event, "message_id"), event]));
  return <ol className="coop-messages">
    {events.map((event) => {
      const sender = text(event, "sender");
      const recipient = text(event, "recipient");
      const kind = text(event, "kind");
      const time = recordedTime(event.timestamp, language);
      const replyId = text(event, "in_reply_to");
      const reply = replyId ? byId.get(replyId) : undefined;
      const recipients = event.payload.delivered_to;
      const delivered = Array.isArray(recipients) && recipients.every(value => value === "A" || value === "B") ? recipients : null;
      const delivery = delivered === null ? t.deliveryUnknown
        : delivered.length ? t.delivered + " " + delivered.join(", ") : t.notDelivered;
      return <li key={event.seq} id={"coop-message-" + event.seq} className="coop-message" data-sender={sender === "A" || sender === "B" ? sender : "unknown"}>
        <div className="coop-message-header">
          <strong className="coop-message-route">{sender || "?"} → {recipient === "all" ? t.everyone : recipient || "?"}</strong>
          <span>#{event.seq} · {messageKindLabel(t, kind)}</span>
          {time ? <time dateTime={time.iso} title={t.recordedAt + ": " + time.iso}>{time.display}</time> : <span>{t.unknownTime}</span>}
        </div>
        <p className="coop-message-content">{text(event, "content")}</p>
        <p className="coop-message-meta">{delivery}</p>
        {replyId && (reply
          ? <a className="coop-reply" href={"#coop-message-" + reply.seq}>↳ {t.replyTo} #{reply.seq} · {text(reply, "sender")}</a>
          : <span className="coop-reply">↳ {t.replyOutside}</span>)}
        {kind === "complete" && <p className="coop-message-meta">{t.claimedComplete}</p>}
      </li>;
    })}
  </ol>;
}
