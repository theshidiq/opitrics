/**
 * The sequence. Reads its shots from props written by the Python
 * pipeline, so nothing about a particular car lives in here.
 */

import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  BarsCard,
  CompositionCard,
  HookCard,
  PhotoCard,
  QuoteCard,
  StatementCard,
} from "./components";
import { FPS, UI } from "./theme";

export type Shot = {
  card: any;
  /** Seconds this shot holds, before the crossfade into the next. */
  hold: number;
  /** Narration file, relative to the public directory. */
  audio?: string | null;
};

export type ShortProps = {
  shots: Shot[];
  music?: string | null;
  musicGainDb?: number;
  crossfade?: number;
};

const renderCard = (card: any) => {
  switch (card?.kind) {
    case "hook":
      return <HookCard {...card} />;
    case "quote":
      return <QuoteCard {...card} />;
    case "bars":
      return <BarsCard {...card} />;
    case "composition":
      return <CompositionCard {...card} />;
    case "photo":
      return <PhotoCard {...card} />;
    default:
      return <StatementCard {...card} />;
  }
};

/** Fades the whole shot at its edges so cuts dissolve rather than snap. */
const Shot: React.FC<{
  card: any;
  durationInFrames: number;
  fadeIn: number;
  fadeOut: number;
}> = ({ card, durationInFrames, fadeIn, fadeOut }) => {
  const frame = useCurrentFrame();
  const opacity = Math.min(
    fadeIn > 0
      ? interpolate(frame, [0, fadeIn], [0, 1], { extrapolateRight: "clamp" })
      : 1,
    fadeOut > 0
      ? interpolate(
          frame,
          [durationInFrames - fadeOut, durationInFrames],
          [1, 0],
          { extrapolateLeft: "clamp" },
        )
      : 1,
  );

  return (
    <AbsoluteFill style={{ backgroundColor: UI.ground, opacity }}>
      {renderCard(card)}
    </AbsoluteFill>
  );
};

export const Short: React.FC<ShortProps> = ({
  shots = [],
  music,
  musicGainDb = -22,
  crossfade = 0.18,
}) => {
  const { fps } = useVideoConfig();
  const fadeFrames = Math.round(crossfade * fps);

  // Shots overlap by the crossfade, so the timeline is shorter than the
  // sum of the holds. Laying it out here keeps the two in step.
  let cursor = 0;
  const placed = shots.map((shot, i) => {
    const duration = Math.max(Math.round(shot.hold * fps), 12);
    const start = cursor;
    cursor += Math.max(duration - fadeFrames, 12);
    return { ...shot, start, duration, index: i };
  });

  // dB to a linear multiplier, which is what Remotion's volume wants.
  const musicVolume = Math.pow(10, musicGainDb / 20);

  return (
    <AbsoluteFill style={{ backgroundColor: UI.ground }}>
      {placed.map((shot) => (
        <Sequence
          key={shot.index}
          from={shot.start}
          durationInFrames={shot.duration}
        >
          <Shot
            card={shot.card}
            durationInFrames={shot.duration}
            fadeIn={shot.index === 0 ? 0 : fadeFrames}
            fadeOut={shot.index === placed.length - 1 ? fadeFrames * 2 : fadeFrames}
          />
          {shot.audio ? (
            <Audio src={staticFile(shot.audio)} />
          ) : null}
        </Sequence>
      ))}
      {music ? <Audio src={staticFile(music)} volume={musicVolume} loop /> : null}
    </AbsoluteFill>
  );
};

/** Total length in frames, so the root can size the composition. */
export const durationOf = (props: ShortProps, fps: number = FPS): number => {
  const shots = props.shots ?? [];
  if (!shots.length) return fps;
  const fade = Math.round((props.crossfade ?? 0.18) * fps);
  let cursor = 0;
  let last = fps;
  for (const shot of shots) {
    const duration = Math.max(Math.round(shot.hold * fps), 12);
    last = cursor + duration;
    cursor += Math.max(duration - fade, 12);
  }
  return last;
};
