import { Composition } from 'remotion';
import { Video, FPS, totalFrames } from './Video';

export const Root = () => (
  <Composition id="Sightline" component={Video} durationInFrames={totalFrames} fps={FPS} width={1920} height={1080} />
);
