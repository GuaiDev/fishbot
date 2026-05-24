"""Tests for RedditPost model."""

from datetime import UTC, datetime

from src.models.reddit_post import RedditPost


def _now() -> datetime:
    return datetime.now(tz=UTC)


def test_valid_post():
    post = RedditPost(
        post_id="abc123",
        subreddit="OntarioFishing",
        post_type="post",
        title="Smallmouth on Grand River",
        body="Had a great session with tubes and ned rigs.",
        url="https://reddit.com/r/OntarioFishing/comments/abc123/",
        author="angler1",
        score=10,
        num_comments=3,
        created_utc=datetime(2024, 5, 1, tzinfo=UTC),
        ingested_at=_now(),
    )
    assert post.post_id == "abc123"
    assert post.post_type == "post"
    assert post.extracted_species == []
    assert post.extracted_locations == []
    assert post.jurisdiction is None


def test_post_id_strips_t3_prefix():
    post = RedditPost(
        post_id="t3_abc123",
        subreddit="OntarioFishing",
        post_type="post",
        body="test",
        url="",
        author="u",
        score=1,
        created_utc=_now(),
        ingested_at=_now(),
    )
    assert post.post_id == "abc123"


def test_post_id_strips_t1_prefix():
    post = RedditPost(
        post_id="t1_xyz789",
        subreddit="Fishing",
        post_type="comment",
        body="Comment text here.",
        url="",
        author="u",
        score=2,
        created_utc=_now(),
        ingested_at=_now(),
    )
    assert post.post_id == "xyz789"


def test_post_id_no_prefix_unchanged():
    post = RedditPost(
        post_id="rawid",
        subreddit="Fishing",
        post_type="post",
        body="body",
        url="",
        author="u",
        score=0,
        created_utc=_now(),
        ingested_at=_now(),
    )
    assert post.post_id == "rawid"


def test_comment_has_no_title():
    post = RedditPost(
        post_id="def456",
        subreddit="OntarioFishing",
        post_type="comment",
        title=None,
        body="Try tubes on the bottom near boulders.",
        url="",
        author="u",
        score=5,
        parent_post_id="abc123",
        created_utc=_now(),
        ingested_at=_now(),
    )
    assert post.title is None
    assert post.parent_post_id == "abc123"
    assert post.post_type == "comment"


def test_extracted_fields_default_to_empty():
    post = RedditPost(
        post_id="p1",
        subreddit="Fishing",
        post_type="post",
        body="Nothing mentioned here.",
        url="",
        author="u",
        score=1,
        created_utc=_now(),
        ingested_at=_now(),
    )
    assert post.extracted_species == []
    assert post.extracted_locations == []


def test_jurisdiction_and_species_stored():
    post = RedditPost(
        post_id="p2",
        subreddit="OntarioFishing",
        post_type="post",
        title="Walleye",
        body="Caught walleye near Caledonia.",
        url="",
        author="u",
        score=7,
        extracted_species=["walleye"],
        extracted_locations=["caledonia"],
        jurisdiction="CA-ON",
        created_utc=_now(),
        ingested_at=_now(),
    )
    assert "walleye" in post.extracted_species
    assert post.jurisdiction == "CA-ON"
