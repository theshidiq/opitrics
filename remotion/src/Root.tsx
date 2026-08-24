/**
 * Composition registry. The duration is calculated from the props, so
 * a longer script produces a longer video without anything here
 * changing.
 */

import React from "react";
import { Composition } from "remotion";
import { Short, ShortProps, durationOf } from "./Short";
import { FPS, HEIGHT, WIDTH } from "./theme";

const FALLBACK: ShortProps = {
  shots: [
    {
      card: {
        kind: "hook",
        figure: "15,950",
        caption: "comments read",
        detail: "no props supplied — this is the placeholder",
        eyebrow: "opitrics",
      },
      hold: 3.5,
    },
  ],
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Short"
    component={Short}
    width={WIDTH}
    height={HEIGHT}
    fps={FPS}
    defaultProps={FALLBACK}
    durationInFrames={durationOf(FALLBACK)}
    calculateMetadata={({ props }) => ({
      durationInFrames: durationOf(props as ShortProps),
    })}
  />
);
