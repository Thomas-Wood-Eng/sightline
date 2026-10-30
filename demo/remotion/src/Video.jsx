// The Sightline demo, laid out by Remotion from the recorder's timeline (demo/make_demo.py, DEMO_BARE=1):
// the app recording sits in a window frame, chapters sit above it, captions below, and titles, the PayPal
// link card and PayPal's own record are drawn here instead of over the app.
import {
  AbsoluteFill, Audio, Img, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from 'remotion';
import timeline from './timeline.json';

export const FPS = 30;
const C = { navy: '#0b1f3a', deep: '#06101f', amber: '#ffb800', teal: '#14a39a', ink: '#e8eefc', dim: '#9fb0cc' };
const FONT = '"Segoe UI", system-ui, sans-serif';
const MONO = 'Consolas, ui-monospace, monospace';
// the app recording is 1920x940; framed at 1560 wide it leaves a band above for chapters and below for captions
const FRAME = { x: 180, y: 92, w: 1560, h: Math.round(1560 * 940 / 1920) };

const segs = timeline.segments.map((s) => ({ ...s, frames: Math.max(1, Math.round(s.dur * FPS)) }));
let at = 0;
for (const s of segs) { s.from = at; at += s.frames; }
export const totalFrames = at;

const markAt = (i, kind) => timeline.marks.find((m) => m.at === i && m.kind === kind);
const chapterFor = (i) => {   // the chapter in force at segment i, and the segment it started at
  let ch = null;
  for (const m of timeline.marks) {
    if (m.at > i) break;
    if (m.kind === 'chapter') ch = m;
    if (m.kind === 'title') ch = null;
  }
  return ch;
};

const fade = (frame, frames, edge = 8) =>
  interpolate(frame, [0, edge, frames - edge, frames], [0, 1, 1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
const rise = (frame, fps, delay = 0) => spring({ frame: frame - delay, fps, config: { damping: 200 } });

const Logo = ({ size = 64 }) => (
  <svg width={size} height={size * 0.75} viewBox="0 0 48 36" aria-hidden>
    <path d="M8 30a16 16 0 0 1 32 0" fill="none" stroke="#fff" strokeWidth="4" strokeLinecap="round" />
    <path d="M2 30h44" stroke={C.amber} strokeWidth="4" strokeLinecap="round" />
  </svg>
);

// ---- captions: short chunks, speaker first ----
function chunks(caption, frames) {
  let speaker = null, text = caption || '';
  const m = text.match(/^(You|Sightline): (.*)$/s);
  if (m) { speaker = m[1]; text = m[2]; }
  const words = text.split(/\s+/).filter(Boolean);
  const parts = [];
  for (let k = 0; k < words.length; k += 9) parts.push(words.slice(k, k + 9).join(' '));
  const total = parts.reduce((n, p) => n + p.length, 0) || 1;
  let t = 0;
  return { speaker, parts: parts.map((p) => { const from = Math.round(t); t += frames * p.length / total; return { p, from, to: Math.round(t) }; }) };
}

const Caption = ({ caption, frames }) => {
  const frame = useCurrentFrame();
  const { speaker, parts } = chunks(caption, frames);
  const cur = parts.find((c) => frame >= c.from && frame < c.to) || parts[parts.length - 1];
  if (!cur) return null;
  const o = interpolate(frame - cur.from, [0, 5], [0, 1], { extrapolateRight: 'clamp' });
  const chip = speaker === 'You' ? C.teal : speaker === 'Sightline' ? C.amber : null;
  return (
    <div style={{ position: 'absolute', left: FRAME.x, width: FRAME.w, top: FRAME.y + FRAME.h + 22, height: 170,
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center', gap: 22, fontFamily: FONT }}>
      {chip && (
        <div style={{ background: chip, color: speaker === 'You' ? '#fff' : C.deep, font: `700 30px ${FONT}`,
          padding: '8px 18px', borderRadius: 12, whiteSpace: 'nowrap', marginTop: 4 }}>{speaker}</div>
      )}
      <div style={{ opacity: o, color: '#fff', font: `${chip ? 500 : 400} 44px/1.25 ${FONT}`, maxWidth: 1250,
        fontStyle: chip ? 'normal' : 'italic', textAlign: chip ? 'left' : 'center' }}>{cur.p}</div>
    </div>
  );
};

const Chapter = ({ text, since }) => {
  const frame = useCurrentFrame() + since;   // frames since the chapter began, so it animates in once
  const { fps } = useVideoConfig();
  if (!text) return null;
  const m = text.match(/^(\d+)\.\s*(.*)$/);
  const s = rise(frame, fps);
  return (
    <div style={{ position: 'absolute', left: FRAME.x, top: 22, display: 'flex', alignItems: 'center', gap: 16,
      opacity: s, transform: `translateY(${(1 - s) * -12}px)`, fontFamily: FONT }}>
      {m && <div style={{ width: 48, height: 48, borderRadius: 24, background: C.amber, color: C.deep, display: 'grid',
        placeItems: 'center', font: `800 28px ${FONT}` }}>{m[1]}</div>}
      <div style={{ color: '#fff', font: `700 34px ${FONT}` }}>{m ? m[2] : text}</div>
    </div>
  );
};

// ---- scenes ----
const AppScene = ({ seg }) => (
  <>
    <div style={{ position: 'absolute', left: FRAME.x - 6, top: FRAME.y - 6, width: FRAME.w + 12, height: FRAME.h + 12,
      borderRadius: 20, background: '#1d3456', boxShadow: '0 24px 70px rgba(0,0,0,.45)' }} />
    <div style={{ position: 'absolute', left: FRAME.x, top: FRAME.y, width: FRAME.w, height: FRAME.h, borderRadius: 14,
      overflow: 'hidden', background: '#fff' }}>
      <OffthreadVideo src={staticFile(seg.clip)} muted style={{ width: '100%', height: '100%' }} />
    </div>
  </>
);

const OpenScene = ({ seg }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const half = Math.round(seg.frames * 0.5);
  const heard = ['button', 'button', 'link, image', 'frame', 'unlabelled graphic'];
  const a = interpolate(frame, [half - 8, half + 4], [1, 0], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  const b = rise(frame, fps, half);
  return (
    <AbsoluteFill style={{ background: `radial-gradient(1200px 700px at 50% 40%, #16335e, ${C.navy})`, fontFamily: FONT }}>
      <AbsoluteFill style={{ opacity: a, alignItems: 'center', justifyContent: 'center', gap: 34, paddingBottom: 140 }}>
        <div style={{ color: C.ink, font: `600 50px ${FONT}` }}>At checkout, a screen reader often hears:</div>
        <div style={{ display: 'flex', gap: 18 }}>
          {heard.map((h, k) => {
            const s = rise(frame, fps, 6 + k * 6);
            return <div key={k} style={{ opacity: s, transform: `translateY(${(1 - s) * 16}px)`, font: `600 48px ${MONO}`,
              color: '#ffd9d0', border: '3px solid #ff8a70', borderRadius: 14, padding: '14px 26px' }}>{h}</div>;
          })}
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{ opacity: b, transform: `scale(${0.96 + 0.04 * b})`, alignItems: 'center',
        justifyContent: 'center', gap: 18, paddingBottom: 140 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 22 }}>
          <Logo size={130} /><div style={{ color: '#fff', font: `800 140px ${FONT}` }}>Sightline</div>
        </div>
        <div style={{ color: C.ink, font: `500 50px ${FONT}` }}>Checkout as a conversation. Every dollar from PayPal, heard first.</div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const OutroScene = ({ title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [l1, l2] = title.split(/(?<=\.)\s+/);
  const s1 = rise(frame, fps, 2), s2 = rise(frame, fps, 14), s3 = rise(frame, fps, 30);
  return (
    <AbsoluteFill style={{ background: `radial-gradient(1200px 700px at 50% 40%, #16335e, ${C.navy})`, fontFamily: FONT,
      alignItems: 'center', justifyContent: 'center', gap: 10, paddingBottom: 150 }}>
      <div style={{ opacity: s1, transform: `translateY(${(1 - s1) * 20}px)`, color: '#fff', font: `800 88px ${FONT}` }}>{l1}</div>
      <div style={{ opacity: s2, transform: `translateY(${(1 - s2) * 20}px)`, color: C.amber, font: `800 88px ${FONT}` }}>{l2}</div>
      <div style={{ opacity: s3, marginTop: 40, display: 'flex', alignItems: 'center', gap: 16, color: C.ink, font: `500 36px ${FONT}` }}>
        <Logo size={48} /> github.com/Thomas-Wood-Eng/sightline
      </div>
      <div style={{ opacity: s3, color: C.dim, font: `400 26px ${FONT}` }}>
        PayPal Vault and Orders v2 in the sandbox · Photos: Wikimedia Commons
      </div>
    </AbsoluteFill>
  );
};

const CardScene = ({ mark, seg }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = rise(frame, fps);
  const zoom = interpolate(frame, [0, seg.frames], [1, 1.06]);
  return (
    <AbsoluteFill style={{ background: C.navy, fontFamily: FONT, flexDirection: 'row', alignItems: 'center',
      justifyContent: 'center', gap: 70, paddingBottom: 150 }}>
      <div style={{ maxWidth: 620, opacity: s, transform: `translateX(${(1 - s) * -30}px)` }}>
        <div style={{ color: '#fff', font: `800 60px/1.15 ${FONT}` }}>{mark.title}</div>
        {mark.items.map((x, k) => <div key={k} style={{ color: C.dim, font: `500 30px ${FONT}`, marginTop: 22 }}>{x}</div>)}
      </div>
      {mark.img && (
        <div style={{ width: 820, height: 640, borderRadius: 20, overflow: 'hidden', boxShadow: '0 20px 60px rgba(0,0,0,.5)', opacity: s }}>
          <Img src={staticFile(`assets/${mark.img}`)} style={{ width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${zoom})` }} />
        </div>
      )}
    </AbsoluteFill>
  );
};

const ProofScene = ({ mark }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const words = { CAPTURED: 'charged', VOIDED: 'hold released, nothing charged' };
  return (
    <AbsoluteFill style={{ background: C.navy, fontFamily: FONT, padding: '70px 110px 0' }}>
      <div style={{ color: '#fff', font: `800 54px ${FONT}` }}>PayPal’s own record of every order</div>
      <div style={{ color: C.dim, font: `400 28px ${FONT}`, marginTop: 8 }}>
        GET /v2/checkout/orders/&#123;id&#125; on the PayPal sandbox, queried when the recording ended
      </div>
      <div style={{ display: 'flex', gap: 32, marginTop: 44 }}>
        {mark.orders.map((o, k) => {
          const s = rise(frame, fps, 6 + k * 8);
          const paid = o.status === 'CAPTURED';
          return (
            <div key={k} style={{ flex: 1, opacity: s, transform: `translateY(${(1 - s) * 30}px)`, background: C.deep,
              borderRadius: 18, padding: '26px 30px', borderTop: `10px solid ${paid ? C.teal : C.amber}` }}>
              <div style={{ color: C.ink, font: `700 32px ${FONT}` }}>{o.label}</div>
              <div style={{ color: paid ? '#5fe0d6' : C.amber, font: `900 58px ${FONT}`, marginTop: 14 }}>{o.status}</div>
              <div style={{ color: C.ink, font: `500 28px ${FONT}` }}>{words[o.status] || ''}</div>
              <div style={{ color: '#fff', font: `800 52px ${FONT}`, marginTop: 18 }}>${o.amount} <span style={{ font: `500 28px ${FONT}`, color: C.dim }}>{o.currency}</span></div>
              <div style={{ color: C.dim, font: `500 22px/1.6 ${MONO}`, marginTop: 18 }}>
                order {o.order}<br />intent {o.intent}, status {o.order_status}<br />authorization {o.auth}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const Segment = ({ seg, i }) => {
  const title = markAt(i, 'title');
  const card = markAt(i, 'card');
  const proof = markAt(i, 'proof');
  const frame = useCurrentFrame();
  const full = title || card || proof;
  let scene;
  if (title) scene = title.last ? <OutroScene title={title.title} /> : <OpenScene seg={seg} />;
  else if (card) scene = <CardScene mark={card} seg={seg} />;
  else if (proof) scene = <ProofScene mark={proof} />;
  else scene = <AppScene seg={seg} />;
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ opacity: full ? fade(frame, seg.frames, 6) : 1 }}>{scene}</AbsoluteFill>
      {!full && chapterFor(i) && <Chapter text={chapterFor(i).text} since={seg.from - segs[chapterFor(i).at].from} />}
      <Caption caption={seg.caption} frames={seg.frames} />
      {seg.voice && <Audio src={staticFile(seg.voice)} />}
    </AbsoluteFill>
  );
};

export const Video = () => (
  <AbsoluteFill style={{ background: C.navy }}>
    {segs.map((seg, i) => (
      <Sequence key={i} from={seg.from} durationInFrames={seg.frames}>
        <Segment seg={seg} i={i} />
      </Sequence>
    ))}
  </AbsoluteFill>
);
