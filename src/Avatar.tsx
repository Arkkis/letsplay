import React from 'react';
import {AbsoluteFill, getInputProps, Img, staticFile} from 'remotion';
import {CYAN, lineStyle, TILT, WHITE} from './look';

// Channel profile picture, 800x800, shown as a circle. Variants (input prop `variant`): a monogram in the channel look over a
// darkened real stream frame or plain dark, or a game frame alone. No small text: unreadable at avatar size.
const variant = ((getInputProps() as {variant?: string}).variant ?? 'mono-ghost');

const frames: Record<string, {src: string; left: number; top: number; scale: number}> = {
	neon: {src: 'neon', left: -1000, top: -300, scale: 1.25},
	tank: {src: 'tank', left: -1250, top: -350, scale: 1.25},
	car: {src: 'car', left: -650, top: -380, scale: 1.0},
};

const Frame: React.FC<{name: string; dim: number}> = ({name, dim}) => {
	const f = frames[name];
	return (
		<>
			<Img src={staticFile(`banner/${f.src}.jpg`)} style={{position: 'absolute', width: 1920 * f.scale, height: 1080 * f.scale, left: f.left, top: f.top,
				filter: `contrast(1.15) saturate(1.25) brightness(${1 - dim})`}} />
			<AbsoluteFill style={{background: 'radial-gradient(circle at 50% 50%, rgba(0,0,0,0) 40%, rgba(0,0,0,0.65) 100%)'}} />
		</>
	);
};

const Mono: React.FC<{color: string; ghost?: string}> = ({color, ghost}) => (
	<div style={{position: 'absolute', left: 0, top: 0, width: 800, height: 800, display: 'flex', alignItems: 'center', justifyContent: 'center',
		transform: `rotate(${TILT}deg)`}}>
		{ghost && <div style={{...lineStyle({text: '', color: ghost, size: 640}), position: 'absolute', transform: 'translate(22px, 18px)',
			WebkitTextStroke: 0, textShadow: 'none', lineHeight: 1}}>A</div>}
		<div style={{...lineStyle({text: '', color, size: 640}), position: 'absolute', lineHeight: 1}}>A</div>
	</div>
);

export const Avatar: React.FC = () => (
	<AbsoluteFill style={{background: '#0b0b0f', overflow: 'hidden'}}>
		{variant === 'mono-neon' && <><Frame name="neon" dim={0.3} /><Mono color={WHITE} /></>}
		{variant === 'mono-tank' && <><Frame name="tank" dim={0.35} /><Mono color={WHITE} /></>}
		{variant === 'mono-dark' && <><AbsoluteFill style={{background: 'radial-gradient(circle at 50% 40%, #1c1f27 0%, #0b0b0f 70%)'}} /><Mono color={CYAN} /></>}
		{variant === 'mono-ghost' && <><AbsoluteFill style={{background: 'radial-gradient(circle at 50% 40%, #1c1f27 0%, #0b0b0f 70%)'}} /><Mono color={WHITE} ghost={CYAN} /></>}
		{variant === 'car' && <Frame name="car" dim={0.05} />}
	</AbsoluteFill>
);
