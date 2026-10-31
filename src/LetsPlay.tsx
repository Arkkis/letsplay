import React from 'react';
import {
	AbsoluteFill, Audio, Easing, Freeze, Img, interpolate, OffthreadVideo, Sequence, spring, staticFile,
	useCurrentFrame, useVideoConfig,
} from 'remotion';
import fallback from './edit.json';
import {getInputProps} from 'remotion';
// Each render passes its episode's timeline as input props, so episodes can render side by side.
const edit = ((getInputProps() as {edit?: typeof fallback}).edit ?? fallback);
import styles from './styles.json';
import {KineticWords} from './Kinetic';
import {CYAN, lineStyle, Stack, TILT, WHITE} from './look';

// Per-game look and music (hype / horror / chill), chosen in the EDL.
const STYLE = styles[edit.style as keyof typeof styles];
const HEAD = STYLE.headline;
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
const rate = (c: Clip) => (c as {rate?: number}).rate ?? 1; // fast-forward (>1) or slow motion (<1)

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
				playbackRate={rate(clip)}
				volume={(vf) => interpolate(vf, [0, 3, clip.dur - 3, clip.dur], [0, 1, 1, 0], clamp) * (rate(clip) > 1 ? 0.3 : 1)}
			/>
		</AbsoluteFill>
	);
};

// Punch-ins: face zooms push toward the webcam, game zooms push to centre, audio punches (loud rises) kick briefly with a
// flash and, in glitch styles, an RGB split. Translation is clamped so no black edges show.
const Zoomer: React.FC<{children: React.ReactNode}> = ({children}) => {
	const f = useCurrentFrame();
	// Zooms ease out before `end`, or drop instantly on the cut when `hard`.
	const zoom = (z: Zoom, inF: number, outF: number) =>
		envelope(f, z.at - inF, inF, Math.max(0, z.end - z.at - (z.hard ? 0 : outF)), z.hard ? 0.001 : outF) * (f < z.end ? 1 : 0);
	const face = Math.max(0, ...edit.faceZooms.map((z) => zoom(z, 7, 14)));
	const game = Math.max(0, ...edit.gameZooms.map((z) => zoom(z, 18, 24)));
	const punch = Math.max(0, ...(edit.punches ?? []).map((p) => (f < p.at - 2 || f > p.at + 20 ? 0 : f < p.at ? (f - p.at + 2) / 2 : Math.exp(-(f - p.at) / 5))));
	const s = (1 + 1.15 * face + 0.2 * game) * (1 + 0.08 * punch);
	const target = face > 0 ? FACE : {x: W / 2, y: H / 2};
	const shake = (edit.faceZooms.some((z) => f >= z.at && f < z.at + 14) ? Math.sin(f * 2.7) * 9 * face : 0) + Math.sin(f * 3.3) * 10 * punch;
	const tx = Math.min(0, Math.max(W - W * s, W / 2 - s * target.x)) + shake;
	const ty = Math.min(0, Math.max(H - H * s, H / 2 - s * target.y)) + shake * 0.6;
	const split = STYLE.glitch && punch > 0.05;
	return (
		<AbsoluteFill style={{transformOrigin: '0 0', transform: `translate(${tx}px, ${ty}px) scale(${s})`,
			filter: punch > 0.05 ? `brightness(${1 + 0.2 * punch})${split ? ' url(#rgb)' : ''}` : undefined}}>
			{split && (
				<svg width={0} height={0} style={{position: 'absolute'}}>
					<filter id="rgb" colorInterpolationFilters="sRGB">
						<feColorMatrix in="SourceGraphic" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" />
						<feOffset dx={14 * punch} result="r" />
						<feColorMatrix in="SourceGraphic" values="0 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0" />
						<feOffset dx={-14 * punch} result="gb" />
						<feBlend in="r" in2="gb" mode="screen" />
					</filter>
				</svg>
			)}
			{children}
		</AbsoluteFill>
	);
};

