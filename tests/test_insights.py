from datetime import datetime, timezone

from app import summarize_insights


def test_summarizes_dynamic_buffer_metrics_and_calculates_engagement():
    posts = [{
        "id": "fb-1", "dueAt": "2026-09-05T12:00:00Z", "metrics": [
            {"type": "reactions", "name": "Reactions", "value": 10, "unit": "count"},
            {"type": "comments", "name": "Comments", "value": 2, "unit": "count"},
            {"type": "shares", "name": "Shares", "value": 3, "unit": "count"},
            {"type": "reach", "name": "Reach", "value": 100, "unit": "count"},
            {"type": "engagementRate", "name": "Eng. Rate", "value": 12, "unit": "percentage"},
        ],
    }, {
        "id": "ig-1", "dueAt": "2026-09-06T12:00:00Z", "metrics": [
            {"type": "likes", "name": "Likes", "value": 5, "unit": "count"},
            {"type": "comments", "name": "Comments", "value": 1, "unit": "count"},
            {"type": "saves", "name": "Saves", "value": 4, "unit": "count"},
            {"type": "reach", "name": "Reach", "value": 100, "unit": "count"},
            {"type": "engagementRate", "name": "Eng. Rate", "value": 8, "unit": "percentage"},
        ],
    }]
    result = summarize_insights(posts, datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 10, 1, tzinfo=timezone.utc))

    assert result["postCount"] == 2
    assert result["totals"]["comments"] == 3
    assert result["totals"]["engagementrate"] == 10
    assert result["derived"]["engagements"] == 25
    assert result["derived"]["engagementRate"] == 12.5
    assert result["derived"]["averageEngagements"] == 12.5


def test_excludes_posts_outside_period():
    result = summarize_insights([{"id": "old", "dueAt": "2025-01-01T00:00:00Z", "metrics": []}], datetime(2026, 9, 1, tzinfo=timezone.utc), datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert result["postCount"] == 0
