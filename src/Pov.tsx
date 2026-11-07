import React from 'react';
import {AbsoluteFill, interpolate, OffthreadVideo, staticFile} from 'remotion';

// The co-op partner's view: a second prepared source on the same clock (their gameplay, the same webcams). Inside the
// EDL's "pov" spans (source frames) it is shown full frame instead of the streamer's, with its own game sound; both
// carry the same mics, so the switch is a hard picture cut with a few frames of audio crossfade.
export type Guest = {source: string; pov: number[][]} | null | undefined;
const RAMP = 2;
const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

export const povAt = (g: Guest, s: number) => !!g && g.pov.some(([a, b]) => s >= a && s < b);
// 0 = the streamer's view, 1 = the partner's, at source frame s
export const povGain = (g: Guest, s: number) =>
	g ? Math.max(0, ...g.pov.map(([a, b]) => interpolate(s, [a - RAMP, a + RAMP, b - RAMP, b + RAMP], [0, 1, 1, 0], clamp))) : 0;
export const povOverlaps = (g: Guest, a: number, b: number) => !!g && g.pov.some(([x, y]) => x < b && y > a);
// The source showing source frame s (for stills: title, zooms, freeze, thumbnail)
export const sourceAt = (g: Guest, main: string, s: number) => (povAt(g, s) ? staticFile(g!.source) : main);

// The partner's view over a clip that crosses a "pov" span: s(f) = source frame shown at the clip's frame f.
export const GuestView: React.FC<{g: Guest; f: number; trimBefore: number; rate: number; style: React.CSSProperties;
	volume: (vf: number) => number; muted?: boolean}> = ({g, f, trimBefore, rate, style, volume, muted}) => (
	<AbsoluteFill style={{opacity: povAt(g, trimBefore + f * rate) ? 1 : 0}}>
		<OffthreadVideo style={style} src={staticFile(g!.source)} trimBefore={trimBefore} playbackRate={rate} muted={muted}
			volume={muted ? 0 : (vf) => volume(vf) * povGain(g, trimBefore + vf * rate)} />
	</AbsoluteFill>
);

// A separately recorded webcam (assemble → prep): its own file on the episode clock, at its box in the 1920x1080
// layout, with its own mic; `alpha`: cut out (VP9 with alpha).
export type Track = {role: string; source: string; box: number[]; alpha: boolean};
export const TrackView: React.FC<{t: Track; trimBefore: number; rate: number; volume: (vf: number) => number; muted?: boolean;
	style?: React.CSSProperties}> = ({t, trimBefore, rate, volume, muted, style}) => (
	<div style={{position: 'absolute', left: t.box[0], top: t.box[1], width: t.box[2], height: t.box[3], ...style}}>
		<OffthreadVideo src={staticFile(t.source)} transparent={t.alpha} trimBefore={trimBefore} playbackRate={rate} muted={muted}
			volume={muted ? 0 : volume} style={{width: '100%', height: '100%'}} />
	</div>
);
