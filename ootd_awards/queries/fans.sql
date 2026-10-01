-- OOTD Year in Review: who likes whose outfits.
-- Paste into Admin > Plugins > Data Explorer and note the query ID.
--
-- Like counts per (member, fan) pair on the member's OOTD outfits posted during
-- the period, self-likes excluded. The script runs it one month at a time
-- (a whole year exceeds the Data Explorer statement timeout) and sums the
-- months to find each member's biggest fan of the year.
--
-- [params]
-- date :start_date
-- date :end_date

WITH ootd_topics AS MATERIALIZED (
  SELECT id
  FROM topics
  WHERE slug LIKE 'outfit-of-the-day%'
    AND slug NOT LIKE '%best-of%'
    AND archetype = 'regular'
    AND deleted_at IS NULL
),
period_outfits AS MATERIALIZED (
  SELECT p.id, p.user_id
  FROM posts p
  JOIN ootd_topics t ON t.id = p.topic_id
  WHERE p.created_at >= :start_date
    AND p.created_at < :end_date
    AND p.deleted_at IS NULL
    AND NOT p.hidden
    AND p.post_type = 1
    -- same rule as year_posts.sql, without the quote/preview check: the author
    -- uploaded at least one photo-sized image for this post
    AND EXISTS (
      SELECT 1
      FROM upload_references ur
      JOIN uploads up ON up.id = ur.upload_id
      WHERE ur.target_type = 'Post'
        AND ur.target_id = p.id
        AND up.user_id = p.user_id
        AND up.width >= 300
        AND up.height >= 300
    )
)
SELECT author.username AS username, fan.username AS fan, COUNT(*) AS likes
FROM post_actions pa
JOIN period_outfits po ON po.id = pa.post_id
JOIN users author ON author.id = po.user_id
JOIN users fan ON fan.id = pa.user_id
WHERE pa.post_action_type_id = 2
  AND pa.deleted_at IS NULL
  AND pa.user_id <> po.user_id
GROUP BY author.username, fan.username
ORDER BY author.username, likes DESC
