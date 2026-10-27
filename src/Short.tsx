import React from 'react';
import {
	AbsoluteFill, Audio, Easing, getInputProps, interpolate, OffthreadVideo, Sequence, spring, staticFile,
	useCurrentFrame, useVideoConfig,
} from 'remotion';
import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import {loadFont as loadLuckiest} from '@remotion/google-fonts/LuckiestGuy';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import styles from './styles.json';

// A vertical Short cut from an episode's prepared source. Laid out at 1080x1920 and rendered at 2/3 scale (720x1280),
// where the 1920x1080-unit source frame shows at its native 1280x720: the game window and webcam are never upscaled.
export type ShortProps = {
	source: string; fps: number; style: string; src: number; dur: number; cropX: number;
	cam: number[] | null; title: string; tag: string; cta: string;
	captions: {at: number; text: string}[]; effects: {at: number; name: string; fi: string}[];
	text: {channel: string; from_stream: string; effect_label: string};
};
export const shortProps = (getInputProps() as {short?: ShortProps}).short ?? {
	source: 'preview.mp4', fps: 60, style: 'hype', src: 0, dur: 600, cropX: 420, cam: [1485, 720, 435, 360],
	title: 'PREVIEW', tag: 'SERIES', cta: 'FULL EPISODE', captions: [], effects: [],
	text: {channel: 'Channel', from_stream: 'from a Twitch stream', effect_label: ''},
};

const anton = loadAnton().fontFamily;
const luckiest = loadLuckiest().fontFamily;
const inter = loadInter('normal', {weights: ['600', '800']}).fontFamily;
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;
const GAME = {top: 430, size: 1080};

const Caption: React.FC<{text: string; i: number; font: string; color: string}> = ({text, i, font, color}) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const pop = spring({frame: f, fps, config: {damping: 11, stiffness: 220}});
	const out = interpolate(f, [120, 132], [1, 0], clamp);
	return (
		<AbsoluteFill style={{top: GAME.top + GAME.size - 330, height: 300, justifyContent: 'center', alignItems: 'center', padding: '0 50px'}}>
			<div style={{
				fontFamily: font, fontSize: text.length > 22 ? 80 : 96, color: i % 3 === 1 ? 'white' : color, textAlign: 'center',
				WebkitTextStroke: '14px black', paintOrder: 'stroke fill', lineHeight: 1.05, textShadow: '0 8px 0 rgba(0,0,0,0.55)',
				transform: `scale(${(0.4 + 0.6 * pop) * out}) rotate(${i % 2 ? 2 : -2}deg)`, opacity: out,
			}}>{text}</div>
		</AbsoluteFill>
	);
};

const Banner: React.FC<{name: string; fi: string; label: string; accent: string; highlight: string; soft: string}> = ({name, fi, label, accent, highlight, soft}) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const inn = spring({frame: f, fps, config: {damping: 14, stiffness: 160}});
	const out = interpolate(f, [190, 210], [0, 1], {...clamp, easing: Easing.in(Easing.cubic)});
	return (
		<AbsoluteFill style={{top: GAME.top + 30, alignItems: 'center', opacity: inn * (1 - out)}}>
			<div style={{background: 'rgba(14,10,24,0.92)', border: `3px solid ${accent}`, borderRadius: 16, padding: '10px 28px 14px',
				transform: `translateY(${(1 - inn) * -40}px)`, maxWidth: 960, textAlign: 'center'}}>
				<div style={{fontFamily: inter, fontWeight: 800, fontSize: 22, letterSpacing: 6, color: highlight}}>{label}</div>
				<div style={{fontFamily: anton, fontSize: 58, color: 'white', lineHeight: 1.05, textTransform: 'uppercase'}}>{name}</div>
				<div style={{fontFamily: inter, fontWeight: 600, fontSize: 28, color: soft}}>{fi}</div>
			</div>
		</AbsoluteFill>
	);
};

