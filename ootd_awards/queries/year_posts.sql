-- OOTD Year in Review: every outfit posted during the period.
-- Paste into Admin > Plugins > Data Explorer and note the query ID.
--
-- One row per post that carries at least one image upload, in OOTD topics
-- (slug "outfit-of-the-day-...", excluding the best-of). Lookbooks are
-- deliberately excluded: they are members' personal spaces, not a pool of
-- outfits for the community awards.
--
-- Data Explorer returns at most 10,000 rows per run, so results are paged by
-- post id: the script re-runs the query with :after_id set to the last id seen.
--
-- Data Explorer also enforces a statement timeout, so each step is narrowed to
-- the period first and materialized once: no CTE carries post text, and the
-- per-member "first OOTD" lookup only reads that member's own posts.
--
-- [params]
-- date :start_date
-- date :end_date
-- int :after_id = 0

WITH ootd_topics AS MATERIALIZED (
  SELECT id, slug, title
  FROM topics
  WHERE archetype = 'regular'
    AND deleted_at IS NULL
    AND slug LIKE 'outfit-of-the-day%'
    AND slug NOT LIKE '%best-of%'
),
ootd_topic_ids AS MATERIALIZED (
  SELECT ARRAY_AGG(id) AS ids
  FROM ootd_topics
),
period_posts AS MATERIALIZED (
  SELECT p.id, p.topic_id, p.post_number, p.user_id, p.created_at, p.like_count,
         ot.slug, ot.title
  FROM posts p
  JOIN ootd_topics ot ON ot.id = p.topic_id
  WHERE p.created_at >= :start_date
    AND p.created_at < :end_date
    AND p.id > :after_id
    AND p.deleted_at IS NULL
    AND NOT p.hidden
    AND p.post_type = 1
),
-- A post's outfit photos are the images its author uploaded, shown in the post
-- body, and big enough to be a photo. This leaves out:
--   * quotes of other members' posts (<aside class="quote">, uploaded by them),
--   * link previews (<aside class="onebox">), whose images Discourse downloads
--     and attaches to the post: Pinterest pins, article thumbnails, site icons.
post_images AS MATERIALIZED (
  SELECT
    pp.id AS post_id,
    JSON_AGG(
      JSON_BUILD_OBJECT('sha1', up.sha1, 'url', up.url, 'width', up.width, 'height', up.height)
      ORDER BY STRPOS(body.cooked, up.sha1)
    ) AS uploads
  FROM period_posts pp
  CROSS JOIN LATERAL (
    SELECT REGEXP_REPLACE(p.cooked, '<aside[^>]*>.*?</aside>', '', 'g') AS cooked
    FROM posts p
    WHERE p.id = pp.id
  ) body
  JOIN upload_references ur ON ur.target_type = 'Post' AND ur.target_id = pp.id
  JOIN uploads up ON up.id = ur.upload_id
  WHERE LOWER(up.extension) IN ('jpg', 'jpeg', 'png', 'webp', 'heic', 'avif')
    AND up.user_id = pp.user_id
    AND up.width >= 300
    AND up.height >= 300
    AND STRPOS(body.cooked, up.sha1) > 0
  GROUP BY pp.id
),
likes AS MATERIALIZED (
  SELECT
    pa.post_id,
    COUNT(*) FILTER (WHERE pa.created_at < pp.created_at + INTERVAL '30 days') AS likes_30d
  FROM post_actions pa
  JOIN period_posts pp ON pp.id = pa.post_id
  WHERE pa.post_action_type_id = 2
    AND pa.deleted_at IS NULL
  GROUP BY pa.post_id
),
first_ootd AS MATERIALIZED (
  SELECT
    members.user_id,
    (
      -- Walk the member's own posts (a few hundred) and keep the oldest OOTD one.
      -- "topic_id + 0" stops Postgres from also scanning the topic index, which
      -- would re-read every OOTD post ever for each member and time out.
      SELECT p.created_at
      FROM posts p, ootd_topic_ids o
      WHERE p.user_id = members.user_id
        AND p.topic_id + 0 = ANY (o.ids)
        AND p.deleted_at IS NULL
        AND p.post_type = 1
      ORDER BY p.created_at
      LIMIT 1
    ) AS first_ootd_at
  FROM (SELECT DISTINCT pp.user_id FROM period_posts pp JOIN post_images pi ON pi.post_id = pp.id) members
)
SELECT
  pp.id,
  pp.topic_id,
  pp.slug,
  pp.title AS topic_title,
  pp.post_number,
  u.username,
  pp.created_at,
  pp.like_count,
  COALESCE(l.likes_30d, 0) AS likes_30d,
  fo.first_ootd_at,
  pi.uploads
FROM period_posts pp
JOIN post_images pi ON pi.post_id = pp.id
JOIN users u ON u.id = pp.user_id
LEFT JOIN likes l ON l.post_id = pp.id
LEFT JOIN first_ootd fo ON fo.user_id = pp.user_id
ORDER BY pp.id
