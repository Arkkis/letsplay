import React from 'react';
import {spring, useCurrentFrame, useVideoConfig} from 'remotion';

// Caption words pop in as they are spoken (frame offsets from build_edit.py); the newest word is in the highlight colour.
export const KineticWords: React.FC<{text: string; words?: number[]; color: string}> = ({text, words, color}) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const list = text.trim().split(/\s+/);
	const at = words ?? list.map(() => 0);
	const current = at.filter((a) => a <= f).length - 1;
	return (
		<>
			{list.map((w, i) => {
				const pop = spring({frame: f - at[i], fps, config: {damping: 10, stiffness: 260}});
				const on = i === current;
				return (
					<React.Fragment key={i}>{i > 0 && ' '}<span style={{
						display: 'inline-block', opacity: f >= at[i] ? 1 : 0, color: on ? color : 'white',
						transform: `translateY(${(1 - pop) * 30}px) scale(${0.3 + 0.7 * pop})`,
					}}>{w}</span></React.Fragment>
				);
			})}
		</>
	);
};
