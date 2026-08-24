/**
 * Card components. Every value that moves is computed from the current
 * frame, which is the point of this rewrite — the previous renderer
 * approximated motion by cross-fading a handful of pre-drawn images,
 * and at thirty frames a second you could see the steps.
 */

import React from "react";
import {
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  FONT_STACK,
  MARGIN_PX,
  MONO_STACK,
  SAFE,
  TONE,
  UI,
  toneFor,
} from "./theme";

// ── shared pieces ───────────────────────────────────────────

const Chrome: React.FC<{ eyebrow: string; footer?: string }> = ({
  eyebrow,
  footer,
}) => (
  <>
    <div
      style={{
        position: "absolute",
        top: `${SAFE.top * 100 - 4}%`,
        left: MARGIN_PX,
        right: MARGIN_PX,
        fontFamily: MONO_STACK,
        fontSize: 22,
        letterSpacing: 6,
        textTransform: "uppercase",
        color: UI.dim,
        display: "flex",
        justifyContent: "space-between",
      }}
    >
      <span>{eyebrow}</span>
      {footer ? <span style={{ letterSpacing: 2 }}>{footer}</span> : null}
    </div>
    <div
      style={{
        position: "absolute",
        top: `${SAFE.top * 100}%`,
        left: MARGIN_PX,
        right: MARGIN_PX,
        height: 2,
        background: UI.rule,
      }}
    />
    <div
      style={{
        position: "absolute",
        bottom: `${SAFE.bottom * 100}%`,
        left: MARGIN_PX,
        right: MARGIN_PX,
        height: 2,
        background: UI.rule,
      }}
    />
    <div
      style={{
        position: "absolute",
        bottom: `${SAFE.bottom * 100 - 4}%`,
        left: MARGIN_PX,
        fontFamily: MONO_STACK,
        fontSize: 20,
        letterSpacing: 6,
        fontWeight: 700,
        color: UI.meta,
      }}
    >
      OPITRICS
    </div>
  </>
);

/**
 * A container that springs into place.
 *
 * `delay` is in frames. Springs rather than linear easing because a
 * spring settles — it decelerates into its resting position the way a
 * physical object would, which is most of what reads as "smooth".
 */
const Enter: React.FC<{
  delay?: number;
  from?: "below" | "scale" | "fade";
  children: React.ReactNode;
  style?: React.CSSProperties;
}> = ({ delay = 0, from = "below", children, style }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({
    frame: frame - delay,
    fps,
    config: { damping: 200, stiffness: 110, mass: 0.7 },
  });

  const opacity = interpolate(frame - delay, [0, 6], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const transform =
    from === "below"
      ? `translateY(${interpolate(progress, [0, 1], [46, 0])}px)`
      : from === "scale"
        ? `scale(${interpolate(progress, [0, 1], [0.82, 1])})`
        : "none";

  return <div style={{ ...style, opacity, transform }}>{children}</div>;
};

/** A number that counts up rather than appearing. */
const Counter: React.FC<{
  value: number;
  delay?: number;
  duration?: number;
  style?: React.CSSProperties;
}> = ({ value, delay = 0, duration = 34, style }) => {
  const frame = useCurrentFrame();
  const shown = Math.round(
    interpolate(frame - delay, [0, duration], [0, value], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      // Decelerating: fast at first, settling onto the final figure.
      easing: (t) => 1 - Math.pow(1 - t, 3),
    }),
  );
  return <span style={style}>{shown.toLocaleString()}</span>;
};

// ── cards ───────────────────────────────────────────────────

export type HookProps = {
  kind: "hook";
  figure: string;
  caption: string;
  detail?: string;
  eyebrow: string;
};

export const HookCard: React.FC<HookProps> = ({
  figure,
  caption,
  detail,
  eyebrow,
}) => {
  // Count only when the figure is a plain number; "78%" and the like
  // are shown whole.
  const numeric = Number(figure.replace(/[,\s]/g, ""));
  const countable = Number.isFinite(numeric) && /^[\d,\s]+$/.test(figure);

  return (
    <>
      <Chrome eyebrow={eyebrow} />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: FONT_STACK,
        }}
      >
        <Enter from="scale">
          <div
            style={{
              fontSize: 210,
              fontWeight: 700,
              color: UI.accent,
              lineHeight: 1,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {countable ? <Counter value={numeric} delay={4} /> : figure}
          </div>
        </Enter>
        <Enter delay={14} style={{ marginTop: 36 }}>
          <div
            style={{
              fontSize: 54,
              color: UI.text,
              textAlign: "center",
              maxWidth: 820,
              lineHeight: 1.25,
            }}
          >
            {caption}
          </div>
        </Enter>
        {detail ? (
          <Enter delay={26} from="fade" style={{ marginTop: 28 }}>
            <div
              style={{
                fontSize: 30,
                color: UI.dim,
                textAlign: "center",
                maxWidth: 780,
              }}
            >
              {detail}
            </div>
          </Enter>
        ) : null}
      </div>
    </>
  );
};

