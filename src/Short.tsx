import React from 'react';
import {
	AbsoluteFill, Audio, getInputProps, interpolate, OffthreadVideo, Sequence, spring, staticFile,
	useCurrentFrame, useVideoConfig,
} from 'remotion';
import styles from './styles.json';
import {KineticWords} from './Kinetic';
import {CYAN, lineStyle, Stack, WHITE} from './look';

// A vertical Short cut from an episode's prepared source. Laid out at 1080x1920 and rendered at 2/3 scale (720x1280),
// where the 1920x1080-unit source frame shows at its native 1280x720: the game window and webcam are never upscaled.
// One or two clips (an internal cut); every spoken word captioned, the episode's own captions shown big.
export type ShortProps = {
	source: string; fps: number; style: string; clips: {src: number; dur: number; from: number}[]; dur: number; cropX: number;
	cam: number[] | null; title: string; tag: string; cta: string;
	captions: {at: number; text: string; words?: number[]; dur?: number; big?: boolean}[]; effects: {at: number; name: string; fi: string}[];
	text: {channel: string; from_stream: string; effect_label: string};
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

export const Short: React.FC = () => {
	const p = shortProps;
	const HEAD = styles[p.style as keyof typeof styles].headline;
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const src = staticFile(p.source);
	const ctaIn = spring({frame: f - (p.dur - 150), fps, config: {damping: 15}});
	const game = (c: {src: number; dur: number}, style: React.CSSProperties, muted = false) => (
		<OffthreadVideo src={src} trimBefore={c.src} muted={muted} style={{width: 1920, height: 1080, ...style}}
			volume={muted ? 0 : (v) => interpolate(v, [0, XFADE, c.dur, c.dur + XFADE], [0, 1, 1, 0], clamp)} />
	);
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
			{/* Webcam at its native size, no frame */}
			{p.cam && p.clips.map((c, i) => (
				<Sequence key={`w${i}`} from={c.from} durationInFrames={c.dur} layout="none">
					<div style={{position: 'absolute', top: GAME.top + GAME.size + 40, right: 40, width: p.cam![2], height: p.cam![3], overflow: 'hidden'}}>
						<div style={{position: 'absolute', left: -p.cam![0], top: -p.cam![1], width: 1920, height: 1080}}>{game(c, {}, true)}</div>
					</div>
				</Sequence>
			))}
			<Stack still style={{left: 70, top: GAME.top + GAME.size + 90}} lines={[{text: p.text.channel, color: WHITE, size: 96}, {text: p.text.from_stream, color: CYAN, size: 42}]} />
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
