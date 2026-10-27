import React from 'react';
import {
	AbsoluteFill, Audio, Easing, Freeze, interpolate, OffthreadVideo, Sequence, spring, staticFile,
	useCurrentFrame, useVideoConfig,
} from 'remotion';
import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {loadFont as loadLuckiest} from '@remotion/google-fonts/LuckiestGuy';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import fallback from './edit.json';
import {getInputProps} from 'remotion';
// Each render passes its episode's timeline as input props, so episodes can render side by side.
const edit = ((getInputProps() as {edit?: typeof fallback}).edit ?? fallback);
import styles from './styles.json';

const anton = loadAnton().fontFamily;
const luckiest = loadLuckiest().fontFamily;
const inter = loadInter('normal', {weights: ['600', '800']}).fontFamily;

// Per-game look and music (hype / horror / chill), chosen in the EDL.
const STYLE = styles[edit.style as keyof typeof styles];
const ACCENT = STYLE.accent;
const HIGHLIGHT = STYLE.highlight;
const W = 1920, H = 1080;
// On-screen words in the channel's language (config.json via build_edit.py).
const TEXT = (edit as {text?: Record<string, string>}).text ?? {effect_label: '', next_episode: '', playlist: ''};
const cam = edit.cam as number[] | null; // null when the stream has no webcam (then there are no face zooms)
const FACE = cam ? {x: cam[0] + cam[2] / 2, y: cam[1] + cam[3] / 2} : {x: W / 2, y: H / 2};
const src = staticFile(edit.source);
const sfx = (name: string) => staticFile(`sfx/${name}.wav`);
const music = (name: string) => staticFile(`music/${name}.mp3`);
const FILL: React.CSSProperties = {width: '100%', height: '100%'};
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

type Clip = (typeof edit.clips)[number];
type Zoom = (typeof edit.faceZooms)[number];

// Envelope 0→1→0 for a timed effect: ease in, hold, ease out.
const envelope = (f: number, at: number, inF: number, hold: number, outF: number) =>
	interpolate(f, [at, at + inF, at + inF + hold, at + inF + hold + outF], [0, 1, 1, 0], {
		...clamp, easing: Easing.bezier(0.33, 1, 0.68, 1),
	});

const ClipView: React.FC<{clip: Clip}> = ({clip}) => {
	const f = useCurrentFrame();
	const t = clip.whoosh ? interpolate(f, [0, 14], [1, 0], {...clamp, easing: Easing.out(Easing.cubic)}) : 0;
	return (
		<AbsoluteFill style={{transform: `scale(${1 + 0.14 * t})`, filter: t > 0.01 ? `blur(${14 * t}px)` : undefined}}>
			<OffthreadVideo style={FILL}
				src={src}
				trimBefore={clip.src}
				volume={(vf) => interpolate(vf, [0, 3, clip.dur - 3, clip.dur], [0, 1, 1, 0], clamp)}
			/>
		</AbsoluteFill>
	);
};

// Punch-ins: face zooms push toward the webcam, game zooms push to centre. Translation is clamped so no black edges show.
const Zoomer: React.FC<{children: React.ReactNode}> = ({children}) => {
	const f = useCurrentFrame();
	// Zooms ease out before `end`, or drop instantly on the cut when `hard`.
	const zoom = (z: Zoom, inF: number, outF: number) =>
		envelope(f, z.at - inF, inF, Math.max(0, z.end - z.at - (z.hard ? 0 : outF)), z.hard ? 0.001 : outF) * (f < z.end ? 1 : 0);
	const face = Math.max(0, ...edit.faceZooms.map((z) => zoom(z, 7, 14)));
	const game = Math.max(0, ...edit.gameZooms.map((z) => zoom(z, 18, 24)));
	const s = 1 + 1.15 * face + 0.2 * game;
	const target = face > 0 ? FACE : {x: W / 2, y: H / 2};
	const shake = edit.faceZooms.some((z) => f >= z.at && f < z.at + 14) ? Math.sin(f * 2.7) * 9 * face : 0;
	const tx = Math.min(0, Math.max(W - W * s, W / 2 - s * target.x)) + shake;
	const ty = Math.min(0, Math.max(H - H * s, H / 2 - s * target.y)) + shake * 0.6;
	return <AbsoluteFill style={{transformOrigin: '0 0', transform: `translate(${tx}px, ${ty}px) scale(${s})`}}>{children}</AbsoluteFill>;
};