export const Short: React.FC = () => {
	const p = shortProps;
	const S = styles[p.style as keyof typeof styles];
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const src = staticFile(p.source);
	const hook = spring({frame: f, fps, config: {damping: 12, stiffness: 140}});
	const ctaIn = spring({frame: f - (p.dur - 150), fps, config: {damping: 15}});
	const captionFont = S.captionFont === 'anton' ? anton : luckiest;
	return (
		<AbsoluteFill style={{background: `linear-gradient(180deg, #0b0614 0%, ${S.accent}55 45%, #0b0614 100%)`}}>
			{/* Hook title */}
			<div style={{position: 'absolute', top: 70, left: 0, right: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18}}>
				<div style={{fontFamily: anton, fontSize: 40, color: 'white', background: S.accent, padding: '2px 22px', borderRadius: 10}}>{p.tag}</div>
				<div style={{
					fontFamily: anton, fontSize: p.title.length > 18 ? 96 : 118, lineHeight: 1, color: S.highlight, textAlign: 'center',
					padding: '0 40px', WebkitTextStroke: '10px black', paintOrder: 'stroke fill', textShadow: '0 8px 0 rgba(0,0,0,0.6)',
					transform: `scale(${0.7 + 0.3 * hook})`,
				}}>{p.title}</div>
			</div>
			{/* Game: a 720x720 native-pixel window of the source frame */}
			<div style={{position: 'absolute', top: GAME.top, left: 0, width: GAME.size, height: GAME.size, overflow: 'hidden',
				borderTop: `6px solid ${S.accent}`, borderBottom: `6px solid ${S.accent}`}}>
				<div style={{position: 'absolute', left: -p.cropX, top: 0, width: 1920, height: 1080}}>
					<OffthreadVideo src={src} trimBefore={p.src} style={{width: 1920, height: 1080}}
						volume={(v) => interpolate(v, [0, 3, p.dur - 3, p.dur], [0, 1, 1, 0], clamp)} />
				</div>
			</div>
			{/* Webcam at its native size */}
			{p.cam && (
				<div style={{position: 'absolute', top: GAME.top + GAME.size + 40, left: 70, width: p.cam[2], height: p.cam[3], overflow: 'hidden',
					borderRadius: 20, border: `5px solid ${S.accent}`}}>
					<div style={{position: 'absolute', left: -p.cam[0], top: -p.cam[1], width: 1920, height: 1080}}>
						<OffthreadVideo src={src} trimBefore={p.src} muted style={{width: 1920, height: 1080}} />
					</div>
				</div>
			)}
			<div style={{position: 'absolute', top: GAME.top + GAME.size + 80, left: p.cam ? 560 : 70, right: 60}}>
				<div style={{fontFamily: anton, fontSize: 70, color: 'white'}}>{p.text.channel}</div>
				<div style={{fontFamily: inter, fontWeight: 700, fontSize: 32, color: S.soft}}>{p.text.from_stream}</div>
			</div>
			{p.effects.map((e, i) => (
				<Sequence key={`e${i}`} from={e.at} durationInFrames={212}><Banner name={e.name} fi={e.fi} label={p.text.effect_label} accent={S.accent} highlight={S.highlight} soft={S.soft} /></Sequence>
			))}
			{p.captions.map((c, i) => (
				<Sequence key={`c${i}`} from={c.at} durationInFrames={132}><Caption text={c.text} i={i} font={captionFont} color={S.highlight} /></Sequence>
			))}
			{p.captions.map((c, i) => (
				<Sequence key={`p${i}`} from={c.at}><Audio src={staticFile('sfx/pop.wav')} volume={0.3} /></Sequence>
			))}
			{p.effects.map((e, i) => (
				<Sequence key={`b${i}`} from={e.at}><Audio src={staticFile('sfx/badge.wav')} volume={0.35} /></Sequence>
			))}
			{/* Call to the full episode, last 2.5 s */}
			<div style={{position: 'absolute', top: GAME.top + GAME.size + 250, left: p.cam ? 560 : 70, right: 40,
				opacity: ctaIn, transform: `translateX(${(1 - ctaIn) * 80}px)`}}>
				<div style={{display: 'inline-block', fontFamily: anton, fontSize: 44, color: 'white', background: '#e62117', padding: '6px 24px', borderRadius: 12}}>{p.cta} ▶</div>
			</div>
		</AbsoluteFill>
	);
};
