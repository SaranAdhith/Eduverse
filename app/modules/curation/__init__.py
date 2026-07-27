"""Video curation pipeline (DOC_03).

Batch job that, per topic, finds allow-listed YouTube videos, fetches their
public captions, asks Claude to segment transcripts into sub-topics, embeds the
segments, and stores everything in a queryable index. No video/audio files are
ever downloaded — metadata and captions only.
"""
