import React from 'react';
import {AbsoluteFill, Freeze, Img, OffthreadVideo, staticFile} from 'remotion';
import fallback from './edit.json';
import {getInputProps} from 'remotion';
// Each render passes its episode's timeline as input props, so episodes can render side by side.
const edit = ((getInputProps() as {edit?: typeof fallback}).edit ?? fallback);
import thumbFallback from './thumb.json';
import styles from './styles.json';
import {CYAN, lineStyle, TILT, WHITE} from './look';
import {Guest, sourceAt} from './Pov';

// Layout and readability come from scripts/thumb_plan.py: hook lines and size, darkening behind the text, headline colour,
// a plate behind the tag when needed, and the webcam cut-out. Text top left, face right of centre: the bottom-right corner
// stays clear for YouTube's duration badge.
type Plan = {lines?: string[]; size?: number; scrim?: number; color?: string; plate?: boolean};
const thumb = ((getInputProps() as {thumb?: typeof thumbFallback & Plan}).thumb ?? thumbFallback) as typeof thumbFallback & Plan;
const src = sourceAt((edit as {guest?: Guest}).guest, staticFile(edit.source), thumb.bg);
const HEAD = styles[edit.style as keyof typeof styles].headline;
const face = (edit as {faceCut?: string}).faceCut;
const size = (thumb.size ?? 12) * 12.8; // % of the 1280 px width → px

export const Thumbnail: React.FC = () => (
	<AbsoluteFill style={{background: 'black', overflow: 'hidden'}}>
		<AbsoluteFill style={{transform: `scale(${thumb.bgZoom})`, transformOrigin: thumb.bgOrigin, filter: 'contrast(1.15) saturate(1.25)'}}>
			<Freeze frame={0}><OffthreadVideo src={src} trimBefore={thumb.bg} muted style={{width: '100%', height: '100%'}} /></Freeze>
		</AbsoluteFill>
		<AbsoluteFill style={{background: `radial-gradient(ellipse 70% 85% at 18% 26%, rgba(0,0,0,${thumb.scrim ?? 0}) 0 40%, transparent 100%)`}} />
		{face && <Img src={staticFile(face)} style={{position: 'absolute', right: '15%', bottom: 0, width: '48%',
			filter: 'brightness(1.1) contrast(1.08) saturate(1.1) drop-shadow(0 0 15px rgba(0,0,0,0.7))'}} />}
		<div style={{position: 'absolute', left: 51, top: 50, transform: `rotate(${TILT}deg)`, transformOrigin: 'left top'}}>
			<div style={{...lineStyle({text: '', color: CYAN, size: 56}), display: 'inline-block', marginBottom: 8,
				...(thumb.plate ? {background: 'rgba(8,10,14,0.8)', padding: '0 16px 4px', WebkitTextStroke: 0, textShadow: 'none'} : {})}}>{thumb.tag}</div>
			{(thumb.lines ?? [thumb.text]).map((l, i) => (
				<div key={i} style={{...lineStyle({text: l, color: thumb.color === 'white' ? WHITE : HEAD, size}), lineHeight: 1}}>{l}</div>
			))}
		</div>
	</AbsoluteFill>
);
