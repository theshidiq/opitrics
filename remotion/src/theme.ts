/**
 * Shared visual language, matching the still cards the Python pipeline
 * renders for X threads. The two have to agree — a viewer who sees a
 * thread card and a short should read them as the same publication.
 */

export const UI = {
  ground: "#FFFFFF",
  surface: "#F9F9F9",
  text: "#0F0F0F",
  meta: "#606060",
  dim: "#909090",
  rule: "#E5E5E5",
  accent: "#065FD4",
  like: "#606060",
} as const;

export const TONE = {
  positive: "#0F7B3E",
  negative: "#CC2A26",
  neutral: "#8A8A8A",
} as const;

export const toneFor = (polarity: number): string =>
  polarity > 0.15 ? TONE.positive : polarity < -0.15 ? TONE.negative : TONE.neutral;

/**
 * Latin first, then a Japanese face. The browser falls through per
 * character, so a mixed-script line renders each part in a face
 * designed for it — which the matplotlib cards had to do by hand.
 */
export const FONT_STACK =
  '"Helvetica Neue", Helvetica, Arial, "Hiragino Sans", "Hiragino Kaku Gothic ProN", sans-serif';

export const MONO_STACK =
  '"SF Mono", Menlo, Monaco, "Courier New", monospace';

/**
 * Vertical bounds no platform's UI covers. TikTok, Reels and Shorts
 * each overlay different chrome; these numbers survive all three.
 */
export const SAFE = {
  top: 0.12,
  bottom: 0.22,
} as const;

export const MARGIN_PX = 92;
export const WIDTH = 1080;
export const HEIGHT = 1920;
export const FPS = 30;
