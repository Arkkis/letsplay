import React from 'react';
import {
	AbsoluteFill, Audio, Freeze, getInputProps, interpolate, OffthreadVideo, Sequence, spring, staticFile,
	useCurrentFrame, useVideoConfig,
} from 'remotion';
import styles from './styles.json';
import {KineticWords} from './Kinetic';
import {CYAN, lineStyle, Stack, WHITE} from './look';
import {Guest, GuestView, povAt, povGain, povOverlaps, sourceAt, Track, TrackView} from './Pov';

// A vertical Short cut from an episode's prepared source. Laid out at 1080x1920 and rendered at 2/3 scale (720x1280),
// where the 1920x1080-unit source frame shows at its native 1280x720: the game window and webcam are never upscaled.
// One or two clips (an internal cut); every spoken word captioned, the episode's own captions shown big.
export type ShortProps = {
	source: string; fps: number; style: string; clips: {src: number; dur: number; from: number}[]; dur: number; hold?: number; cropX: number;
	cam: number[] | null; title: string; tag: string; cta: string;
	captions: {at: number; text: string; words?: number[]; dur?: number; big?: boolean}[]; effects: {at: number; name: string; fi: string}[];
	text: {channel: string; from_stream: string; effect_label: string; partner?: {text: string; sub?: string}}; guest?: Guest; // co-op: the partner's view in "pov" spans
	tracks?: Track[] | null; // separate recordings: webcams as their own files (your webcam shown, the partner's heard)
};
export const shortProps = (getInputProps() as {short?: ShortProps}).short ?? {
	source: 'preview.mp4', fps: 60, style: 'hype', clips: [{src: 0, dur: 600, from: 0}], dur: 600, cropX: 420, cam: [1485, 720, 435, 360],
	title: 'PREVIEW', tag: 'SERIES', cta: 'FULL EPISODE', captions: [], effects: [],
	text: {channel: 'Channel', from_stream: 'from a Twitch stream', effect_label: ''},
};

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const GAME = {top: 430, size: 1080};
const XFADE = 5;

const Caption: React.FC<{text: string; words?: number[]; dur: number; i: number; color: string; big?: boolean}> = ({text, words, dur, i, color, big}) => {
	const f = useCurrentFrame();
	const out = interpolate(f, [dur - 8, dur], [1, 0], clamp);
	const size = big ? (text.length > 22 ? 84 : 100) : (text.length > 24 ? 60 : 68);
	return (
		<AbsoluteFill style={{top: GAME.top + GAME.size - 330, height: 300, justifyContent: 'center', alignItems: 'center', padding: '0 50px'}}>
			<div style={{
				...lineStyle({text, color: WHITE, size}), whiteSpace: 'normal', textAlign: 'center', lineHeight: 1.05,
				transform: `scale(${out}) rotate(${big ? (i % 2 ? 2 : -3) : 0}deg)`, opacity: out,
			}}><KineticWords text={text} words={words} color={color} /></div>
		</AbsoluteFill>
	);
};

// The end: the last frame held (as the episode's end freeze: slow push-in, colour draining) under the call to the full
// episode, so the Short doesn't stop dead on its last word.
const Hold: React.FC<{children: (style: React.CSSProperties) => React.ReactNode}> = ({children}) => {
	const f = useCurrentFrame();
	return (
		<div style={{position: 'absolute', inset: 0, transform: `scale(${1 + f * 0.0012})`, transformOrigin: '50% 40%',
			filter: `saturate(${interpolate(f, [0, 20], [1, 0.3], clamp)}) contrast(1.1)`}}>
			<Freeze frame={0}>{children({width: 1920, height: 1080})}</Freeze>
		</div>
	);
};

