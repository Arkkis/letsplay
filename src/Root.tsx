import {Composition} from 'remotion';
import {LetsPlay} from './LetsPlay';
import {Thumbnail} from './Thumbnail';
import {Short, shortProps} from './Short';
import fallback from './edit.json';
import {getInputProps} from 'remotion';
// Each render passes its episode's timeline as input props, so episodes can render side by side.
const edit = ((getInputProps() as {edit?: typeof fallback}).edit ?? fallback);

export const Root = () => (
	<>
		<Composition id="LetsPlay" component={LetsPlay} durationInFrames={edit.duration} fps={edit.fps} width={1920} height={1080} />
		<Composition id="Thumbnail" component={Thumbnail} durationInFrames={1} fps={edit.fps} width={1280} height={720} />
		<Composition id="Short" component={Short} durationInFrames={shortProps.dur} fps={shortProps.fps} width={1080} height={1920} />
	</>
);