export type QuoteProps = {
  kind: "quote";
  original: string;
  english?: string;
  likes: number;
  avatarColour: string;
};

export const QuoteCard: React.FC<QuoteProps> = ({
  original,
  english,
  likes,
  avatarColour,
}) => {
  // Size to length rather than a fixed scale — the browser wraps, so
  // this only has to pick a point size that fits five lines.
  const size = original.length < 60 ? 52 : original.length < 120 ? 44 : 36;

  return (
    <>
      <Chrome eyebrow="youtube comment" footer={`${likes.toLocaleString()} likes`} />
      <div
        style={{
          position: "absolute",
          top: `${SAFE.top * 100 + 6}%`,
          bottom: `${SAFE.bottom * 100 + 6}%`,
          left: MARGIN_PX,
          right: MARGIN_PX,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          fontFamily: FONT_STACK,
        }}
      >
        <Enter from="fade">
          <div style={{ display: "flex", alignItems: "center", gap: 22 }}>
            <div
              style={{
                width: 52,
                height: 52,
                borderRadius: "50%",
                background: avatarColour,
                flex: "none",
              }}
            />
            <div
              style={{
                width: 150,
                height: 12,
                background: UI.rule,
                borderRadius: 6,
              }}
            />
            <div style={{ fontSize: 22, color: UI.dim }}>identity withheld</div>
          </div>
        </Enter>

        <Enter delay={7} style={{ marginTop: 34 }}>
          <div
            style={{
              fontSize: size,
              color: UI.text,
              lineHeight: 1.45,
              maxHeight: 5 * size * 1.45,
              overflow: "hidden",
            }}
          >
            {original}
          </div>
        </Enter>

        {english ? (
          // Late on purpose: a viewer who reads Japanese gets a beat
          // with the original before the English arrives.
          <Enter delay={26} style={{ marginTop: 26 }}>
            <div style={{ fontSize: 30, color: UI.meta, lineHeight: 1.45 }}>
              {english}
            </div>
          </Enter>
        ) : null}

        <Enter delay={38} from="scale" style={{ marginTop: 30 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <ThumbIcon />
            <span
              style={{
                fontFamily: MONO_STACK,
                fontSize: 30,
                color: UI.meta,
              }}
            >
              {likes.toLocaleString()}
            </span>
          </div>
        </Enter>
      </div>
    </>
  );
};

const ThumbIcon: React.FC = () => (
  <svg width="34" height="34" viewBox="0 0 24 24" fill={UI.like}>
    <path d="M1 21h4V9H1v12zm22-11c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2z" />
  </svg>
);

export type StatementProps = {
  kind: "statement";
  text: string;
  eyebrow: string;
};

export const StatementCard: React.FC<StatementProps> = ({ text, eyebrow }) => {
  // One word per layer, staggered. This is the thing the still-image
  // renderer could not do at all.
  const words = text.split(/\s+/);
  const size = text.length < 60 ? 62 : text.length < 120 ? 52 : 42;

  return (
    <>
      <Chrome eyebrow={eyebrow} />
      <div
        style={{
          position: "absolute",
          top: `${SAFE.top * 100 + 6}%`,
          bottom: `${SAFE.bottom * 100 + 6}%`,
          left: MARGIN_PX,
          right: MARGIN_PX,
          display: "flex",
          alignItems: "center",
          fontFamily: FONT_STACK,
        }}
      >
        <div
          style={{
            fontSize: size,
            color: UI.text,
            lineHeight: 1.3,
            display: "flex",
            flexWrap: "wrap",
            gap: `0 ${size * 0.26}px`,
          }}
        >
          {words.map((word, i) => (
            <Enter key={i} delay={i * 2.2} from="below">
              <span>{word}</span>
            </Enter>
          ))}
        </div>
      </div>
    </>
  );
};

export type BarRow = { label: string; size: number; polarity: number };

export type BarsProps = {
  kind: "bars";
  title: string;
  rows: BarRow[];
  eyebrow: string;
};

export const BarsCard: React.FC<BarsProps> = ({ title, rows, eyebrow }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const peak = Math.max(...rows.map((r) => r.size), 1);

  return (
    <>
      <Chrome eyebrow={eyebrow} />
      <div
        style={{
          position: "absolute",
          top: `${SAFE.top * 100 + 5}%`,
          bottom: `${SAFE.bottom * 100 + 4}%`,
          left: MARGIN_PX,
          right: MARGIN_PX,
          fontFamily: FONT_STACK,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
        }}
      >
        <Enter from="fade">
          <div style={{ fontSize: 46, color: UI.text, marginBottom: 52 }}>
            {title}
          </div>
        </Enter>

        <div style={{ display: "flex", flexDirection: "column", gap: 26 }}>
          {rows.map((row, i) => {
            // Each bar grows on its own spring, staggered — the width is
            // recomputed every frame rather than picked from a set of
            // pre-drawn images.
            const grow = spring({
              frame: frame - (10 + i * 5),
              fps,
              config: { damping: 200, stiffness: 90, mass: 0.9 },
            });
            const full = (row.size / peak) * 100;
            return (
              <div
                key={i}
                style={{ display: "flex", alignItems: "center", gap: 18 }}
              >
                <div
                  style={{
                    width: 380,
                    fontSize: 24,
                    lineHeight: 1.2,
                    color: UI.meta,
                    textAlign: "right",
                    flex: "none",
                  }}
                >
                  {row.label}
                </div>
                <div
                  style={{
                    flex: 1,
                    height: 44,
                    background: "#EFEFEF",
                    position: "relative",
                  }}
                >
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: `${full * grow}%`,
                      background: toneFor(row.polarity),
                    }}
                  />
                </div>
                <div
                  style={{
                    width: 110,
                    fontFamily: MONO_STACK,
                    fontSize: 26,
                    color: UI.meta,
                    opacity: interpolate(
                      frame - (28 + i * 5),
                      [0, 8],
                      [0, 1],
                      { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
                    ),
                  }}
                >
                  {row.size.toLocaleString()}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
};

export type CompositionProps = {
  kind: "composition";
  title: string;
  segments: { value: number; label: string; colour: string }[];
  eyebrow: string;
};

export const CompositionCard: React.FC<CompositionProps> = ({
  title,
  segments,
  eyebrow,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const total = Math.max(
    segments.reduce((sum, s) => sum + s.value, 0),
    1,
  );

  return (
    <>
      <Chrome eyebrow={eyebrow} />
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: `0 ${MARGIN_PX}px`,
          fontFamily: FONT_STACK,
        }}
      >
        <Enter from="fade">
          <div style={{ fontSize: 46, color: UI.text, marginBottom: 56 }}>
            {title}
          </div>
        </Enter>

        <div style={{ display: "flex", height: 130, background: "#EFEFEF" }}>
          {segments.map((seg, i) => {
            const grow = spring({
              frame: frame - (12 + i * 9),
              fps,
              config: { damping: 200, stiffness: 95, mass: 0.8 },
            });
            const pct = (seg.value / total) * 100;
            return (
              <div
                key={i}
                style={{
                  width: `${pct * grow}%`,
                  background: seg.colour,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  overflow: "hidden",
                }}
              >
                {pct > 10 ? (
                  <span
                    style={{
                      fontSize: 44,
                      fontWeight: 700,
                      color: "#FFFFFF",
                      opacity: interpolate(grow, [0.6, 1], [0, 1], {
                        extrapolateLeft: "clamp",
                      }),
                    }}
                  >
                    {Math.round(pct)}%
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>

        <div style={{ display: "flex", marginTop: 26 }}>
          {segments.map((seg, i) => (
            <div
              key={i}
              style={{
                width: `${(seg.value / total) * 100}%`,
                opacity: interpolate(frame - (34 + i * 6), [0, 10], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                }),
                paddingRight: 16,
              }}
            >
              <div style={{ fontSize: 26, color: UI.meta, lineHeight: 1.3 }}>
                {seg.label}
              </div>
              <div
                style={{
                  fontFamily: MONO_STACK,
                  fontSize: 24,
                  color: UI.dim,
                  marginTop: 8,
                }}
              >
                {seg.value.toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
};

export type PhotoProps = {
  kind: "photo";
  src: string;
  caption?: string;
  credit: string;
};

export const PhotoCard: React.FC<PhotoProps> = ({ src, caption, credit }) => {
  const frame = useCurrentFrame();
  // A slow push across the shot, so a still photograph is not a still
  // frame. Computed per frame rather than stepped.
  const scale = interpolate(frame, [0, 150], [1.0, 1.09], {
    extrapolateRight: "clamp",
  });

  return (
    <>
      <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
        <img
          src={src}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${scale})`,
          }}
        />
      </div>
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: "38%",
          background:
            "linear-gradient(to top, rgba(0,0,0,0.86), rgba(0,0,0,0))",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: MARGIN_PX,
          right: MARGIN_PX,
          bottom: `${SAFE.bottom * 100 - 6}%`,
          fontFamily: FONT_STACK,
        }}
      >
        {caption ? (
          <Enter delay={8}>
            <div
              style={{
                fontSize: 56,
                color: "#FFFFFF",
                lineHeight: 1.25,
                fontWeight: 600,
              }}
            >
              {caption}
            </div>
          </Enter>
        ) : null}
        <Enter delay={20} from="fade" style={{ marginTop: 22 }}>
          <div style={{ fontSize: 20, color: "#D8D8D8" }}>{credit}</div>
        </Enter>
      </div>
    </>
  );
};