export const Short: React.FC = () => {
	const p = shortProps;
	const HEAD = styles[p.style as keyof typeof styles].headline;
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const src = staticFile(p.source);
	const hold = p.hold ?? 0;
	const last = p.clips[p.clips.length - 1];
	const lastSrc = last.src + last.dur - 1;
	const now = p.clips.find((c) => f >= c.from && f < c.from + c.dur);
	// the label names whoever's view and webcam are on screen: the partner's tag inside "pov" spans
	const partner = p.text.partner && povAt(p.guest, now ? now.src + f - now.from : lastSrc) ? p.text.partner : null;
	const ctaIn = spring({frame: f - (p.dur - hold - 150), fps, config: {damping: 15}});
	const game = (c: {src: number; dur: number; from: number}, style: React.CSSProperties, muted = false) => {
		const volume = (v: number) => interpolate(v, [0, XFADE, c.dur, c.dur + XFADE], [0, 1, 1, 0], clamp);
		const pov = povOverlaps(p.guest, c.src, c.src + c.dur + XFADE);
		const s = {width: 1920, height: 1080, ...style};
		return (
			<>
				<OffthreadVideo src={src} trimBefore={c.src} muted={muted} style={s}
					volume={muted ? 0 : (v) => volume(v) * (pov ? 1 - povGain(p.guest, c.src + v) : 1)} />
				{pov && <GuestView g={p.guest} f={f - c.from} trimBefore={c.src} rate={1} style={s} volume={volume} muted={muted} />}
			</>
		);
	};
	return (
		<AbsoluteFill style={{background: 'linear-gradient(180deg, #14161c 0%, #0b0b0f 100%)', overflow: 'hidden'}}>
			{/* Hook, as on the thumbnail: the first frame works as the Shorts-feed cover */}
			<Stack still style={{left: 70, top: 110}} lines={[{text: p.tag, color: CYAN, size: 54}, {text: p.title, color: HEAD, size: Math.min(124, 940 / (p.title.length * 0.47))}]} />
			{/* Game: a 720x720 native-pixel window of the source frame; clips crossfade their audio over the cut */}
			{p.clips.map((c, i) => (
				<Sequence key={`g${i}`} from={c.from} durationInFrames={c.dur + XFADE} layout="none">
					<div style={{position: 'absolute', top: GAME.top, left: 0, width: GAME.size, height: GAME.size, overflow: 'hidden', opacity: f < c.from + c.dur ? 1 : 0}}>
						<div style={{position: 'absolute', left: -p.cropX, top: 0, width: 1920, height: 1080}}>{game(c, {})}</div>
					</div>
				</Sequence>
			))}
			{hold > 0 && (
				<Sequence from={last.from + last.dur} durationInFrames={hold} layout="none">
					<div style={{position: 'absolute', top: GAME.top, left: 0, width: GAME.size, height: GAME.size, overflow: 'hidden'}}>
						<Hold>{(st) => (
							<div style={{position: 'absolute', left: -p.cropX, top: 0, width: 1920, height: 1080}}>
								<OffthreadVideo src={sourceAt(p.guest, src, lastSrc)} trimBefore={lastSrc} muted style={st} />
							</div>
						)}</Hold>
					</div>
				</Sequence>
			)}
			{/* Webcam at its native size, no frame */}
			{p.cam && p.clips.map((c, i) => {
				const slot = {position: 'absolute', top: GAME.top + GAME.size + 40, right: 40, width: p.cam![2], height: p.cam![3], overflow: 'hidden'} as const;
				const volume = (v: number) => interpolate(v, [0, XFADE, c.dur, c.dur + XFADE], [0, 1, 1, 0], clamp);
				return (
					<Sequence key={`w${i}`} from={c.from} durationInFrames={c.dur + XFADE} layout="none">
						{p.tracks ? p.tracks.map((t) => {
							// the slot shows the webcam of whoever's view is on screen: the partner's inside "pov" spans
							const shown = t.role === (povAt(p.guest, c.src + f - c.from) ? 'guestcam' : 'cam') && f < c.from + c.dur;
							return <TrackView key={t.role} t={t} trimBefore={c.src} rate={1} volume={volume}
								style={t.role === 'cam' || t.role === 'guestcam' ? {...slot, left: undefined, height: t.box[3], opacity: shown ? 1 : 0} : {opacity: 0}} />;
						}) : (
							<div style={{...slot, opacity: f < c.from + c.dur ? 1 : 0}}>
								<div style={{position: 'absolute', left: -p.cam![0], top: -p.cam![1], width: 1920, height: 1080}}>{game(c, {}, true)}</div>
							</div>
						)}
					</Sequence>
				);
			})}
			{hold > 0 && p.cam && (() => {
				const slot = {position: 'absolute', top: GAME.top + GAME.size + 40, right: 40, width: p.cam![2], height: p.cam![3], overflow: 'hidden'} as const;
				const cam = p.tracks?.find((t) => t.role === (povAt(p.guest, lastSrc) ? 'guestcam' : 'cam')) ?? p.tracks?.find((t) => t.role === 'cam');
				return (
					<Sequence from={last.from + last.dur} durationInFrames={hold} layout="none">
						<Freeze frame={0}>
							{cam ? <TrackView t={cam} trimBefore={lastSrc} rate={1} volume={() => 0} muted style={{...slot, left: undefined, height: cam.box[3]}} /> : (
								<div style={slot}>
									<div style={{position: 'absolute', left: -p.cam![0], top: -p.cam![1], width: 1920, height: 1080}}>
										<OffthreadVideo src={src} trimBefore={lastSrc} muted style={{width: 1920, height: 1080}} />
									</div>
								</div>
							)}
						</Freeze>
					</Sequence>
				);
			})()}
			{hold > 0 && <Sequence from={last.from + last.dur}><Audio src={staticFile('sfx/hit.wav')} volume={0.5} /></Sequence>}
			<Stack still style={{left: 70, top: GAME.top + GAME.size + 90}} lines={[{text: partner?.text ?? p.text.channel, color: WHITE, size: 96}, {text: partner ? (partner.sub ?? '') : p.text.from_stream, color: CYAN, size: 42}]} />
			{p.effects.map((e, i) => (
				<Sequence key={`e${i}`} from={e.at} durationInFrames={212}>
					<AbsoluteFill style={{top: GAME.top + 40, alignItems: 'center'}}>
						<Stack dur={210} style={{position: 'relative'}} lines={[
							...(p.text.effect_label ? [{text: p.text.effect_label, color: CYAN, size: 34}] : []),
							{text: e.name, color: HEAD, size: 76}, ...(e.fi ? [{text: e.fi, color: WHITE, size: 36, light: true}] : []),
						]} />
					</AbsoluteFill>
				</Sequence>
			))}
			{p.captions.map((c, i) => (
				<Sequence key={`c${i}`} from={c.at} durationInFrames={c.dur ?? 132}><Caption text={c.text} words={c.words} dur={c.dur ?? 132} i={i} color={HEAD} big={c.big} /></Sequence>
			))}
			{p.effects.map((e, i) => (
				<Sequence key={`b${i}`} from={e.at}><Audio src={staticFile('sfx/badge.wav')} volume={0.35} /></Sequence>
			))}
			{p.clips.slice(1).map((c, i) => (
				<Sequence key={`cut${i}`} from={c.from - 20}><Audio src={staticFile('sfx/whoosh.wav')} volume={0.35} /></Sequence>
			))}
			{/* Call to the full episode, last 2.5 s */}
			<div style={{position: 'absolute', top: GAME.top + GAME.size + 320, left: 70, opacity: ctaIn, transform: `translateX(${(1 - ctaIn) * -80}px)`}}>
				<Stack still style={{position: 'relative'}} lines={[{text: `${p.cta} ▶`, color: CYAN, size: 60}]} />
			</div>
		</AbsoluteFill>
	);
};
