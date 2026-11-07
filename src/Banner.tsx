import React from 'react';
import {AbsoluteFill, Img, staticFile} from 'remotion';
import {CYAN, lineStyle, TILT, WHITE} from './look';

// YouTube channel banner, 2560x1440. Everything that matters sits in the 1546x423 safe area (x 507–2053, y 508–931) that
// every device shows; the rest is more footage for desktop and TV. Four real stream frames from different games
// (public/banner/*.jpg) with tilted seams, the channel look's text on the left, the webcam cut-out right.
const SKEW = Math.tan((-TILT * Math.PI) / 180) * 1440; // horizontal run of a seam over the full height, so seams match the text tilt
// Each panel shows its frame zoomed in (scale) around a focus point (fx, fy as fractions of the frame), which keeps the
// stream overlay (vote list, chat, webcam, HUD) outside the crop.
const panels: {src: string; from: number; to: number; fx: number; fy: number; scale: number}[] = [
	{src: 'car', from: 0, to: 700, fx: 0.5, fy: 0.46, scale: 1.5},
	{src: 'neon', from: 700, to: 1320, fx: 0.5, fy: 0.42, scale: 1.5},
	{src: 'tank', from: 1320, to: 1940, fx: 0.6, fy: 0.52, scale: 1.5},
	{src: 'zombies', from: 1940, to: 2560, fx: 0.6, fy: 0.5, scale: 1.5},
];
const seam = (x: number) => [x + SKEW / 2, x - SKEW / 2]; // top x, bottom x

export const Banner: React.FC = () => (
	<AbsoluteFill style={{background: '#0b0b0f', overflow: 'hidden'}}>
		{panels.map((p) => {
			const [lt, lb] = seam(p.from), [rt, rb] = seam(p.to);
			const w = 2560 * p.scale, h = 1440 * p.scale, cx = (p.from + p.to) / 2;
			return (
				<AbsoluteFill key={p.src} style={{clipPath: `polygon(${lt - 200}px 0, ${rt - 6}px 0, ${rb - 6}px 1440px, ${lb - 200}px 1440px)`}}>
					<Img src={staticFile(`banner/${p.src}.jpg`)} style={{position: 'absolute', width: w, height: h, left: cx - p.fx * w, top: 720 - p.fy * h,
						filter: 'contrast(1.15) saturate(1.25)'}} />
				</AbsoluteFill>
			);
		})}
		<AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(0,0,0,0) 22%, rgba(0,0,0,0.55) 36%, rgba(0,0,0,0.55) 64%, rgba(0,0,0,0) 78%)'}} />
		<AbsoluteFill style={{background: 'radial-gradient(ellipse 34% 40% at 36% 50%, rgba(0,0,0,0.55) 0 30%, transparent 100%)'}} />
		<Img src={staticFile('gtav-chaos-mod-2022-07-25-ep1-face-198630.png')} style={{position: 'absolute', right: 560, bottom: 500, width: 520,
			filter: 'brightness(1.1) contrast(1.08) saturate(1.1) drop-shadow(0 0 18px rgba(0,0,0,0.7))',
			maskImage: 'linear-gradient(180deg, #000 72%, transparent 100%), linear-gradient(90deg, transparent 0, #000 18%)', maskComposite: 'intersect'}} />
		<div style={{position: 'absolute', left: 580, top: 560, transform: `rotate(${TILT}deg)`, transformOrigin: 'left top'}}>
			<div style={{...lineStyle({text: '', color: WHITE, size: 200}), lineHeight: 0.95}}>Arkkis</div>
			<div style={{...lineStyle({text: '', color: CYAN, size: 72}), marginTop: 14}}>Pelejä ja kaaosta suomeksi</div>
			<div style={{...lineStyle({text: '', color: WHITE, size: 46, light: true}), marginTop: 10}}>Twitch-striimit leikattuna jaksoiksi</div>
		</div>
	</AbsoluteFill>
);