// Captions that overlap an earlier one take the next slot down, so they stack instead of colliding.
const Caption: React.FC<{text: string; i: number; slot: number}> = ({text, i, slot}) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const pop = spring({frame: f, fps, config: {damping: 11, stiffness: 220}});
	const out = interpolate(f, [120, 132], [1, 0], clamp);
	return (
		<AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 250 - 115 * slot, paddingRight: 380}}>
			<div style={{
				fontFamily: STYLE.captionFont === 'anton' ? anton : luckiest, fontSize: text.length > 24 ? 74 : 92, color: i % 3 === 1 ? 'white' : HIGHLIGHT,
				WebkitTextStroke: '14px black', paintOrder: 'stroke fill', textAlign: 'center', maxWidth: 1300, lineHeight: 1.05,
				letterSpacing: 1, textShadow: '0 8px 0 rgba(0,0,0,0.55)',
				transform: `scale(${(0.4 + 0.6 * pop) * out}) rotate(${i % 2 ? 2.5 : -2.5}deg)`, opacity: out,
			}}>{text}</div>
		</AbsoluteFill>
	);
};

const EffectBadge: React.FC<{name: string; fi: string}> = ({name, fi}) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const inn = spring({frame: f, fps, config: {damping: 14, stiffness: 160}});
	const out = interpolate(f, [190, 210], [0, 1], {...clamp, easing: Easing.in(Easing.cubic)});
	const y = -220 + 280 * inn - 280 * out;
	return (
		<AbsoluteFill style={{alignItems: 'center'}}>
			<div style={{
				marginTop: y, display: 'flex', alignItems: 'stretch', background: 'rgba(14,10,24,0.92)', borderRadius: 18,
				boxShadow: '0 18px 50px rgba(0,0,0,0.5)', overflow: 'hidden', border: `3px solid ${ACCENT}`,
			}}>
				<div style={{width: 18, background: `linear-gradient(${ACCENT}, ${STYLE.accent2})`}} />
				<div style={{padding: '14px 36px 18px 26px'}}>
					<div style={{fontFamily: inter, fontWeight: 800, fontSize: 22, letterSpacing: 6, color: HIGHLIGHT}}>{TEXT.effect_label}</div>
					<div style={{fontFamily: anton, fontSize: 64, color: 'white', lineHeight: 1.05, textTransform: 'uppercase'}}>{name}</div>
					<div style={{fontFamily: inter, fontWeight: 600, fontSize: 28, color: STYLE.soft}}>{fi}</div>
				</div>
			</div>
		</AbsoluteFill>
	);
};

const Title: React.FC = () => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const t = edit.title;
	const big = spring({frame: f, fps, config: {damping: 12, stiffness: 120}});
	const tag = spring({frame: f - 22, fps, config: {damping: 16}});
	const ep = spring({frame: f - 12, fps, config: {damping: 9, stiffness: 180}});
	const glitch = STYLE.glitch && f < 12 ? (f % 3) * 6 - 6 : 0;
	const fadeOut = interpolate(f, [t.dur - 10, t.dur], [1, 0], clamp);
	return (
		<AbsoluteFill style={{opacity: fadeOut, background: 'black'}}>
			<AbsoluteFill style={{filter: 'blur(16px) brightness(0.45) saturate(1.3)', transform: `scale(${1.1 + f * 0.0006})`}}>
				<Freeze frame={0}><OffthreadVideo style={FILL} src={src} trimBefore={t.bg} muted /></Freeze>
			</AbsoluteFill>
			<AbsoluteFill style={{background: `radial-gradient(circle at 50% 55%, ${ACCENT}55, transparent 60%)`}} />
			<AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', flexDirection: 'column'}}>
				<div style={{fontFamily: anton, fontSize: 90, color: 'white', letterSpacing: 24, opacity: big, transform: `translateY(${(1 - big) * -60}px)`}}>{t.kicker}</div>
				<div style={{
					fontFamily: anton, fontSize: 250, lineHeight: 1, color: HIGHLIGHT, transform: `scale(${0.6 + 0.4 * big})`,
					textShadow: `${glitch}px 0 0 #ff2bd6, ${-glitch}px 0 0 #00e5ff, 0 14px 0 rgba(0,0,0,0.6)`,
				}}>{t.title}</div>
				<div style={{
					marginTop: 18, fontFamily: anton, fontSize: 64, color: 'white', background: ACCENT, padding: '4px 38px', borderRadius: 12,
					transform: `scale(${ep}) rotate(${-4 * ep}deg)`,
				}}>{t.episode}</div>
				<div style={{marginTop: 28, fontFamily: inter, fontWeight: 600, fontSize: 38, color: '#eee', opacity: tag, transform: `translateY(${(1 - tag) * 30}px)`}}>{t.tagline}</div>
			</AbsoluteFill>
		</AbsoluteFill>
	);
};

