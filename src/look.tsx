import React from 'react';
import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Oswald';

// The channel look, shared by episodes, Shorts and thumbnails: Oswald capitals stacked in the style's headline colour,
// white and cyan, tilted -5°, no boxes. A thin near-black outline under a soft shadow keeps text readable on any frame.
export const oswald = loadFont('normal', {weights: ['500', '600']}).fontFamily;
export const CYAN = '#00C8F8';
export const WHITE = '#FFFFFF';
export const TILT = -5;

export type Line = {text: string; color: string; size: number; light?: boolean};

export const lineStyle = ({color, size, light}: Line): React.CSSProperties => ({
	fontFamily: oswald, fontWeight: light ? 500 : 600, fontSize: size, lineHeight: 1.02, color, whiteSpace: 'nowrap',
	textTransform: light ? 'none' : 'uppercase', WebkitTextStroke: `${Math.min(6, size * 0.12)}px #0b0b0f`, paintOrder: 'stroke fill',
	textShadow: `0 ${size * 0.05}px ${size * 0.15}px rgba(0,0,0,0.85), 0 0 4px rgba(0,0,0,0.6)`,
});

// A tilted stack of lines that slide in one after another (3 frames apart) and fade out over the last 10 frames.
export const Stack: React.FC<{lines: Line[]; dur?: number; align?: 'left' | 'right' | 'center'; style?: React.CSSProperties; still?: boolean}> = ({lines, dur, align = 'left', style, still}) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const out = dur ? interpolate(f, [dur - 10, dur], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}) : 1;
	const dir = align === 'right' ? 1 : -1;
	return (
		<div style={{position: 'absolute', display: 'flex', flexDirection: 'column', textAlign: align, opacity: out,
			alignItems: align === 'right' ? 'flex-end' : align === 'center' ? 'center' : 'flex-start',
			transform: `rotate(${TILT}deg)`, transformOrigin: align === 'right' ? 'right top' : align === 'center' ? 'center top' : 'left top', ...style}}>
			{lines.map((l, i) => {
				const s = still ? 1 : spring({frame: f - 3 * i, fps, config: {damping: 16, stiffness: 170}});
				// umlaut dots sit above the cap height: give them room so they don't touch the line above
				const dots = i > 0 && /[ÄÖÅÜäöåü]/.test(l.text) ? {paddingTop: l.size * 0.12} : {};
				return <div key={i} style={{...lineStyle(l), ...dots, opacity: s, transform: `translateX(${dir * (1 - s) * 60}px)`}}>{l.text}</div>;
			})}
		</div>
	);
};
