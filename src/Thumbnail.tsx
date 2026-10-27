import React from 'react';
import {AbsoluteFill, Freeze, OffthreadVideo, staticFile} from 'remotion';
import {loadFont as loadAnton} from '@remotion/google-fonts/Anton';
import fallback from './edit.json';
import {getInputProps} from 'remotion';
// Each render passes its episode's timeline as input props, so episodes can render side by side.
const edit = ((getInputProps() as {edit?: typeof fallback}).edit ?? fallback);
import thumbFallback from './thumb.json';
const thumb = ((getInputProps() as {thumb?: typeof thumbFallback}).thumb ?? thumbFallback);
import styles from './styles.json';

const anton = loadAnton().fontFamily;
const src = staticFile(edit.source);
const STYLE = styles[edit.style as keyof typeof styles];
// Webcam rect in 1920x1080 layout units; null when the stream has no webcam (then the game frame fills the thumbnail).
const cam = edit.cam as number[] | null;
const CAM = cam && {x: cam[0], y: cam[1], w: cam[2], h: cam[3]};
const S = CAM ? Math.max(560 / CAM.w, 464 / CAM.h) : 1; // fill the 560x464 webcam frame

export const Thumbnail: React.FC = () => (
	<AbsoluteFill style={{background: 'black', overflow: 'hidden'}}>
		<AbsoluteFill style={{transform: `scale(${thumb.bgZoom})`, transformOrigin: thumb.bgOrigin, filter: 'brightness(1.08) contrast(1.3) saturate(1.5)'}}>
			<Freeze frame={0}><OffthreadVideo src={src} trimBefore={thumb.bg} muted style={{width: "100%", height: "100%"}} /></Freeze>
		</AbsoluteFill>
		<AbsoluteFill style={{background: 'linear-gradient(90deg, rgba(10,4,24,0.6) 0%, rgba(10,4,24,0.3) 40%, transparent 62%)'}} />
		{/* Webcam reaction, cropped out of the frame and enlarged */}
		{CAM && thumb.face !== null && <div style={{
			position: 'absolute', right: -10, bottom: -20, width: 560, height: 464, overflow: 'hidden', borderRadius: 28,
			border: '10px solid white', boxShadow: `0 0 0 8px ${STYLE.accent}, 0 20px 60px rgba(0,0,0,0.6)`, transform: 'rotate(-3deg)',
		}}>
			<div style={{position: 'absolute', width: 1920, height: 1080, left: -CAM.x * S, top: -CAM.y * S, transform: `scale(${S})`, transformOrigin: '0 0'}}>
				<Freeze frame={0}><OffthreadVideo src={src} trimBefore={thumb.face} muted style={{width: 1920, height: 1080}} /></Freeze>
			</div>
		</div>}
		<div style={{position: 'absolute', left: 50, top: 40, fontFamily: anton, fontSize: 44, color: 'white', background: STYLE.accent, padding: '2px 22px', borderRadius: 10}}>
			{thumb.tag}
		</div>
		<div style={{
			position: 'absolute', left: 46, top: 130, width: CAM ? 720 : 1180, fontFamily: anton, fontSize: 150, lineHeight: 0.98, color: STYLE.highlight,
			WebkitTextStroke: '12px black', paintOrder: 'stroke fill', textShadow: '0 10px 0 rgba(0,0,0,0.6)', textTransform: 'uppercase',
		}}>
			{thumb.text}
		</div>
	</AbsoluteFill>
);
