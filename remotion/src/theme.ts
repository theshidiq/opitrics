/**
 * Shared visual language, matching the still cards the Python pipeline
 * renders for X threads. The two have to agree — a viewer who sees a
 * thread card and a short should read them as the same publication.
 */

/**
 * Contrast ratios below are against the white ground, measured, not
 * estimated. The originals were set for a page that was actually
 * white; once a photograph sits behind every card the effective
 * background is a light grey, so anything that was marginal on paper
 * became unreadable on video. `dim` measured 3.19:1 and `neutral`
 * 3.45:1 — both below the 4.5:1 floor, both used on small type.
 *
 * A phone held at arm's length in daylight is a harsher viewing
 * condition than a monitor, so these aim past the minimum rather than
 * at it.
 */
export const UI = {
  ground: "#FFFFFF",
  surface: "#F4F4F4",
  text: "#000000",       // 21.0:1
  meta: "#3D3D3D",       // 10.9:1  was #606060, 6.29:1
  dim: "#5A5A5A",        //  7.0:1  was #909090, 3.19:1 — failed
  rule: "#BFBFBF",       //  2.5:1  hairlines, not text
  accent: "#0546A8",     //  8.6:1  was #065FD4, 5.84:1
  like: "#3D3D3D",       // 10.9:1
} as const;

export const TONE = {
  positive: "#0A5F2F",   //  8.0:1  was #0F7B3E, 5.35:1
  negative: "#A81C19",   //  8.0:1  was #CC2A26, 5.35:1
  neutral: "#5A5A5A",    //  7.0:1  was #8A8A8A, 3.45:1 — failed
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