// Captions that overlap an earlier one take the next slot down, so they stack instead of colliding.
const Caption: React.FC<{text: string; words?: number[]; dur: number; i: number; slot: number}> = ({text, words, dur, i, slot}) => {
	const f = useCurrentFrame();
	const out = interpolate(f, [dur - 12, dur], [1, 0], clamp);
	const size = text.length > 24 ? 76 : 92;
	return (
		<AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: 250 - 115 * slot, paddingRight: 380}}>
			<div style={{
				...lineStyle({text, color: WHITE, size}), whiteSpace: 'normal', textAlign: 'center', maxWidth: 1300, lineHeight: 1.05,
				transform: `scale(${out}) rotate(${i % 2 ? 2 : -3}deg)`, opacity: out,
			}}><KineticWords text={text} words={words} color={HEAD} /></div>
		</AbsoluteFill>
	);
};

// Banner for a game event (Chaos Mod effect, or a hand-placed one such as a randomizer outcome): label, name, description.
const EffectBadge: React.FC<{name: string; fi: string}> = ({name, fi}) => (
	<AbsoluteFill style={{alignItems: 'center', paddingTop: 70}}>
		<Stack dur={210} style={{position: 'relative'}} lines={[
			...(TEXT.effect_label ? [{text: TEXT.effect_label, color: CYAN, size: 34}] : []),
			{text: name, color: HEAD, size: 88}, ...(fi ? [{text: fi, color: WHITE, size: 38, light: true}] : []),
		]} />
	</AbsoluteFill>
);

// Fast-forward / slow-motion marker, top right, for the length of the clip.
const SpeedBadge: React.FC<{rate: number; dur: number}> = ({rate, dur}) => (
	<Stack dur={dur} align="right" style={{top: 60, right: 80}} lines={[{text: `×${rate} ${rate > 1 ? '▶▶' : '▶'}`, color: HEAD, size: 110}]} />
);

const Title: React.FC = () => {
	const f = useCurrentFrame();
	const t = edit.title;
	const face = (edit as {faceCut?: string}).faceCut;
	const fadeOut = interpolate(f, [t.dur - 10, t.dur], [1, 0], clamp);
	return (
		<AbsoluteFill style={{opacity: fadeOut, background: 'black'}}>
			<AbsoluteFill style={{filter: 'blur(16px) brightness(0.55) saturate(1.3)', transform: `scale(${1.1 + f * 0.0006})`}}>
				<Freeze frame={0}><OffthreadVideo style={FILL} src={src} trimBefore={t.bg} muted /></Freeze>
			</AbsoluteFill>
			{face && <Img src={staticFile(face)} style={{position: 'absolute', right: 30, bottom: 0, height: 700,
				filter: 'brightness(1.1) contrast(1.08) drop-shadow(0 0 24px rgba(0,0,0,0.7))',
				transform: `translateY(${interpolate(f, [0, 14], [80, 0], {...clamp, easing: Easing.out(Easing.cubic)})}px)`}} />}
			<Stack style={{left: 130, top: 250}} lines={[
				{text: t.kicker, color: CYAN, size: 96}, {text: t.title, color: HEAD, size: face ? 230 : 270},
				{text: t.episode, color: WHITE, size: 130}, {text: t.tagline, color: WHITE, size: 52, light: true},
			]} />
		</AbsoluteFill>
	);
};

// Name tag above a webcam. `side: "right"` puts it over a bottom-right webcam; a co-op `guest` gets one on the other side.
type Tag = {text: string; sub: string};
const NameTag: React.FC<{tag: Tag; right: boolean; delay: number; dur: number}> = ({tag, right, delay, dur}) => (
	<Sequence from={delay} durationInFrames={dur - delay} layout="none">
		<Stack dur={dur - delay} align={right ? 'right' : 'left'} style={{bottom: 330, [right ? 'right' : 'left']: 80}}
			lines={[{text: tag.text, color: HEAD, size: 110}, {text: tag.sub, color: CYAN, size: 40}]} />
	</Sequence>
);

