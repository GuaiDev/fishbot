import { useState } from 'react';
import GrainOverlay from './GrainOverlay';
import '../fishdex-tokens.css';
import './journal-reveal.css';

// Reusable "opening like a journal" transition for a screen's entry moment —
// built for My FishDex (the collection's emotional-heart screen) but scoped
// generically so other reveal moments (e.g. a session summary card) can
// reuse it later.
//
// Two-stage choreography (see journal-reveal.css for the full physical
// model): stage 1 is an opaque cover rotateY-swinging away on its left edge
// to REVEAL the content that was physically underneath it from frame 0 (never
// faded in); stage 2, overlapping stage 1's tail, is a push-in on the content
// layer from set-back-inside-the-journal up to a flat, frame-filling rest. All
// CSS transform/opacity/filter/box-shadow — no canvas or animation library —
// so real content is never delayed, only visually covered for ~360ms while
// the cover clears.
//
// Only two elements make up the journal object: the cover and the shadow it
// casts on the page beneath it. No separate "spine" strip or other book
// chrome — the pivot is simply the cover's left edge. Both are torn down when
// the cover finishes swinging (~360ms); the content's push-in keeps running
// underneath to ~620ms, leaving nothing of the journal behind. Fires on every
// mount: screens are conditionally mounted per nav tab (see App.jsx), so a
// fresh JournalReveal mount happens each time the tab is opened, matching the
// "signature moment on every visit" brief.
export default function JournalReveal({ children }) {
  const [showCover, setShowCover] = useState(true);

  return (
    <div className="fx-journal-wrap">
      <div className="fx-journal-content">{children}</div>
      {showCover && (
        <>
          {/* Shadow the lifted cover casts onto the page beneath it — above
              the content, below the cover. */}
          <div className="fx-journal-cast-shadow" aria-hidden="true" />
          <div
            className="fx-journal-cover"
            aria-hidden="true"
            onAnimationEnd={() => setShowCover(false)}
          >
            <GrainOverlay />
          </div>
        </>
      )}
    </div>
  );
}
