// Shared "whisper of paper grain" texture — see .fx-grain in fishdex-tokens.css.
// Render as the first child of any position:relative screen root; it covers
// that surface only (DESIGN.md's Sparing Grain Rule: non-photo background
// material, one or two large surfaces per screen, never on top of photography).
export default function GrainOverlay() {
  return <div className="fx-grain" aria-hidden="true" />;
}
