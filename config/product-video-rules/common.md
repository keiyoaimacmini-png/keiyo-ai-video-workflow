# Common product-video rules

Preserve originals, Drive stored objects, git-tracked files, settings, and JSON receipts.

Local `footage/`, `voice/`, `out/`, `.runtime/product-video-inputs/`, case media under `outputs/<case-id>/`, and `Downloads/<completed_video_filename>` are working copies. After `COMPLETE` and verified destination storage, they must not remain on the Cloud VM or the operator Mac.

Do not delete a local completed video when it is the only remaining copy. Do not delete shared working copies while another case is not `COMPLETE`. Do not add a fourth checkpoint for this purge.
