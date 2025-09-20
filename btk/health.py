"""
Bookmark health scoring and quality tracking system for BTK.

This module provides comprehensive health analysis for bookmarks,
tracking quality metrics and providing actionable recommendations.
"""

import logging
import math
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlparse
import re

logger = logging.getLogger(__name__)


class BookmarkHealth:
    """Calculate and track bookmark health scores."""

    def __init__(self):
        """Initialize the health scoring system."""
        self.weights = {
            'reachability': 0.25,
            'freshness': 0.20,
            'completeness': 0.20,
            'engagement': 0.20,
            'metadata_quality': 0.15
        }

    def calculate_health_score(self, bookmark: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate comprehensive health score for a bookmark.

        Args:
            bookmark: The bookmark dictionary

        Returns:
            Dictionary with overall score, component scores, and recommendations
        """
        scores = {
            'reachability': self._score_reachability(bookmark),
            'freshness': self._score_freshness(bookmark),
            'completeness': self._score_completeness(bookmark),
            'engagement': self._score_engagement(bookmark),
            'metadata_quality': self._score_metadata_quality(bookmark)
        }

        # Calculate weighted overall score
        overall = sum(scores[k] * self.weights[k] for k in scores)

        # Generate health status
        status = self._get_health_status(overall)

        # Generate recommendations
        recommendations = self._generate_recommendations(scores, bookmark)

        return {
            'overall': round(overall, 2),
            'status': status,
            'scores': {k: round(v, 2) for k, v in scores.items()},
            'recommendations': recommendations,
            'timestamp': datetime.now().isoformat()
        }

    def _score_reachability(self, bookmark: Dict[str, Any]) -> float:
        """Score based on URL reachability and last check time."""
        # Check if reachability has been tested
        if 'reachable' not in bookmark:
            return 0.5  # Unknown status

        if bookmark.get('reachable') is False:
            return 0.0  # Not reachable

        # If reachable, score based on how recently it was checked
        if 'last_checked' in bookmark:
            try:
                last_checked = datetime.fromisoformat(bookmark['last_checked'])
                days_since = (datetime.now() - last_checked).days

                # Decay score based on time since last check
                if days_since < 7:
                    return 1.0
                elif days_since < 30:
                    return 0.9
                elif days_since < 90:
                    return 0.7
                elif days_since < 180:
                    return 0.5
                else:
                    return 0.3  # Very old check
            except (ValueError, TypeError):
                pass

        return 0.8  # Reachable but no check date

    def _score_freshness(self, bookmark: Dict[str, Any]) -> float:
        """Score based on how recently the bookmark was accessed."""
        # Check last visited date
        if not bookmark.get('last_visited'):
            # Never visited - score based on age
            if bookmark.get('added'):
                try:
                    added = datetime.fromisoformat(bookmark['added'])
                    days_old = (datetime.now() - added).days
                    if days_old < 30:
                        return 0.7  # New bookmark, not yet visited
                    else:
                        return 0.3  # Old, never visited
                except (ValueError, TypeError):
                    pass
            return 0.3

        try:
            last_visit = datetime.fromisoformat(bookmark['last_visited'])
            days_since = (datetime.now() - last_visit).days

            # Score based on recency of visit
            if days_since < 7:
                return 1.0
            elif days_since < 30:
                return 0.8
            elif days_since < 90:
                return 0.6
            elif days_since < 180:
                return 0.4
            elif days_since < 365:
                return 0.2
            else:
                return 0.1  # Very stale
        except (ValueError, TypeError):
            return 0.3

    def _score_completeness(self, bookmark: Dict[str, Any]) -> float:
        """Score based on metadata completeness."""
        score = 0.0
        max_score = 0.0

        # Essential fields and their weights
        field_weights = {
            'title': 0.25,
            'description': 0.20,
            'tags': 0.20,
            'favicon': 0.10,
            'unique_id': 0.05,
            'added': 0.10,
            'url': 0.10
        }

        for field, weight in field_weights.items():
            max_score += weight
            if field in bookmark and bookmark[field]:
                # Check quality of the field
                if field == 'title':
                    # Title should not be the URL
                    if bookmark[field] != bookmark.get('url'):
                        score += weight
                    else:
                        score += weight * 0.3  # Partial credit
                elif field == 'tags':
                    # More tags is better (up to a point)
                    num_tags = len(bookmark[field]) if isinstance(bookmark[field], list) else 0
                    if num_tags > 0:
                        tag_score = min(1.0, num_tags / 5.0)
                        score += weight * tag_score
                elif field == 'description':
                    # Longer descriptions are better
                    desc_len = len(bookmark[field])
                    if desc_len > 20:
                        desc_score = min(1.0, desc_len / 100.0)
                        score += weight * desc_score
                else:
                    score += weight

        return score / max_score if max_score > 0 else 0.0

    def _score_engagement(self, bookmark: Dict[str, Any]) -> float:
        """Score based on user engagement metrics."""
        score = 0.0

        # Visit count (logarithmic scale)
        visit_count = bookmark.get('visit_count', 0)
        if visit_count > 0:
            # Use log scale for visits (max out around 100 visits)
            visit_score = min(1.0, math.log(visit_count + 1) / math.log(101))
            score += visit_score * 0.5

        # Starred status
        if bookmark.get('stars', False):
            score += 0.5

        # If never visited and not starred, low engagement
        if visit_count == 0 and not bookmark.get('stars', False):
            score = max(score, 0.1)

        return min(1.0, score)

    def _score_metadata_quality(self, bookmark: Dict[str, Any]) -> float:
        """Score based on metadata quality indicators."""
        score = 0.0
        checks = 0

        # URL quality
        url = bookmark.get('url', '')
        if url:
            checks += 1
            url_score = self._assess_url_quality(url)
            score += url_score

        # Title quality
        title = bookmark.get('title', '')
        if title:
            checks += 1
            # Title should be descriptive, not too short or too long
            title_len = len(title)
            if 10 <= title_len <= 100 and title != url:
                score += 1.0
            elif title_len > 0:
                score += 0.5

        # Tag quality
        tags = bookmark.get('tags', [])
        if isinstance(tags, list) and tags:
            checks += 1
            # Tags should be meaningful (not too short)
            good_tags = [t for t in tags if len(t) > 2]
            if good_tags:
                score += min(1.0, len(good_tags) / 3)

        # Has unique identifier
        if bookmark.get('unique_id'):
            checks += 1
            score += 1.0

        return score / checks if checks > 0 else 0.5

    def _assess_url_quality(self, url: str) -> float:
        """Assess the quality of a URL."""
        score = 1.0

        # Parse URL
        try:
            parsed = urlparse(url)
        except:
            return 0.0

        # HTTPS is better than HTTP
        if parsed.scheme == 'https':
            score *= 1.0
        elif parsed.scheme == 'http':
            score *= 0.8
        else:
            score *= 0.5

        # Check for URL shorteners (generally less desirable)
        shorteners = ['bit.ly', 'tinyurl.com', 'goo.gl', 't.co', 'short.link']
        if any(s in parsed.netloc.lower() for s in shorteners):
            score *= 0.7

        # Check for tracking parameters
        tracking_params = ['utm_', 'fbclid', 'gclid', 'ref=', 'source=']
        if parsed.query and any(p in parsed.query.lower() for p in tracking_params):
            score *= 0.9

        # Very long URLs might be problematic
        if len(url) > 500:
            score *= 0.8

        return score

    def _get_health_status(self, score: float) -> str:
        """Get health status label from score."""
        if score >= 0.8:
            return "excellent"
        elif score >= 0.6:
            return "good"
        elif score >= 0.4:
            return "fair"
        elif score >= 0.2:
            return "poor"
        else:
            return "critical"

    def _generate_recommendations(self, scores: Dict[str, float],
                                 bookmark: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations based on scores."""
        recommendations = []

        # Reachability recommendations
        if scores['reachability'] < 0.5:
            if bookmark.get('reachable') is False:
                recommendations.append("URL is unreachable - consider removing or updating")
            else:
                recommendations.append("Reachability status unknown - run health check")
        elif scores['reachability'] < 0.8:
            recommendations.append("Reachability check is outdated - recheck URL status")

        # Freshness recommendations
        if scores['freshness'] < 0.3:
            recommendations.append("Bookmark is stale - consider reviewing or removing")
        elif scores['freshness'] < 0.6:
            recommendations.append("Bookmark hasn't been visited recently - review if still relevant")

        # Completeness recommendations
        if scores['completeness'] < 0.5:
            missing = []
            if not bookmark.get('title') or bookmark.get('title') == bookmark.get('url'):
                missing.append("title")
            if not bookmark.get('description'):
                missing.append("description")
            if not bookmark.get('tags'):
                missing.append("tags")
            if missing:
                recommendations.append(f"Add missing metadata: {', '.join(missing)}")

        # Engagement recommendations
        if scores['engagement'] < 0.3:
            if bookmark.get('visit_count', 0) == 0:
                recommendations.append("Never visited - consider if bookmark is needed")
            elif not bookmark.get('stars'):
                recommendations.append("Low engagement - consider starring if important")

        # Metadata quality recommendations
        if scores['metadata_quality'] < 0.5:
            url = bookmark.get('url', '')
            if 'http://' in url:
                recommendations.append("Consider updating to HTTPS if available")
            if any(s in url for s in ['utm_', 'fbclid', 'gclid']):
                recommendations.append("URL contains tracking parameters - consider cleaning")

        return recommendations


def analyze_library_health(bookmarks: List[Dict[str, Any]],
                          detailed: bool = False) -> Dict[str, Any]:
    """
    Analyze health of entire bookmark library.

    Args:
        bookmarks: List of bookmark dictionaries
        detailed: Include per-bookmark analysis

    Returns:
        Library health analysis report
    """
    health = BookmarkHealth()

    # Analyze each bookmark
    analyses = []
    total_score = 0
    status_counts = {
        'excellent': 0,
        'good': 0,
        'fair': 0,
        'poor': 0,
        'critical': 0
    }

    problem_bookmarks = []

    for bookmark in bookmarks:
        analysis = health.calculate_health_score(bookmark)
        analyses.append(analysis)

        total_score += analysis['overall']
        status_counts[analysis['status']] += 1

        # Track problematic bookmarks
        if analysis['overall'] < 0.4:
            problem_bookmarks.append({
                'id': bookmark.get('id'),
                'title': bookmark.get('title', 'Untitled'),
                'url': bookmark.get('url'),
                'score': analysis['overall'],
                'issues': analysis['recommendations']
            })

    # Calculate library statistics
    avg_score = total_score / len(bookmarks) if bookmarks else 0

    # Identify common issues
    all_recommendations = []
    for analysis in analyses:
        all_recommendations.extend(analysis['recommendations'])

    # Count recommendation frequencies
    recommendation_counts = {}
    for rec in all_recommendations:
        # Generalize recommendations for counting
        rec_type = rec.split(' - ')[0] if ' - ' in rec else rec
        recommendation_counts[rec_type] = recommendation_counts.get(rec_type, 0) + 1

    # Sort by frequency
    common_issues = sorted(recommendation_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    report = {
        'total_bookmarks': len(bookmarks),
        'average_health': round(avg_score, 2),
        'library_status': health._get_health_status(avg_score),
        'status_distribution': status_counts,
        'common_issues': [
            {'issue': issue, 'count': count}
            for issue, count in common_issues
        ],
        'problem_bookmarks': problem_bookmarks[:10],  # Top 10 worst
        'recommendations': _generate_library_recommendations(avg_score, status_counts, common_issues)
    }

    if detailed:
        report['bookmark_analyses'] = [
            {
                'id': bookmarks[i].get('id'),
                'title': bookmarks[i].get('title', 'Untitled'),
                'analysis': analyses[i]
            }
            for i in range(len(bookmarks))
        ]

    return report


def _generate_library_recommendations(avg_score: float,
                                     status_counts: Dict[str, int],
                                     common_issues: List[Tuple[str, int]]) -> List[str]:
    """Generate library-level recommendations."""
    recommendations = []

    total = sum(status_counts.values())

    if avg_score < 0.4:
        recommendations.append("Library health is critical - immediate maintenance recommended")
    elif avg_score < 0.6:
        recommendations.append("Library health needs improvement - schedule regular maintenance")

    # Check for high percentage of problematic bookmarks
    problem_count = status_counts['poor'] + status_counts['critical']
    if problem_count > total * 0.3:
        recommendations.append(f"Over 30% of bookmarks have issues - run 'btk health fix' to auto-repair")

    # Check for stale bookmarks
    if any('stale' in issue[0].lower() for issue in common_issues[:3]):
        recommendations.append("Many stale bookmarks detected - review and remove outdated links")

    # Check for metadata issues
    if any('metadata' in issue[0].lower() or 'missing' in issue[0].lower() for issue in common_issues[:3]):
        recommendations.append("Widespread metadata issues - run 'btk maintain --enrich' to improve")

    # Check for reachability issues
    if any('reachable' in issue[0].lower() for issue in common_issues[:3]):
        recommendations.append("Many bookmarks need reachability check - run 'btk reachable'")

    if status_counts['excellent'] > total * 0.5:
        recommendations.append("Good job! Over 50% of bookmarks are in excellent health")

    return recommendations


def auto_fix_bookmark(bookmark: Dict[str, Any],
                     fix_types: List[str] = None) -> Tuple[Dict[str, Any], List[str]]:
    """
    Automatically fix common bookmark issues.

    Args:
        bookmark: Bookmark to fix
        fix_types: Types of fixes to apply (None = all)

    Returns:
        Tuple of (fixed bookmark, list of applied fixes)
    """
    if fix_types is None:
        fix_types = ['url', 'title', 'metadata']

    fixed = bookmark.copy()
    applied_fixes = []

    # Fix URL issues
    if 'url' in fix_types and fixed.get('url'):
        url = fixed['url']

        # Remove tracking parameters
        if '?' in url:
            parsed = urlparse(url)
            if parsed.query:
                # Remove common tracking params
                import urllib.parse as up
                params = up.parse_qs(parsed.query)
                tracking = ['utm_source', 'utm_medium', 'utm_campaign', 'fbclid', 'gclid']
                cleaned_params = {k: v for k, v in params.items() if k not in tracking}

                if len(cleaned_params) < len(params):
                    # Rebuild URL without tracking
                    new_query = up.urlencode(cleaned_params, doseq=True)
                    new_url = up.urlunparse((
                        parsed.scheme, parsed.netloc, parsed.path,
                        parsed.params, new_query, parsed.fragment
                    ))
                    fixed['url'] = new_url
                    applied_fixes.append("Removed tracking parameters")

        # Normalize URL (remove trailing slashes from paths)
        if url.endswith('/') and url.count('/') > 3:
            fixed['url'] = url.rstrip('/')
            applied_fixes.append("Normalized URL")

    # Fix title issues
    if 'title' in fix_types:
        title = fixed.get('title', '')
        url = fixed.get('url', '')

        # If title is missing or is the URL, try to generate one
        if not title or title == url:
            # Extract domain as fallback title
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.replace('www.', '')
                if domain:
                    fixed['title'] = domain.split('.')[0].capitalize()
                    applied_fixes.append("Generated title from domain")
            except:
                pass

    # Fix metadata issues
    if 'metadata' in fix_types:
        # Ensure required fields exist
        if 'tags' not in fixed:
            fixed['tags'] = []
            applied_fixes.append("Added empty tags field")

        if 'visit_count' not in fixed:
            fixed['visit_count'] = 0
            applied_fixes.append("Added visit_count field")

        if 'stars' not in fixed:
            fixed['stars'] = False
            applied_fixes.append("Added stars field")

        if 'added' not in fixed:
            fixed['added'] = datetime.now().isoformat()
            applied_fixes.append("Added timestamp")

    return fixed, applied_fixes