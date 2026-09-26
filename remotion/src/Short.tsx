/**
 * The sequence. Reads its shots from props written by the Python
 * pipeline, so nothing about a particular car lives in here.
 */

import React from "react";
import {
  AbsoluteFill,
  Audio,
  Img,
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
  /** One-shot effect at the start of this shot, relative to public/. */
  sfx?: string | null;
  /** Gain for that effect, in dB. Negative sits it under the voice. */
  sfxGainDb?: number;
};

export type ShortProps = {
  shots: Shot[];
  music?: string | null;
  musicGainDb?: number;
  crossfade?: number;
  /** Photograph held behind every card, relative to public/. */
  backdrop?: string | null;
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
    <AbsoluteFill style={{ opacity }}>{renderCard(card)}</AbsoluteFill>
  );
};

/**
 * The car, held behind every card for the length of the short.
 *
 * Card kinds other than "photo" drew on flat white, so a quote-led
 * short was twenty-six seconds of text on an empty page and the
 * product never appeared at all. Worse for this subject specifically:
 * the Racco is white, photographed on a white turntable under white
 * show lighting, so even the photo cards read as blank.
 *
 * This sits at the root rather than inside each Shot so the drift is
 * continuous — restarting the motion on every cut reads as a slideshow.
 * It is washed out hard on purpose: the job is to stop the frame being
 * empty, not to compete with the words. Cards that carry their own
 * full-bleed photograph paint straight over it.
 */
const Backdrop: React.FC<{
  src: string;
  frames: number;
  /** Frame ranges where a chart owns the screen. */
  chartRanges?: readonly (readonly [number, number])[];
}> = ({ src, frames, chartRanges = [] }) => {
  const frame = useCurrentFrame();

  // How far out of the way the car is, 0 to 1. Ramped over a third of
  // a second at each boundary rather than switched, since a backdrop
  // that jumps on a cut reads as a glitch.
  const RAMP = 10;
  const yielding = chartRanges.reduce((acc, [start, end]) => {
    const rising = interpolate(frame, [start - RAMP, start], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    const falling = interpolate(frame, [end - RAMP, end], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    return Math.max(acc, Math.min(rising, falling));
  }, 0);
  const drift = interpolate(frame, [0, frames], [0, -34], {
    extrapolateRight: "clamp",
  });
  // No zoom past 1.0. A landscape photograph cover-cropped into a 9:16
  // frame is already showing only a slice of its width; scaling on top
  // of that cropped past the bodywork and left a wheel arch filling
  // the screen. The slow drift supplies the motion instead.
  const scale = interpolate(frame, [0, frames], [1.0, 1.04], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: UI.ground }}>
      {/*
        Feathered at the top and bottom. `contain` leaves the
        photograph as a band with two hard horizontal edges across the
        frame, which reads as a pasted-in rectangle rather than a
        background; fading the image itself dissolves both seams into
        the page.
      */}
      {/*
        A band, not a fill. Cover-cropping a 3:2 photograph into 9:16
        keeps about a third of its width, and on a car photographed
        from any distance that third is bodywork — every vertical
        offset tried gave a wheel arch. Constraining the height and
        letting the image keep its own aspect inside that height is
        the only framing that shows a vehicle.
      */}
      <AbsoluteFill
        style={{
          // Slides further down and shrinks while a chart is on
          // screen: bar rows were otherwise landing on the roofline.
          top: `${50 + yielding * 12}%`,
          height: `${38 - yielding * 5}%`,
          overflow: "hidden",
          // The photograph now fills the frame, so this is what keeps
          // the top clear for text: a long ramp from nothing at the
          // headline down to full strength across the lower third.
          // Because it fades the image rather than clipping it, there
          // is no edge anywhere.
          // Feathered top and bottom, so the band has no edges.
          maskImage:
            "linear-gradient(to bottom, transparent 0%, black 26%, " +
            "black 72%, transparent 100%)",
          WebkitMaskImage:
            "linear-gradient(to bottom, transparent 0%, black 26%, " +
            "black 72%, transparent 100%)",
        }}
      >
        <Img
          src={staticFile(src)}
          style={{
            width: "100%",
            height: "100%",
            // `contain` inside the band. The band is already close to
            // the photograph's own proportions, so almost nothing is
            // cropped and the whole car shows. Filling the full frame
            // with `cover` was tried at several vertical offsets and
            // gave a wheel arch every time — a 3:2 photograph cropped
            // to 9:16 keeps roughly a third of its width, and on a car
            // shot from any distance that third is bodywork.
            objectFit: "contain",
            objectPosition: "center center",
            transform: `translateY(${drift}px) scale(${scale})`,
            // Desaturated and lifted so body text keeps its contrast.
            filter: "grayscale(0.35) contrast(1.02) brightness(1.02)",
            opacity: 0.62 - yielding * 0.32,
          }}
        />
      </AbsoluteFill>
      {/*
        A white scrim over the photograph, weighted to where the words
        actually are. A flat wash forces a choice between a legible
        card and a visible car; shaping it keeps both — near-opaque
        through the middle band where body text sits, much thinner at
        the top and bottom edges so the roofline and the wheels still
        read as a vehicle.
      */}
      <AbsoluteFill
        style={{
          // Even and light. The band carries its own feathering now,
          // so this only takes the last of the contrast out of the
          // photograph rather than shaping where it shows.
          background: "rgba(255,255,255,0.34)",
        }}
      />
    </AbsoluteFill>
  );
};

export const Short: React.FC<ShortProps> = ({
  shots = [],
  music,
  musicGainDb = -22,
  crossfade = 0.18,
  backdrop,
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

  const totalFrames = Math.max(cursor + fadeFrames * 2, 1);

  // Frame ranges where a chart is on screen. The backdrop steps aside
  // for these rather than being dropped entirely, so the car does not
  // vanish and reappear mid-video.
  const chartRanges = placed
    .filter((s) => s.card?.kind === "bars" || s.card?.kind === "composition")
    .map((s) => [s.start, s.start + s.duration] as const);

  return (
    <AbsoluteFill style={{ backgroundColor: UI.ground }}>
      {backdrop ? (
        <Backdrop
          src={backdrop}
          frames={totalFrames}
          chartRanges={chartRanges}
        />
      ) : null}
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
          {/*
            One-shot, not looped, and well under the narration. An
            effect competing with the voice is worse than no effect:
            the voice is the content and the effect is punctuation.
          */}
          {shot.sfx ? (
            <Audio
              src={staticFile(shot.sfx)}
              volume={Math.pow(10, (shot.sfxGainDb ?? -14) / 20)}
            />
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
