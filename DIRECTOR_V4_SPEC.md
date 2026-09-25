# JUD.M Universal Director V4 Contract

## Goal
Any gameplay recording must be treated as raw footage for a human editor/director,
not as a pre-defined game template. Unknown games are first-class inputs.

## Fixed architecture
1. Universal signal analysis is the default path.
2. Game profiles are optional hints only.
3. The engine generates multiple story candidates before choosing a clip.
4. Candidate selection considers event strength, buildup, relief, sustained action,
   audiovisual sync, locality, outro/menu risk, and recent edit diversity.
5. The selected story decides the treatment; one edit template is never forced on all videos.

## Director story types
- CLEAR: a strong event followed by a meaningful visual release.
- TURNAROUND: tension or activity falls after a decisive event.
- BUILDUP: activity rises into a payoff.
- IMPACT: a strong localized audiovisual moment.
- RHYTHM: repeated satisfying action with continuity.
- FEVER: profile-supported high-intensity chain event.
- ASMR: gameplay itself is the hook and copy should stay minimal.

## Treatment rules
- REVEAL: payoff cold-open, then return to setup.
- PUNCH: stronger payoff zoom/audio emphasis.
- BUILD: preserve buildup and emphasize the payoff.
- RHYTHM: minimal interference; keep play rhythm.
- CLEAN: restrained edit for self-explanatory footage.

## Framing
- Landscape footage uses motion-derived focal tracking.
- Focus confidence controls how aggressively the image is enlarged.
- Portrait footage preserves the native composition whenever possible.
- Captions automatically move away from the primary play area.

## Copy policy
- Never invent gameplay facts.
- Never claim score, record, success, failure, or a number without evidence.
- Avoid generic clickbait and AI-ad phrasing.
- If the scene works without words, use no in-video caption.
- Known game profiles may add short copy only when scene evidence supports it.

## Quality gate
Reject rather than publish when:
- there is no director-worthy candidate,
- the opening would be visually dead,
- the event is too close to protected outro/menu footage,
- the final render has wrong geometry/duration,
- the final render appears black/broken,
- the source itself is invalid.

## Diversity
If the same creative style was used in the two most recent posted videos,
a different candidate may be selected when its score is at least 80% of the best candidate.

## Output
- 1080x1920 vertical master.
- Preserve original gameplay truth.
- Preserve original game audio and emphasize real payoff audio only.
- The engine may use profiles for accuracy, but must continue to work for GENERIC/unknown games.