const LowerThird: React.FC = () => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const l = edit.lowerThird;
	const wipe = spring({frame: f, fps, config: {damping: 18}});
	const out = interpolate(f, [l.dur - 18, l.dur], [0, 1], clamp);
	return (
		<AbsoluteFill style={{justifyContent: 'flex-end', paddingLeft: 70, paddingBottom: 300}}>
			<div style={{clipPath: `inset(0 ${100 * (1 - wipe + out)}% 0 0)`, display: 'flex', alignItems: 'center', gap: 22}}>
				<div style={{width: 10, height: 120, background: HIGHLIGHT}} />
				<div style={{background: 'rgba(14,10,24,0.88)', padding: '10px 30px 14px', borderLeft: `6px solid ${ACCENT}`}}>
					<div style={{fontFamily: anton, fontSize: 70, color: 'white', lineHeight: 1.05}}>{l.text}</div>
					<div style={{fontFamily: inter, fontWeight: 600, fontSize: 28, color: STYLE.soft}}>{l.sub}</div>
				</div>
			</div>
		</AbsoluteFill>
	);
};

const EndFreeze: React.FC = () => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const z = edit.freeze;
	const slam = spring({frame: f - 8, fps, config: {damping: 10, stiffness: 200}});
	return (
		<AbsoluteFill>
			<AbsoluteFill style={{transform: `scale(${1 + f * 0.0006})`, filter: `saturate(${interpolate(f, [0, 20], [1, 0.25], clamp)}) contrast(1.1)`}}>
				<Freeze frame={0}><OffthreadVideo style={FILL} src={src} trimBefore={z.src} muted /></Freeze>
			</AbsoluteFill>
			<AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'flex-start', padding: 90}}>
				<div style={{
					fontFamily: anton, fontSize: 150, color: HIGHLIGHT, WebkitTextStroke: '10px black', paintOrder: 'stroke fill',
					transform: `scale(${1.8 - 0.8 * slam})`, opacity: slam, transformOrigin: 'left bottom',
				}}>{z.text}</div>
			</AbsoluteFill>
		</AbsoluteFill>
	);
};

