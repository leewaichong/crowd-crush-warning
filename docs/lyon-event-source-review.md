# Lyon event source review

## Status

This is source admission only. It contains no model forecast, feature analysis, fit, score, or effectiveness evaluation. Any event-level comparison remains NOT RUN. CROWD4 and CROWD49 remain open.

The catalog contains 33 timed observations in final Supplementary Information Tables 4–8 and one untimed ambulance observation. The observations describe temporary standing groups, running, density heterogeneity, serpentine groups, pushchairs, and bicycles. They are qualitative interval labels reported by the paper authors. The paper does not provide independent adjudication, annotator agreement, injury labels, or crush labels for these cases.

## Source records and terms

The final paper is by Oscar Dufour, Huu-Tu Dang, Jakob Cordes, Raphael Korbmacher, Mohcine Chraibi, Benoit Gaudou, Alexandre Nicolas, and Antoine Tordeux. Its title is “Dense Crowd Dynamics and Pedestrian Trajectories: A Multiscale Field Dataset from the Festival of Lights in Lyon,” *Scientific Data* 12, 718 (2025), [doi:10.1038/s41597-025-04732-3](https://doi.org/10.1038/s41597-025-04732-3). The paper and its supplement are CC BY 4.0. The final [Supplementary Information PDF](https://static-content.springer.com/esm/art%3A10.1038%2Fs41597-025-04732-3/MediaObjects/41597_2025_4732_MOESM1_ESM.pdf) contains Tables 3–8. Tables 4–8 provide this phenomenon catalog; Table 3 gives sequence recording times.

The dataset is credited separately as Oscar Dufour et al., “Dense Crowd Dynamics and Pedestrian Trajectories: A Multiscale Field Study at the Fête des Lumières in Lyon,” [Zenodo record 13830435](https://doi.org/10.5281/zenodo.13830435), CC BY 4.0. The admitted `Data_Madras.zip` is 33,639,872 bytes, SHA-256 `efd80ef53dcf124286e5ca280d7d3daf52e0b6b2fe9441afb1d23c9a0baf150c`.

The source-manifest file `sources/lyon-topview.json` has SHA-256 `f4b9f0f1fc3343ab20d3f18f0f523d0aac753c4d7302cbd1f00013190f0037cf`. The downloaded final supplement PDF has SHA-256 `807e8b1de354779e6331ea93aaa53647878c21dcdee3e04f2d9b28c17375f54a`. The private original trajectory-member manifest has SHA-256 `653d071662146d6de9da95f3b9f06df0353d2dfb58c34f3e2673e04d04d30f98`. The sanitized interval-support manifest in [lyon-event-interval-support.json](lyon-event-interval-support.json) has SHA-256 `06e54513473ebdbb63d167fb9ff08cbf1298a6ed6bdc4e1501bc3fceec60d587`. It contains aggregate frame/time support and per-member hashes, without coordinates or person IDs.

## Current companion-video route

The earlier route check used the archived app release `v1.0`. Its two generic YouTube links did not identify Lyon sequences. That finding applies only to that archived release. The official [current app repository](https://github.com/PedestrianDynamics/madras-data-app/tree/09c41edffcb9b555b5ee1b810d99bc23a9d4157b) has a camera configuration with 20 camera-specific video links. The current data factory still points to the already admitted Zenodo `Data_Madras.zip`.

I checked public oEmbed metadata for all 20 links. Nineteen returned metadata and one returned HTTP 404. I also checked watch-page metadata for the four whose titles name a TopView sequence. The camera configuration Git blob is `820f2ce0dab485b3f8a3200a831346f164aeeb81`; the data-factory blob is `999500365bfae13a1154c5914cab0cf2454e2840`. The current repository commit is `09c41edffcb9b555b5ee1b810d99bc23a9d4157b`. Its code license is MIT (LICENSE blob `ff23a3cab188b57da9f175a966fd5509dcb17bfc`). Private request records and per-response hashes are retained under ignored `.planning/m08/current-youtube-metadata/`; the compact admission summary has SHA-256 `ff29801eefeb94f0d1a198c07056bd07e0159baf2bfd80f9364ed10ed2685b8c`.

Four video titles name TopView 1A, 1B, 2D, and 2F. Supplementary Table 3 gives their recording starts as 22:40:45, 22:55:06, 23:10:16, and 23:54:59 UTC+1. The YouTube metadata reports durations of 219, 166, 166, and 82 seconds. The published Table 3 intervals span 210, 160, 161, and 91 seconds. These title matches make the clips candidates for review. They do not establish where each clip begins within its named recording. The 2F clip is also shorter than the published interval. The other current links have generic or LargeView titles; their metadata does not name the remaining TopView sequences.

The four watch pages report 2024 upload dates, empty descriptions, and no video-license value in the returned metadata. They give no native PTS, source-clock offset, original-versus-transcoded provenance, or explicit reuse terms. The paper and dataset CC BY 4.0 terms and the app code's MIT license do not establish permission to reuse these YouTube videos. No video bytes were downloaded. An exact video-to-annotation time join and applicable video reuse terms remain unresolved, so none of these clips is admitted for comparison. This does not change the separate trajectory-file support counts above: 26 full-in-range, 5 partial-overhang, 0 no-support, and 2 unverified-clock.

## Admission checks

For each of the nine TopView trajectory files, the check read only frame number and source `t/s` from each data row. It retained aggregate counts and bounds, not source coordinates or identities. Sequence start time came from the member's ISO recording-start header minus the explicitly declared `2022-12-09T20:00:00+01:00` epoch. It did not use nominal FPS to map interval time to frame number.

Across all nine members, every observed frame mapped to one `t/s` value, and every `t/s` value mapped to one frame. The aggregate sequence timeline had no missing integer frame values. This checks the union of source rows. It does not certify continuous visibility or gap-free individual tracks.

TopView 2D's first data row is frame 4 at `t/s = -74983.867`, 0.133 seconds after its header start. Later rows include frame 0 at `t/s = -74984.000`. The member's aggregate support therefore begins at frame 0. File order does not establish sequence order.

TopView 2F has malformed recording-start text. Its source `t/s` values remain in the support manifest, but the sequence-start mapping is unverified. The date was not repaired from neighboring files or expected frame rate. Both catalog intervals assigned to TopView 2F are excluded from clock-admitted cases.

## Timed interval support

Support means that the published elapsed interval maps inside the observed trajectory `t/s` envelope. “Full” means both interval endpoints fall within that envelope. “Partial” means some of the interval lies beyond the observed envelope. “No support” means no observed `t/s` sample falls inside the interval. An invalid sequence clock is “unverified.” These labels describe trajectory-file time support, not video PTS or visual confirmation.

| Source table | Timed cases | Full | Partial | No support | Unverified clock |
| --- | ---: | ---: | ---: | ---: | ---: |
| 4, temporarily static groups | 10 | 7 | 2 | 0 | 1 |
| 5, running pedestrians | 2 | 2 | 0 | 0 | 0 |
| 6, density heterogeneity | 4 | 3 | 1 | 0 | 0 |
| 7, serpentine groups and lanes | 9 | 8 | 1 | 0 | 0 |
| 8, pushchairs and bicycles | 8 | 6 | 1 | 0 | 1 |
| Total | 33 | 26 | 5 | 0 | 2 |

The five partial intervals are Table 4 TopView 1B, ending 0.167 seconds beyond observed trajectory support; Table 4 TopView 2A, 0.067 seconds beyond; Table 6 TopView 1B, 4.167 seconds beyond; Table 7 TopView 1B, 0.167 seconds beyond; and Table 8 TopView 2A, 0.067 seconds beyond. The Table 6 TopView 1B interval ends at 2:44, while that member's last observed `t/s` is 2:39.833 relative to its header start. No interval was clipped to fit.

The ambulance observation has no sequence or interval and is not part of the timed counts. The full per-interval support decisions, mapped `t/s` bounds, overhangs, member hashes, and source-time gap checks are in the sanitized JSON manifest.

## Processing and timing limits

The paper says the source videos were recorded at 30 fps. For TopView tracking, staff manually detected heads, then used PeTrack's extended pyramidal iterative Lucas–Kanade tracker and made manual corrections, often after lighting changes. The authors say they visually inspected and manually corrected the TopView trajectories.

The paper's Data Records section says trajectory coordinates have geometric corrections and interpolation applied, are provided at 10 Hz, and have no smoothing or filtering. The released TopView file headers state 30 fps, and the observed `t/s` cadence is about 1/30 second. The paper and file cadence conflict. The source does not explain the discrepancy or specify the interpolation method. This review preserves both claims and uses source `t/s` for support checks. It does not convert annotation seconds to frames or infer onset precision from sampling cadence.

Table 4 excludes groups that stop for less than two seconds. The other tables are selected observations, not complete positive or negative labeling. Whole-second interval endpoints do not establish one-second onset accuracy. Onset uncertainty remains unknown. Unlisted times are unlabeled, not negative.

## Limits for later comparisons

The labels and released trajectories come from the same source sequences. They are not independent references for model effectiveness. The paper reports that TopView 1B/2C and 1C/2D show similar fields of view and overlap in time. Keep those camera pairs grouped in any split or summary. The catalog labels belong to their named sequences; do not copy a label to the paired camera or infer person identities across views.

These observations can support only a source-published weak-interval comparison after a concrete protocol is frozen and reviewed. They cannot establish physical force, injury risk, crush events, calibrated danger boundaries, or warning effectiveness. The untimed ambulance note cannot support an event-time comparison.