const LowerThird: React.FC = () => {
	const l = edit.lowerThird as Tag & {dur: number; side?: string; guest?: Tag};
	const right = l.side === 'right';
	return (
		<>
			<NameTag tag={l} right={right} delay={0} dur={l.dur} />
			{l.guest && <NameTag tag={l.guest} right={!right} delay={12} dur={l.dur} />}
		</>
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
			<div style={{position: 'absolute', left: 90, top: 470, opacity: slam, transform: `scale(${1.8 - 0.8 * slam})`, transformOrigin: 'left top'}}>
				<Stack still style={{position: 'relative'}} lines={[{text: z.text, color: HEAD, size: 210}]} />
			</div>
		</AbsoluteFill>
	);
};

const EndScreen: React.FC = () => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const e = edit.end;
	const a = (d: number) => spring({frame: f - d, fps, config: {damping: 15}});
	const slot = (d: number): React.CSSProperties => ({
		width: 600, height: 338, borderRadius: 16, border: '4px dashed rgba(255,255,255,0.6)', background: 'rgba(0,0,0,0.3)',
		display: 'flex', alignItems: 'flex-end', padding: 22, opacity: a(d), transform: `translateY(${(1 - a(d)) * 60}px)`,
	});
	return (
		<AbsoluteFill style={{background: 'black', opacity: interpolate(f, [0, 12, e.dur - 20, e.dur], [0, 1, 1, 0], clamp)}}>
			<AbsoluteFill style={{filter: 'blur(22px) brightness(0.4)', transform: 'scale(1.15)'}}>
				<Freeze frame={0}><OffthreadVideo style={FILL} src={src} trimBefore={edit.freeze.src} muted /></Freeze>
			</AbsoluteFill>
			<div style={{position: 'absolute', top: 50, left: 0, right: 0, display: 'flex', justifyContent: 'center'}}>
				<Stack align="center" style={{position: 'relative'}} lines={[{text: e.title, color: HEAD, size: 130}]} />
			</div>
			{/* Slots line up with YouTube end-screen elements in one row: video, subscribe, video. YouTube won't place elements
			    near the bottom edge and the subscribe element has a minimum size, so it gets a wide gap of its own. */}
			<div style={{position: 'absolute', left: 100, top: 300}}><div style={slot(6)}><span style={lineStyle({text: '', color: WHITE, size: 40})}>{TEXT.next_episode}</span></div></div>
			<div style={{position: 'absolute', left: 1220, top: 300}}><div style={slot(12)}><span style={lineStyle({text: '', color: WHITE, size: 40})}>{TEXT.playlist}</span></div></div>
			<div style={{position: 'absolute', left: 700, width: 520, top: 300, height: 338, display: 'flex', justifyContent: 'center', alignItems: 'center', opacity: a(18)}}>
				<div style={{width: 230, height: 230, borderRadius: '50%', border: `8px solid ${CYAN}`}} />
			</div>
			<div style={{position: 'absolute', left: 0, right: 0, top: 690, display: 'flex', justifyContent: 'center', opacity: a(18)}}>
				<div style={{...lineStyle({text: e.cta, color: CYAN, size: 96}), transform: `rotate(${TILT}deg)`}}>{e.cta}</div>
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
				<Sequence key={`cap${i}`} from={c.at} durationInFrames={c.dur ?? 132}><Caption text={c.text} words={c.words} dur={c.dur ?? 132} i={i} slot={c.slot ?? 0} /></Sequence>
			))}
			{edit.clips.filter((c) => rate(c) !== 1).map((c, i) => (
				<Sequence key={`sp${i}`} from={c.from} durationInFrames={c.dur}><SpeedBadge rate={rate(c)} dur={c.dur} /></Sequence>
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
		</AbsoluteFill>
	);
};