const EndScreen: React.FC = () => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const e = edit.end;
	const a = (d: number) => spring({frame: f - d, fps, config: {damping: 15}});
	const slot = (d: number): React.CSSProperties => ({
		width: 600, height: 338, borderRadius: 16, border: '4px dashed rgba(255,255,255,0.55)', background: 'rgba(0,0,0,0.35)',
		display: 'flex', alignItems: 'flex-end', padding: 22, fontFamily: inter, fontWeight: 800, fontSize: 30, color: 'white',
		letterSpacing: 4, opacity: a(d), transform: `translateY(${(1 - a(d)) * 60}px)`,
	});
	return (
		<AbsoluteFill style={{background: 'black', opacity: interpolate(f, [0, 12, e.dur - 20, e.dur], [0, 1, 1, 0], clamp)}}>
			<AbsoluteFill style={{filter: 'blur(22px) brightness(0.35)', transform: 'scale(1.15)'}}>
				<Freeze frame={0}><OffthreadVideo style={FILL} src={src} trimBefore={edit.freeze.src} muted /></Freeze>
			</AbsoluteFill>
			<AbsoluteFill style={{background: `linear-gradient(135deg, ${ACCENT}66, transparent 55%)`}} />
			<div style={{position: 'absolute', top: 60, left: 0, right: 0, textAlign: 'center', fontFamily: anton, fontSize: 110, color: HIGHLIGHT, opacity: a(0)}}>{e.title}</div>
			{/* Slots line up with YouTube end-screen elements in one row: video, subscribe, video. YouTube won't place elements
			    near the bottom edge and the subscribe element has a minimum size, so it gets a wide gap of its own. */}
			<div style={{position: 'absolute', left: 100, top: 300}}><div style={slot(6)}>{TEXT.next_episode}</div></div>
			<div style={{position: 'absolute', left: 1220, top: 300}}><div style={slot(12)}>{TEXT.playlist}</div></div>
			<div style={{position: 'absolute', left: 700, width: 520, top: 300, height: 338, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', gap: 30, opacity: a(18)}}>
				<div style={{width: 230, height: 230, borderRadius: '50%', border: `8px solid ${ACCENT}`, boxShadow: `0 0 50px ${ACCENT}`}} />
			</div>
			<div style={{position: 'absolute', left: 0, right: 0, top: 700, display: 'flex', justifyContent: 'center', opacity: a(18)}}>
				<div style={{fontFamily: anton, fontSize: 72, color: 'white', background: '#e62117', padding: '6px 40px', borderRadius: 12}}>{e.cta}</div>
			</div>
		</AbsoluteFill>
	);
};

export const LetsPlay: React.FC = () => {
	const {title, freeze, end, lowerThird} = edit;
	return (
		<AbsoluteFill style={{background: 'black'}}>
			<Zoomer>
				{edit.clips.map((c, i) => (
					<Sequence key={i} from={c.from} durationInFrames={c.dur} premountFor={90}>
						<ClipView clip={c} />
					</Sequence>
				))}
			</Zoomer>
			{edit.effects.map((e, i) => (
				<Sequence key={`fx${i}`} from={e.at} durationInFrames={212}><EffectBadge name={e.name} fi={e.fi} /></Sequence>
			))}
			{edit.captions.map((c, i) => (
				<Sequence key={`cap${i}`} from={c.at} durationInFrames={132}><Caption text={c.text} i={i} slot={c.slot ?? 0} /></Sequence>
			))}
			<Sequence from={lowerThird.from} durationInFrames={lowerThird.dur}><LowerThird /></Sequence>
			<Sequence from={title.from} durationInFrames={title.dur}><Title /></Sequence>
			<Sequence from={freeze.from} durationInFrames={freeze.dur}><EndFreeze /></Sequence>
			<Sequence from={end.from} durationInFrames={end.dur}><EndScreen /></Sequence>

			{/* Music: loud under the title, ducked under the intro talk, out before gameplay; elevator music on the end screen. */}
			<Sequence from={title.from} durationInFrames={edit.introEnd - title.from}>
				<Audio src={music(STYLE.intro)} loop volume={(f) => interpolate(f, [0, title.dur - 20, title.dur + 20, edit.introEnd - title.from - 60, edit.introEnd - title.from], [STYLE.introVolume, STYLE.introVolume, 0.09, 0.09, 0], clamp)} />
			</Sequence>
			<Sequence from={end.from} durationInFrames={end.dur}>
				<Audio src={music(STYLE.outro)} volume={(f) => interpolate(f, [0, 20, end.dur - 40, end.dur], [0, 0.4, 0.4, 0], clamp)} />
			</Sequence>

			{/* Sound design */}
			<Sequence from={title.from - 96}><Audio src={sfx('riser')} volume={0.3} /></Sequence>
			{STYLE.glitch && [0, 4, 9].map((d) => <Sequence key={`gl${d}`} from={title.from + d}><Audio src={sfx('glitch')} volume={0.5} /></Sequence>)}
			<Sequence from={title.from}><Audio src={sfx('hit')} volume={0.7} /></Sequence>
			<Sequence from={freeze.from + 8}><Audio src={sfx('hit')} volume={0.7} /></Sequence>
			{edit.clips.filter((c) => c.whoosh).map((c, i) => (
				<Sequence key={`wh${i}`} from={c.from - 20}><Audio src={sfx('whoosh')} volume={0.35} /></Sequence>
			))}
			{edit.faceZooms.map((z, i) => (
				<Sequence key={`bm${i}`} from={z.at - 4}><Audio src={sfx('hit')} volume={0.5} /></Sequence>
			))}
			{edit.effects.map((e, i) => (
				<Sequence key={`fxw${i}`} from={e.at}><Audio src={sfx('badge')} volume={0.35} /></Sequence>
			))}
			{edit.captions.map((c, i) => (
				<Sequence key={`pop${i}`} from={c.at}><Audio src={sfx('pop')} volume={0.3} /></Sequence>
			))}
		</AbsoluteFill>
	);
};
